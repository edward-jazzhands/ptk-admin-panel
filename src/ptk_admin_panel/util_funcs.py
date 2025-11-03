# Standard library:
from __future__ import annotations
import socket
from typing import Any #, Iterable, Tuple
from datetime import datetime
from dataclasses import dataclass
# import functools
# import os
# from pathlib import Path




# Third party:
import psutil
from psutil._common import pconn, sconn


############################
# psutil-Related Functions #
############################


def get_connections_list_filtered() -> list[sconn]:
    
    conns_list: list[sconn] = psutil.net_connections(kind="inet")
    filtered: list[sconn] = [c for c in conns_list if c.status != "TIME_WAIT"]            
    filtered.sort(key=lambda c: c.laddr)
    return filtered

@dataclass
class ProcessInfo:
    name: str
    cmdline: str
    user: str           # which user owns it
    cwd: str            # working directory
    create_time: str  # when process started
    cpu_percent: float  # CPU usage
    memory_mb: str      # RAM in MB
    num_threads: int
    connections: list[Any]   # ALL connections for this process
    exe: str            # full executable path
    status: str         # running, sleeping, etc

def get_enhanced_proc_info(pid: int) -> ProcessInfo | None:
    """Get rich process information"""
    
    if pid == -1:
        return
    
    try:
        p = psutil.Process(pid)
        dt_object = datetime.fromtimestamp(p.create_time())
        readable_date = dt_object.strftime('%Y-%m-%d %H:%M:%S')
        
        
        p_info = ProcessInfo(
            name = p.name(),
            cmdline = " ".join(p.cmdline()) or "",
            user = p.username(),
            cwd = p.cwd(),  
            create_time = readable_date, 
            cpu_percent = p.cpu_percent(interval=0.1),
            memory_mb = p.memory_info().rss / 1024 / 1024, 
            num_threads = p.num_threads(),
            connections = p.net_connections(kind='inet'),
            exe = p.exe(),  
            status = p.status(),  
        )
    except Exception as e:
        raise e
    else:
        return p_info
    
def get_proc_connecions(pid: int) -> list[pconn] | None:

    if pid == -1:
        return
    
    try:
        p = psutil.Process(pid)
        connections = p.net_connections(kind='inet')
    except Exception as e:
        raise e
    else:
        return connections
    

#########################
# SSH-Related Functions #
#########################

class ModuleCache:
    ssh_port: int | None = None

@dataclass
class SSHStatus:
    """SSH server status information."""
    is_active: bool
    active_connections: dict[int, sconn] | None
    port: int | None
    pid: int | None
    error_message: str | None = None
        

def get_ssh_status() -> SSHStatus:
    """
    Check if SSH server is active and count active connections.
    
    Returns:
        SSHStatus object with server status and connection count
    """
    ssh_conns = None
    pid = None
    ssh_port = None
    
    is_active, pid = is_sshd_running()
    connections = get_connections_list_filtered()
    if ModuleCache.ssh_port:
        ssh_port = ModuleCache.ssh_port
    else:
        ssh_port = detect_ssh_port_unpriveleged(connections)
        ModuleCache.ssh_port = ssh_port
    if ssh_port:
        ssh_conns = get_ssh_connections(ssh_port, connections)
    
    return SSHStatus(
        is_active=is_active,
        port=ssh_port,
        pid=pid,
        active_connections=ssh_conns
    )

def is_sshd_running() -> tuple[bool, int | None]:
    
    processes = list(psutil.process_iter())
    for process in processes:
        if process.name() == "sshd":
            return True, process.pid
    return False, None
        
def detect_ssh_port_unpriveleged(conns: list[sconn]) -> int | None:
    
    print("Probing to find the SSH port...")
    ports: set[int] = set()
    for c in conns:
        if c.status == "LISTEN":
            probe_result = probe_ssh_once(c.laddr.ip, c.laddr.port) # type: ignore
            if probe_result:
                ports.add(c.laddr.port)  # type: ignore
    if len(ports) > 1:
        print("WARNING: more than 1 SSH port detected. Why would there be more than one?")
    if len(ports) == 0:
        return None
    return ports.pop()
            

def probe_ssh_once(host: str, port: int, timeout: float = 0.5) -> str | None:
    """
    Attempt a single TCP connect to (host, port) and return the SSH banner string
    if the peer sends one (e.g. "SSH-2.0-OpenSSH_8.9p1..."). Returns None on failure.
    This is intentionally lightweight and tolerant of truncated replies.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            # SSH servers normally send a banner immediately; read a short chunk.
            s.settimeout(timeout)
            data = s.recv(512)
            if not data:
                return None
            try:
                banner = data.decode('utf-8', errors='ignore').strip()
            except Exception:
                banner = data.decode('ascii', errors='ignore').strip()
            if banner.startswith("SSH-"):
                return banner
            # Sometimes banner may be later in stream if server prints a preamble.
            if "SSH-" in banner:
                idx = banner.find("SSH-")
                return banner[idx:].splitlines()[0]
            return None
    except (OSError, socket.timeout):
        return None

def get_ssh_connections(ssh_port: int, conns: list[sconn]) -> dict[int, sconn]:
    print("Counting SSH Connections on provided port...")
    counter = 1
    ssh_conns: dict[int, sconn] = {}
    for conn in conns:
        if (conn.laddr.port == ssh_port and conn.status == "ESTABLISHED"): # type: ignore
            ssh_conns[counter] = conn
            counter += 1
    return ssh_conns

##########################
# HTTP-Related Functions #
##########################

def probe_http_once(ip: str, port: int, timeout: float = 0.5) -> bool:
    """
    Return True if the endpoint at (ip, port) responds like HTTP to a HEAD request.
    This is lightweight and intentionally tolerant of truncated/partial replies.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            # send minimal HEAD request; use HTTP/1.0 to avoid chunked responses
            s.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            s.settimeout(timeout)
            data = s.recv(512)
            return b"HTTP/" in data or b"Server:" in data or b"Content-Type" in data
    except Exception:
        return False

