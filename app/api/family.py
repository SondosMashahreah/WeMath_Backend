from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.dependencies import require_roles
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import ChildCreateRequest, ChildUpdateRequest, LoginRequest, PasswordResetRequest
from app.services import family_service as family
from app.services.auth_service import user_payload
from app.services.learning_service import progress_summary, results_summary, lesson_resources

router = APIRouter(prefix="/api/parents", tags=["Family"])
parent_user = require_roles("parent")


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "تعذّر الحفظ؛ قد يكون الحساب مرتبطًا أو اسم المستخدم مستخدمًا") from None


@router.get("/children")
def children(parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    return {"limit": 5, "children": family.list_children(db, parent.id)}


@router.post("/children", status_code=201)
def create_child(data: ChildCreateRequest, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    try:
        child = family.add_child(db, parent.id, data)
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "الحساب موجود بالفعل أو وصلت إلى الحد المسموح") from None
    return user_payload(db, child)


@router.post("/children/link", status_code=201)
def link_child(data: LoginRequest, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    try:
        child = family.link_child(db, parent.id, data)
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "الحساب مرتبط بالفعل أو وصلت إلى الحد المسموح") from None
    return user_payload(db, child)


@router.patch("/children/{child_id}")
def edit_child(child_id: int, data: ChildUpdateRequest, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    child = family.update_child(db, parent.id, child_id, data)
    commit(db)
    return user_payload(db, child)


@router.put("/children/{child_id}/password", status_code=204)
def reset_password(child_id: int, data: PasswordResetRequest, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    family.reset_child_password(db, parent.id, child_id, data.password)
    commit(db)


@router.get("/children/{child_id}/progress")
def child_progress(child_id: int, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    family.owned_child(db, parent.id, child_id)
    return progress_summary(db, child_id)


@router.get("/children/{child_id}/results")
def child_results(child_id: int, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    family.owned_child(db, parent.id, child_id)
    return results_summary(db, child_id)


@router.get("/children/{child_id}/lessons/{lesson_id}")
def preview_lesson(child_id: int, lesson_id: str, parent: User = Depends(parent_user), db: Session = Depends(get_db)):
    family.owned_child(db, parent.id, child_id)
    return lesson_resources(db, child_id, lesson_id)
