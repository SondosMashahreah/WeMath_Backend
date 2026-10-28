"""Run with python -m pytest -q tests/test_platform_expansion.py (pytest/httpx are test-only)."""
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-platform-secret-which-is-never-used-in-production-12345")

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.jwt import decode_access_token
from app.core.config import settings
from app.db.base import Base
from app.db.database import get_db
from app.models import CurriculumBook, CurriculumLesson, CurriculumUnit, Role, User
from app.platform.api import install_platform
from app.platform.models import PlatformEntry


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def attach(connection, record):
        connection.execute("ATTACH DATABASE ':memory:' AS wemath_curriculum")
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Role(name="teacher"))
        book = CurriculumBook(id="book1", grade=1, semester=1, period_label="الفصل الأول", title="رياضيات 1", source_url="https://example.org/book.pdf", catalog_urls=[], source_sha256="0" * 64, snapshot_date=date.today())
        unit = CurriculumUnit(id="unit1", number_in_book=1, position=1, title="الأعداد")
        unit.lessons = [CurriculumLesson(id="lesson1", position=1, title="الجمع")]
        book.units = [unit]
        db.add(book)
        db.add(CurriculumBook(id="book2", grade=2, semester=1, period_label="الفصل الأول", title="رياضيات 2", source_url="https://example.org/book2.pdf", catalog_urls=[], source_sha256="1" * 64, snapshot_date=date.today()))
        for data in json.loads((Path(__file__).parents[1] / "alembic/data/platform_catalog_20261026.json").read_text()):
            if data["event_date"]: data["event_date"] = date.fromisoformat(data["event_date"])
            db.add(PlatformEntry(**data))
        db.commit()
    app = FastAPI()
    install_platform(app)

    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as test_client:
        test_client.db_engine = engine
        yield test_client
    engine.dispose()


def register(client, username="teacher.one"):
    response = client.post("/api/platform/teachers/register", json={"username": username, "password": "TeacherPassword123!", "full_name": "معلّم تجريبي", "school": ""})
    assert response.status_code == 201, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data


def plan(**changes):
    return {"kind": "plan", "title": "تحضير الجمع", "grade": 1, "book_id": "book1", "lesson_id": "lesson1", "content": {"objectives": "يشرح الجمع", "steps": "يمثل المجموعات", "assessment": "بطاقة خروج", "materials": "أقلام", "duration": 45}, **changes}


