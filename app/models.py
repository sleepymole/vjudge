import json
from datetime import datetime
from datetime import timedelta

from authlib.jose import jwt, JoseError
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db, login_manager


class Permission:
    FOLLOW = 0x01
    MODERATE = 0x40
    ADMINISTER = 0x80


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship("User", backref="role", lazy="dynamic")

    @staticmethod
    def insert_roles():
        roles = {
            "User": (Permission.FOLLOW, True),
            "Moderator": (Permission.FOLLOW | Permission.MODERATE, False),
            "Administrator": (0xFF, False),
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
        return "<Role {}>".format(self.name)


class Follow(db.Model):
    __tablename__ = "follows"
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    oj_name = db.Column(db.String, nullable=False)
    problem_id = db.Column(db.String, nullable=False)
    language = db.Column(db.String, nullable=False)
    source_code = db.Column(db.String, nullable=False)
    share = db.Column(db.Boolean, default=False)
    run_id = db.Column(db.String)
    verdict = db.Column(db.String, default="Queuing")
    exe_time = db.Column(db.Integer, default=0)
    exe_mem = db.Column(db.Integer, default=0)
    time_stamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["oj_name", "problem_id"], ["problems.oj_name", "problems.problem_id"]
        ),
        {},
    )

    def __repr__(self):
        return "<Submission(id={}, user_id={}, oj_name={}, problem_id={} verdict={})>".format(
            self.run_id, self.user_id, self.oj_name, self.problem_id, self.verdict
        )


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text)
    member_since = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    solved = db.Column(db.Integer, default=0)
    submitted = db.Column(db.Integer, default=0)
    followed = db.relationship(
        "Follow",
        foreign_keys=[Follow.follower_id],
        backref=db.backref("follower", lazy="joined"),
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    followers = db.relationship(
        "Follow",
        foreign_keys=[Follow.followed_id],
        backref=db.backref("followed", lazy="joined"),
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    submissions = db.relationship(
        "Submission", foreign_keys=[Submission.user_id], backref="user", lazy="dynamic"
    )

    def __init__(self):
        super().__init__()
        if self.role is None:
            self.role = Role.query.filter_by(default=True).first()

    @property
    def password(self):
        raise AttributeError("password is not a readable attribute")

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_reset_token(self, expiration=3600):
        header = {"alg": "HS256"}
        payload = {
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(seconds=expiration),
            "reset": self.id,
        }
        return jwt.encode(header, payload, current_app.config["SECRET_KEY"])

    def reset_password(self, token, new_password):
        try:
            data = jwt.decode(token, current_app.config["SECRET_KEY"])
            data.validate()
        except JoseError:
            return False
        if data.get("reset") != self.id:
            return False
        self.password = new_password
        db.session.add(self)
        return True

    def can(self, permissions):
        return (
            self.role is not None
            and (self.role.permissions & permissions) == permissions
        )

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
        return "<User {}>".format(self.username)


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
    __tablename__ = "problems"
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
    submissions = db.relationship(
        "Submission",
        foreign_keys=[Submission.oj_name, Submission.problem_id],
        backref="problem",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Problem(oj_name={self.oj_name}, problem_id{self.problem_id}, {self.title})>"


class Contest(db.Model):
    __tablename__ = "contests"
    id = db.Column(db.Integer, primary_key=True)
    problems = db.Column(db.String, default="[]")
    is_clone = db.Column(db.Boolean, default=False)
    clone_name = db.Column(db.String)
    title = db.Column(db.String, default="")
    public = db.Column(db.Boolean, default=False)
    status = db.Column(db.String, default="Pending")
    start_time = db.Column(db.DateTime, default=datetime.utcfromtimestamp(0))
    end_time = db.Column(db.DateTime, default=datetime.utcfromtimestamp(0))

    def get_ori_problem(self, problem_id):
        ori_problems = self.get_ori_problems()
        if ori_problems is not None:
            return ori_problems.get(problem_id)

    def get_ori_problems(self):
        self._ori_problems = getattr(self, "_ori_problems", None)
        if self._ori_problems is None:
            try:
                problem_list = json.loads(self.problems)
            except json.JSONDecodeError:
                return
            if not isinstance(problem_list, list):
                return
            self._ori_problems = {}
            for problem in problem_list:
                self._ori_problems[problem[0]] = (problem[1], problem[2])
        return self._ori_problems

    def __repr__(self):
        return f"<Contest(id={self.id}, title={self.title})>"


class ContestSubmission(db.Model):
    __tablename__ = "contest_submissions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    seq = db.Column(db.Integer, nullable=False)
    contest_id = db.Column(db.String, nullable=False)
    oj_name = db.Column(db.String, nullable=False)
    problem_id = db.Column(db.String, nullable=False)
    language = db.Column(db.String, nullable=False)
    source_code = db.Column(db.String, nullable=False)
    share = db.Column(db.Boolean, default=False)
    run_id = db.Column(db.String)
    verdict = db.Column(db.String, default="Queuing")
    exe_time = db.Column(db.Integer, default=0)
    exe_mem = db.Column(db.Integer, default=0)
    time_stamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<ContestSubmission(id={self.run_id}, user_id={self.user_id}, oj_name={self.oj_name}, "
            f"problem_id={self.problem_id} verdict={self.verdict})>"
        )
