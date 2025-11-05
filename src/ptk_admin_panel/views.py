# standard lib
# from typing import NamedTuple, Any

# third party
from flask import Blueprint, render_template #, request
# import psutil
# from psutil._common import sconn

# local
# from . import util_funcs

views = Blueprint("views", __name__)
    

@views.route("/")
def home():
    return render_template("home.html")


@views.route("/network")
def network():
    return render_template("network.html")



@views.route("/git")
def git():
    return render_template("git.html")

