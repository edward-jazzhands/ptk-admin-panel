"""
Detect local web servers (inside same network namespace / container) using psutil.

Requirements:
    pip install psutil

Run as root (or with sufficient permissions) to reliably map sockets -> PIDs/processes.
"""

# Standard library:
from __future__ import annotations
import socket
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any

# Third party:
import psutil


@dataclass
class ServerInfo:
    ip: str
    port: int
    pid: Optional[int]
    process_cmdline: str
    process_name: str
    http_probe: bool
    last_seen: float


def probe_http(ip: str, port: int, timeout: float = 0.5) -> bool:
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


def gather_listening_conns() -> List[Tuple[str, int, Optional[int]]]:
    """
    Use psutil.net_connections to gather all TCP listening sockets.
    Returns list of (ip, port, pid). pid may be None on some platforms or if permission denied.
    """
    conns: List[Tuple[str, int, Optional[int]]] = []
    # psutil.net_connections(kind='tcp') includes all TCP sockets; we filter for LISTEN
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status != psutil.CONN_LISTEN:
                continue
            if not c.laddr:
                continue
            # About laddr: This is the "local address" - a tuple of (ip, port) 
            # that the socket is bound to. The check if not c.laddr: filters out 
            # any connections that don't have a valid local address 
            # (though this is rare for listening sockets).
            ip = c.laddr.ip
            port = c.laddr.port
            pid = c.pid  # may be None
            conns.append((ip, port, pid))
    except Exception:
        # Fallback: try with 'inet' or generic call (platform differences)
        for c in psutil.net_connections():
            if c.status == psutil.CONN_LISTEN and c.laddr:
                conns.append((c.laddr.ip, c.laddr.port, c.pid))
    return conns


def get_proc_info(pid: Optional[int]) -> Tuple[str, str]:
    """
    Return (name, cmdline) for a pid. If pid is None or not accessible, return ("unknown", "").
    """
    if pid is None:
        return "unknown", ""
    try:
        p = psutil.Process(pid)
        name = p.name()
        cmdline = " ".join(p.cmdline()) or ""
        return name, cmdline
    except Exception:
        return "unknown", ""
    
#! NOT USED YET
def get_enhanced_proc_info(pid: Optional[int]) -> dict[str, Any]:
    """Get rich process information"""
    if pid is None:
        return {"name": "unknown", "cmdline": "", "user": "", "cwd": "", 
                "connections": [], "cpu_percent": 0.0, "memory_mb": 0.0}
    
    try:
        p = psutil.Process(pid)
        return {
            "name": p.name(),
            "cmdline": " ".join(p.cmdline()) or "",
            "user": p.username(),  # which user owns it
            "cwd": p.cwd(),  # working directory
            "create_time": p.create_time(),  # when process started
            "cpu_percent": p.cpu_percent(interval=0.1),  # CPU usage
            "memory_mb": p.memory_info().rss / 1024 / 1024,  # RAM in MB
            "num_threads": p.num_threads(),
            "connections": p.net_connections(kind='inet'),  # ALL connections for this process
            "exe": p.exe(),  # full executable path
            "status": p.status(),  # running, sleeping, etc
        }
    except Exception as e:
        return {"error": str(e)}

#! NOT USED YET
def get_active_connections() -> List[dict[str, Any]]:
    """Get all active (ESTABLISHED) connections"""
    active: List[dict[str, Any]] = []
    for c in psutil.net_connections(kind='inet'):
        if c.status == psutil.CONN_ESTABLISHED:
            if not c.laddr:
                continue
            active.append({
                "local": f"{c.laddr.ip}:{c.laddr.port}",
                "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "?",
                "pid": c.pid,
                "family": "IPv4" if c.family == socket.AF_INET else "IPv6",
            })
    return active

def build_server_list(ignore_pids: List[int] | None = None) -> List[ServerInfo]:
    """
    Scan for listening TCP ports, probe each for HTTP, and attach process info.
    ignore_pids: optional list of PIDs to ignore (e.g., the scanner's own PID).
    """
    ignore_pids = ignore_pids or []
    seen: dict[tuple[str, int], ServerInfo] = {}
    conns = gather_listening_conns()
    for (ip, port, pid) in conns:
        key = (ip, port)
        if key in seen:
            # update PID if we didn't have it before
            if seen[key].pid is None and pid is not None:
                seen[key].pid = pid
            continue
        if pid in ignore_pids:
            continue
        name, cmdline = get_proc_info(pid)
        http_ok = probe_http(ip, port)
        seen[key] = ServerInfo(
            ip=ip,
            port=port,
            pid=pid,
            process_cmdline=cmdline,
            process_name=name,
            http_probe=http_ok,
            last_seen=time.time(),
        )
    return list(seen.values())


def pretty_print(servers: List[ServerInfo]) -> None:
    """
    Print a compact table-like snapshot to stdout.
    """
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nScan time: {now}  —  detected {len(servers)} listening HTTP-like services\n")
    if not servers:
        print("  (none detected)")
        return
    # header
    header = f"{'IP:PORT':21s} {'HTTP?':6s} {'PID':6s} {'PROCESS':30s} CMDLINE"
    print(header)
    print("-" * len(header))
    for s in sorted(servers, key=lambda x: (x.ip, x.port)):
        ipport = f"{s.ip}:{s.port}"
        http_flag = "yes" if s.http_probe else "no"
        pid_str = str(s.pid) if s.pid is not None else "-"
        proc_name = (s.process_name[:29] + "…") if len(s.process_name) > 30 else s.process_name
        cmd = s.process_cmdline
        print(f"{ipport:21s} {http_flag:6s} {pid_str:6s} {proc_name:30s} {cmd}")


def main(poll_interval: float = 5.0) -> None:
    """
    Main loop: poll every poll_interval seconds and update terminal with found services.
    """
    # avoid reporting ourselves
    our_pid = psutil.Process().pid
    try:
        while True:
            servers = build_server_list(ignore_pids=[our_pid])
            # clear screen in a portable way
            print("\033[2J\033[H", end="")  # ANSI clear screen + move cursor home
            print("Local web server detector (psutil-based). Press Ctrl-C to quit.")
            pretty_print(servers)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print("ERROR:")
        print(e)
        

#! NOT USED YET
# psutil can give you per-interface stats:
net_io = psutil.net_io_counters(pernic=True)
# Returns bytes_sent, bytes_recv, packets_sent, packets_recv per interface

# For per-connection bandwidth, you'd need to:
# 1. Sample net_io_counters() at intervals
# 2. Calculate deltas
# 3. Attribute to connections (tricky - psutil doesn't do per-connection bandwidth directly)

if __name__ == "__main__":
    main()
