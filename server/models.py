import sqlalchemy as sql
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from sqlalchemy.orm import relationship
from flask_login import UserMixin, AnonymousUserMixin
from flask import current_app
from datetime import datetime
from . import db, login_manager


class Permission:
    FOLLOW = 0x01
    ADMINISTER = 0x80


class Role(db.Model):
    __tablename__ = 'roles'
    id = sql.Column(sql.Integer, primary_key=True)
    name = sql.Column(sql.String(64), unique=True)
    default = sql.Column(sql.Boolean, default=False, index=True)
    permissions = sql.Column(sql.Integer)
    users = relationship('User', backref='role', lazy='dynamic')

    @staticmethod
    def insert_roles():
        roles = {
            'User': (Permission.FOLLOW, True),
            'Administrator': (0xff, False)
        }
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.permissions = roles[r][0]
            role.default = roles[r][1]
            db.session.add(role)
        db.session.commit()

    def __repr__(self):
        return '<Role {}>'.format(self.name)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = sql.Column(sql.Integer, primary_key=True)
    email = sql.Column(sql.String(64), unique=True, index=True)
    username = sql.Column(sql.String(64), unique=True, index=True)
    role_id = sql.Column(sql.Integer, sql.ForeignKey('roles.id'))
    password_hash = sql.Column(sql.String(128))
    name = sql.Column(sql.String(64))
    location = sql.Column(sql.String(64))
    about_me = sql.Column(sql.Text)
    member_since = sql.Column(sql.DateTime, default=datetime.utcnow)
    last_seen = sql.Column(sql.DateTime, default=datetime.utcnow)

    def __init__(self):
        super().__init__()
        if self.role is None:
            self.role = Role.query.filter_by(default=True).first()

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_reset_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'reset': self.id})

    def reset_password(self, token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.load(token)
        except:
            return False
        if data.get('reset') != self.id:
            return False
        self.password = new_password
        db.session.add(self)
        return True

    def can(self, permissions):
        return self.role is not None and \
               (self.role.permissions & permissions) == permissions

    def is_administrator(self):
        return self.can(Permission.ADMINISTER)

    def ping(self):
        self.last_seen = datetime.utcnow()
        db.session.add(self)

    def __repr__(self):
        return '<User {}>'.format(self.username)


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False


class Submission(db.Model):
    __tablename__ = 'submission'
    run_id = sql.Column(sql.Integer, primary_key=True)
    user_id = sql.Column(sql.String)
    oj_name = sql.Column(sql.String, nullable=False)
    problem_id = sql.Column(sql.String, nullable=False)
    language = sql.Column(sql.String, nullable=False)
    source_code = sql.Column(sql.String)
    submit_time = sql.Column(sql.Integer, nullable=False)
    remote_run_id = sql.Column(sql.String)
    remote_user_id = sql.Column(sql.String)
    verdict = sql.Column(sql.String, default='Queuing')
    exe_time = sql.Column(sql.Integer)
    exe_mem = sql.Column(sql.Integer)

    def update(self, **kwargs):
        for attr in kwargs:
            if hasattr(self, attr):
                setattr(self, attr, kwargs.get(attr))

    def __repr__(self):
        return '<Submission(run_id={}, user_id={}, oj_name={}, problem_id={} verdict={})>'. \
            format(self.run_id, self.user_id, self.oj_name, self.problem_id, self.verdict)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
