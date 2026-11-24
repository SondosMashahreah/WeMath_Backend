import pytest
from sqlalchemy import select
from app.models import Role, UserRole, User
from app.cms.models import Content
from app.platform.models import PlatformEntry

PASSWORD = "test-password-123"


def account(client, username, admin=False):
    response = client.post('/api/auth/register', json={'username': username, 'password': PASSWORD, 'full_name': username, 'role': 'parent'})
    assert response.status_code == 201, response.text
    data = response.json()
    if admin:
        with client.db_sessions() as db:
            role = db.scalar(select(Role).where(Role.name == 'admin'))
            db.add(UserRole(user_id=data['user']['id'], role_id=role.id)); db.commit()
    return {'Authorization': f"Bearer {data['access_token']}"}


def setup(client, modules=None, publish=False):
    admin = account(client, 'administrator', True)
    response = client.post('/api/cms/staff', headers=admin, json={'username': 'editor', 'full_name': 'مدخل بيانات', 'password': PASSWORD})
    assert response.status_code == 201, response.text
    editor_id = response.json()['id']
    editor = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json={'username': 'editor', 'password': PASSWORD}).json()['access_token']}
    response = client.post('/api/cms/workspaces', headers=admin, json={'name': 'فريق الاختبارات', 'modules': modules or ['quiz', 'worksheet'], 'member_ids': [editor_id], 'can_publish': publish})
    assert response.status_code == 201, response.text
    return admin, editor, response.json(), editor_id


