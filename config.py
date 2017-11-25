import os


class Config(object):
    SECRET_KEY = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?R'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.dirname(__file__) + '/data.sqlite'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FLASKY_FOLLOWERS_PER_PAGE = 20


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
    'default': DevelopmentConfig
}
