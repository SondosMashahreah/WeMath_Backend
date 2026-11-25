from copy import deepcopy
import pytest
from sqlalchemy import select
from app.models import Role
from app.games.schemas import Game
from test_cms import setup, create, state


def teacher(client, username='teacher.games'):
    with client.db_sessions() as db:
        if not db.scalar(select(Role).where(Role.name == 'teacher')):
            db.add(Role(name='teacher')); db.commit()
    r = client.post('/api/platform/teachers/register', json={'username': username, 'full_name': 'معلم ألعاب', 'password': 'TeacherPassword123!', 'school': ''})
    assert r.status_code == 201, r.text
    return {'Authorization': 'Bearer ' + r.json()['access_token']}, r.json()['user']['id']


def game(kind='quiz'):
    return {'kind': kind, 'items': [{'prompt': '1+1', 'answer': '2', 'options': ['2','3'], 'correct': 0, 'value': '1/2', 'numerator': 1, 'denominator': 2}, {'prompt': '1+2', 'answer': '3', 'options': ['3','4'], 'correct': 0, 'value': '1'}], 'step': '1/2'}


def body(**changes):
    return {'title': 'لعبة الجمع', 'grade': 1, 'book_id': 'book1', 'unit_id': 'unit1', 'lesson_id': 'lesson1-1', 'game': game(), **changes}


def new(client, headers, **changes):
    r = client.post('/api/platform/teachers/games', headers=headers, json=body(**changes))
    assert r.status_code == 201, r.text
    return r.json()


def transition(client, headers, row, status, admin=False):
    base = '/api/cms/teacher-games' if admin else '/api/platform/teachers/games'
    return client.post(f"{base}/{row['id']}/status", headers=headers, json={'version': row['version'], 'status': status})


@pytest.mark.parametrize('kind', ['matching','memory','quiz','true_false','sorting','wheel','number_line','fractions','maze'])
def test_all_engines_validate(kind):
    g = game(kind)
    if kind == 'true_false':
        for i in g['items']: i['options']=['صح','خطأ']
    assert Game.model_validate(g).kind == kind


@pytest.mark.parametrize('mutate', [lambda g:g.update(items=[]), lambda g:g.update(kind='number_line',step='0'), lambda g:g.update(kind='number_line',step='0.001'), lambda g:g.update(kind='number_line',minimum='1/0'), lambda g:g['items'][0].update(correct=5), lambda g:g['items'][0].update(options=['2','2']), lambda g:g.update(kind='fractions',items=[{'denominator':2,'numerator':3}]), lambda g:g.update(kind='matching',items=[g['items'][0]]), lambda g:g['items'][0].update(image_url='javascript:alert(1)'), lambda g:g['items'][0].update(image_url='https://example.org/a.png',image_alt='')])
def test_invalid_games_rejected(mutate):
    g=game(); mutate(g)
    with pytest.raises(ValueError): Game.model_validate(g)


def test_owner_permissions_versions_and_draft_validation(client):
    h,_=teacher(client); other,_=teacher(client,'teacher.other')
    row=new(client,h,game={'kind':'matching','items':[]})
    assert transition(client,h,row,'review').status_code==422
    assert transition(client,h,row,'published').status_code==403
    path=f"/api/platform/teachers/games/{row['id']}"
    assert client.get(path,headers=other).status_code==404
    assert client.put(path,headers=other,json=body(version=1)).status_code==404
    assert transition(client,other,row,'archived').status_code==404
    assert client.get('/api/platform/teachers/games',headers=other).json()['total']==0
    assert client.put(path,headers=h,json=body(version=99)).status_code==409
    assert client.put(path,headers=h,json=body()).status_code==409
    assert client.put(path,headers=h,json=body(version=1,grade=2)).status_code==422
    assert client.get(path).status_code==401


