import pytest
from sqlalchemy import select
from app.models import User
from app.cms.models import StaffProfile, MediaAsset
from app.cms.catalog import MODULES
from app.cms.invitations import invitation_preview
from app.core.config import settings
from test_cms import account, setup, create, state, PASSWORD

PNG = b'\x89PNG\r\n\x1a\n' + b'initial-test-content'
MP4 = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 12


@pytest.mark.parametrize('kind', ['students', 'teachers', 'other'])
def test_create_team_defaults_all_modules_email_and_disabled_invitation(client, kind, monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, 'SMTP', lambda *a, **k: pytest.fail('Email must remain disabled'))
    admin = account(client, 'admin', True)
    response = client.post('/api/cms/staff', headers=admin, json={'full_name': 'فريق جديد', 'username': 'newstaff', 'password': PASSWORD, 'email': 'Team@Example.org', 'team_type': kind, 'create_workspace': True})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['email'] == 'team@example.org' and result['invitation_status'] == 'disabled'
    assert PASSWORD not in response.text and 'password' not in response.text
    token = client.post('/api/auth/login', json={'username': 'newstaff', 'password': PASSWORD}).json()['access_token']
    staff = {'Authorization': 'Bearer ' + token}
    profile = client.get('/api/cms/me', headers=staff).json()
    workspace = profile['workspaces'][0]
    assert set(workspace['modules']) == set(MODULES) and workspace['team_type'] == kind
    assert not workspace['can_publish'] and not profile['is_admin']
    assert client.get('/api/cms/staff', headers=staff).status_code == 403
    assert client.get(f'/api/cms/staff?team_type={kind}', headers=admin).json()['total'] == 1
    with client.db_sessions() as db:
        assert db.get(User, result['id']).password_hash != PASSWORD
        assert db.get(StaffProfile, result['id']).invitation_status == 'disabled'
    assert invitation_preview('Name', 'newstaff', kind)['status'] == 'disabled'
    duplicate = client.post('/api/cms/staff', headers=admin, json={'full_name': 'اسم آخر', 'username': 'second', 'password': PASSWORD, 'email': 'TEAM@example.org'})
    assert duplicate.status_code == 409
    invalid = client.post('/api/cms/staff', headers=admin, json={'full_name': 'اسم آخر', 'username': 'third', 'password': PASSWORD, 'email': 'broken'})
    assert invalid.status_code == 422


def upload(client, headers, workspace, module='story_video', content=PNG):
    return client.post(f"/api/cms/media?workspace_id={workspace['id']}&module={module}&filename=test.png", headers={**headers, 'Content-Type': 'application/octet-stream'}, content=content)


def test_media_scoping_publication_snapshot_withdrawal_and_ranges(client):
    admin, editor, workspace, _ = setup(client, ['story_video', 'film', 'worksheet', 'initiatives'], True)
    other = client.post('/api/cms/workspaces', headers=admin, json={'name': 'آخر', 'modules': ['story_video']}).json()
    response = upload(client, editor, workspace)
    assert response.status_code == 201, response.text
    item = response.json(); key = item['asset_id']
    assert client.get(f'/api/media/{key}').status_code == 404
    assert client.get(f'/api/cms/media/{key}').status_code == 401
    assert client.get(f'/api/cms/media/{key}', headers=editor).content == PNG
    assert upload(client, editor, other).status_code == 403
    ref = {'asset_id': key, 'kind': 'image', 'alt': 'وصف الصورة', 'caption': 'تعليق'}
    bad = client.post('/api/cms/content', headers=admin, json={'workspace_id': other['id'], 'module': 'story_video', 'title': 'محتوى', 'payload': {'media': [ref]}})
    assert bad.status_code == 422
    row = create(client, editor, workspace, 'story_video', media=[ref])
    live = state(client, editor, row, 'published')
    assert live.status_code == 200, live.text
    response = client.get(f'/api/media/{key}', headers={'Range': 'bytes=0-7'})
    assert response.status_code == 206 and response.content == PNG[:8]
    assert response.headers['content-range'] == f'bytes 0-7/{len(PNG)}'
    assert client.get(f'/api/media/{key}', headers={'Range': 'bytes=-3'}).content == PNG[-3:]
    assert client.get(f'/api/media/{key}', headers={'Range': 'bytes=999-1000'}).status_code == 416
    edit = {k: live.json()[k] for k in ('workspace_id', 'module', 'title', 'payload', 'version')}
    edit['payload']['media'] = []
    changed = client.put(f"/api/cms/content/{row['id']}", headers=editor, json=edit).json()
    assert client.get(f'/api/media/{key}').status_code == 200  # Old live snapshot stays available.
    assert state(client, editor, changed, 'published').status_code == 200
    assert client.get(f'/api/media/{key}').status_code == 404
    row2 = create(client, editor, workspace, 'story_video', media=[ref])
    live2 = state(client, editor, row2, 'published').json()
    assert client.get(f'/api/media/{key}').status_code == 200
    assert state(client, editor, live2, 'archived').status_code == 200
    assert client.get(f'/api/media/{key}').status_code == 404


def test_formats_size_quota_and_module_rules(client, monkeypatch):
    _, editor, workspace, _ = setup(client, ['worksheet', 'film'], True)
    assert upload(client, editor, workspace, 'film', MP4).status_code == 201
    assert upload(client, editor, workspace, 'film', PNG).status_code == 422
    assert upload(client, editor, workspace, 'worksheet', MP4).status_code == 422
    assert upload(client, editor, workspace, 'worksheet', b'<svg onload="alert(1)"/>').status_code == 415
    assert upload(client, editor, workspace, 'worksheet', PNG + b'x' * (8 * 1024 * 1024)).status_code == 413
    monkeypatch.setattr(settings, 'CMS_MEDIA_WORKSPACE_MB', 0)
    assert upload(client, editor, workspace, 'worksheet', PNG).status_code == 413


def test_worksheet_questions_and_image_and_initiative_video(client):
    _, editor, workspace, _ = setup(client, ['worksheet', 'initiatives'], True)
    item = upload(client, editor, workspace, 'worksheet').json()
    ref = {'asset_id': item['asset_id'], 'kind': 'image', 'alt': '', 'caption': ''}
    row = create(client, editor, workspace, 'worksheet', media=[ref], questions=[{'prompt': '2>1', 'type': 'true_false', 'options': ['صح', 'خطأ'], 'correct': 0}])
    assert state(client, editor, row, 'published').status_code == 422
    row['payload']['media'][0]['alt'] = 'رسم'
    changed = client.put(f"/api/cms/content/{row['id']}", headers=editor, json={k:row[k] for k in ('workspace_id','module','title','payload','version')}).json()
    assert state(client, editor, changed, 'published').status_code == 200
    video = upload(client, editor, workspace, 'initiatives', MP4).json()
    initiative = create(client, editor, workspace, 'initiatives', summary='مبادرة', category='schools', media=[{'asset_id': video['asset_id'], 'kind': 'video'}])
    assert state(client, editor, initiative, 'published').status_code == 200
    payload = client.get(f"/api/platform/entries/cms-{initiative['id']}").json()
    assert payload['details']['media'][0]['asset_id'] == video['asset_id']
