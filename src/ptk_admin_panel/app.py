from flask import Flask
from .views import views
# from .auth import auth
from .api import api

app = Flask(__name__)
app.config['SECRET_KEY'] = "my_secret_key_lol"

app.register_blueprint(views)
# app.register_blueprint(auth)
app.register_blueprint(api)

