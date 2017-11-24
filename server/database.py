from math import ceil
from sqlalchemy import create_engine, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from flask import abort, request
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

    @property
    def prev_num(self):
        if not self.has_prev:
            return None
        return self.page - 1

    @property
    def has_prev(self):
        return self.page > 1

    def next(self, error_out=False):
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return self.query.paginate(self.page + 1, self.per_page, error_out)

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        if not self.has_next:
            return None
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge \
                    or (self.page - left_current - 1 < num < self.page + right_current) \
                    or num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


class BaseQuery(orm.Query):
    def get_or_404(self, ident):
        rv = self.get(ident)
        if rv is None:
            abort(404)
        return rv

    def first_or_404(self):
        rv = self.first()
        if rv is None:
            abort(404)
        return rv

    def paginate(self, page=None, per_page=None, error_out=True, max_per_page=None):
        if request:
            if page is None:
                try:
                    page = int(request.args.get('page', 1))
                except (TypeError, ValueError):
                    if error_out:
                        abort(404)
                    page = 1
            if per_page is None:
                try:
                    per_page = int(request.args.get('per_page', 20))
                except (TypeError, ValueError):
                    if error_out:
                        abort(404)
                    per_page = 20
        else:
            if page is None:
                page = 1
            if per_page is None:
                per_page = 20
        if max_per_page is not None:
            per_page = min(per_page, max_per_page)
        if page < 1:
            if error_out:
                abort(404)
            else:
                page = 1
        if per_page < 0:
            if error_out:
                abort(404)
            else:
                per_page = 20
        items = self.limit(per_page).offset((page - 1) * per_page).all()
        if not items and page != 1 and error_out:
            abort(404)
        if page == 1 and len(items) < per_page:
            total = len(items)
        else:
            total = self.order_by(None).count()
        return Pagination(self, page, per_page, total, items)


def _set_default_query_class(d, cls):
    if 'query_class' not in d:
        d['query_class'] = cls


def _wrapped_relationship(*args, **kwargs):
    _set_default_query_class(kwargs, BaseQuery)
    if 'backref' in kwargs:
        backref = kwargs['backref']
        if isinstance(backref, str):
            backref = (backref, {})
        _set_default_query_class(backref[1], BaseQuery)
        kwargs['backref'] = backref
    return relationship(*args, **kwargs)


class SQLManager(object):
    def __init__(self, app=None):
        engine = create_engine(SQLALCHEMY_DATABASE_URI)
        session_factory = sessionmaker(bind=engine)
        self._session = scoped_session(session_factory)
        self.Model = declarative_base(bind=engine)
        self.Model.query = self._session.query_property(query_cls=BaseQuery)
        self.relationship = _wrapped_relationship

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
