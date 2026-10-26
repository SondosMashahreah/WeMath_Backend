from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.password import hash_password, verify_password
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.models.learning import StudentProfile


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower().strip()))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_roles(db: Session, user_id: int) -> list[str]:
    return list(db.scalars(select(Role.name).join(UserRole).where(UserRole.user_id == user_id)))


def create_account(db: Session, data) -> User:
    """Build account and profile atomically; the caller owns the transaction."""
    if db.scalar(select(User.id).where(User.username == data.username)):
        raise ValueError("اسم المستخدم مستخدم بالفعل")
    email = str(data.email).lower().strip() if data.email else None
    if email and get_user_by_email(db, email):
        raise ValueError("البريد الإلكتروني مستخدم بالفعل")
    role = db.scalar(select(Role).where(Role.name == data.role))
    if role is None:
        raise ValueError("يرجى تهيئة أدوار المنصة أولًا")
    user = User(username=data.username, full_name=data.full_name.strip(), email=email, password_hash=hash_password(data.password))
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if data.role == "student":
        db.add(StudentProfile(user_id=user.id, **data.model_dump(include={"grade", "identity_number", "school", "phone", "directorate"})))
    db.flush()
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def user_payload(db: Session, user: User):
    profile = db.get(StudentProfile, user.id)
    return {
        "id": user.id, "username": user.username, "full_name": user.full_name,
        "email": user.email, "is_active": user.is_active, "roles": get_user_roles(db, user.id),
        **{name: getattr(profile, name) if profile else None for name in ["grade", "school", "phone", "directorate", "identity_number"]},
    }
