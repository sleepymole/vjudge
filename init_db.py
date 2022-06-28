from config import Config
from manage import db, Role, User
from core import db as core_db


def init_db():
    db.create_all()
    Role.insert_roles()
    admin = User.query.get(1) or User()
    admin.username = Config.FLASKY_ADMIN
    admin.password = "123456"
    db.session.add(admin)
    db.session.commit()
    admin.role_id = 3
    db.session.commit()
    core_db.create_all()


if __name__ == "__main__":
    init_db()
