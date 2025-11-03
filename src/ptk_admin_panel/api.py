# standard lib
from typing import NamedTuple, Any
from dataclasses import dataclass

# third party
from flask import Blueprint, render_template, request
import psutil

# local
from . import util_funcs


api = Blueprint("api", __name__)




class BasicInfo(NamedTuple):
    disk_usage: Any
    pids: list[int]
    users: list[Any]
    
    
@api.route("/api/basic_info")
def basic_info():
    
    info = BasicInfo(
        disk_usage = psutil.disk_usage("/"),
        pids = psutil.pids(),
        users = psutil.users(),
    )
    return render_template("_basic.html", context=info)

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
    return render_template("_connections.html", context=my_sconns)

@api.route("/api/conn-info")
def conn_info():
    
    query = request.args.get('q')
    pid = -1
    if query:
        try:
            pid = int(query)
        except Exception:
            pass
    
    try:
        info = util_funcs.get_enhanced_proc_info(pid)
    except Exception as e:
        info = None
        print(f"Error: {e}")

    return render_template("_info.html", context=info)


@api.route("/api/ssh-status")
def ssh_status() -> str:
    
    status = util_funcs.get_ssh_status()
    
    return render_template("_ssh_status.html", context=status)
