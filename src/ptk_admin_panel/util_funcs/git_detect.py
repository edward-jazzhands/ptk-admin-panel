# Standard library:
from __future__ import annotations
from typing import NamedTuple
import subprocess
from pathlib import Path



class GitStatus(NamedTuple):
    repo_path: Path
    branch: str
    is_clean: bool
    ahead: int
    behind: int
    staged: int
    modified: int
    untracked: int
    error: str | None = None


def _find_git_repos(root_path: Path) -> list[Path]:
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


def _get_git_status(repo_path: Path) -> GitStatus:
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
        return GitStatus(
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
            return GitStatus(
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
                return GitStatus(
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
            
            return _parse_git_status(repo_path, branch, status_result.stdout)


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
    
    return GitStatus(
        repo_path=repo_path,
        branch=branch,
        is_clean=is_clean,
        ahead=ahead,
        behind=behind,
        staged=staged,
        modified=modified,
        untracked=untracked
    )


def scan_git_repos(root_path: Path = Path("/home/devuser/workspace")) -> list[GitStatus]:
    """
    Scan for git repositories and return their status.
    
    Args:
        root_path: Root directory to scan (default: /home)
        
    Returns:
        List of GitStatus objects for all found repositories
    """
    repos = _find_git_repos(root_path)
    return [_get_git_status(repo) for repo in repos]