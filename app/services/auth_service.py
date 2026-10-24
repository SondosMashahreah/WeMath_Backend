from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.email == email.lower().strip()
        )
    )


def get_user_by_id(
    db: Session,
    user_id: int,
) -> User | None:
    return db.scalar(
        select(User).where(User.id == user_id)
    )


def get_user_roles(
    db: Session,
    user_id: int,
) -> list[str]:
    result = db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )

    return list(result.scalars().all())


def register_student(
    db: Session,
    full_name: str,
    email: str,
    password: str,
) -> User:
    email = email.lower().strip()

    if get_user_by_email(db, email):
        raise ValueError("Email already registered")

    student_role = db.scalar(
        select(Role).where(Role.name == "student")
    )

    if not student_role:
        raise ValueError("Student role is not configured")

    user = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=hash_password(password),
    )

    db.add(user)
    db.flush()

    db.add(
        UserRole(
            user_id=user.id,
            role_id=student_role.id,
        )
    )

    db.commit()
    db.refresh(user)

    return user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    user = get_user_by_email(
        db,
        email.lower().strip(),
    )

    if not user:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    if not user.is_active:
        return None

    return user