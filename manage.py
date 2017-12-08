#!/usr/bin/env python
import os
from app import create_app, celery, db
from app.models import User, Role, Problem, Submission
from flask_script import Manager, Shell

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
app.app_context().push()

manager = Manager(app)


def make_shell_context():
    return dict(app=app, celery=celery, db=db, User=User, Role=Role, Problem=Problem, Submission=Submission)


manager.add_command('shell', Shell(make_context=make_shell_context))

if __name__ == '__main__':
    manager.run()
