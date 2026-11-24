from datetime import date, datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CurriculumLesson, User
from app.platform.models import PlatformEntry
from app.platform.schemas import AssessmentContent
from app.services.auth_service import get_user_roles
from .catalog import MODULES, RESOURCE_LABELS
from .models import Audit, Content, Membership, PublishedResource, Workspace


def is_admin(db, user):
    return "admin" in get_user_roles(db, user.id)


def require_staff(db, user):
    if not set(get_user_roles(db, user.id)) & {"admin", "content_editor"}:
        raise HTTPException(403, "هذه اللوحة مخصصة لفريق إدارة المحتوى")


def accessible_workspaces(db, user):
    if is_admin(db, user):
        return list(db.scalars(select(Workspace).order_by(Workspace.id)))
    return list(db.scalars(select(Workspace).join(Membership).where(Membership.user_id == user.id, Workspace.active.is_(True)).order_by(Workspace.id)))


def workspace_access(db, user, workspace_id, module=None, publish=False):
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(404, "اللوحة غير موجودة")
    if not is_admin(db, user):
        if not workspace.active or db.get(Membership, (workspace_id, user.id)) is None:
            raise HTTPException(403, "ليس لديك وصول إلى هذه اللوحة")
        if module and module not in workspace.modules:
            raise HTTPException(403, "القسم غير مسموح في هذه اللوحة")
        if publish and not workspace.can_publish:
            raise HTTPException(403, "النشر والأرشفة يحتاجان موافقة الأدمن")
    return workspace


def content_access(db, user, content_id, lock=False):
    statement = select(Content).where(Content.id == content_id)
    row = db.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise HTTPException(404, "المادة غير موجودة")
    workspace_access(db, user, row.workspace_id, row.module)
    return row


def check_version(row, version):
    if row.version != version:
        raise HTTPException(409, "عدّل شخص آخر هذا السجل؛ احتفظ بنسختك وأعد فتح السجل قبل المحاولة")


def audit(db, user, action, target):
    db.add(Audit(actor_id=user.id, action=action, target=str(target)))


def serialize(row):
    return {key: getattr(row, key) for key in ("id", "workspace_id", "module", "title", "payload", "status", "version", "author_id", "updated_at")}


def validate_publish(db, row):
    data = dict(row.payload)
    if data.get("questions"):
        try:
            data["questions"] = AssessmentContent.model_validate({"questions": data["questions"], "instructions": ""}).model_dump()["questions"]
        except ValueError:
            raise HTTPException(422, "أكمل نص الأسئلة والخيارات والإجابات الصحيحة") from None
    if row.module in RESOURCE_LABELS:
        if not data.get("lesson_id") or not db.get(CurriculumLesson, data["lesson_id"]):
            raise HTTPException(422, "اختر درسًا موجودًا قبل النشر")
        if not (row.module == "quiz" and data.get("questions")) and not data.get("source_url") and not data.get("body"):
            raise HTTPException(422, "أضف نص المورد أو رابطه قبل النشر")
    else:
        if data.get("category") not in MODULES[row.module]["categories"]:
            raise HTTPException(422, "اختر تصنيفًا صحيحًا")
        if not data.get("body") or not data.get("summary"):
            raise HTTPException(422, "أكمل الوصف المختصر والتفاصيل قبل النشر")
        if row.module in ("competitions", "workshops") and not data.get("event_date"):
            raise HTTPException(422, "موعد الورشة أو المسابقة مطلوب للنشر")
    row.payload = data


def publish(db, row):
    validate_publish(db, row)
    data = row.payload
    if row.module in RESOURCE_LABELS:
        resource = db.get(PublishedResource, row.id)
        if resource is None:
            resource = PublishedResource(content_id=row.id)
            db.add(resource)
        resource.lesson_id, resource.resource_type = data["lesson_id"], row.module
        resource.payload = {"content_id": row.id, "title": row.title, "text": data["body"], "url": data["source_url"] or None,
                            "attachments": data["attachments"], "questions": data["questions"]}
    else:
        key = row.source_entry_id or f"cms-{row.id}"
        entry = db.get(PlatformEntry, key)
        if entry is None:
            entry = PlatformEntry(id=key, section=row.module)
            db.add(entry)
        entry.title, entry.summary, entry.body = row.title, data["summary"], data["body"]
        entry.category, entry.source_url = data["category"], data["source_url"] or None
        entry.event_date = date.fromisoformat(data["event_date"]) if data["event_date"] else None
        entry.archived, entry.published, entry.is_demo = False, True, False
        entry.activity = AssessmentContent.model_validate({"questions": data["questions"], "instructions": ""}).model_dump() if data.get("questions") else None
        entry.details = {key: data[key] for key in ("organizer", "audience", "location", "registration_start", "registration_end", "attachments", "results", "examples")}
        entry.published_at = datetime.now(timezone.utc)


def unpublish(db, row):
    resource = db.get(PublishedResource, row.id)
    if resource:
        db.delete(resource)
    entry = db.get(PlatformEntry, row.source_entry_id or f"cms-{row.id}")
    if entry:
        entry.published = False


def live_resources(db, lesson_id, defaults):
    rows = db.scalars(select(PublishedResource).where(PublishedResource.lesson_id == lesson_id).order_by(PublishedResource.content_id)).all()
    grouped = {}
    for row in rows:
        grouped.setdefault(row.resource_type, []).append(row.payload)
    return [{**resource, "demo": False, "text": "", "url": None, "items": grouped[resource["id"]]} if resource["id"] in grouped else resource for resource in defaults]
