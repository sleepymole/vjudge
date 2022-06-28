import logging
import os
import re
from datetime import timedelta

from celery.schedules import crontab
from gunicorn.glogging import Logger

LOG_ENV = os.environ.get("LOG_ENV") or "NORMAL"
LOG_LEVEL = os.environ.get("LOG_LEVEL") or "info"
LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

if LOG_ENV == "JOURNAL":
    log_format = r"[%(levelname)s] %(message)s"
else:
    log_format = r"[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s"

date_fmt = r"%Y-%m-%d %H:%M:%S %z"


class GLogger(Logger):
    error_fmt = log_format
    datefmt = date_fmt


log_level = LOG_LEVELS.get(LOG_LEVEL, logging.INFO)
logging.basicConfig(level=log_level, format=log_format, datefmt=date_fmt)
logger = logging.getLogger("vjudge")

SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(
    os.getcwd(), "data.sqlite"
)


class Config(object):
    SECRET_KEY = os.environ.get("SECRET_KEY") or "A0Zr98j/3yX R~XHH!jmN]LWX/,?R"
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BOOTSTRAP_SERVE_LOCAL = True
    FLASKY_ADMIN = "admin"
    FLASKY_FOLLOWERS_PER_PAGE = 20
    ENABLE_UTC = True
    CELERYBEAT_SCHEDULE = {
        "update-problems": {
            "task": "update_problem_all",
            "schedule": crontab(hour={13, 22}, minute=0),
        },
        "refresh_recent_contest": {
            "task": "refresh_recent_contest",
            "schedule": timedelta(minutes=5),
        },
    }
    CELERY_BROKER_URL = (
        os.environ.get("CELERY_BROKER_URL") or "redis://localhost:6379/1"
    )

    CELERY_RESULT_BACKEND = (
        os.environ.get("CELERY_RESULT_BACKEND") or "redis://localhost:6379/2"
    )


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    pass


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}

VJUDGE_REDIS_CONFIG = {"host": "localhost", "port": 6379, "db": 0}


def init_redis_config():
    redis_uri = os.environ.get("VJUDGE_REDIS_CONFIG") or "redis://localhost:6379/0"
    match = re.match("^redis://(.*?):([0-9]+)/([0-9]+)$", redis_uri)
    if match:
        host, port, db = match.groups()
        (
            VJUDGE_REDIS_CONFIG["host"],
            VJUDGE_REDIS_CONFIG["port"],
            VJUDGE_REDIS_CONFIG["db"],
        ) = (host, int(port), int(db))


init_redis_config()
