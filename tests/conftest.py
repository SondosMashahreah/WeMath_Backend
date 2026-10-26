import os
from datetime import date
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "local-test-key-at-least-32-characters")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.db.database import get_db
from app.main import app
from app.models import CurriculumBook, CurriculumUnit, CurriculumLesson, Role


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
                           execution_options={"schema_translate_map": {"wemath_curriculum": None}})
    @event.listens_for(engine, "connect")
    def enforce_fks(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add_all([Role(name="student"), Role(name="parent"), Role(name="admin")])
        for grade in [1, 2, 12]:
            book = CurriculumBook(id=f"book{grade}", grade=grade, semester=None if grade == 12 else 1,
                period_label="كتاب كامل" if grade == 12 else "الفصل الأول", title=f"كتاب {grade}",
                source_url=f"https://example.org/book{grade}.pdf", catalog_urls=[], source_sha256="a"*64,
                snapshot_date=date(2026, 10, 19))
            unit = CurriculumUnit(id=f"unit{grade}", number_in_book=1, position=1, title="وحدة الأشكال")
            unit.lessons = [CurriculumLesson(id=f"lesson{grade}-{i}", position=i, title=f"درس {i}") for i in [1,2]]
            book.units = [unit]; db.add(book)
        db.commit()
    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        test_client.db_sessions = sessions
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
