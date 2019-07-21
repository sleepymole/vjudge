import os
import re
from datetime import timedelta


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'A0Zr98j/3yX R~XHH!jmN]LWX/,?R'
    SQLALCHEMY_DATABASE_URI = (os.environ.get('DATABASE_URL') or
                               'sqlite:///' + os.path.dirname(__file__) + '/data.sqlite')
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BOOTSTRAP_SERVE_LOCAL = True
    FLASKY_ADMIN = 'admin'
    FLASKY_FOLLOWERS_PER_PAGE = 20
    ENABLE_UTC = True
    CELERYBEAT_SCHEDULE = {
        'update-problems': {
            'task': 'update_problem_all',
            'schedule': timedelta(hours=12)
        },
        'refresh_recent_contest': {
            'task': 'refresh_recent_contest',
            'schedule': timedelta(minutes=5)
        }
    }
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/1'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/2'
    VJUDGE_REMOTE_URL = os.environ.get('VJUDGE_REMOTE_URL') or 'http://localhost:5000'


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    pass


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}

VJUDGE_REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0
}


def init_redis_config():
    redis_uri = os.environ.get('VJUDGE_REDIS_CONFIG') or 'redis://localhost:6379/0'
    match = re.match('^redis://(.*?):([0-9]+)/([0-9]+)$', redis_uri)
    if match:
        host, port, db = match.groups()
        VJUDGE_REDIS_CONFIG['host'], VJUDGE_REDIS_CONFIG['port'], VJUDGE_REDIS_CONFIG['db'] = host, int(port), int(db)


init_redis_config()
