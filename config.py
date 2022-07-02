import logging
import os
from datetime import timedelta
from typing import List

import toml
from celery.schedules import crontab


class NormalAccount(object):
    def __init__(self, site, username, password):
        self.site = site
        self.username = username
        self.password = password


class ContestAccount(object):
    def __init__(self, site, username, password, authorized_contests):
        self.site = site
        self.username = username
        self.password = password
        self.authorized_contests = authorized_contests


class Config(object):
    LOG_ENV = os.environ.get("LOG_ENV") or "NORMAL"
    LOG_LEVEL = os.environ.get("LOG_LEVEL") or "info"
    DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite:///data.sqlite"
    DEFAULT_REDIS_URL = (
        os.environ.get("DEFAULT_REDIS_URL") or "redis://localhost:6379/0"
    )
    CELERY_BROKER_URL = (
        os.environ.get("CELERY_BROKER_URL") or "redis://localhost:6379/1"
    )
    CELERY_RESULT_BACKEND = (
        os.environ.get("CELERY_RESULT_BACKEND") or "redis://localhost:6379/2"
    )
    NORMAL_ACCOUNTS: List[NormalAccount] = []
    CONTEST_ACCOUNTS: List[ContestAccount] = []


def _load_config_from_file():
    filepath = os.environ.get("CONFIG_FILE") or "config.toml"
    if not os.path.exists(filepath):
        return
    config = toml.load(filepath)
    if config.get("log-level") is not None:
        Config.LOG_LEVEL = config["log-level"]
        del config["log-level"]
    if config.get("database-url") is not None:
        Config.DATABASE_URL = config["database-url"]
        del config["database-url"]
    if config.get("default-redis-url") is not None:
        Config.DEFAULT_REDIS_URL = config["default-redis-url"]
        del config["default-redis-url"]
    if config.get("celery-broker-url") is not None:
        Config.CELERY_BROKER_URL = config["celery-broker-url"]
        del config["celery-broker-url"]
    if config.get("celery-backend-url") is not None:
        Config.CELERY_RESULT_BACKEND = config["celery-backend-url"]
        del config["celery-backend-url"]
    accounts = config.get("accounts")
    if accounts is not None:
        normal = accounts.get("normal")
        assert isinstance(normal, list)
        for account in normal:
            Config.NORMAL_ACCOUNTS.append(
                NormalAccount(
                    site=account["site"],
                    username=account["username"],
                    password=account["password"],
                )
            )
        del accounts["normal"]
        contest = accounts.get("contest")
        assert isinstance(contest, list)
        for account in contest:
            authorized_contests = account.get("authorized-contests")
            authorized_contests = (
                list(map(int, authorized_contests)) if authorized_contests else []
            )
            Config.CONTEST_ACCOUNTS.append(
                ContestAccount(
                    site=account["site"],
                    username=account["username"],
                    password=account["password"],
                    authorized_contests=authorized_contests,
                )
            )
        del accounts["contest"]
    if len(accounts) == 0:
        del config["accounts"]
    if len(config) > 0:
        raise ValueError(f"Unknown config: {config}")


_load_config_from_file()


def _init_logger():
    if Config.LOG_ENV == "JOURNAL":
        log_format = r"[%(levelname)s] %(message)s"
    else:
        log_format = r"[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s"
    date_fmt = r"%Y-%m-%d %H:%M:%S %z"
    log_levels = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }
    log_level = log_levels.get(Config.LOG_LEVEL, logging.INFO)
    logging.basicConfig(level=log_level, format=log_format, datefmt=date_fmt)
    return logging.getLogger("vjudge")


logger = _init_logger()


class AppConfig(object):
    SECRET_KEY = os.environ.get("SECRET_KEY") or "A0Zr98j/3yX R~XHH!jmN]LWX/,?R"
    SQLALCHEMY_DATABASE_URI = Config.DATABASE_URL
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
    CELERY_BROKER_URL = Config.CELERY_BROKER_URL
    CELERY_RESULT_BACKEND = Config.CELERY_RESULT_BACKEND


class DevelopmentAppConfig(AppConfig):
    DEBUG = True


class TestingAppConfig(AppConfig):
    TESTING = True


class ProductionAppConfig(AppConfig):
    pass


app_configs = {
    "development": DevelopmentAppConfig,
    "testing": TestingAppConfig,
    "production": ProductionAppConfig,
    "default": ProductionAppConfig,
}
