from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_roles
from app.auth.password import hash_password
from app.db.database import get_db
from app.models import Role, User, UserRole
from . import service
from .catalog import MODULES, blank_template
from .models import Audit, Content, Membership, Workspace, StaffProfile
from app.platform.models import PlatformEntry
from .schemas import Payload, ContentWrite, StaffCreate, StaffUpdate, Transition, WorkspaceWrite

router = APIRouter(prefix="/api/cms", tags=["Content management"])
admin = require_roles("admin")


def staff(user=Depends(get_current_user), db=Depends(get_db)):
    service.require_staff(db, user)
    return user


def workspace_payload(db, row):
    return {"id": row.id, "name": row.name, "team_type": row.team_type, "modules": row.modules, "can_publish": row.can_publish,
            "active": row.active, "version": row.version,
            "member_ids": list(db.scalars(select(Membership.user_id).where(Membership.workspace_id == row.id)))}


@router.get("/me")
def me(user=Depends(staff), db: Session = Depends(get_db)):
    return {"id": user.id, "name": user.full_name, "is_admin": service.is_admin(db, user),
            "workspaces": [workspace_payload(db, row) for row in service.accessible_workspaces(db, user)], "modules": MODULES}


@router.get("/templates/{module}")
def template(module: str, workspace_id: int, user=Depends(staff), db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, "القالب غير موجود")
    service.workspace_access(db, user, workspace_id, module)
    return blank_template(module)


@router.get("/staff")
def list_staff(include_teachers: bool = False, team_type: Literal["students", "teachers", "other"] | None = None, q: str = Query("", max_length=100), offset: int = Query(0, ge=0), user=Depends(admin), db: Session = Depends(get_db)):
    filters = [Role.name.in_(["content_editor", "teacher"] if include_teachers else ["content_editor"]), or_(User.full_name.icontains(q, autoescape=True), User.username.icontains(q, autoescape=True))]
    if team_type:
        filters.append(User.id.in_(select(StaffProfile.user_id).where(StaffProfile.team_type == team_type)) if team_type != "other" else ~User.id.in_(select(StaffProfile.user_id).where(StaffProfile.team_type != "other")))
    statement = select(User).join(UserRole).join(Role).where(*filters).distinct()
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(User.id).offset(offset).limit(50)).all()
    return {"items": [{"id": row.id, "name": row.full_name, "username": row.username, "active": row.is_active, "email": row.email, "team_type": (db.get(StaffProfile, row.id).team_type if db.get(StaffProfile, row.id) else "other"), "invitation_status": "disabled"} for row in rows], "total": total}


@router.post("/staff", status_code=201)
def create_staff(data: StaffCreate, user=Depends(admin), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == data.username)):
        raise HTTPException(409, "اسم المستخدم موجود مسبقًا")
    role = db.scalar(select(Role).where(Role.name == "content_editor"))
    if role is None:
        role = Role(name="content_editor", description="Content entry team")
        db.add(role)
        db.flush()
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "الإيميل مستخدم مسبقًا")
    row = User(username=data.username, full_name=data.full_name, email=email, password_hash=hash_password(data.password))
    db.add(row)
    try:
        db.flush()
        db.add(UserRole(user_id=row.id, role_id=role.id))
        db.add(StaffProfile(user_id=row.id, team_type=data.team_type, invitation_status="disabled"))
        if data.create_workspace:
            workspace = Workspace(name=f"فريق {data.full_name}"[:150], team_type=data.team_type, modules=data.modules, can_publish=False, active=True)
            db.add(workspace)
            db.flush()
            db.add(Membership(workspace_id=workspace.id, user_id=row.id))
            service.audit(db, user, "workspace.save", workspace.id)
        service.audit(db, user, "staff.create", row.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "اسم المستخدم أو الإيميل موجود مسبقًا") from None
    return {"id": row.id, "name": row.full_name, "username": row.username, "active": row.is_active, "email": row.email, "team_type": data.team_type, "invitation_status": "disabled"}


@router.patch("/staff/{staff_id}")
def update_staff(staff_id: int, data: StaffUpdate, user=Depends(admin), db: Session = Depends(get_db)):
    row = db.get(User, staff_id)
    if not row or "content_editor" not in service.get_user_roles(db, staff_id) or service.is_admin(db, row):
        raise HTTPException(404, "حساب إدخال البيانات غير موجود")
    row.is_active = data.is_active
    row.token_version += 1
    if data.password:
        row.password_hash = hash_password(data.password)
    service.audit(db, user, "staff.update", staff_id)
    db.commit()
    return {"ok": True}


