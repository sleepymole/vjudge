#!/usr/bin/env python3
from flask_script import Manager, Shell

from server import app
from vjudge import db
from vjudge.models import Submission, Problem


def make_shell_context():
    return dict(app=app, db=db, Submission=Submission, Problem=Problem)


manager = Manager(app)
manager.add_command('shell', Shell(make_context=make_shell_context))

if __name__ == '__main__':
    manager.run()
