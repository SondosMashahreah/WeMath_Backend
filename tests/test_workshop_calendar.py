from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from app.platform.models import PlatformEntry
from test_cms import setup, create, state


def put_entry(db, key, day, category='ministry', published=True, archived=False):
    db.add(PlatformEntry(id=key, section='workshops', category=category, title='ورشة '+key, summary='ملخص', body='تفاصيل', event_date=day, published=published, archived=archived, is_demo=False, details={'location': 'رام الله'}))


def test_public_month_counts_include_all_days_not_only_first_page(client):
    with client.db_sessions() as db:
        for i in range(25): put_entry(db, f'ministry-{i:02}', date(2026, 11, 10))
        put_entry(db, 'another-day', date(2026, 11, 30), archived=True)
        put_entry(db, 'wrong-category', date(2026, 11, 10), category='universities')
        put_entry(db, 'private', date(2026, 11, 10), published=False)
        put_entry(db, 'next-month', date(2026, 12, 1))
        put_entry(db, 'no-date', None)
        db.commit()
    url='/api/platform/workshops/calendar?category=ministry&month=2026-11'
    response=client.get(url); assert response.status_code==200, response.text
    data=response.json()
    assert data['total']==26 and len(data['items'])==20
    assert data['days']=={'2026-11-10':25,'2026-11-30':1}
    assert data['counts']['undated']==1
    assert client.get(url+'&offset=20').json()['items'][-1]['id']=='another-day'
    assert client.get(url+'&mode=day&day=2026-11-30').json()['total']==1
    assert client.get(url+'&mode=undated').json()['items'][0]['id']=='no-date'
    assert client.get(url+'&q=another').json()['days']=={'2026-11-30':1}
    assert client.get(url+'&mode=day&day=2026-12-01').status_code==422
    assert client.get(url+'&mode=day').status_code==422
    assert client.get(url+'&status=draft').status_code==422
    assert client.get(url.replace('ministry','unknown')).status_code==404
    assert client.get(url.replace('2026-11','2026-13')).status_code==422


def test_past_and_upcoming_use_local_today_and_sort(client):
    today=datetime.now(ZoneInfo('Asia/Jerusalem')).date()
    with client.db_sessions() as db:
        for key, delta in [('before',-1),('today',0),('later',1),('earlier',-2)]: put_entry(db,key,today+timedelta(days=delta))
        db.commit()
    url=f'/api/platform/workshops/calendar?category=ministry&month={today:%Y-%m}'
    assert [r['id'] for r in client.get(url+'&mode=past').json()['items']]==['before','earlier']
    data=client.get(url+'&mode=upcoming').json()
    assert data['today']==today.isoformat()
    assert [r['id'] for r in data['items']]==['today','later']


def test_staff_scope_snapshot_and_date_required_for_publication(client):
    admin,editor,workspace,_=setup(client,['workshops'],True)
    other=client.post('/api/cms/workspaces',headers=admin,json={'name':'فريق آخر','modules':['workshops']}).json()
    data=create(client,editor,workspace,'workshops',category='ministry',summary='ملخص',event_date='2026-11-12',location='القدس')
    undated=create(client,editor,workspace,'workshops',category='ministry',summary='ملخص')
    assert state(client,editor,undated,'published').status_code==422
    url=f"/api/cms/workshops/calendar?workspace_id={workspace['id']}&category=ministry&month=2026-11"
    assert client.get(url).status_code==401
    assert client.get(url,headers=editor).json()['total']==1
    assert client.get(url+'&mode=undated',headers=editor).json()['total']==1
    assert client.get(url.replace(f"workspace_id={workspace['id']}",f"workspace_id={other['id']}"),headers=editor).status_code==403
    public='/api/platform/workshops/calendar?category=ministry&month=2026-11'
    assert client.get(public).json()['total']==0
    live=state(client,editor,data,'published').json()
    assert client.get(public).json()['days']=={'2026-11-12':1}
    edit={k:live[k] for k in ('workspace_id','module','title','payload','version')}
    edit['payload']['event_date']='2026-12-15'
    edited=client.put(f"/api/cms/content/{live['id']}",headers=editor,json=edit).json()
    assert client.get(url,headers=editor).json()['total']==0
    assert client.get(public).json()['days']=={'2026-11-12':1}
    published=state(client,editor,edited,'published').json()
    assert client.get(public).json()['total']==0
    assert client.get(public.replace('2026-11','2026-12')).json()['days']=={'2026-12-15':1}
    assert state(client,editor,published,'archived').status_code==200
    assert client.get(public.replace('2026-11','2026-12')).json()['total']==0
    assert client.get(url.replace('2026-11','2026-12')+'&status=archived',headers=editor).json()['total']==1


def test_staff_without_workshop_module_cannot_read_calendar(client):
    _,editor,workspace,_=setup(client,['worksheet'])
    assert client.get(f"/api/cms/workshops/calendar?workspace_id={workspace['id']}&category=ministry&month=2026-11",headers=editor).status_code==403
