from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.role import Role


ROLES = [
    {"name": "parent", "description": "Parent or guardian"},
    {
        "name": "student",
        "description": "Student user",
    },
    {
        "name": "teacher",
        "description": "Teacher user",
    },
    {
        "name": "admin",
        "description": "Platform administrator",
    },
    {
        "name": "supervisor",
        "description": "Educational supervisor",
    },
    {
        "name": "guest",
        "description": "Guest user with limited access",
    },
]


def seed_roles():
    db = SessionLocal()

    try:
        for role_data in ROLES:
            existing_role = db.scalar(
                select(Role).where(Role.name == role_data["name"])
            )

            if existing_role:
                print(f"Role already exists: {role_data['name']}")
                continue

            role = Role(**role_data)
            db.add(role)

        db.commit()
        print("Roles seeded successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_roles()