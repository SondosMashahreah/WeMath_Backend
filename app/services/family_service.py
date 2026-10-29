from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.password import hash_password
from app.domain.learning import DomainError, available_slot
from app.models.learning import ParentChild, StudentProfile
from app.models.user import User
from app.services.auth_service import authenticate_user, create_account, get_user_roles, user_payload, validate_student_track


def reserve_slot(db: Session, parent_id: int):
    # Serialize sibling writes across workers. SQL constraints also enforce the cap.
    db.scalar(select(User).where(User.id == parent_id).with_for_update())
    return available_slot(set(db.scalars(select(ParentChild.slot).where(ParentChild.parent_id == parent_id))))


def owned_child(db: Session, parent_id: int, child_id: int, lock=False):
    statement = select(User).join(ParentChild, ParentChild.child_id == User.id).where(ParentChild.parent_id == parent_id, User.id == child_id)
    if lock:
        statement = statement.with_for_update()
    user = db.scalar(statement)
    if user is None:
        raise DomainError("الطفل غير موجود في حسابك", 404)
    return user


def list_children(db: Session, parent_id: int):
    children = db.scalars(select(User).join(ParentChild, ParentChild.child_id == User.id).where(ParentChild.parent_id == parent_id).order_by(ParentChild.slot))
    return [user_payload(db, child) for child in children]


def add_child(db: Session, parent_id: int, data):
    slot = reserve_slot(db, parent_id)
    try:
        child = create_account(db, data)
    except ValueError as exc:
        raise DomainError(str(exc), 409) from None
    db.add(ParentChild(parent_id=parent_id, child_id=child.id, slot=slot))
    db.flush()
    return child


def link_child(db: Session, parent_id: int, data):
    slot = reserve_slot(db, parent_id)
    child = authenticate_user(db, data.username, data.password)
    if not child or "student" not in get_user_roles(db, child.id):
        raise DomainError("تعذّر ربط الحساب؛ تحقق من بيانات دخول الطالب", 400)
    db.scalar(select(User).where(User.id == child.id).with_for_update())
    if db.get(ParentChild, child.id):
        raise DomainError("الحساب مرتبط بولي أمر بالفعل", 409)
    db.add(ParentChild(parent_id=parent_id, child_id=child.id, slot=slot))
    db.flush()
    return child


def update_child(db: Session, parent_id: int, child_id: int, data):
    child = owned_child(db, parent_id, child_id, lock=True)
    profile = db.get(StudentProfile, child_id)
    if profile is None:
        profile = StudentProfile(user_id=child_id)
        db.add(profile)
    track = validate_student_track(db, data.grade, data.track)
    if child.is_active != data.is_active or profile.grade != data.grade or profile.track != track:
        child.token_version += 1
    child.full_name, child.is_active = data.full_name, data.is_active
    values = data.model_dump(exclude={"full_name", "is_active"})
    values["track"] = track
    for key, value in values.items():
        setattr(profile, key, value)
    return child


def reset_child_password(db: Session, parent_id: int, child_id: int, password: str):
    child = owned_child(db, parent_id, child_id, lock=True)
    child.password_hash = hash_password(password)
    child.token_version += 1
