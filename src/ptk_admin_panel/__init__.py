from flask import Flask
from .views import views
from .auth import auth
from .api import api


def main():

    app = Flask(__name__)
    app.config['SECRET_KEY'] = "wpjnaw98h252ba79"
    
    app.register_blueprint(views)
    app.register_blueprint(auth)
    app.register_blueprint(api)
    app.run(host="0.0.0.0", debug=True)