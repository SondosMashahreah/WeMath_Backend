from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.curriculum import book_payload
from app.models.curriculum import CurriculumBook, CurriculumLesson, CurriculumUnit
from .domain import PlatformError, SECTIONS
from .models import PlatformEntry, TeacherDocument


def entry_payload(row):
    return {key: getattr(row, key) for key in ("id", "section", "category", "title", "summary", "body", "source_url", "event_date", "archived", "is_demo", "activity")}


def list_entries(db, section, category=None, archived=False, q="", offset=0, limit=6, month=None, teacher=False):
    if section not in SECTIONS or (section == "teacher_resources" and not teacher):
        raise PlatformError("القسم غير متاح", 404)
    if category and category not in SECTIONS[section]:
        raise PlatformError("التصنيف غير متاح", 404)
    filters = [PlatformEntry.section == section, PlatformEntry.published.is_(True), PlatformEntry.archived == archived]
    if category:
        filters.append(PlatformEntry.category == category)
    if q.strip():
        filters.append(or_(PlatformEntry.title.icontains(q.strip(), autoescape=True), PlatformEntry.summary.icontains(q.strip(), autoescape=True)))
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
    if not row or not row.published or row.section == "teacher_resources":
        raise PlatformError("المحتوى غير متاح", 404)
    return entry_payload(row)


def guest_catalog(db):
    books = db.scalars(select(CurriculumBook).options(selectinload(CurriculumBook.units).selectinload(CurriculumUnit.lessons)).order_by(CurriculumBook.grade, CurriculumBook.id)).all()
    result = []
    for book in books:
        payload = book_payload(book, include_units=False)
        sample = next(((unit, lesson) for unit in book.units for lesson in unit.lessons), None)
        payload["sample"] = {"unit": sample[0].title, "lesson": sample[1].title, "lesson_id": sample[1].id} if sample else None
        result.append(payload)
    return {"books": result, "preview": True}


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
