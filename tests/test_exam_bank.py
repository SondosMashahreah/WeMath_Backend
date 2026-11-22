from fractions import Fraction
import pytest
from pydantic import ValidationError
from app.exams.generator import GenerateRequest, MathTemplate, generate
from app.exams.schemas import Question
from test_cms import setup, create, state


def template(**changes):
    return {'prompt': '{a} / {b}', 'variables': [{'name': 'a', 'minimum': 1, 'maximum': 60}, {'name': 'b', 'minimum': 1, 'maximum': 10}], 'answer': 'a/b', 'constraints': ['a%b==0'], 'explanation': 'الإجابة {answer}', **changes}


def test_division_unique_exact_deterministic_and_nonnegative_subtraction():
    request = GenerateRequest(workspace_id=1, template=template(), count=30, seed=42)
    items = generate(request)
    assert items == generate(request)
    assert len({q['prompt'] for q in items}) == 30
    for q in items:
        a, b = map(int, q['prompt'].split(' / '))
        assert a % b == 0
        assert Fraction(q['options'][q['correct']]) == Fraction(a, b)
        assert len(set(q['options'])) == len(q['options'])
    items = generate(GenerateRequest(workspace_id=1, template=template(prompt='{a} - {b}', answer='a-b', constraints=['a>=b']), count=30))
    assert all(Fraction(q['options'][q['correct']]) >= 0 for q in items)


def test_true_false_math_braces_fractions_and_zero_rejection():
    items = generate(GenerateRequest(workspace_id=1, template=template(type='true_false', prompt='${a} > {b}$', answer='a>b', constraints=[]), count=30, seed=6))
    assert {q['correct'] for q in items} == {0, 1}
    for q in items:
        a, b = map(int, q['prompt'].strip('$').split(' > '))
        assert q['correct'] == (0 if a > b else 1)
        assert q['options'] == ['صح', 'خطأ']
    items = generate(GenerateRequest(workspace_id=1, template=template(prompt=r'$\frac{{{a}}}{{{b}}}$', constraints=[]), count=10))
    assert all(r'\frac{' in q['prompt'] and '{{' not in q['prompt'] for q in items)
    t = template(variables=[{'name': 'a', 'minimum': 1, 'maximum': 4}, {'name': 'b', 'minimum': 0, 'maximum': 1}], constraints=[])
    items = generate(GenerateRequest(workspace_id=1, template=t, count=4))
    assert all(q['prompt'].endswith(' / 1') for q in items)


@pytest.mark.parametrize('expression', ["__import__('os')", 'a.real', 'a[0]', '[a for a in b]', '2.5', 'a+unknown', 'sum(a)', 'a' * 201])
def test_unsafe_expressions_rejected(expression):
    with pytest.raises(ValidationError): MathTemplate(**template(answer=expression))


@pytest.mark.parametrize('changes', [
    {'constraints': ['a<0']}, {'distractors': ['answer']}, {'answer': 'a/0'},
    {'variables': [{'name': 'a', 'minimum': 1, 'maximum': 1}, {'name': 'b', 'minimum': 1, 'maximum': 1}]},
])
def test_impossible_generation_does_not_return_partial_results(changes):
    with pytest.raises(ValueError, match='تعذر توليد'):
        generate(GenerateRequest(workspace_id=1, template=template(**changes), count=5))


def test_image_and_question_contract():
    legacy = Question(prompt='1+1', options=['2', '3'], correct=0)
    assert legacy.type == 'mcq' and legacy.points == 1
    for url in ['javascript:alert(1)', 'http://example.org/a.png', 'https://user:pass@example.org/x']:
        with pytest.raises(ValidationError): Question(**{**legacy.model_dump(), 'image_url': url, 'image_alt': 'image'})
    with pytest.raises(ValidationError): Question(**{**legacy.model_dump(), 'type': 'true_false'})
    with pytest.raises(ValidationError): Question(**{**legacy.model_dump(), 'image_url': 'https://example.org/a.png'})


