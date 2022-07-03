import os

from celery import Celery
from flask import Flask
from flask_bootstrap import Bootstrap
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy

from config import app_configs, AppConfig

bootstrap = Bootstrap()
moment = Moment()
db = SQLAlchemy(session_options={"autoflush": False})
celery = Celery(__name__, broker=AppConfig.CELERY_BROKER_URL)

login_manager = LoginManager()
login_manager.session_protection = "basic"
login_manager.login_view = "auth.login"


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(app_configs[config_name])

    db.init_app(app)
    bootstrap.init_app(app)
    login_manager.init_app(app)
    moment.init_app(app)

    for k, v in app.config.items():
        if k.startswith("CELERY_"):
            k = k[len("CELERY_") :].lower()
            celery.conf[k] = v
    # Broker connection is lazy, so we don't need to connect and retry on startup.
    celery.conf.broker_connection_retry_on_startup = False

    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)
    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint, url_prefix="/auth")
    from .contest import contest as contest_blueprint

    app.register_blueprint(contest_blueprint, url_prefix="/contest")
    return app


app = create_app(os.getenv("FLASK_CONFIG") or "default")
migrate = Migrate(app, db)
app.app_context().push()
