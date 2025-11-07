# standard lib
from typing import Any
import time
from dataclasses import dataclass

# third party
from flask import Blueprint, render_template, request
import psutil

# local
from . import util_funcs


api = Blueprint("api", __name__)


@api.route("/api/placeholder")
def placeholder():
    
    return render_template("partials/_placeholder.html")


@dataclass
class MySconn:
    "the same as sconn except adds name if pid is available"
    
    name: str | None
    fd: int
    family: Any
    type: int
    laddr: Any
    raddr: Any
    status: str
    pid: int | None
    
@api.route("/api/connections")
def connections():

    conns_list = util_funcs.get_connections_list_filtered()
    my_sconns: list[MySconn] = []
    for c in conns_list:
        process = None
        name = None
        if c.pid:
            process = psutil.Process(c.pid)
            name = process.name()
            if len(name) > 18:
                name = name[:18]+"..."
        my_sconns.append(MySconn(
            name = name,
            fd = c.fd,
            family = c.family,
            type = c.type,
            laddr = c.laddr,
            raddr = c.raddr,
            status = c.status,
            pid = c.pid,
        ))
    return render_template("partials/_connections.html", context=my_sconns)

@api.route("/api/conn-info")
def conn_info():
    
    query = request.args.get('q')
    pid = -1
    if query:
        try:
            pid = int(query)
        except Exception as e:
            return f"Failed to get process by PID: {e}"
    else:
        return "Invalid query provided. Please provide valid PID"
    
    process = psutil.Process(pid)
    
    try:
        info = util_funcs.get_enhanced_proc_info(process)
    except Exception as e:
        info = None
        print(f"Error: {e}")

    return render_template("partials/_info.html", context=info)


@api.route("/api/ssh-status")
def ssh_status() -> str:
    
    status = util_funcs.SSHDetector.get_ssh_status()
    return render_template("partials/_ssh_status.html", context=status)


@api.route("/api/modified-files")
def modified_files() -> str:
    
    modified = util_funcs.get_recent_files(
        # exclude_hidden=True,
        limit=10,
    )
    return render_template("partials/_modified_files.html",context=modified)

@api.route("/api/zombies")
def zombies() -> str:
    
    zombies = util_funcs.ZombieDetector.get_zombie_processes()
    return render_template("partials/_zombies.html", context=zombies)


@api.route("/api/uptime")
def uptime() -> str:
    
    uptime = util_funcs.get_uptime_info()
    return render_template("partials/_uptime.html", context=uptime)


@api.route("/api/tmux")
def tmux() -> str:
    
    tmux_status = util_funcs.TmuxDetector.get_status()
    return render_template("partials/_tmux.html", context=tmux_status)


@api.route("/api/git")
def git() -> str:

    starttime = time.time()    
    git_repos = util_funcs.GitDetector.scan_git_repos()
    elapsed = f"{time.time() - starttime:.2f}"
    return render_template("partials/_git.html", context=git_repos, elapsed=elapsed)
