# Standard library:
from __future__ import annotations
import socket
from typing import NamedTuple

# Third party:
import psutil
from psutil._common import sconn

# Local:
from . import get_connections_list_filtered



class ModuleCache:
    ssh_port: int | None = None



class SSHStatus(NamedTuple):
    """SSH server status information."""
    is_active: bool
    active_connections: dict[int, sconn] | None
    port: int | None
    pid: int | None
    error_message: str | None = None
        
        
# @api.route("/api/ssh-status")
def get_ssh_status() -> SSHStatus:
    """
    Check if SSH server is active and count active connections.
    
    Returns:
        SSHStatus object with server status and connection count
    """
    ssh_conns = None
    pid = None
    ssh_port = None
    
    is_active, pid = _is_sshd_running()
    connections = get_connections_list_filtered()
    if ModuleCache.ssh_port:
        ssh_port = ModuleCache.ssh_port
    else:
        ssh_port = _detect_ssh_port_unpriveleged(connections)
        ModuleCache.ssh_port = ssh_port
    if ssh_port:
        ssh_conns = _get_ssh_connections(ssh_port, connections)
    
    return SSHStatus(
        is_active=is_active,
        port=ssh_port,
        pid=pid,
        active_connections=ssh_conns
    )


def _is_sshd_running() -> tuple[bool, int | None]:
    
    processes = list(psutil.process_iter())
    for process in processes:
        if process.name() == "sshd":
            return True, process.pid
    return False, None
        

def _detect_ssh_port_unpriveleged(conns: list[sconn]) -> int | None:
    
    print("Probing to find the SSH port...")
    ports: set[int] = set()
    for c in conns:
        if c.status == "LISTEN":
            probe_result = _probe_ssh_once(c.laddr.ip, c.laddr.port) # type: ignore
            if probe_result:
                ports.add(c.laddr.port)  # type: ignore
    if len(ports) > 1:
        print("WARNING: more than 1 SSH port detected. Why would there be more than one?")
    if len(ports) == 0:
        return None
    return ports.pop()
            

def _probe_ssh_once(host: str, port: int, timeout: float = 0.5) -> str | None:
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


def _get_ssh_connections(ssh_port: int, conns: list[sconn]) -> dict[int, sconn]:
    print("Counting SSH Connections on provided port...")
    counter = 1
    ssh_conns: dict[int, sconn] = {}
    for conn in conns:
        if (conn.laddr.port == ssh_port and conn.status == "ESTABLISHED"): # type: ignore
            ssh_conns[counter] = conn
            counter += 1
    return ssh_conns

