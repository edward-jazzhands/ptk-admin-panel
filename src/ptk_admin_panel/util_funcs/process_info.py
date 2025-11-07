from typing import NamedTuple, Any
import psutil
from datetime import datetime

class ProcessInfo(NamedTuple):
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


# USED BY: @api.route("/api/conn-info")
def get_enhanced_proc_info(p: psutil.Process) -> ProcessInfo:
    """Get rich process information"""
    
    try:
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