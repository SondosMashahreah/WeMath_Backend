from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.database import get_db
from . import assistant, auth, notifications, service
from .domain import PlatformError, SECTIONS
from .schemas import ArchiveWrite, AssistantRequest, CompetitionWrite, Credentials, DocumentWrite, TeacherRegister

router = APIRouter(prefix="/api/platform", tags=["Platform extensions"])


@router.get("/sections")
def sections():
    return {"sections": {key: value for key, value in SECTIONS.items() if key != "teacher_resources"}}


@router.get("/entries")
def entries(section: str, category: str | None = None, archived: bool = False,
            q: str = Query(default="", max_length=100), offset: int = Query(default=0, ge=0),
            limit: int = Query(default=6, ge=1, le=40),
            month: str | None = Query(default=None, pattern=r"^(19|20|21)\d{2}-(0[1-9]|1[0-2])$"), db: Session = Depends(get_db)):
    return service.list_entries(db, section, category, archived, q, offset, limit, month)


@router.get("/entries/{entry_id}")
def entry(entry_id: str, db: Session = Depends(get_db)):
    return service.get_entry(db, entry_id)


@router.post("/competitions", status_code=201)
def publish_competition(data: CompetitionWrite, background: BackgroundTasks, user=Depends(require_roles("admin", "supervisor")), db: Session = Depends(get_db)):
    payload, notify = service.save_competition(db, data, user.id)
    if notify:
        background.add_task(notifications.dispatch_competition_email, payload["id"])
    return payload


@router.post("/assistant")
def ask(data: AssistantRequest, db: Session = Depends(get_db)):
    return assistant.respond(db, data)


@router.post("/teachers/register", status_code=201)
def register(data: TeacherRegister, db: Session = Depends(get_db)):
    return auth.register(db, data)


@router.post("/teachers/login")
def login(data: Credentials, db: Session = Depends(get_db)):
    return auth.login(db, data)


@router.get("/teachers/me")
def me(user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return auth.profile_payload(db, user)


@router.post("/teachers/logout")
def logout(user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return auth.logout(db, user)


@router.get("/teachers/library")
def library(category: str | None = None, q: str = Query(default="", max_length=100),
            offset: int = Query(default=0, ge=0), limit: int = Query(default=6, ge=1, le=40),
            user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.list_entries(db, "teacher_resources", category=category, q=q, offset=offset, limit=limit, teacher=True)


@router.get("/teachers/library/{entry_id}")
def library_entry(entry_id: str, user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.get_teacher_entry(db, entry_id)


@router.get("/teachers/documents")
def documents(kind: Literal["plan", "assessment"] = "plan", archived: bool = False,
              offset: int = Query(default=0, ge=0), limit: int = Query(default=6, ge=1, le=40),
              user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.list_documents(db, user.id, kind, archived, offset, limit)


@router.post("/teachers/documents", status_code=201)
def create_document(data: DocumentWrite, user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.save_document(db, user.id, data)


@router.get("/teachers/documents/{document_id}")
def document(document_id: int, user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.document_payload(service.own_document(db, user.id, document_id))


@router.put("/teachers/documents/{document_id}")
def update_document(document_id: int, data: DocumentWrite, user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.save_document(db, user.id, data, document_id)


@router.patch("/teachers/documents/{document_id}/archive")
def archive(document_id: int, data: ArchiveWrite, user=Depends(auth.teacher_required), db: Session = Depends(get_db)):
    return service.archive_document(db, user.id, document_id, data)


def install_platform(app):
    async def handle_platform_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": exc.message})
    app.add_exception_handler(PlatformError, handle_platform_error)
    app.include_router(router)
