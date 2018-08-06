import os
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
    CELERYBEAT_SCHEDULE = {
        'update-problems': {
            'task': 'update_problem_all',
            'schedule': timedelta(hours=1)
        },
    }
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
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