def test_teacher_session_is_separate_and_logout_revokes(client):
    headers, data = register(client)
    assert decode_access_token(data["access_token"]) is None
    old_token = jwt.encode({"sub": str(data["user"]["id"]), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert client.get("/api/platform/teachers/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.get("/api/platform/teachers/me", headers=headers).json()["role"] == "teacher"
    assert client.post("/api/platform/teachers/logout", headers=headers).status_code == 200
    assert client.get("/api/platform/teachers/me", headers=headers).status_code == 401
    with Session(client.db_engine) as db:
        assert db.get(User, data["user"]["id"]).token_version == 0, "Teacher logout must not revoke family sessions"


def test_teacher_signup_login_and_duplicate_username(client):
    register(client)
    body = {"username": "TEACHER.ONE", "password": "TeacherPassword123!"}
    assert client.post("/api/platform/teachers/login", json=body).status_code == 200
    assert client.post("/api/platform/teachers/login", json={**body, "password": "WrongPassword"}).status_code == 401
    assert client.post("/api/platform/teachers/register", json={**body, "full_name": "أحمد"}).status_code == 409
    assert client.post("/api/platform/teachers/register", json={**body, "full_name": "أحمد", "role": "admin"}).status_code == 422


def test_private_documents_never_cross_accounts(client):
    first, _ = register(client); second, _ = register(client, "teacher.two")
    response = client.post("/api/platform/teachers/documents", headers=first, json=plan())
    assert response.status_code == 201
    doc = response.json(); url = f"/api/platform/teachers/documents/{doc['id']}"
    assert client.get(url, headers=second).status_code == 404
    assert client.put(url, headers=second, json=plan(version=doc["version"])).status_code == 404
    assert client.patch(url + "/archive", headers=second, json={"version": doc["version"], "archived": True}).status_code == 404
    assert client.get("/api/platform/teachers/documents", headers=second).json()["total"] == 0
    assert client.get("/api/platform/teachers/documents").status_code == 401


def test_document_grade_and_lesson_must_match(client):
    headers, _ = register(client)
    for payload in (plan(grade=2), plan(book_id="book2", grade=2), plan(lesson_id=None), plan(grade=13)):
        assert client.post("/api/platform/teachers/documents", headers=headers, json=payload).status_code == 422


def test_edit_uses_version_guard(client):
    headers, _ = register(client)
    doc = client.post("/api/platform/teachers/documents", headers=headers, json=plan()).json()
    url = f"/api/platform/teachers/documents/{doc['id']}"
    assert client.put(url, headers=headers, json=plan(title="خطة جديدة", version=1)).json()["version"] == 2
    assert client.put(url, headers=headers, json=plan(version=1)).status_code == 409
    assert client.get(url, headers=headers).json()["title"] == "خطة جديدة"


def test_archive_and_restore_preserve_document(client):
    headers, _ = register(client)
    doc = client.post("/api/platform/teachers/documents", headers=headers, json=plan()).json()
    url = f"/api/platform/teachers/documents/{doc['id']}"
    assert client.patch(url + "/archive", headers=headers, json={"version": 1, "archived": True}).status_code == 200
    assert client.get("/api/platform/teachers/documents", headers=headers).json()["total"] == 0
    assert client.get("/api/platform/teachers/documents?archived=true", headers=headers).json()["total"] == 1
    assert client.put(url, headers=headers, json=plan(version=2)).status_code == 409
    assert client.patch(url + "/archive", headers=headers, json={"version": 2, "archived": False}).status_code == 200
    assert client.get(url, headers=headers).json()["content"] == plan()["content"]


def test_assessment_validation_and_private_library(client):
    headers, _ = register(client)
    payload = {"kind": "assessment", "title": "اختبار", "grade": 1, "content": {"questions": [{"prompt": "1+1", "options": ["1", "2"], "correct": 1}]}}
    assert client.post("/api/platform/teachers/documents", headers=headers, json=payload).status_code == 201
    payload["content"]["questions"][0]["correct"] = 3
    assert client.post("/api/platform/teachers/documents", headers=headers, json=payload).status_code == 422
    assert client.get("/api/platform/teachers/library").status_code == 401
    assert client.get("/api/platform/teachers/library", headers=headers).json()["total"] == 6
    assert client.get("/api/platform/entries?section=teacher_resources").status_code == 404


def test_public_search_pagination_calendar_and_archive(client):
    base = "/api/platform/entries?section=workshops"
    assert client.get(base + "&limit=2&offset=2").json()["total"] == 6
    assert len(client.get(base + "&limit=2&offset=2").json()["items"]) == 2
    assert client.get(base + "&q=%25").json()["items"] == []
    assert client.get(base + "&q=الكسور").json()["total"] == 2
    assert client.get("/api/platform/entries?section=competitions&month=2026-11").json()["total"] == 2
    assert client.get("/api/platform/entries?section=competitions&month=2025-11&archived=true").json()["total"] == 2
    assert client.get("/api/platform/entries?section=competitions&month=2026-13").status_code == 422


def test_assistant_is_bounded_and_returns_real_catalog_links(client):
    assert client.post("/api/platform/assistant", json={"message": "(١٢ + ٨) ÷ ٤"}).json()["answer"] == "الناتج = 5"
    for expression in ("1 / 0", "9 ** 999999", "2 ** (2 ** 8)"):
        assert "تعذّر" in client.post("/api/platform/assistant", json={"message": expression}).json()["answer"]
    data = client.post("/api/platform/assistant", json={"message": "الجمع", "grade": 1}).json()
    assert data["is_demo"] and data["sources"][0]["source_url"] == "https://example.org/book.pdf"
    assert client.post("/api/platform/assistant", json={"message": "__import__('os')"}).json()["sources"] == []


def test_guest_is_readonly_and_public_entries_cannot_be_written(client):
    data = client.get("/api/platform/guest/catalog").json()
    assert data["preview"] and data["books"][0]["sample"]["lesson"] == "الجمع"
    assert client.post("/api/platform/entries", json={}).status_code == 405
    with Session(client.db_engine) as db:
        assert db.scalars(select(User)).all() == []


def test_teacher_library_direct_link_requires_teacher_and_published_entry(client):
    headers, session = register(client)
    entry_id = client.get('/api/platform/teachers/library', headers=headers).json()['items'][0]['id']
    url = f'/api/platform/teachers/library/{entry_id}'
    assert client.get(url).status_code == 401
    family_token = jwt.encode({'sub': str(session['user']['id']), 'exp': datetime.now(timezone.utc) + timedelta(minutes=5), 'ver': 0}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert client.get(url, headers={'Authorization': f'Bearer {family_token}'}).status_code == 401
    assert client.get(url, headers=headers).json()['id'] == entry_id
    assert client.get(f'/api/platform/entries/{entry_id}').status_code == 404
    public_id = client.get('/api/platform/entries?section=workshops').json()['items'][0]['id']
    assert client.get(f'/api/platform/teachers/library/{public_id}', headers=headers).status_code == 404
    assert client.get('/api/platform/teachers/library/missing-entry', headers=headers).status_code == 404
    with Session(client.db_engine) as db:
        db.get(PlatformEntry, entry_id).published = False
        db.commit()
    assert client.get(url, headers=headers).status_code == 404
