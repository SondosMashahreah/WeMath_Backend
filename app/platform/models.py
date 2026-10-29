from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherProfile(Base):
    __tablename__ = "platform_teacher_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    school: Mapped[str | None] = mapped_column(String(150), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class PlatformEntry(Base):
    __tablename__ = "platform_entries"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    section: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(180))
    summary: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    activity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompetitionNotification(Base):
    __tablename__ = "platform_competition_notifications"
    __table_args__ = (UniqueConstraint("entry_id", "user_id", name="uq_competition_notification_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("platform_entries.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeacherDocument(Base):
    __tablename__ = "platform_teacher_documents"
    __table_args__ = (
        CheckConstraint("grade BETWEEN 1 AND 12", name="platform_document_grade"),
        CheckConstraint("kind IN ('plan','assessment')", name="platform_document_kind"),
        CheckConstraint("version > 0", name="platform_document_version"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(180))
    grade: Mapped[int] = mapped_column(Integer)
    book_id: Mapped[str | None] = mapped_column(ForeignKey("wemath_curriculum.books.id"), nullable=True)
    lesson_id: Mapped[str | None] = mapped_column(ForeignKey("wemath_curriculum.lessons.id"), nullable=True)
    content: Mapped[dict] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
