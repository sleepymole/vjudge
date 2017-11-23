from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from flask import current_app
from . import db, login_manager


class Role(db.Model):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    users = relationship('User', backref='role', lazy='dynamic')

    def __repr__(self):
        return '<Role {}>'.format(self.name)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True)
    role_id = Column(Integer, ForeignKey('roles.id'))
    password_hash = Column(String(128))

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

    def __repr__(self):
        return '<User {}>'.format(self.username)


class Submission(db.Model):
    __tablename__ = 'submission'
    run_id = Column(Integer, primary_key=True)
    user_id = Column(String)
    oj_name = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    language = Column(String, nullable=False)
    source_code = Column(String)
    submit_time = Column(Integer, nullable=False)
    remote_run_id = Column(String)
    remote_user_id = Column(String)
    verdict = Column(String, default='Queuing')
    exe_time = Column(Integer)
    exe_mem = Column(Integer)

    def update(self, **kwargs):
        for attr in kwargs:
            if hasattr(self, attr):
                setattr(self, attr, kwargs.get(attr))

    def __repr__(self):
        return '<Submission(run_id={}, user_id={}, oj_name={}, problem_id={} verdict={})>'. \
            format(self.run_id, self.user_id, self.oj_name, self.problem_id, self.verdict)


@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(int(user_id))
