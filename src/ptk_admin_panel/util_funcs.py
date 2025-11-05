# Standard library:
from __future__ import annotations
import socket
from typing import Any, NamedTuple
from datetime import datetime, timedelta
# from dataclasses import dataclass
import os
import subprocess
from pathlib import Path
import functools


# Third party:
import psutil
from psutil._common import sconn



class ModuleCache:
    ssh_port: int | None = None

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

# @api.route("/api/ssh-status")
class SSHDetector:

    class SSHStatus(NamedTuple):
        """SSH server status information."""
        is_active: bool
        active_connections: dict[int, sconn] | None
        port: int | None
        pid: int | None
        error_message: str | None = None
            
    @staticmethod
    def get_ssh_status() -> SSHStatus:
        """
        Check if SSH server is active and count active connections.
        
        Returns:
            SSHStatus object with server status and connection count
        """
        ssh_conns = None
        pid = None
        ssh_port = None
        
        is_active, pid = SSHDetector.is_sshd_running()
        connections = get_connections_list_filtered()
        if ModuleCache.ssh_port:
            ssh_port = ModuleCache.ssh_port
        else:
            ssh_port = SSHDetector.detect_ssh_port_unpriveleged(connections)
            ModuleCache.ssh_port = ssh_port
        if ssh_port:
            ssh_conns = SSHDetector.get_ssh_connections(ssh_port, connections)
        
        return SSHDetector.SSHStatus(
            is_active=is_active,
            port=ssh_port,
            pid=pid,
            active_connections=ssh_conns
        )

    @staticmethod
    def is_sshd_running() -> tuple[bool, int | None]:
        
        processes = list(psutil.process_iter())
        for process in processes:
            if process.name() == "sshd":
                return True, process.pid
        return False, None
            
    @staticmethod
    def detect_ssh_port_unpriveleged(conns: list[sconn]) -> int | None:
        
        print("Probing to find the SSH port...")
        ports: set[int] = set()
        for c in conns:
            if c.status == "LISTEN":
                probe_result = SSHDetector.probe_ssh_once(c.laddr.ip, c.laddr.port) # type: ignore
                if probe_result:
                    ports.add(c.laddr.port)  # type: ignore
        if len(ports) > 1:
            print("WARNING: more than 1 SSH port detected. Why would there be more than one?")
        if len(ports) == 0:
            return None
        return ports.pop()
                
    @staticmethod
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

    @staticmethod
    def get_ssh_connections(ssh_port: int, conns: list[sconn]) -> dict[int, sconn]:
        print("Counting SSH Connections on provided port...")
        counter = 1
        ssh_conns: dict[int, sconn] = {}
        for conn in conns:
            if (conn.laddr.port == ssh_port and conn.status == "ESTABLISHED"): # type: ignore
                ssh_conns[counter] = conn
                counter += 1
        return ssh_conns


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


class FileInfo(NamedTuple):
    """Information about a file and its modification time."""
    path: str
    modified_time: float
    
    @property
    def modified_datetime(self) -> datetime:
        """Convert timestamp to datetime object."""
        return datetime.fromtimestamp(self.modified_time)
    
    @property
    def modified_str(self) -> str:
        """Return the modified_datetime in string format"""    
        return self.modified_datetime.strftime("%Y-%m-%d %H:%M:%S")
    
    
# @api.route("/api/modified-files")
def get_recent_files(
    directory: str = "/home/devuser/workspace",
    limit: int = 20,
    exclude_hidden: bool = False
) -> list[FileInfo]:
    """
    Get the most recently modified files in a directory tree.
    
    Args:
        directory: Root directory to search
        limit: Maximum number of files to return
        exclude_hidden: Whether to exclude hidden files/directories
    
    Returns:
        list of FileInfo objects sorted by modification time (newest first)
    """
    files: list[FileInfo] = []
    
    try:
        for root, dirs, filenames in os.walk(directory):
            # Filter out hidden directories if requested
            if exclude_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in filenames:
                # Skip hidden files if requested
                if exclude_hidden and filename.startswith('.'):
                    continue
                
                filepath = os.path.join(root, filename)
                
                try:
                    stat_info = os.stat(filepath)
                    files.append(FileInfo(
                        path=filepath,
                        modified_time=stat_info.st_mtime,
                    ))
                except (OSError, PermissionError):
                    # Skip files we can't access
                    continue
    
    except (OSError, PermissionError) as e:
        print(f"Error accessing directory {directory}: {e}")
        return []
    
    # Sort by modification time (newest first) and return top N
    files.sort(key=lambda f: f.modified_time, reverse=True)
    return files[:limit]


