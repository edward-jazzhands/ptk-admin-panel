from datetime import timedelta
import psutil
import socket
from psutil._common import sconn


################
# ~ Generics ~ #
################


# USED BY: get_uptime_info, TmuxDetector._get_sessions
def format_timedelta(time_delta: timedelta, incl_seconds: bool = False) -> str:
    
    # Format uptime as "X days, Y hours, Z minutes, W seconds"
    days: int = time_delta.days
    hours: int = time_delta.seconds // 3600
    minutes: int = (time_delta.seconds % 3600) // 60
    seconds: int = time_delta.seconds % 60
    
    uptime_parts: list[str] = []
    if days > 0:
        uptime_parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0 or days > 0:
        uptime_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0 or hours > 0 or days > 0:
        uptime_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if incl_seconds:
            uptime_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    
    return ", ".join(uptime_parts)



# USED BY: SSH detector
def get_connections_list_filtered() -> list[sconn]:
    
    conns_list: list[sconn] = psutil.net_connections(kind="inet")
    filtered: list[sconn] = [c for c in conns_list if c.status != "TIME_WAIT"]            
    filtered.sort(key=lambda c: c.laddr)
    return filtered





# NOT USED YET
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

