#!/usr/bin/env python3
import os
from server import create_app, db, submit_queue
from server.models import User, Role, Submission
from flask_script import Manager, Shell
from vjudge.base import VJudge

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
manager = Manager(app)


def make_shell_context():
    return dict(app=app, db=db, User=User, Role=Role, Submission=Submission)


manager.add_command('shell', Shell(make_context=make_shell_context))

judge = VJudge(submit_queue)
judge.setDaemon(True)
judge.start()

if __name__ == '__main__':
    manager.run()
