from sqlalchemy import create_engine, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from math import ceil
from config import SQLALCHEMY_DATABASE_URI


class Pagination(object):
    def __init__(self, query, page, per_page, total, items):
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items

    @property
    def pages(self):
        if self.per_page == 0:
            pages = 0
        else:
            pages = int(ceil(self.total / float(self.per_page)))
        return pages

    def prev(self, error_out=False):
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return self.query.paginate(self.page - 1, self.per_page, error_out)

    def next(self, error_out=False):
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return self.query.paginate(self.page + 1, self.per_page, error_out)

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        if not self.has_prev:
            return None
        return self.page - 1

    @property
    def next_num(self):
        if not self.has_next:
            return None
        return self.page + 1


class BaseQuery(orm.Query):
    def paginate(self, page=1, per_page=20, error_out=True):
        if page < 1:
            if error_out:
                raise IndexError
            else:
                page = 1
        if per_page < 0:
            if error_out:
                raise IndexError
            else:
                per_page = 20
        items = self.limit(per_page).offset((page - 1) * per_page).all()
        if not items and page != 1:
            if error_out:
                raise IndexError
            else:
                page = 1
        if page == 1 and len(items) < per_page:
            total = len(items)
        else:
            total = self.order_by(None).count()
        return Pagination(self, page, per_page, total, items)


class SQLManager(object):
    def __init__(self):
        if 'sqlite' in SQLALCHEMY_DATABASE_URI:
            connect_args = {'check_same_thread': False}
            engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=False, connect_args=connect_args)
        else:
            engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=False)
        session_factory = sessionmaker(bind=engine)
        self._session = scoped_session(session_factory)
        self.Model = declarative_base(bind=engine)
        self.Model.query = self._session.query_property(query_cls=BaseQuery)

    @property
    def session(self):
        return self._session

    def create_all(self):
        self.Model.metadata.create_all()

    def drop_all(self):
        self.Model.metadata.drop_all()
