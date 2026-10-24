from datetime import date

from sqlalchemy import Date, ForeignKey, JSON, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


SCHEMA = "wemath_curriculum"


class CurriculumBook(Base):
    __tablename__ = "books"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False, index=True)
    semester: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, index=True)
    period_label: Mapped[str] = mapped_column(Text, nullable=False)
    classification_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    units: Mapped[list["CurriculumUnit"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="CurriculumUnit.position",
    )


class CurriculumUnit(Base):
    __tablename__ = "units"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    book_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number_in_book: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    book: Mapped[CurriculumBook] = relationship(back_populates="units")
    lessons: Mapped[list["CurriculumLesson"]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by="CurriculumLesson.position",
    )


class CurriculumLesson(Base):
    __tablename__ = "lessons"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    unit_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    unit: Mapped[CurriculumUnit] = relationship(back_populates="lessons")
