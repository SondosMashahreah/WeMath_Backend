"""Regression coverage for the scientific student's logout API contract.

The UI redirect fix belongs to the frontend; no schema migration is needed.
"""
from datetime import date

import pytest
from app.models import CurriculumBook


@pytest.mark.parametrize("grade", [11, 12])
def test_scientific_student_logout_revokes_token_and_can_login_again(client, grade):
    with client.db_sessions() as db:
        db.add(CurriculumBook(
            id=f"scientific-{grade}", grade=grade, semester=None,
            classification_label="علمي", period_label="كتاب كامل",
            title="الرياضيات — علمي", source_url="https://example.org/scientific.pdf",
            catalog_urls=[], source_sha256="b" * 64, snapshot_date=date(2026, 10, 29),
        ))
        db.commit()
    credentials = {"username": f"scientific-{grade}", "password": "science-password-123"}
    response = client.post("/api/auth/register", json={
        **credentials, "full_name": "طالب علمي", "role": "student", "grade": grade, "track": "علمي",
    })
    assert response.status_code == 201, response.text
    session = response.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    profile = client.get("/api/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["track"] == "علمي"
    assert profile.json()["grade"] == grade
    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 204
    assert not logout.content
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/logout", headers=headers).status_code == 401
    login = client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200
    new_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    restored = client.get("/api/auth/me", headers=new_headers)
    assert restored.status_code == 200
    assert restored.json()["id"] == session["user"]["id"]
    assert restored.json()["track"] == "علمي"
    assert client.get("/api/auth/me", headers=headers).status_code == 401
