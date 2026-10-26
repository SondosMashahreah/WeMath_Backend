import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import User, ParentChild, StudentProfile
from app.auth.password import verify_password

PASSWORD = "test-password-123"


def register(client, username, role="student", grade=1):
    payload = {"username": username, "password": PASSWORD, "full_name": "حساب تجريبي", "role": role}
    if role == "student": payload["grade"] = grade
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    return data["user"], {"Authorization": f"Bearer {data['access_token']}"}


def child_data(username="child-one", grade=1):
    return {"username": username, "password": PASSWORD, "full_name": "طفل تجريبي", "grade": grade}


def test_username_login_and_required_grade(client):
    for grade in [None, 0, 13]:
        assert client.post("/api/auth/register", json=child_data(grade=grade)).status_code == 422
    user, headers = register(client, "  STUDENT.ONE  ", grade=12)
    assert user["username"] == "student.one" and user["grade"] == 12
    assert "password" not in str(user)
    assert client.post("/api/auth/login", json={"username": " STUDENT.ONE ", "password": PASSWORD}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "test@example.com", "password": PASSWORD}).status_code == 422
    assert client.post("/api/auth/login", json={"username": user["username"], "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/register", json=child_data("student.one")).status_code == 409
    assert client.post("/api/auth/register", json={**child_data("evil"), "role": "admin"}).status_code == 422
    with client.db_sessions() as db:
        stored = db.get(User, user["id"])
        assert stored.password_hash != PASSWORD and verify_password(PASSWORD, stored.password_hash)
    assert client.get("/api/parents/children", headers=headers).status_code == 403
    assert client.get("/api/parents/children").status_code == 401


def test_parent_creates_five_children_with_real_student_logins(client):
    _, headers = register(client, "guardian", "parent")
    for i in range(5):
        response = client.post("/api/parents/children", headers=headers, json=child_data(f"kid{i}", i+1))
        assert response.status_code == 201, response.text
        assert response.json()["grade"] == i+1 and response.json()["roles"] == ["student"]
        assert client.post("/api/auth/login", json={"username": f"kid{i}", "password": PASSWORD}).status_code == 200
    assert client.post("/api/parents/children", headers=headers, json=child_data("kid6")).status_code == 409
    assert len(client.get("/api/parents/children", headers=headers).json()["children"]) == 5
    with client.db_sessions() as db:
        assert db.scalar(select(User).where(User.username == "kid6")) is None


def test_link_requires_credentials_and_preserves_progress(client):
    child, ch = register(client, "existing")
    client.put("/api/learning/lessons/lesson1-1/progress", headers=ch, json={"activity": "completed"})
    _, ph = register(client, "guardian", "parent")
    _, other = register(client, "other-guardian", "parent")
    assert client.post("/api/parents/children/link", headers=ph, json={"username": "existing", "password": "bad"}).status_code == 400
    assert client.post("/api/parents/children/link", headers=ph, json={"username": "existing", "password": PASSWORD}).status_code == 201
    assert client.post("/api/parents/children/link", headers=other, json={"username": "existing", "password": PASSWORD}).status_code == 409
    assert client.post("/api/parents/children/link", headers=ph, json={"username": "other-guardian", "password": PASSWORD}).status_code == 400
    assert client.get(f"/api/parents/children/{child['id']}/progress", headers=ph).json()["completed"] == 1


def test_ownership_for_view_edit_reset_and_preview(client):
    _, owner = register(client, "owner", "parent")
    _, stranger = register(client, "stranger", "parent")
    child = client.post("/api/parents/children", headers=owner, json=child_data()).json()
    path = f"/api/parents/children/{child['id']}"
    assert client.get(path+"/progress", headers=stranger).status_code == 404
    assert client.get(path+"/lessons/lesson1-1", headers=stranger).status_code == 404
    assert client.patch(path, headers=stranger, json={"full_name": "اختراق", "grade": 2}).status_code == 404
    assert client.put(path+"/password", headers=stranger, json={"password": "changed-password"}).status_code == 404
    assert client.put("/api/learning/lessons/lesson1-1/progress", headers=owner, json={"activity": "completed"}).status_code == 403


def test_child_controls_revoke_tokens(client):
    _, ph = register(client, "guardian", "parent")
    child = client.post("/api/parents/children", headers=ph, json=child_data()).json()
    path = f"/api/parents/children/{child['id']}"
    def login(password=PASSWORD):
        response = client.post("/api/auth/login", json={"username": "child-one", "password": password})
        return response, {"Authorization": "Bearer " + response.json().get("access_token", "")}
    _, ch = login()
    assert client.patch(path, headers=ph, json={"full_name": "طفلي", "grade": 2, "is_active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=ch).status_code == 401
    assert login()[0].status_code == 401
    client.patch(path, headers=ph, json={"full_name": "طفلي", "grade": 2, "is_active": True})
    _, ch = login()
    assert client.get("/api/auth/me", headers=ch).json()["grade"] == 2
    assert client.put(path+"/password", headers=ph, json={"password": "new-password-123"}).status_code == 204
    assert client.get("/api/auth/me", headers=ch).status_code == 401
    assert login()[0].status_code == 401
    assert login("new-password-123")[0].status_code == 200


def test_progress_idempotent_and_grade_scoped(client):
    _, ch = register(client, "student")
    path = "/api/learning/lessons/lesson1-1"
    resources = client.get(path, headers=ch).json()
    assert resources["book"]["source_url"] == "https://example.org/book1.pdf"
    assert all(r["demo"] for r in resources["resources"])
    assert client.put(path+"/progress", headers=ch, json={"activity": "opened", "student_id": 999}).status_code == 422
    assert client.put(path+"/progress", headers=ch, json={"activity": "fabricated"}).status_code == 422
    assert client.get("/api/learning/lessons/lesson2-1", headers=ch).status_code == 403
    assert client.put("/api/learning/lessons/lesson2-1/progress", headers=ch, json={"activity": "completed"}).status_code == 403
    assert client.get("/api/learning/lessons/missing", headers=ch).status_code == 404
    for action in ["opened", "opened", "book", "completed", "opened"]:
        assert client.put(path+"/progress", headers=ch, json={"activity": action}).status_code == 200
    summary = client.get("/api/learning/progress", headers=ch).json()
    assert summary["visited"] == summary["completed"] == 1
    assert summary["lessons"][0]["completed_at"] is not None
    _, oh = register(client, "second-student")
    assert client.get("/api/learning/progress", headers=oh).json()["visited"] == 0


def test_legacy_profile_and_logout(client):
    user, headers = register(client, "legacy")
    with client.db_sessions() as db:
        db.get(StudentProfile, user["id"]).grade = None; db.commit()
    assert client.get("/api/auth/me", headers=headers).json()["grade"] is None
    assert client.patch("/api/auth/me/profile", headers=headers, json={"full_name": "طالب قديم", "grade": 12}).status_code == 200
    assert client.patch("/api/auth/me/profile", headers=headers, json={"full_name": "طالب قديم", "grade": 2}).status_code == 409
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_database_enforces_parent_slots(client):
    parent, _ = register(client, "guardian", "parent")
    child, _ = register(client, "student")
    with client.db_sessions() as db:
        db.add(ParentChild(parent_id=parent["id"], child_id=child["id"], slot=6))
        with pytest.raises(IntegrityError): db.commit()


def test_config_rejects_example_key():
    from app.core.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL="sqlite://", JWT_SECRET_KEY="CHANGE_ME_generate_a_new_random_secret", _env_file=None)
