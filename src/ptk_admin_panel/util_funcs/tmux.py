# Standard library:
from __future__ import annotations
from typing import NamedTuple
from datetime import datetime, timedelta
import subprocess
import functools
# Third party:
import psutil

from .common import format_timedelta



class TmuxClient(NamedTuple):
    """Represents a connected tmux client."""
    session_name: str
    window_index: int
    pane_index: int
    client_name: str
    terminal: str
    created: str



class TmuxSession(NamedTuple):
    """Represents a tmux session."""
    name: str
    windows: int
    created: str
    attached: bool
    clients: list[TmuxClient]



class TmuxStatus(NamedTuple):
    """Overall tmux status information."""
    is_installed: bool
    is_running: bool
    server_pid: int | None
    sessions: list[TmuxSession]
    total_clients: int
    error_message: Exception | None = None  



@functools.cache
def _is_tmux_installed() -> bool:
    """Check if tmux is installed on the system."""
    try:
        result = subprocess.run(
            ["which", "tmux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _get_tmux_server_pid() -> int | None:
    """Get the PID of the tmux server process using psutil."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if process name contains 'tmux'
            if proc.info['name'] and 'tmux' in proc.info['name']:
                cmdline = proc.info['cmdline']
                if cmdline:
                    # The server process typically has 'tmux' as the executable
                    # and may have various arguments, but we can identify it
                    # by checking if it's NOT a client connection
                    cmdline_str = ' '.join(cmdline)
                    # Skip tmux client commands like "tmux attach" or "tmux new"
                    if not any(cmd in cmdline_str for cmd in ['attach', 'new-session', 'new']):
                        return proc.info['pid']
                    # If it's just 'tmux' with 'server' or no args, it's the server
                    elif len(cmdline) <= 2:
                        return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None


def _run_tmux_command(args: list[str]) -> str | None:
    """Run a tmux command and return output."""
    try:
        result = subprocess.run(
            ["tmux"] + args,
            capture_output=True,
            text=True,
            timeout=5
        )
        # Tmux returns 0 on success, but also check if we got output
        if result.returncode == 0 or result.stdout.strip():
            return result.stdout.strip()
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _is_tmux_running() -> bool:
    """Check if tmux server is running by trying to list sessions."""
    # The most reliable way is to ask tmux itself
    output = _run_tmux_command(["list-sessions"])
    # Even if there are no sessions, tmux will return successfully if server is running
    # If server is not running, it will return None (error)
    return output is not None or _session_list_succeeded()


def _session_list_succeeded() -> bool:
    """Check if list-sessions command succeeds (even with no output)."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Return code 0 means server is running (even if no sessions)
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _get_sessions() -> list[TmuxSession]:
    """Get list of tmux sessions with their details."""
    sessions: list[TmuxSession] = []
    
    # Get session list with format: name,windows,created,attached
    output = _run_tmux_command([
        "list-sessions",
        "-F",
        "#{session_name}|#{session_windows}|#{session_created}|#{session_attached}"
    ])
    
    if not output:
        return sessions
    
    for line in output.split("\n"):
        if not line:
            continue
        
        parts = line.split("|")
        if len(parts) != 4:
            continue
        
        session_name, windows_str, created_str, attached_str = parts
        
        try: 
            created_float = float(created_str)
        except Exception as e:
            raise e
        
        created_datetime: datetime = datetime.fromtimestamp(created_float)
        current_time: datetime = datetime.now()
        
        created_delta: timedelta = current_time - created_datetime
        created_formatted = format_timedelta(created_delta)
        
        # Get clients for this session
        clients = _get_clients_for_session(session_name)
        
        sessions.append(TmuxSession(
            name=session_name,
            windows=int(windows_str),
            created=created_formatted,
            attached=attached_str != "0",
            clients=clients
        ))
    
    return sessions


def _get_clients_for_session(session_name: str) -> list[TmuxClient]:
    """Get list of clients connected to a specific session."""
    clients: list[TmuxClient] = []
    
    # Get client list with format: session,window,pane,client,terminal,created
    output = _run_tmux_command([
        "list-clients",
        "-t", session_name,
        "-F",
        "#{session_name}|#{window_index}|#{pane_index}|#{client_name}|#{client_termname}|#{client_created}"
    ])
    
    if not output:
        return clients
    
    for line in output.split("\n"):
        if not line:
            continue
        
        parts = line.split("|")
        if len(parts) != 6:
            continue
        
        sess_name, win_idx, pane_idx, client_name, terminal, created = parts
        
        clients.append(TmuxClient(
            session_name=sess_name,
            window_index=int(win_idx),
            pane_index=int(pane_idx),
            client_name=client_name,
            terminal=terminal,
            created=created
        ))
    
    return clients


def _get_all_clients() -> list[TmuxClient]:
    """Get list of all clients connected to any session."""
    clients: list[TmuxClient] = []
    
    # Get all clients without specifying a session
    output = _run_tmux_command([
        "list-clients",
        "-F",
        "#{session_name}|#{window_index}|#{pane_index}|#{client_name}|#{client_termname}|#{client_created}"
    ])
    
    if not output:
        return clients
    
    for line in output.split("\n"):
        if not line:
            continue
        
        parts = line.split("|")
        if len(parts) != 6:
            continue
        
        sess_name, win_idx, pane_idx, client_name, terminal, created = parts
        
        clients.append(TmuxClient(
            session_name=sess_name,
            window_index=int(win_idx),
            pane_index=int(pane_idx),
            client_name=client_name,
            terminal=terminal,
            created=created
        ))
    
    return clients


def get_status() -> TmuxStatus:
    """Get complete tmux status information."""
    is_installed = _is_tmux_installed()
    
    if not is_installed:
        return TmuxStatus(
            is_installed=False,
            is_running=False,
            server_pid=None,
            sessions=[],
            total_clients=0
        )
    
    # Check if tmux is actually running by querying it
    is_running = _is_tmux_running()
    
    sessions: list[TmuxSession] = []
    total_clients = 0
    server_pid: int | None = None
    
    if is_running:
        sessions = _get_sessions()
        # Get total clients across all sessions
        all_clients = _get_all_clients()
        total_clients = len(all_clients)
        # Try to get server PID
        server_pid = _get_tmux_server_pid()
    
    return TmuxStatus(
        is_installed=is_installed,
        is_running=is_running,
        server_pid=server_pid,
        sessions=sessions,
        total_clients=total_clients,
        error_message=None,
    )
    
