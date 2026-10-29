import pytest
from pydantic import ValidationError

from app.platform.domain import SECTIONS
from app.schemas.auth import StudentDetails


def test_removed_internal_sections_are_not_exposed():
    assert "research" not in SECTIONS


def test_grade_11_and_12_support_optional_track():
    from app.schemas.auth import RegisterRequest

    grade11 = RegisterRequest(
        username="grade11",
        password="password-123",
        full_name="???? 11",
        role="student",
        grade=11,
    )
    grade12 = RegisterRequest(
        username="grade12",
        password="password-123",
        full_name="???? 12",
        role="student",
        grade=12,
    )

    assert grade11.track is None
    assert grade12.track is None


def test_grade_10_does_not_require_track():
    student = StudentDetails(full_name="Test Student", grade=10)
    assert student.track is None
