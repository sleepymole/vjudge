from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from config import SQLALCHEMY_DATABASE_URI


class SQLManager(object):
    def __init__(self, app=None):
        engine = create_engine(SQLALCHEMY_DATABASE_URI)
        session_factory = sessionmaker(bind=engine)
        self.Model = declarative_base(bind=engine)
        self._session = scoped_session(session_factory)
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.teardown_appcontext
        def shutdown_session(response_or_exc):
            if app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN']:
                if response_or_exc is None:
                    self.session.commit()

            self.session.remove()
            return response_or_exc

    @property
    def session(self):
        return self._session

    def create_all(self):
        self.Model.metadata.create_all()

    def drop_all(self):
        self.Model.metadata.drop_all()
