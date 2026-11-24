"""Date-only workshop calendars: published snapshots for visitors, scoped drafts for staff."""
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from app.db.database import get_db
from app.platform.models import PlatformEntry
from app.platform.domain import SECTIONS
from .api import staff
from .models import Content
from . import service

router = APIRouter(tags=['Workshop calendars'])


class CalendarQuery:
    def __init__(self, category: str, month: str = Query(pattern=r'^(19|20|21)\d{2}-(0[1-9]|1[0-2])$'),
                 mode: Literal['month', 'day', 'upcoming', 'past', 'undated'] = 'month',
                 day: date | None = None, q: str = Query('', max_length=100), offset: int = Query(0, ge=0),
                 status: Literal['draft', 'review', 'published', 'archived'] | None = None):
        if category not in SECTIONS['workshops']:
            raise HTTPException(404, 'تصنيف الورشات غير موجود')
        if mode == 'day' and (not day or day.isoformat()[:7] != month):
            raise HTTPException(422, 'اختر يومًا من الشهر المعروض')
        self.category, self.month, self.mode, self.day = category, month, mode, day
        self.q, self.offset, self.status = q, offset, status


def calendar_data(db, params, workspace_id=None):
    public = workspace_id is None
    model = PlatformEntry if public else Content
    event_date = cast(PlatformEntry.event_date, String) if public else Content.payload['event_date'].as_string()
    category = PlatformEntry.category if public else Content.payload['category'].as_string()
    filters = ([PlatformEntry.section == 'workshops', PlatformEntry.published.is_(True)] if public else
               [Content.module == 'workshops', Content.workspace_id == workspace_id]) + [category == params.category]
    # Past published workshops stay visible; withdrawn CMS content is never exposed.
    if not public:
        filters.append(Content.status == params.status if params.status else Content.status != 'archived')
    if params.q.strip(): filters.append(model.title.icontains(params.q.strip(), autoescape=True))
    year, month = map(int, params.month.split('-'))
    first, after = date(year, month, 1).isoformat(), date(year + (month == 12), month % 12 + 1, 1).isoformat()
    today = datetime.now(ZoneInfo('Asia/Jerusalem')).date().isoformat()
    dated = event_date.is_not(None) & (event_date != '')
    month_filter = dated & (event_date >= first) & (event_date < after)
    days = dict(db.execute(select(event_date, func.count()).select_from(model).where(*filters, month_filter).group_by(event_date)).all())
    scopes = {'month': month_filter, 'day': event_date == (params.day.isoformat() if params.day else ''),
              'past': dated & (event_date < today), 'upcoming': dated & (event_date >= today),
              'undated': or_(event_date.is_(None), event_date == '')}
    counts = {key: db.scalar(select(func.count()).select_from(model).where(*filters, scopes[key])) for key in ('month', 'past', 'upcoming', 'undated')}
    filters.append(scopes[params.mode])
    total = db.scalar(select(func.count()).select_from(model).where(*filters))
    order = event_date.desc() if params.mode == 'past' else event_date.asc()
    rows = db.scalars(select(model).where(*filters).order_by(order.nulls_last(), model.id).offset(params.offset).limit(20)).all()
    items = []
    for row in rows:
        data = row.details or {} if public else row.payload
        items.append({'id': row.id, 'title': row.title, 'event_date': row.event_date if public else data.get('event_date'),
                      'summary': row.summary if public else data.get('summary', ''), 'location': data.get('location', ''),
                      'organizer': data.get('organizer', ''), 'status': 'published' if public else row.status,
                      'is_demo': row.is_demo if public else False})
    return {'items': items, 'total': total, 'days': days, 'counts': counts, 'today': today, 'offset': params.offset, 'limit': 20}


@router.get('/api/platform/workshops/calendar')
def public_calendar(params: CalendarQuery = Depends(), db=Depends(get_db)):
    if params.status: raise HTTPException(422, 'حالة المسودة غير متاحة في التقويم العام')
    return calendar_data(db, params)


@router.get('/api/cms/workshops/calendar')
def staff_calendar(workspace_id: int, params: CalendarQuery = Depends(), user=Depends(staff), db=Depends(get_db)):
    service.workspace_access(db, user, workspace_id, 'workshops')
    return calendar_data(db, params, workspace_id)
