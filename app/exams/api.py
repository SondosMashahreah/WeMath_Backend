from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.cms.api import staff
from app.cms import service
from app.cms.models import ExamBankItem
from .schemas import Strict, Question, Exam
from .generator import MathTemplate, GenerateRequest, generate

router = APIRouter(prefix='/api/cms/exams', tags=['Exam bank'])


class BankWrite(Strict):
    workspace_id: int
    kind: Literal['question', 'template', 'exam']
    title: str = Field(min_length=2, max_length=180)
    grade: int | None = Field(default=None, ge=1, le=12)
    topic: str = Field(default='', max_length=150)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    payload: dict

    @model_validator(mode='after')
    def validate_payload(self):
        model = {'question': Question, 'template': MathTemplate, 'exam': Exam}[self.kind]
        self.payload = model.model_validate(self.payload).model_dump()
        return self


class Archive(Strict):
    version: int = Field(ge=1)
    archived: bool


def output(row):
    return {key: getattr(row, key) for key in ('id', 'workspace_id', 'kind', 'title', 'grade', 'topic', 'difficulty', 'payload', 'archived', 'version', 'created_at')}


@router.post('/generate')
def generate_questions(data: GenerateRequest, user=Depends(staff), db: Session = Depends(get_db)):
    service.workspace_access(db, user, data.workspace_id, 'quiz')
    try:
        return {'questions': generate(data), 'seed': data.seed}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('/bank', status_code=201)
def save_bank(data: BankWrite, user=Depends(staff), db: Session = Depends(get_db)):
    service.workspace_access(db, user, data.workspace_id, 'quiz')
    row = ExamBankItem(**data.model_dump(), author_id=user.id)
    db.add(row)
    db.flush()
    service.audit(db, user, 'exam_bank.create', row.id)
    db.commit()
    return output(row)


@router.get('/bank')
def list_bank(workspace_id: int, kind: Literal['question', 'template', 'exam'] | None = None,
              q: str = Query('', max_length=100), grade: int | None = Query(None, ge=1, le=12),
              difficulty: Literal['easy', 'medium', 'hard'] | None = None, archived: bool = False,
              offset: int = Query(0, ge=0), user=Depends(staff), db: Session = Depends(get_db)):
    service.workspace_access(db, user, workspace_id, 'quiz')
    filters = [ExamBankItem.workspace_id == workspace_id, ExamBankItem.archived == archived]
    if kind: filters.append(ExamBankItem.kind == kind)
    if grade: filters.append(ExamBankItem.grade == grade)
    if difficulty: filters.append(ExamBankItem.difficulty == difficulty)
    if q: filters.append(or_(ExamBankItem.title.icontains(q, autoescape=True), ExamBankItem.topic.icontains(q, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(ExamBankItem).where(*filters))
    rows = db.scalars(select(ExamBankItem).where(*filters).order_by(ExamBankItem.id.desc()).offset(offset).limit(20))
    return {'items': [output(row) for row in rows], 'total': total}


@router.patch('/bank/{item_id}')
def archive_bank(item_id: int, data: Archive, user=Depends(staff), db: Session = Depends(get_db)):
    row = db.scalar(select(ExamBankItem).where(ExamBankItem.id == item_id).with_for_update())
    if not row: raise HTTPException(404, 'العنصر غير موجود')
    service.workspace_access(db, user, row.workspace_id, 'quiz')
    service.check_version(row, data.version)
    row.archived = data.archived
    row.version += 1
    service.audit(db, user, 'exam_bank.archive' if data.archived else 'exam_bank.restore', row.id)
    db.commit()
    return output(row)