def test_review_publish_snapshot_and_student_visibility(client):
    admin,editor,workspace,_=setup(client)
    h,_=teacher(client); row=new(client,h)
    student=client.post('/api/auth/register',json={'username':'game.student','full_name':'طالب','password':'test-password-123','role':'student','grade':1}).json()
    sh={'Authorization':'Bearer '+student['access_token']}
    def visible(lesson='lesson1-1'):
        r=client.get('/api/learning/lessons/'+lesson,headers=sh)
        assert r.status_code==200,r.text
        return next(r for r in r.json()['resources'] if r['id']=='game').get('items',[])
    assert visible()==[]
    assert client.get('/api/cms/teacher-games',headers=editor).status_code==403
    row=transition(client,h,row,'review').json()
    assert client.get('/api/cms/teacher-games?status=review',headers=admin).json()['total']==1
    r=transition(client,admin,row,'published',True);assert r.status_code==200,r.text;row=r.json()
    assert visible()[0]['game']['kind']=='quiz'
    edited=client.put(f"/api/platform/teachers/games/{row['id']}",headers=h,json=body(version=row['version'],title='مسودة جديدة',lesson_id='lesson1-2')).json()
    assert visible()[0]['title']=='لعبة الجمع' and visible('lesson1-2')==[]
    assert transition(client,admin,row,'published',True).status_code==409
    row=transition(client,admin,edited,'published',True).json()
    assert visible()==[] and visible('lesson1-2')[0]['title']=='مسودة جديدة'
    row=transition(client,h,row,'archived').json()
    assert visible('lesson1-2')==[]
    assert client.put(f"/api/platform/teachers/games/{row['id']}",headers=h,json=body(version=row['version'])).status_code==409
    assert transition(client,h,row,'draft').status_code==200


def test_bank_permission_assignment_and_revocation(client):
    admin,editor,workspace,_=setup(client)
    h,user_id=teacher(client)
    url=f"/api/platform/teachers/game-bank?workspace_id={workspace['id']}"
    assert client.get(url,headers=h).status_code==403
    assert client.get('/api/platform/teachers/game-sources',headers=h).json()['workspaces']==[]
    candidates=client.get('/api/cms/staff?include_teachers=true',headers=admin).json()['items']
    assert user_id in [u['id'] for u in candidates]
    update={k:workspace[k] for k in ['name','team_type','modules','can_publish','active','version','member_ids']};update['member_ids'].append(user_id)
    r=client.put(f"/api/cms/workspaces/{workspace['id']}",headers=admin,json=update);assert r.status_code==200,r.text
    updated=r.json()
    assert client.get(url,headers=h).status_code==200
    assert client.get('/api/platform/teachers/game-sources',headers=h).json()['workspaces'][0]['id']==workspace['id']
    question={'type':'mcq','prompt':'1+1','options':['2','3'],'correct':0}
    assert client.post('/api/cms/exams/bank',headers=editor,json={'workspace_id':workspace['id'],'title':'سؤال الجمع','kind':'question','payload':question}).status_code==201
    assert client.get(url,headers=h).json()['items'][0]['payload']['correct']==0
    # Teacher membership grants bank import, not a CMS login or another user's games.
    assert client.get('/api/cms/me',headers=h).status_code==401
    update={k:updated[k] for k in update};update['active']=False
    assert client.put(f"/api/cms/workspaces/{workspace['id']}",headers=admin,json=update).status_code==200
    assert client.get(url,headers=h).status_code==403


def test_cms_game_publication_and_wrong_module_rejected(client):
    admin,editor,w,_=setup(client,['game','worksheet'],publish=True)
    row=create(client,editor,w,'game',game=game('memory'))
    published=state(client,editor,row,'published');assert published.status_code==200,published.text
    row=create(client,editor,w,'worksheet',game=game())
    assert state(client,editor,row,'published').status_code==422
    row=create(client,editor,w,'game',game={'kind':'quiz','items':[]})
    assert state(client,editor,row,'published').status_code==422


def test_missing_curriculum_cannot_publish_and_generation_denied(client):
    admin,*_=setup(client);h,_=teacher(client)
    row=new(client,h,book_id=None,unit_id=None,lesson_id=None)
    assert transition(client,admin,row,'published',True).status_code==422
    template={'type':'mcq','prompt':'{a}+1','variables':[{'name':'a','minimum':1,'maximum':5,'step':1}],'answer':'a+1','distractors':['answer+1'],'constraints':[]}
    response=client.post('/api/platform/teachers/game-generate',headers=h,json={'workspace_id':1,'template':template,'count':1,'seed':1})
    assert response.status_code==403,response.text
