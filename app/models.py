from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask_login import UserMixin, AnonymousUserMixin
from flask import current_app
from datetime import datetime
from . import db, login_manager


class Permission:
    FOLLOW = 0x01
    MODERATE = 0x40
    ADMINISTER = 0x80


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship('User', backref='role', lazy='dynamic')

    @staticmethod
    def insert_roles():
        roles = {
            'User': (Permission.FOLLOW, True),
            'Moderator': (Permission.FOLLOW |
                          Permission.MODERATE, False),
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


class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Submission(db.Model):
    __tablename__ = 'submissions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    oj_name = db.Column(db.String, nullable=False)
    problem_id = db.Column(db.String, nullable=False)
    language = db.Column(db.String, nullable=False)
    source_code = db.Column(db.String, nullable=False)
    share = db.Column(db.Boolean, default=False)
    run_id = db.Column(db.String)
    verdict = db.Column(db.String, default='Queuing')
    exe_time = db.Column(db.Integer, default=0)
    exe_mem = db.Column(db.Integer, default=0)
    time_stamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.ForeignKeyConstraint(
        ['oj_name', 'problem_id'], ['problems.oj_name', 'problems.problem_id']), {})

    def __repr__(self):
        return '<Submission(id={}, user_id={}, oj_name={}, problem_id={} verdict={})>'. \
            format(self.run_id, self.user_id, self.oj_name, self.problem_id, self.verdict)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text)
    member_since = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    solved = db.Column(db.Integer, default=0)
    submitted = db.Column(db.Integer, default=0)
    followed = db.relationship('Follow',
                               foreign_keys=[Follow.follower_id],
                               backref=db.backref('follower', lazy='joined'),
                               lazy='dynamic',
                               cascade='all, delete-orphan')
    followers = db.relationship('Follow',
                                foreign_keys=[Follow.followed_id],
                                backref=db.backref('followed', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')
    submissions = db.relationship('Submission',
                                  foreign_keys=[Submission.user_id],
                                  backref='user',
                                  lazy='dynamic')

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

    def follow(self, user):
        if not self.is_following(user):
            f = Follow(follower=self, followed=user)
            db.session.add(f)

    def unfollow(self, user):
        f = self.followed.filter_by(followed_id=user.id).first()
        if f:
            db.session.delete(f)

    def is_following(self, user):
        return self.followed.filter_by(followed_id=user.id).first() is not None

    def is_followed_by(self, user):
        return self.followers.filter_by(follower_id=user.id).first() is not None

    def __repr__(self):
        return '<User {}>'.format(self.username)


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Problem(db.Model):
    __tablename__ = 'problems'
    oj_name = db.Column(db.String, primary_key=True)
    problem_id = db.Column(db.String, primary_key=True)
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    solved = db.Column(db.Integer, default=0)
    title = db.Column(db.String)
    description = db.Column(db.String)
    input = db.Column(db.String)
    output = db.Column(db.String)
    sample_input = db.Column(db.String)
    sample_output = db.Column(db.Integer)
    mem_limit = db.Column(db.Integer)
    time_limit = db.Column(db.Integer)
    submissions = db.relationship('Submission', foreign_keys=[Submission.oj_name, Submission.problem_id],
                                  backref='problem', lazy='dynamic')

    def __repr__(self):
        return '<Problem {} {}: {}>'.format(self.oj_name, self.problem_id, self.title)