# @api.route("/api/zombies")
class ZombieDetector:


    class ZombieInfo(NamedTuple):
        name: str
        user: str           # which user owns it
        create_time: str  # when process started
        cpu_percent: float  # CPU usage
        memory_mb: str      # RAM in MB

    @staticmethod
    def get_zombie_info(p: psutil.Process) -> ZombieInfo:
        """Get rich process information"""
        
        try:
            dt_object = datetime.fromtimestamp(p.create_time())
            readable_date = dt_object.strftime('%H:%M:%S %Y-%m-%d')
            
            p_info = ZombieDetector.ZombieInfo(
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
        
    @staticmethod    
    def get_zombie_processes() -> list[ZombieDetector.ZombieInfo]:
        
        zombies: list[ZombieDetector.ZombieInfo] = []
        for p in psutil.process_iter():
            if p.status() == psutil.STATUS_ZOMBIE:
                try:
                    proc_info = ZombieDetector.get_zombie_info(p) # raises on error
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



####################
# Uptime Detection #
####################

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


##################
# Tmux Detection #
##################


class TmuxDetector:
    """Detects and reports on tmux status."""
    

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
        clients: list[TmuxDetector.TmuxClient]



    class TmuxStatus(NamedTuple):
        """Overall tmux status information."""
        is_installed: bool
        is_running: bool
        server_pid: int | None
        sessions: list[TmuxDetector.TmuxSession]
        total_clients: int
        error_message: Exception | None = None  
    
    
    @staticmethod
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
    
    @staticmethod
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
    
    @staticmethod
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
    
    @staticmethod
    def _is_tmux_running() -> bool:
        """Check if tmux server is running by trying to list sessions."""
        # The most reliable way is to ask tmux itself
        output = TmuxDetector._run_tmux_command(["list-sessions"])
        # Even if there are no sessions, tmux will return successfully if server is running
        # If server is not running, it will return None (error)
        return output is not None or TmuxDetector._session_list_succeeded()
    
    @staticmethod
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
    
    @staticmethod
    def _get_sessions() -> list[TmuxDetector.TmuxSession]:
        """Get list of tmux sessions with their details."""
        sessions: list[TmuxDetector.TmuxSession] = []
        
        # Get session list with format: name,windows,created,attached
        output = TmuxDetector._run_tmux_command([
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
            clients = TmuxDetector._get_clients_for_session(session_name)
            
            sessions.append(TmuxDetector.TmuxSession(
                name=session_name,
                windows=int(windows_str),
                created=created_formatted,
                attached=attached_str != "0",
                clients=clients
            ))
        
        return sessions
    
    @staticmethod
    def _get_clients_for_session(session_name: str) -> list[TmuxClient]:
        """Get list of clients connected to a specific session."""
        clients: list[TmuxDetector.TmuxClient] = []
        
        # Get client list with format: session,window,pane,client,terminal,created
        output = TmuxDetector._run_tmux_command([
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
            
            clients.append(TmuxDetector.TmuxClient(
                session_name=sess_name,
                window_index=int(win_idx),
                pane_index=int(pane_idx),
                client_name=client_name,
                terminal=terminal,
                created=created
            ))
        
        return clients
    
    @staticmethod
    def _get_all_clients() -> list[TmuxDetector.TmuxClient]:
        """Get list of all clients connected to any session."""
        clients: list[TmuxDetector.TmuxClient] = []
        
        # Get all clients without specifying a session
        output = TmuxDetector._run_tmux_command([
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
            
            clients.append(TmuxDetector.TmuxClient(
                session_name=sess_name,
                window_index=int(win_idx),
                pane_index=int(pane_idx),
                client_name=client_name,
                terminal=terminal,
                created=created
            ))
        
        return clients
    
    @staticmethod
    def get_status() -> TmuxStatus:
        """Get complete tmux status information."""
        is_installed = TmuxDetector._is_tmux_installed()
        
        if not is_installed:
            return TmuxDetector.TmuxStatus(
                is_installed=False,
                is_running=False,
                server_pid=None,
                sessions=[],
                total_clients=0
            )
        
        # Check if tmux is actually running by querying it
        is_running = TmuxDetector._is_tmux_running()
        
        sessions: list[TmuxDetector.TmuxSession] = []
        total_clients = 0
        server_pid: int | None = None
        
        if is_running:
            sessions = TmuxDetector._get_sessions()
            # Get total clients across all sessions
            all_clients = TmuxDetector._get_all_clients()
            total_clients = len(all_clients)
            # Try to get server PID
            server_pid = TmuxDetector._get_tmux_server_pid()
        
        return TmuxDetector.TmuxStatus(
            is_installed=is_installed,
            is_running=is_running,
            server_pid=server_pid,
            sessions=sessions,
            total_clients=total_clients,
            error_message=None,
        )
        

class GitDetector:
    class GitStatus(NamedTuple):
        """Immutable data class representing git repository status."""
        repo_path: Path
        branch: str
        is_clean: bool
        ahead: int
        behind: int
        staged: int
        modified: int
        untracked: int
        error: str | None = None

    @staticmethod
    def find_git_repos(root_path: Path) -> list[Path]:
        """
        Find all git repositories under the given root path.
        
        Args:
            root_path: Root directory to search for git repos
            
        Returns:
            List of paths to git repositories (directories containing .git)
        """
        try:
            git_repos: list[Path] = []
            
            # Walk through directory tree
            for item in root_path.rglob(".git"):
                if item.is_dir():
                    # Parent of .git directory is the repo root
                    repo_root = item.parent
                    git_repos.append(repo_root)
                    
            return sorted(git_repos)
        except PermissionError:
            # If we can't read certain directories, continue with what we can read
            return []

    @staticmethod
    def get_git_status(repo_path: Path) -> GitStatus:
        """
        Get detailed git status for a repository.
        
        Args:
            repo_path: Path to git repository
            
        Returns:
            GitStatus object with repository information
        """
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return GitDetector.GitStatus(
                repo_path=repo_path,
                branch="unknown",
                is_clean=False,
                ahead=0,
                behind=0,
                staged=0,
                modified=0,
                untracked=0,
                error=str(e)
            )
        else:
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
            
            # Get status in porcelain format for easy parsing
            try:
                status_result = subprocess.run(
                    ["git", "-C", str(repo_path), "status", "--porcelain", "--branch"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            except subprocess.TimeoutExpired as e:
                return GitDetector.GitStatus(
                    repo_path=repo_path,
                    branch=branch,
                    is_clean=False,
                    ahead=0,
                    behind=0,
                    staged=0,
                    modified=0,
                    untracked=0,
                    error=str(e)
                )
            else:
                if status_result.returncode != 0:
                    return GitDetector.GitStatus(
                        repo_path=repo_path,
                        branch=branch,
                        is_clean=False,
                        ahead=0,
                        behind=0,
                        staged=0,
                        modified=0,
                        untracked=0,
                        error=status_result.stderr.strip()
                    )
                
                return GitDetector._parse_git_status(repo_path, branch, status_result.stdout)

    @staticmethod
    def _parse_git_status(repo_path: Path, branch: str, status_output: str) -> GitStatus:
        """
        Parse git status porcelain output into GitStatus object.
        
        Args:
            repo_path: Path to repository
            branch: Current branch name
            status_output: Output from git status --porcelain --branch
            
        Returns:
            GitStatus object with parsed information
        """
        lines = status_output.strip().split("\n")
        
        ahead = 0
        behind = 0
        staged = 0
        modified = 0
        untracked = 0
        
        for line in lines:
            if not line:
                continue
                
            # First line contains branch info
            if line.startswith("## "):
                # Parse ahead/behind info: ## branch...origin/branch [ahead 2, behind 1]
                if "[ahead" in line:
                    ahead_part = line.split("[ahead ")[1].split("]")[0]
                    if "," in ahead_part:
                        ahead = int(ahead_part.split(",")[0])
                    else:
                        ahead = int(ahead_part)
                if "behind" in line:
                    behind_part = line.split("behind ")[1].split("]")[0]
                    behind = int(behind_part.rstrip("]"))
            else:
                # Parse file status
                # Format: XY filename
                # X = index status, Y = working tree status
                if len(line) >= 2:
                    index_status = line[0]
                    worktree_status = line[1]
                    
                    # Staged changes (index has changes)
                    if index_status in ("M", "A", "D", "R", "C"):
                        staged += 1
                        
                    # Modified in working tree
                    if worktree_status == "M":
                        modified += 1
                        
                    # Untracked files
                    if line.startswith("??"):
                        untracked += 1
        
        is_clean = (staged == 0 and modified == 0 and untracked == 0)
        
        return GitDetector.GitStatus(
            repo_path=repo_path,
            branch=branch,
            is_clean=is_clean,
            ahead=ahead,
            behind=behind,
            staged=staged,
            modified=modified,
            untracked=untracked
        )

    @staticmethod
    def scan_git_repos(root_path: Path = Path("/home/devuser/workspace")) -> list[GitStatus]:
        """
        Scan for git repositories and return their status.
        
        Args:
            root_path: Root directory to scan (default: /home)
            
        Returns:
            List of GitStatus objects for all found repositories
        """
        repos = GitDetector.find_git_repos(root_path)
        return [GitDetector.get_git_status(repo) for repo in repos]