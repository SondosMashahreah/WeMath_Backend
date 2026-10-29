from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (CheckConstraint("grade BETWEEN 1 AND 12", name="ck_student_grade"),)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    grade: Mapped[int | None] = mapped_column(Integer)
    track: Mapped[str | None] = mapped_column(String(150), nullable=True)
    identity_number: Mapped[str | None] = mapped_column(String(12))
    school: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    directorate: Mapped[str | None] = mapped_column(String(150))


class ParentChild(Base):
    __tablename__ = "parent_children"
    __table_args__ = (
        UniqueConstraint("parent_id", "slot", name="uq_parent_child_slot"),
        CheckConstraint("slot BETWEEN 1 AND 5", name="ck_parent_child_slot"),
        CheckConstraint("parent_id <> child_id", name="ck_parent_not_child"),
    )
    child_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (CheckConstraint("status IN ('started', 'completed')", name="ck_progress_status"),)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("wemath_curriculum.lessons.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="started", nullable=False)
    last_activity: Mapped[str] = mapped_column(String(24), default="opened", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    __table_args__ = (
        UniqueConstraint("student_id", "assessment_key", name="uq_student_assessment_result"),
        CheckConstraint("score >= 0 AND max_score > 0 AND score <= max_score", name="ck_assessment_score"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    assessment_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
