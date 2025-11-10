# Standard library:
from __future__ import annotations
from typing import NamedTuple
from datetime import datetime, timedelta

# third party:
import psutil

# local:
from .common import format_timedelta


class UptimeInfo(NamedTuple):
    """Type definition for uptime information."""
    uptime_seconds: float
    uptime_formatted: str
    boot_time: str
    boot_timestamp: float


# @api.route("/api/uptime")
def get_uptime_info() -> UptimeInfo:
    """
    Get container uptime information using psutil.
    
    Returns:
        UptimeInfo: Dictionary containing uptime metrics
    """
    pid1_process: psutil.Process = psutil.Process(1)
    start_timestamp: float = pid1_process.create_time()
    
    boot_datetime: datetime = datetime.fromtimestamp(start_timestamp)
    current_time: datetime = datetime.now()
    
    uptime_delta: timedelta = current_time - boot_datetime
    uptime_seconds: float = uptime_delta.total_seconds()
    uptime_formatted = format_timedelta(uptime_delta)
    
    return UptimeInfo(
        uptime_seconds = uptime_seconds,
        uptime_formatted = uptime_formatted,
        boot_time = boot_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        boot_timestamp = start_timestamp,
    )

