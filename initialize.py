import logging
from manage import app, db, Role, User
from config import Config

logging.basicConfig(level=logging.INFO)

app.app_context().push()


def init_db():
    db.create_all()
    Role.insert_roles()
    admin = User.query.get(1) or User()
    admin.username = Config.FLASKY_ADMIN
    admin.password = '123456'
    db.session.add(admin)
    db.session.commit()
    admin.role_id = 3
    db.session.commit()


if __name__ == '__main__':
    init_db()