def save_workspace(db, user, data, row):
    service.check_version(row, data.version) if row.id else None
    for member in set(data.member_ids):
        person = db.get(User, member)
        if not person or not {"content_editor", "teacher"}.intersection(service.get_user_roles(db, member)):
            raise HTTPException(422, "اختر حسابات إدخال بيانات أو معلمين موجودة")
    if row.id:
        row.version += 1
        db.execute(delete(Membership).where(Membership.workspace_id == row.id))
    row.team_type = data.team_type
    row.name, row.modules, row.can_publish, row.active = data.name, data.modules, data.can_publish, data.active
    db.add(row)
    db.flush()
    for member in set(data.member_ids):
        db.add(Membership(workspace_id=row.id, user_id=member))
    service.audit(db, user, "workspace.save", row.id)
    db.commit()
    return workspace_payload(db, row)


@router.post("/workspaces", status_code=201)
def create_workspace(data: WorkspaceWrite, user=Depends(admin), db: Session = Depends(get_db)):
    return save_workspace(db, user, data, Workspace(version=1))


@router.put("/workspaces/{workspace_id}")
def edit_workspace(workspace_id: int, data: WorkspaceWrite, user=Depends(admin), db: Session = Depends(get_db)):
    row = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "اللوحة غير موجودة")
    return save_workspace(db, user, data, row)


