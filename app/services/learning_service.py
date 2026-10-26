from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domain.learning import DomainError
from app.models.curriculum import CurriculumBook, CurriculumLesson, CurriculumUnit
from app.models.learning import LessonProgress, StudentProfile
from app.models.user import User
from app.repositories.lesson_resources import for_lesson


def student_lesson(db: Session, student_id: int, lesson_id: str):
    profile = db.get(StudentProfile, student_id)
    lesson = db.get(CurriculumLesson, lesson_id)
    if not lesson:
        raise DomainError("الدرس غير موجود", 404)
    if profile is None or profile.grade is None:
        raise DomainError("أكمل صفك الدراسي أولًا", 409)
    if lesson.unit.book.grade != profile.grade:
        raise DomainError("هذا الدرس ليس ضمن صفك الدراسي", 403)
    return lesson


def lesson_resources(db: Session, student_id: int, lesson_id: str):
    lesson = student_lesson(db, student_id, lesson_id)
    book = lesson.unit.book
    return {"id": lesson.id, "title": lesson.title, "unit_title": lesson.unit.title,
            "book": {"id": book.id, "title": book.title, "source_url": book.source_url, "period_label": book.period_label, "classification_label": book.classification_label},
            "resources": for_lesson(lesson_id)}


def record_progress(db: Session, student_id: int, lesson_id: str, activity: str):
    db.scalar(select(User).where(User.id == student_id).with_for_update())
    student_lesson(db, student_id, lesson_id)
    progress = db.get(LessonProgress, (student_id, lesson_id))
    now = datetime.now(timezone.utc)
    if progress is None:
        progress = LessonProgress(student_id=student_id, lesson_id=lesson_id, status="started")
        db.add(progress)
    progress.updated_at, progress.last_activity = now, activity
    if activity == "completed":
        progress.status = "completed"
        if progress.completed_at is None:
            progress.completed_at = now
    db.flush()
    return progress_payload(progress)


def progress_payload(progress):
    return {"lesson_id": progress.lesson_id, "status": progress.status, "last_activity": progress.last_activity,
            "started_at": progress.started_at, "updated_at": progress.updated_at, "completed_at": progress.completed_at}


def progress_summary(db: Session, student_id: int):
    rows = db.execute(select(LessonProgress, CurriculumLesson, CurriculumUnit, CurriculumBook)
        .join(CurriculumLesson, CurriculumLesson.id == LessonProgress.lesson_id)
        .join(CurriculumUnit, CurriculumUnit.id == CurriculumLesson.unit_id)
        .join(CurriculumBook, CurriculumBook.id == CurriculumUnit.book_id)
        .where(LessonProgress.student_id == student_id).order_by(LessonProgress.updated_at.desc())).all()
    items = [{**progress_payload(p), "lesson_title": lesson.title, "unit_title": unit.title,
              "unit_id": unit.id, "book_id": book.id, "book_title": book.title, "grade": book.grade,
              "period_label": book.period_label} for p, lesson, unit, book in rows]
    return {"visited": len(items), "completed": sum(p["status"] == "completed" for p in items),
            "last_activity_at": items[0]["updated_at"] if items else None, "lessons": items}
