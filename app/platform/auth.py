from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.core.config import settings
from app.db.database import get_db
from app.models import Role, User, UserRole
from .domain import PlatformError
from .models import TeacherProfile

AUDIENCE = "wemath-teachers"
bearer = HTTPBearer(auto_error=False)


def is_teacher(db, user):
    return bool(db.scalar(select(Role.id).join(UserRole).where(UserRole.user_id == user.id, Role.name == "teacher")))


def profile_payload(db, user):
    profile = db.get(TeacherProfile, user.id)
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "school": profile.school if profile else None, "role": "teacher"}


def issue_session(db, user):
    profile = db.get(TeacherProfile, user.id)
    if not profile:
        profile = TeacherProfile(user_id=user.id, session_version=0)
        db.add(profile)
        db.commit()
    token = jwt.encode({"sub": str(user.id), "aud": AUDIENCE, "role": "teacher", "ver": profile.session_version, "user_ver": user.token_version,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)},
                       settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "user": profile_payload(db, user)}


def register(db, data):
    if db.scalar(select(User.id).where(func.lower(User.username) == data.username)):
        raise PlatformError("اسم المستخدم مستخدم بالفعل", 409)
    role = db.scalar(select(Role).where(Role.name == "teacher"))
    if not role:
        raise PlatformError("يلزم تشغيل تحديث قاعدة البيانات أولًا", 503)
    user = User(full_name=data.full_name, username=data.username, email=None, password_hash=hash_password(data.password), token_version=0)
    try:
        db.add(user)
        db.flush()
        db.add_all([UserRole(user_id=user.id, role_id=role.id), TeacherProfile(user_id=user.id, school=data.school or None)])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PlatformError("اسم المستخدم مستخدم بالفعل", 409) from None
    return issue_session(db, user)


def login(db, data):
    user = db.scalar(select(User).where(func.lower(User.username) == data.username))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash) or not is_teacher(db, user):
        raise PlatformError("بيانات دخول المعلّم غير صحيحة", 401)
    return issue_session(db, user)


def teacher_required(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise PlatformError("سجّل دخول المعلّم أولًا", 401)
    try:
        claims = jwt.decode(credentials.credentials, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM],
                            audience=AUDIENCE, options={"require": ["sub", "exp", "aud", "ver", "user_ver", "role"]})
        user = db.get(User, int(claims["sub"]))
        profile = db.get(TeacherProfile, user.id) if user else None
        if not user or not profile or not user.is_active or claims["role"] != "teacher" or claims["ver"] != profile.session_version or claims["user_ver"] != user.token_version or not is_teacher(db, user):
            raise ValueError()
    except (InvalidTokenError, ValueError, TypeError):
        raise PlatformError("انتهت جلسة المعلّم؛ سجّل الدخول مجددًا", 401) from None
    return user


def logout(db, user):
    # A multi-role user's parent/student session must survive teacher logout.
    db.execute(update(TeacherProfile).where(TeacherProfile.user_id == user.id).values(session_version=TeacherProfile.session_version + 1))
    db.commit()
    return {"success": True}