def test_bank_permissions_filters_archive_conflicts_and_independent_reuse(client):
    admin, editor, workspace, _ = setup(client)
    base = '/api/cms/exams'
    other = client.post('/api/cms/workspaces', headers=admin, json={'name': 'فريق آخر', 'modules': ['quiz']}).json()
    data = {'workspace_id': workspace['id'], 'kind': 'question', 'title': 'مقارنة الأعداد', 'grade': 4, 'topic': 'أعداد', 'difficulty': 'easy', 'payload': {'type': 'true_false', 'prompt': '2>1', 'options': ['صح', 'خطأ'], 'correct': 0, 'image_url': 'https://example.org/q.png', 'image_alt': 'خط أعداد', 'points': 3}}
    assert client.post(base+'/bank', json=data).status_code == 401
    response = client.post(base+'/bank', headers=editor, json=data)
    assert response.status_code == 201, response.text
    row = response.json()
    url = base+f"/bank?workspace_id={workspace['id']}"
    assert client.get(url+'&grade=4&difficulty=easy&q=أعداد', headers=editor).json()['total'] == 1
    assert client.get(url+'&grade=5', headers=editor).json()['total'] == 0
    assert client.get(base+f"/bank?workspace_id={other['id']}", headers=editor).status_code == 403
    assert client.post(base+'/bank', headers=editor, json={**data, 'workspace_id': other['id']}).status_code == 403
    foreign = client.post(base+'/bank', headers=admin, json={**data, 'workspace_id': other['id']}).json()
    assert client.patch(base+f"/bank/{foreign['id']}", headers=editor, json={'version': 1, 'archived': True}).status_code == 403
    content = create(client, editor, workspace, module='quiz', questions=[row['payload']])
    response = state(client, admin, content, 'published'); assert response.status_code == 200, response.text
    content = response.json()
    payload = content['payload']; payload['questions'][0]['prompt'] = 'changed draft'
    response = client.put(f"/api/cms/content/{content['id']}", headers=editor, json={**{k: content[k] for k in ['workspace_id', 'module', 'title', 'version']}, 'payload': payload})
    assert response.status_code == 200, response.text
    assert client.get(url, headers=editor).json()['items'][0]['payload']['prompt'] == '2>1'
    with client.db_sessions() as db:
        from app.cms.models import PublishedResource
        live = db.get(PublishedResource, content['id']).payload['questions'][0]
        assert live['prompt'] == '2>1' and live['points'] == 3 and live['image_alt'] == 'خط أعداد'
    endpoint = base+f"/bank/{row['id']}"
    assert client.patch(endpoint, headers=editor, json={'version': 1, 'archived': True}).status_code == 200
    assert client.patch(endpoint, headers=editor, json={'version': 1, 'archived': False}).status_code == 409
    assert client.get(url, headers=editor).json()['total'] == 0
    assert client.get(url+'&archived=true', headers=editor).json()['total'] == 1
    assert client.patch(endpoint, headers=editor, json={'version': 2, 'archived': False}).status_code == 200


def test_generator_and_bank_reject_non_quiz_editors_and_invalid_complete_items(client):
    admin, editor, workspace, _ = setup(client, modules=['worksheet'])
    request = {'workspace_id': workspace['id'], 'template': template(), 'count': 5}
    assert client.post('/api/cms/exams/generate', headers=editor, json=request).status_code == 403
    response = client.post('/api/cms/exams/generate', headers=admin, json=request)
    assert response.status_code == 200, response.text
    for kind, payload in [('template', template()), ('exam', {'instructions': 'حل الأسئلة', 'questions': response.json()['questions']})]:
        data = {'workspace_id': workspace['id'], 'kind': kind, 'title': 'قالب رياضيات', 'payload': payload}
        assert client.post('/api/cms/exams/bank', headers=editor, json=data).status_code == 403
        assert client.post('/api/cms/exams/bank', headers=admin, json=data).status_code == 201
    data = {'workspace_id': workspace['id'], 'kind': 'question', 'title': 'غير مكتمل', 'payload': {'prompt': '', 'options': ['', ''], 'correct': -1}}
    assert client.post('/api/cms/exams/bank', headers=admin, json=data).status_code == 422
