from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class TeacherGame(Base):
    __tablename__ = 'teacher_games'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    grade: Mapped[int] = mapped_column(Integer)
    book_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    game: Mapped[dict] = mapped_column(JSON)
    external_url: Mapped[str] = mapped_column(String(2000), default='')
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_lesson_id: Mapped[str | None] = mapped_column(ForeignKey('wemath_curriculum.lessons.id'), index=True, nullable=True)
    published_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
