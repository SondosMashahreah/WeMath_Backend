from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.models.curriculum import CurriculumBook, CurriculumUnit


router = APIRouter(prefix="/api/curriculum", tags=["Curriculum"])


def lesson_payload(lesson):
    return {
        "id": lesson.id,
        "position": lesson.position,
        "title": lesson.title,
    }


def unit_payload(unit):
    return {
        "id": unit.id,
        "number_in_book": unit.number_in_book,
        "position": unit.position,
        "title": unit.title,
        "lessons": [lesson_payload(lesson) for lesson in unit.lessons],
    }


def book_payload(book, include_units=True):
    payload = {
        "id": book.id,
        "grade": book.grade,
        "semester": book.semester,
        "period_label": book.period_label,
        "classification_label": book.classification_label,
        "title": book.title,
        "source_url": book.source_url,
        "catalog_urls": book.catalog_urls,
        "source_sha256": book.source_sha256,
        "snapshot_date": book.snapshot_date.isoformat(),
    }
    if include_units:
        payload["units"] = [unit_payload(unit) for unit in book.units]
    return payload


@router.get("/grades")
def list_grades(db: Session = Depends(get_db)):
    grades = db.scalars(
        select(CurriculumBook.grade).distinct().order_by(CurriculumBook.grade)
    ).all()
    return {"grades": grades}


@router.get("/books")
def list_books(
    grade: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    statement = select(CurriculumBook).order_by(
        CurriculumBook.grade,
        CurriculumBook.semester.nulls_last(),
        CurriculumBook.classification_label,
        CurriculumBook.id,
    )
    if grade is not None:
        statement = statement.where(CurriculumBook.grade == grade)
    books = db.scalars(statement).all()
    return {"books": [book_payload(book, include_units=False) for book in books]}


@router.get("/books/{book_id}")
def get_book(book_id: str, db: Session = Depends(get_db)):
    statement = (
        select(CurriculumBook)
        .where(CurriculumBook.id == book_id)
        .options(
            selectinload(CurriculumBook.units).selectinload(CurriculumUnit.lessons)
        )
    )
    book = db.scalar(statement)
    if not book:
        raise HTTPException(status_code=404, detail="Curriculum book not found")
    return book_payload(book)


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)):
    statement = (
        select(CurriculumBook)
        .options(
            selectinload(CurriculumBook.units).selectinload(CurriculumUnit.lessons)
        )
        .order_by(
            CurriculumBook.grade,
            CurriculumBook.semester.nulls_last(),
            CurriculumBook.classification_label,
            CurriculumBook.id,
        )
    )
    books = db.scalars(statement).all()
    return {"books": [book_payload(book) for book in books]}
