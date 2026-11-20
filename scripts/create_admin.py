"""Run once with python -m scripts.create_admin; never stores a default password."""
from getpass import getpass
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models import Role, User, UserRole
from app.auth.password import hash_password
from app.cms.schemas import StaffCreate


def main():
    username = input("Admin username: ")
    name = input("Full name: ")
    password = getpass("Password (at least 8 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    data = StaffCreate(username=username, full_name=name, password=password)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == data.username)):
            raise SystemExit("Username already exists. Choose a new dedicated admin username.")
        role = db.scalar(select(Role).where(Role.name == "admin"))
        if role is None:
            role = Role(name="admin", description="Platform administrator")
            db.add(role)
            db.flush()
        user = User(username=data.username, full_name=data.full_name, password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
    print("Admin created. Open /admin in the frontend.")


if __name__ == "__main__":
    main()
