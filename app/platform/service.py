from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select

from app.models.curriculum import CurriculumBook, CurriculumLesson, CurriculumUnit
from .domain import PlatformError, SECTIONS
from .models import PlatformEntry, TeacherDocument


def entry_payload(row):
    return {key: getattr(row, key) for key in ("id", "section", "category", "title", "summary", "body", "source_url", "event_date", "archived", "is_demo", "activity", "details", "published_at")}


def list_entries(db, section, category=None, archived=False, q="", offset=0, limit=6, month=None, teacher=False):
    if section not in SECTIONS or (section == "teacher_resources" and not teacher):
        raise PlatformError("القسم غير متاح", 404)
    if category and category not in SECTIONS[section]:
        raise PlatformError("التصنيف غير متاح", 404)
    filters = [PlatformEntry.section == section, PlatformEntry.published.is_(True)]
    if section == "competitions" and not month:
        today = date.today()
        filters.append(or_(PlatformEntry.archived.is_(True), PlatformEntry.event_date < today) if archived else (PlatformEntry.archived.is_(False) & or_(PlatformEntry.event_date.is_(None), PlatformEntry.event_date >= today)))
    elif section != "competitions":
        filters.append(PlatformEntry.archived == archived)
    if category:
        filters.append(PlatformEntry.category == category)
    if q.strip():
        filters.append(or_(
            PlatformEntry.title.icontains(q.strip(), autoescape=True),
            PlatformEntry.summary.icontains(q.strip(), autoescape=True),
            PlatformEntry.body.icontains(q.strip(), autoescape=True),
        ))
    if month:
        year, number = map(int, month.split("-"))
        first = date(year, number, 1)
        after = date(year + (number == 12), number % 12 + 1, 1)
        filters.extend([PlatformEntry.event_date >= first, PlatformEntry.event_date < after])
    total = db.scalar(select(func.count()).select_from(PlatformEntry).where(*filters))
    rows = db.scalars(select(PlatformEntry).where(*filters).order_by(PlatformEntry.event_date.desc().nulls_last(), PlatformEntry.id).offset(offset).limit(limit)).all()
    return {"items": [entry_payload(row) for row in rows], "total": total, "offset": offset, "limit": limit}


def get_entry(db, entry_id):
    row = db.get(PlatformEntry, entry_id)
    if not row or not row.published or row.section == "teacher_resources" or row.section not in SECTIONS:
        raise PlatformError("المحتوى غير متاح", 404)
    return entry_payload(row)


def get_teacher_entry(db, entry_id):
    row = db.get(PlatformEntry, entry_id)
    if not row or not row.published or row.section != "teacher_resources":
        raise PlatformError("المحتوى غير متاح", 404)
    return entry_payload(row)


def save_competition(db, data, publisher_id):
    row = db.get(PlatformEntry, data.id)
    created = row is None
    if row is None:
        row = PlatformEntry(id=data.id, section="competitions", is_demo=False)
        db.add(row)
    elif row.section != "competitions":
        raise PlatformError("المعرّف مستخدم في قسم آخر", 409)
    row.category = data.category
    row.title = data.title
    row.summary = data.summary
    row.body = data.body
    row.source_url = data.source_url
    row.event_date = data.event_date
    row.archived = data.archived
    row.published = data.published
    row.is_demo = False
    row.activity = None
    row.details = {
        "organizer": data.organizer, "audience": data.audience, "location": data.location,
        "registration_start": data.registration_start.isoformat() if data.registration_start else None,
        "registration_end": data.registration_end.isoformat() if data.registration_end else None,
        "examples": data.examples, "attachments": data.attachments, "results": data.results, "publisher_id": publisher_id,
    }
    if data.published and row.published_at is None:
        row.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    notify = created and row.published and not row.archived and row.event_date >= date.today()
    return entry_payload(row), notify


def document_payload(row):
    return {key: getattr(row, key) for key in ("id", "kind", "title", "grade", "book_id", "lesson_id", "content", "archived", "version", "created_at", "updated_at")}


def own_document(db, teacher_id, document_id, lock=False):
    statement = select(TeacherDocument).where(TeacherDocument.id == document_id, TeacherDocument.teacher_id == teacher_id)
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if not row:
        raise PlatformError("الملف غير موجود", 404)
    return row


def list_documents(db, teacher_id, kind, archived, offset, limit):
    filters = [TeacherDocument.teacher_id == teacher_id, TeacherDocument.kind == kind, TeacherDocument.archived == archived]
    total = db.scalar(select(func.count()).select_from(TeacherDocument).where(*filters))
    rows = db.scalars(select(TeacherDocument).where(*filters).order_by(TeacherDocument.updated_at.desc(), TeacherDocument.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [document_payload(row) for row in rows], "total": total}


def validate_curriculum(db, data):
    if data.book_id:
        book = db.get(CurriculumBook, data.book_id)
        if not book or book.grade != data.grade:
            raise PlatformError("الكتاب لا يتبع الصف المحدد", 422)
    if data.lesson_id:
        lesson_book = db.scalar(select(CurriculumUnit.book_id).join(CurriculumLesson).where(CurriculumLesson.id == data.lesson_id))
        if lesson_book != data.book_id:
            raise PlatformError("الدرس لا يتبع الكتاب المحدد", 422)


def save_document(db, teacher_id, data, document_id=None):
    validate_curriculum(db, data)
    if document_id is None:
        row = TeacherDocument(teacher_id=teacher_id, version=1, archived=False)
        db.add(row)
    else:
        row = own_document(db, teacher_id, document_id, lock=True)
        if row.version != data.version:
            raise PlatformError("تم تعديل الملف في جلسة أخرى؛ أعد فتحه قبل الحفظ", 409)
        if row.archived:
            raise PlatformError("استعد الملف من الأرشيف قبل تعديله", 409)
        if row.kind != data.kind:
            raise PlatformError("لا يمكن تغيير نوع الملف", 422)
        row.version += 1
    for key in ("kind", "title", "grade", "book_id", "lesson_id", "content"):
        setattr(row, key, getattr(data, key))
    db.commit()
    db.refresh(row)
    return document_payload(row)


def archive_document(db, teacher_id, document_id, data):
    row = own_document(db, teacher_id, document_id, lock=True)
    if row.version != data.version:
        raise PlatformError("تم تعديل الملف؛ أعد فتح القائمة", 409)
    row.archived, row.version = data.archived, row.version + 1
    db.commit()
    db.refresh(row)
    return document_payload(row)