@router.get("/content")
def list_content(team_type: Literal["students", "teachers", "other"] | None = None, workspace_id: int | None = None, module: str | None = None, status: str | None = None,
                 q: str = Query("", max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                 user=Depends(staff), db: Session = Depends(get_db)):
    workspaces = service.accessible_workspaces(db, user)
    if team_type:
        workspaces = [w for w in workspaces if w.team_type == team_type]
    if workspace_id is not None:
        service.workspace_access(db, user, workspace_id, module)
        workspaces = [row for row in workspaces if row.id == workspace_id]
    allowed = [(Content.workspace_id == row.id) if service.is_admin(db, user) else ((Content.workspace_id == row.id) & Content.module.in_(row.modules)) for row in workspaces]
    filters = [or_(*allowed) if allowed else Content.id == -1]
    if module:
        filters.append(Content.module == module)
    if status:
        filters.append(Content.status == status)
    if q:
        filters.append(Content.title.icontains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(Content).where(*filters))
    counts = dict(db.execute(select(Content.status, func.count()).where(*filters).group_by(Content.status)).all())
    rows = db.scalars(select(Content).where(*filters).order_by(Content.updated_at.desc(), Content.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [service.serialize(row) for row in rows], "total": total, "counts": counts}


def new_content(db, user, data):
    workspace = service.workspace_access(db, user, data.workspace_id, data.module)
    if data.module not in workspace.modules:
        raise HTTPException(422, "أضيفي القسم إلى اللوحة قبل إدخال محتواه")
    from .media import validate_media
    validate_media(db, data.workspace_id, data.module, data.payload.model_dump())
    row = Content(workspace_id=data.workspace_id, module=data.module, title=data.title,
                  payload=data.payload.model_dump(mode="json"), author_id=user.id, status="draft", version=1)
    db.add(row)
    db.flush()
    service.audit(db, user, "content.create", row.id)
    return row


@router.post("/content", status_code=201)
def create_content(data: ContentWrite, user=Depends(staff), db: Session = Depends(get_db)):
    row = new_content(db, user, data)
    db.commit()
    return service.serialize(row)


class ImportBatch(BaseModel):
    items: list[ContentWrite] = Field(min_length=1, max_length=100)


@router.post("/import", status_code=201)
def import_batch(data: ImportBatch, user=Depends(staff), db: Session = Depends(get_db)):
    # Validate every scope first. All rows and their audits commit atomically.
    for item in data.items:
        service.workspace_access(db, user, item.workspace_id, item.module)
    rows = [new_content(db, user, item) for item in data.items]
    db.commit()
    return {"created": len(rows), "ids": [row.id for row in rows]}


@router.get("/content/{content_id}")
def get_content(content_id: int, user=Depends(staff), db: Session = Depends(get_db)):
    return service.serialize(service.content_access(db, user, content_id))


@router.put("/content/{content_id}")
def edit_content(content_id: int, data: ContentWrite, user=Depends(staff), db: Session = Depends(get_db)):
    row = service.content_access(db, user, content_id, lock=True)
    service.check_version(row, data.version)
    if (row.workspace_id, row.module) != (data.workspace_id, data.module):
        raise HTTPException(422, "لا يمكن نقل المادة إلى لوحة أو قسم آخر")
    if row.status == "archived":
        raise HTTPException(409, "استعد المادة كمسودة أولًا")
    from .media import validate_media
    validate_media(db, data.workspace_id, data.module, data.payload.model_dump())
    row.title, row.payload = data.title, data.payload.model_dump(mode="json")
    # Published snapshot remains live until explicitly republished or withdrawn.
    row.status, row.version = "draft", row.version + 1
    service.audit(db, user, "content.edit", row.id)
    db.commit()
    return service.serialize(row)


@router.post("/content/{content_id}/status")
def transition(content_id: int, data: Transition, user=Depends(staff), db: Session = Depends(get_db)):
    row = service.content_access(db, user, content_id, lock=True)
    service.check_version(row, data.version)
    if data.status in {"published", "archived"}:
        service.workspace_access(db, user, row.workspace_id, row.module, publish=True)
    if data.status == "published":
        service.publish(db, row)
    elif data.status == "archived":
        service.unpublish(db, row)
    row.status, row.version = data.status, row.version + 1
    service.audit(db, user, f"content.{data.status}", row.id)
    db.commit()
    return service.serialize(row)


@router.get("/audit")
def audit_log(offset: int = Query(0, ge=0), user=Depends(admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Audit, User.full_name).join(User, User.id == Audit.actor_id).order_by(Audit.id.desc()).offset(offset).limit(50)).all()
    return {"items": [{"id": row.id, "actor": name, "action": row.action, "target": row.target, "created_at": row.created_at} for row, name in rows],
            "total": db.scalar(select(func.count()).select_from(Audit))}


@router.get("/legacy")
def legacy(q: str = Query("", max_length=100), offset: int = Query(0, ge=0), user=Depends(admin), db: Session = Depends(get_db)):
    filters = [PlatformEntry.section.in_(MODULES), ~PlatformEntry.id.like("cms-%"),
               ~PlatformEntry.id.in_(select(Content.source_entry_id).where(Content.source_entry_id.is_not(None)))]
    if q:
        filters.append(PlatformEntry.title.icontains(q, autoescape=True))
    rows = db.scalars(select(PlatformEntry).where(*filters).order_by(PlatformEntry.id).offset(offset).limit(25)).all()
    return {"items": [{"id": row.id, "title": row.title, "module": row.section, "published": row.published} for row in rows],
            "total": db.scalar(select(func.count()).select_from(PlatformEntry).where(*filters))}


class Adopt(BaseModel):
    entry_id: str = Field(max_length=80)
    workspace_id: int


@router.post("/legacy/adopt", status_code=201)
def adopt(data: Adopt, user=Depends(admin), db: Session = Depends(get_db)):
    entry = db.scalar(select(PlatformEntry).where(PlatformEntry.id == data.entry_id).with_for_update())
    if not entry or entry.section not in MODULES or entry.id.startswith("cms-"):
        raise HTTPException(404, "المادة غير موجودة")
    if db.scalar(select(Content.id).where(Content.source_entry_id == entry.id)):
        raise HTTPException(409, "هذه المادة موجودة في لوحة الإدارة بالفعل")
    service.workspace_access(db, user, data.workspace_id, entry.section)
    details = entry.details or {}
    try:
        payload = Payload(questions=(entry.activity or {}).get("questions", []), summary=entry.summary, body=entry.body, source_url=entry.source_url or "", category=entry.category,
                          event_date=entry.event_date, **{key: details[key] for key in ("organizer", "audience", "location", "registration_start", "registration_end", "attachments", "results", "examples") if details.get(key) is not None})
    except ValueError:
        raise HTTPException(422, "بيانات المادة السابقة لا تطابق النموذج؛ راجعي روابطها وأسئلتها قبل نقلها") from None
    from .media import validate_media
    validate_media(db, data.workspace_id, entry.section, payload.model_dump())
    row = Content(workspace_id=data.workspace_id, module=entry.section, title=entry.title,
                  payload=payload.model_dump(mode="json"), author_id=user.id, source_entry_id=entry.id,
                  status="published" if entry.published else "draft", version=1)
    db.add(row)
    db.flush()
    service.audit(db, user, "content.adopt", row.id)
    db.commit()
    return service.serialize(row)
