from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.auth.dependencies import require_roles
from app.db.database import get_db
from app.models.user import User
from app.services.learning_service import lesson_resources, progress_summary, record_progress

router = APIRouter(prefix="/api/learning", tags=["Learning"])
student_user = require_roles("student")


class ProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: Literal["opened", "book", "learn", "video", "practice", "game", "completed"]


@router.get("/progress")
def progress(student: User = Depends(student_user), db: Session = Depends(get_db)):
    return progress_summary(db, student.id)


@router.get("/lessons/{lesson_id}")
def resources(lesson_id: str, student: User = Depends(student_user), db: Session = Depends(get_db)):
    return lesson_resources(db, student.id, lesson_id)


@router.put("/lessons/{lesson_id}/progress")
def update_progress(lesson_id: str, data: ProgressRequest, student: User = Depends(student_user), db: Session = Depends(get_db)):
    result = record_progress(db, student.id, lesson_id, data.activity)
    db.commit()
    return result
