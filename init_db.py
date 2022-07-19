from app.models import db, Role, User
from config import AppConfig
from core import db as core_db


def init_db():
    db.create_all()
    Role.insert_roles()
    admin = User.query.get(1)
    if not admin:
        admin = User()
        admin.role = Role.query.filter_by(name="Administrator").first()
        admin.username = AppConfig.FLASKY_ADMIN
        admin.password = "123456"
        db.session.add(admin)
        db.session.commit()
    core_db.create_all()


if __name__ == "__main__":
    init_db()
