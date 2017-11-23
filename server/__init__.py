from flask_bootstrap import Bootstrap
from flask_login import LoginManager
from flask_moment import Moment
from flask import Flask
from queue import Queue
from config import config
from .database import SQLManager

bootstrap = Bootstrap()
moment = Moment()

login_manager = LoginManager()
login_manager.session_protection = 'basic'
login_manager.login_view = 'auth.login'

db = SQLManager()

submit_queue = Queue()


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    db.init_app(app)
    bootstrap.init_app(app)
    login_manager.init_app(app)
    moment.init_app(app)
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    return app
