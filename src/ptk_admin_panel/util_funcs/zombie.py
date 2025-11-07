# Standard library:
from __future__ import annotations
from typing import NamedTuple
from datetime import datetime


# Third party:
import psutil



class ZombieInfo(NamedTuple):
    name: str
    user: str           # which user owns it
    create_time: str  # when process started
    cpu_percent: float  # CPU usage
    memory_mb: str      # RAM in MB


def _get_zombie_info(p: psutil.Process) -> ZombieInfo:
    """Get rich process information"""
    
    try:
        dt_object = datetime.fromtimestamp(p.create_time())
        readable_date = dt_object.strftime('%H:%M:%S %Y-%m-%d')
        
        p_info = ZombieInfo(
            name = p.name(),
            user = p.username(),
            create_time = readable_date, 
            cpu_percent = p.cpu_percent(interval=0.1),
            memory_mb = p.memory_info().rss / 1024 / 1024, 
        )
    except Exception as e:
        raise e
    else:
        return p_info
    
# @api.route("/api/zombies")    
def get_zombie_processes() -> list[ZombieInfo]:
    
    zombies: list[ZombieInfo] = []
    for p in psutil.process_iter():
        if p.status() == psutil.STATUS_ZOMBIE:
            try:
                proc_info = _get_zombie_info(p) # raises on error
            except psutil.NoSuchProcess as e:
                print(f"Zombie process detected but got error: {e}")
                pass
            except Exception as e:
                # any other exception means problem getting info
                print(f"Zombie process detected but error getting info: {e}")
            else:
                zombies.append(proc_info)
                print("Zombie added to list successfully")
    return zombies