def create(client, headers, workspace, module='worksheet', **payload):
    data = {'workspace_id': workspace['id'], 'module': module, 'title': 'مادة جديدة', 'payload': {'body': 'تفاصيل تعليمية', 'lesson_id': 'lesson1-1', **payload}}
    response = client.post('/api/cms/content', headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def state(client, headers, row, status):
    return client.post(f"/api/cms/content/{row['id']}/status", headers=headers, json={'status': status, 'version': row['version']})


def test_only_admin_can_delegate_and_public_registration_cannot_escalate(client):
    regular = account(client, 'outsider')
    assert client.get('/api/cms/me', headers=regular).status_code == 403
    assert client.get('/api/cms/staff', headers=regular).status_code == 403
    assert client.post('/api/auth/register', json={'username': 'hacker', 'full_name': 'Hacker', 'password': PASSWORD, 'role': 'admin'}).status_code == 422
    admin, editor, workspace, editor_id = setup(client)
    assert client.post('/api/cms/workspaces', headers=editor, json={'name': 'forbidden', 'modules': ['quiz']}).status_code == 403
    assert client.get('/api/cms/audit', headers=editor).status_code == 403
    assert client.get('/api/cms/me', headers=editor).json()['workspaces'][0]['id'] == workspace['id']


def test_workspace_and_module_permissions_cover_reads_writes_and_templates(client):
    admin, editor, workspace, _ = setup(client)
    other = client.post('/api/cms/workspaces', headers=admin, json={'name': 'ورشات', 'modules': ['workshops']}).json()
    row = create(client, admin, other, 'workshops')
    assert client.get(f"/api/cms/content/{row['id']}", headers=editor).status_code == 403
    assert client.get('/api/cms/content', headers=editor).json()['total'] == 0
    assert client.get(f"/api/cms/content?workspace_id={other['id']}", headers=editor).status_code == 403
    assert client.get(f"/api/cms/templates/workshops?workspace_id={workspace['id']}", headers=editor).status_code == 403
    assert client.post('/api/cms/content', headers=editor, json={'workspace_id': workspace['id'], 'module': 'workshops', 'title': 'حيلة', 'payload': {}}).status_code == 403
    valid = create(client, editor, workspace)
    moved = {key: valid[key] for key in ('workspace_id', 'module', 'title', 'payload', 'version')}; moved['workspace_id'] = other['id']
    assert client.put(f"/api/cms/content/{valid['id']}", headers=editor, json=moved).status_code == 422


def test_publication_review_snapshot_and_archive_reach_real_student_api(client):
    admin, editor, workspace, _ = setup(client)
    row = create(client, editor, workspace, source_url='https://example.org/work.pdf')
    student = client.post('/api/auth/register', json={'username': 'student', 'full_name': 'طالب', 'password': PASSWORD, 'role': 'student', 'grade': 1}).json()
    headers = {'Authorization': 'Bearer ' + student['access_token']}
    def resource():
        result = client.get('/api/learning/lessons/lesson1-1', headers=headers)
        assert result.status_code == 200, result.text
        return next(r for r in result.json()['resources'] if r['id'] == 'worksheet')
    assert 'items' not in resource()
    assert state(client, editor, row, 'published').status_code == 403
    reviewed = state(client, editor, row, 'review').json()
    published = state(client, admin, reviewed, 'published')
    assert published.status_code == 200, published.text
    assert resource()['items'][0]['url'] == 'https://example.org/work.pdf'
    row = published.json()
    edit = {key: row[key] for key in ('workspace_id', 'module', 'title', 'payload', 'version')}
    edit['title'] = 'مسودة معدلة'
    draft = client.put(f"/api/cms/content/{row['id']}", headers=editor, json=edit).json()
    assert draft['status'] == 'draft'
    assert resource()['items'][0]['title'] == 'مادة جديدة'
    assert state(client, editor, draft, 'archived').status_code == 403
    updated = state(client, admin, draft, 'published').json()
    assert resource()['items'][0]['title'] == 'مسودة معدلة'
    assert state(client, admin, updated, 'archived').status_code == 200
    assert 'items' not in resource()


def test_permission_changes_and_disabled_users_apply_to_existing_sessions(client):
    admin, editor, workspace, editor_id = setup(client)
    row = create(client, editor, workspace)
    body = {key: workspace[key] for key in ('name', 'modules', 'member_ids', 'can_publish', 'active', 'version')}
    body['member_ids'] = []
    response = client.put(f"/api/cms/workspaces/{workspace['id']}", headers=admin, json=body)
    assert response.status_code == 200
    assert client.get(f"/api/cms/content/{row['id']}", headers=editor).status_code == 403
    assert client.patch(f'/api/cms/staff/{editor_id}', headers=admin, json={'is_active': False}).status_code == 200
    assert client.get('/api/cms/me', headers=editor).status_code == 401


def test_stale_versions_cannot_overwrite_content_or_workspace(client):
    admin, editor, workspace, _ = setup(client)
    row = create(client, editor, workspace)
    newer = state(client, editor, row, 'review')
    assert newer.status_code == 200
    assert state(client, admin, row, 'published').status_code == 409
    edit = {key: row[key] for key in ('workspace_id', 'module', 'title', 'payload', 'version')}
    assert client.put(f"/api/cms/content/{row['id']}", headers=editor, json=edit).status_code == 409
    body = {key: workspace[key] for key in ('name', 'modules', 'member_ids', 'can_publish', 'active', 'version')}
    assert client.put(f"/api/cms/workspaces/{workspace['id']}", headers=admin, json=body).status_code == 200
    assert client.put(f"/api/cms/workspaces/{workspace['id']}", headers=admin, json=body).status_code == 409


def test_import_is_atomic_paginated_and_draft_only(client):
    admin, editor, workspace, _ = setup(client)
    item = {'workspace_id': workspace['id'], 'module': 'worksheet', 'title': 'دفعة بيانات', 'payload': {}}
    bad = {**item, 'module': 'competitions'}
    assert client.post('/api/cms/import', headers=editor, json={'items': [item, bad]}).status_code == 403
    assert client.get('/api/cms/content', headers=admin).json()['total'] == 0
    assert client.post('/api/cms/import', headers=editor, json={'items': [item] * 30}).json()['created'] == 30
    page = client.get('/api/cms/content?offset=25&limit=25&q=دفعة', headers=editor).json()
    assert page['total'] == 30 and len(page['items']) == 5
    assert page['counts'] == {'draft': 30}
    assert client.post('/api/cms/import', headers=editor, json={'items': [item] * 101}).status_code == 422


def test_publishing_validates_quiz_lessons_categories_and_links(client):
    admin, editor, workspace, _ = setup(client, ['quiz', 'workshops'], True)
    row = create(client, editor, workspace, 'quiz', lesson_id='does-not-exist')
    assert state(client, editor, row, 'published').status_code == 422
    row = create(client, editor, workspace, 'quiz', questions=[{'prompt': 'Question', 'options': ['a', 'b'], 'correct': 4}])
    assert state(client, editor, row, 'published').status_code == 422
    row = create(client, editor, workspace, 'workshops', category='wrong')
    assert state(client, editor, row, 'published').status_code == 422
    response = client.post('/api/cms/content', headers=editor, json={'workspace_id': workspace['id'], 'module': 'quiz', 'title': 'unsafe url', 'payload': {'source_url': 'javascript:alert(1)'}})
    assert response.status_code == 422


def test_platform_publication_and_legacy_adoption_keep_existing_url(client):
    admin, editor, workspace, _ = setup(client, ['workshops'], True)
    row = create(client, editor, workspace, 'workshops', category='scientific', summary='ملخص', event_date='2026-11-22')
    published = state(client, editor, row, 'published')
    assert published.status_code == 200, published.text
    assert client.get(f"/api/platform/entries/cms-{row['id']}").json()['title'] == row['title']
    with client.db_sessions() as db:
        db.add(PlatformEntry(id='old-workshop', section='workshops', category='scientific', title='ورشة سابقة', summary='ملخص', body='تفاصيل', published=True, archived=False, is_demo=False)); db.commit()
    response = client.post('/api/cms/legacy/adopt', headers=admin, json={'entry_id': 'old-workshop', 'workspace_id': workspace['id']})
    assert response.status_code == 201, response.text
    adopted = response.json()
    assert client.post('/api/cms/legacy/adopt', headers=admin, json={'entry_id': 'old-workshop', 'workspace_id': workspace['id']}).status_code == 409
    edit = {key: adopted[key] for key in ('workspace_id', 'module', 'title', 'payload', 'version')}; edit['title'] = 'ورشة محدثة'; edit['payload']['event_date'] = '2026-11-22'
    updated = client.put(f"/api/cms/content/{adopted['id']}", headers=admin, json=edit).json()
    assert state(client, admin, updated, 'published').status_code == 200
    assert client.get('/api/platform/entries/old-workshop').json()['title'] == 'ورشة محدثة'
    assert client.get('/api/cms/legacy', headers=editor).status_code == 403


def test_removed_module_remains_visible_to_admin_only(client):
    admin, editor, workspace, _ = setup(client)
    row = create(client, editor, workspace)
    body = {key: workspace[key] for key in ('name', 'modules', 'member_ids', 'can_publish', 'active', 'version')}; body['modules'] = ['quiz']
    assert client.put(f"/api/cms/workspaces/{workspace['id']}", headers=admin, json=body).status_code == 200
    assert client.get('/api/cms/content', headers=editor).json()['total'] == 0
    assert client.get('/api/cms/content', headers=admin).json()['total'] == 1
    assert client.get(f"/api/cms/content/{row['id']}", headers=admin).status_code == 200


@pytest.mark.parametrize("activity", ["quiz", "worksheet", "film", "activity", "game", "story_video"])
def test_new_resource_buttons_record_progress_without_validation_errors(client, activity):
    session = client.post('/api/auth/register', json={'username': 'student-progress', 'full_name': 'طالب', 'password': PASSWORD, 'role': 'student', 'grade': 1}).json()
    headers = {'Authorization': 'Bearer ' + session['access_token']}
    response = client.put('/api/learning/lessons/lesson1-1/progress', headers=headers, json={'activity': activity})
    assert response.status_code == 200, response.text
    assert response.json()['last_activity'] == activity
