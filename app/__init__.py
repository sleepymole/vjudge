from celery import Celery
from flask import Flask
from flask_bootstrap import Bootstrap
from flask_login import LoginManager
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy

from config import config, Config

bootstrap = Bootstrap()
moment = Moment()
db = SQLAlchemy(session_options={"autoflush": False})
celery = Celery(__name__, broker=Config.CELERY_BROKER_URL)

login_manager = LoginManager()
login_manager.session_protection = "basic"
login_manager.login_view = "auth.login"


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    bootstrap.init_app(app)
    login_manager.init_app(app)
    moment.init_app(app)
    celery.conf.update(app.config)

    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)
    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint, url_prefix="/auth")
    from .contest import contest as contest_blueprint

    app.register_blueprint(contest_blueprint, url_prefix="/contest")
    return app
