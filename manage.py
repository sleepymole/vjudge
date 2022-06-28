import os
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager, Shell

from app import create_app, celery, db
from app.models import User, Role, Problem, Submission, Contest, ContestSubmission
from core.models import Problem as CoreProblem
from core.models import Submission as CoreSubmission
from core.models import Contest as CoreContest
from core import db as core_db

app = create_app(os.getenv("FLASK_CONFIG") or "default")
migrate = Migrate(app, db)
app.app_context().push()

manager = Manager(app)


def make_shell_context():
    return dict(
        app=app,
        celery=celery,
        db=db,
        User=User,
        Role=Role,
        Problem=Problem,
        Submission=Submission,
        Contest=Contest,
        ContestSubmission=ContestSubmission,
        core_db=core_db,
        CoreProblem=CoreProblem,
        CoreSubmission=CoreSubmission,
        CoreContest=CoreContest,
    )


manager.add_command("shell", Shell(make_context=make_shell_context))
manager.add_command("db", MigrateCommand)

if __name__ == "__main__":
    manager.run()
