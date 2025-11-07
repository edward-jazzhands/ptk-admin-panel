# Standard library:
from __future__ import annotations
from typing import NamedTuple
from datetime import datetime
import os



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
