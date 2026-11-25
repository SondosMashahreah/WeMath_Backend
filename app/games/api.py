from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from app.db.database import get_db
from app.auth.dependencies import require_roles
from app.platform.auth import teacher_required
from app.cms import service as cms
from app.cms.models import ExamBankItem
from app.models import CurriculumBook, CurriculumUnit, CurriculumLesson
from app.exams.generator import GenerateRequest, generate
from .models import TeacherGame
from .schemas import Game, GameWrite, Transition

router = APIRouter(tags=['Game builder'])
admin = require_roles('admin')


def payload(row):
    return {k: getattr(row, k) for k in ('id','teacher_id','title','grade','book_id','unit_id','lesson_id','game','external_url','status','version','updated_at')} | {'has_published_copy': row.published_payload is not None}


def own(db, user, key):
    row = db.scalar(select(TeacherGame).where(TeacherGame.id == key, TeacherGame.teacher_id == user.id).with_for_update())
    if not row: raise HTTPException(404, 'اللعبة غير موجودة')
    return row


def curriculum(db, data, publishing=False):
    book = db.get(CurriculumBook, data.book_id) if data.book_id else None
    unit = db.get(CurriculumUnit, data.unit_id) if data.unit_id else None
    lesson = db.get(CurriculumLesson, data.lesson_id) if data.lesson_id else None
    if (data.book_id and (not book or book.grade != data.grade)) or (data.unit_id and (not unit or unit.book_id != data.book_id)) or (data.lesson_id and (not lesson or lesson.unit_id != data.unit_id)):
        raise HTTPException(422, 'الصف والكتاب والوحدة والدرس يجب أن تنتمي إلى نفس المسار')
    if publishing and not (book and unit and lesson): raise HTTPException(422, 'حدد الكتاب والوحدة والدرس قبل النشر')


@router.get('/api/platform/teachers/games')
def games(q: str = Query('', max_length=100), offset: int = Query(0, ge=0), user=Depends(teacher_required), db=Depends(get_db)):
    filters = [TeacherGame.teacher_id == user.id, TeacherGame.title.icontains(q, autoescape=True)]
    return {'items': [payload(r) for r in db.scalars(select(TeacherGame).where(*filters).order_by(TeacherGame.updated_at.desc(),TeacherGame.id.desc()).offset(offset).limit(20))], 'total': db.scalar(select(func.count()).select_from(TeacherGame).where(*filters)), 'can_publish': cms.is_admin(db,user)}


@router.post('/api/platform/teachers/games', status_code=201)
def create(data: GameWrite, user=Depends(teacher_required), db=Depends(get_db)):
    curriculum(db,data)
    row = TeacherGame(teacher_id=user.id, **data.model_dump(exclude={'version'}))
    db.add(row); db.flush(); cms.audit(db,user,'game.create',row.id); db.commit()
    return payload(row)


@router.get('/api/platform/teachers/games/{game_id}')
def get(game_id: int, user=Depends(teacher_required), db=Depends(get_db)):
    return payload(own(db,user,game_id)) | {'can_publish': cms.is_admin(db,user)}


@router.put('/api/platform/teachers/games/{game_id}')
def edit(game_id: int, data: GameWrite, user=Depends(teacher_required), db=Depends(get_db)):
    row=own(db,user,game_id); cms.check_version(row,data.version); curriculum(db,data)
    if row.status == 'archived': raise HTTPException(409, 'استعد اللعبة كمسودة أولًا')
    for key,value in data.model_dump(exclude={'version'}).items(): setattr(row,key,value)
    row.version += 1; row.status='draft'; cms.audit(db,user,'game.edit',row.id); db.commit()
    return payload(row)


def transition(db,user,row,data,reviewer=False):
    cms.check_version(row,data.version)
    if data.status == 'published':
        if not reviewer and not cms.is_admin(db,user): raise HTTPException(403,'أرسل اللعبة للمراجعة؛ النشر يحتاج الأدمن')
        curriculum(db,row,publishing=True)
    if data.status in ('review','published'):
        try: game=Game.model_validate(row.game).model_dump()
        except ValueError as error: raise HTTPException(422,str(error)) from None
    if data.status == 'published':
        row.published_lesson_id=row.lesson_id
        row.published_payload={'content_id': f'teacher-game-{row.id}', 'title':row.title,'text':game['instructions'],'url':row.external_url or None,'attachments':[],'questions':[],'game':game}
    elif data.status == 'archived': row.published_payload=None; row.published_lesson_id=None
    row.status=data.status; row.version+=1; cms.audit(db,user,'game.'+data.status,row.id); db.commit()
    return payload(row)


@router.post('/api/platform/teachers/games/{game_id}/status')
def change(game_id:int,data:Transition,user=Depends(teacher_required),db=Depends(get_db)):
    return transition(db,user,own(db,user,game_id),data)


@router.get('/api/cms/teacher-games')
def review_list(status: str | None = Query(None, pattern='^(draft|review|published|archived)$'), offset:int=Query(0,ge=0),user=Depends(admin),db=Depends(get_db)):
    filters=[TeacherGame.status==status] if status else []
    return {'items':[payload(r) for r in db.scalars(select(TeacherGame).where(*filters).order_by(TeacherGame.updated_at.desc(),TeacherGame.id.desc()).offset(offset).limit(20))], 'total':db.scalar(select(func.count()).select_from(TeacherGame).where(*filters))}


@router.post('/api/cms/teacher-games/{game_id}/status')
def review(game_id:int,data:Transition,user=Depends(admin),db=Depends(get_db)):
    row=db.scalar(select(TeacherGame).where(TeacherGame.id==game_id).with_for_update())
    if not row: raise HTTPException(404,'اللعبة غير موجودة')
    return transition(db,user,row,data,True)


@router.get('/api/platform/teachers/game-sources')
def sources(user=Depends(teacher_required),db=Depends(get_db)):
    # Membership checks still apply; being a teacher does not unlock private CMS banks.
    return {'workspaces':[{'id':w.id,'name':w.name} for w in cms.accessible_workspaces(db,user) if w.active and ('quiz' in w.modules or cms.is_admin(db,user))]}


@router.get('/api/platform/teachers/game-bank')
def bank(workspace_id:int,q:str=Query('',max_length=100),offset:int=Query(0,ge=0),user=Depends(teacher_required),db=Depends(get_db)):
    cms.workspace_access(db,user,workspace_id,'quiz')
    filters=[ExamBankItem.workspace_id==workspace_id,ExamBankItem.archived.is_(False),ExamBankItem.kind.in_(['question','exam']),ExamBankItem.title.icontains(q,autoescape=True)]
    return {'items':[{'id':r.id,'title':r.title,'kind':r.kind,'payload':r.payload} for r in db.scalars(select(ExamBankItem).where(*filters).order_by(ExamBankItem.id.desc()).offset(offset).limit(20))], 'total':db.scalar(select(func.count()).select_from(ExamBankItem).where(*filters))}


@router.post('/api/platform/teachers/game-generate')
def generate_game(data:GenerateRequest,user=Depends(teacher_required),db=Depends(get_db)):
    cms.workspace_access(db,user,data.workspace_id,'quiz')
    try: return {'questions':generate(data)}
    except ValueError as error: raise HTTPException(422,str(error)) from None
