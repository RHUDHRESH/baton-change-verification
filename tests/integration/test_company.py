from fastapi.testclient import TestClient
import os


def test_company_story_is_grounded_in_world_and_citations(service):
    client = TestClient(service.app)
    company = client.get('/api/company').json()
    data = client.get('/api/demo?seed=7').json()
    assert company['fictional'] and company['name'] == 'Halden'
    assert len(company['work']) == 6
    risks = {r['duty'] for r in data['lanes']['G']['failures']}
    assert {w['id'] for w in company['work']} == risks
    sources = {s['id'] for s in company['sources']}
    assert all(s['id'] in sources for r in data['lanes']['G']['failures'] for s in r['sources'])
    assert any('Our launch depends on it' in s['text'] for s in company['sources'])
    for path in ('/', '/amb.html', '/rehearsal.html', '/benchmark.html'):
        assert client.get(path).status_code == 200
    assert 'Fictional company' in client.get('/sandbox.html').text
    assert 'Run available checks' not in client.get('/').text
    assert 'Hana’s handover' in client.get('/sandbox.html').text
    homepage = client.get('/').text
    assert 'PUBLIC ENGINEERING WORKBOARD' in homepage
    assert 'Turn an issue into' in homepage and 'work you can verify.' in homepage
    assert 'id="executions"' in homepage
    assert 'code checks run by Codex in an isolated Docker environment' in homepage
    assert 'it does not launch a Rust build' in homepage


def test_follow_up_tasks_require_operator_and_persist(service):
    anonymous = TestClient(service.app)
    body = {'title':'Confirm CSV format with Bao','work_id':'promise-oaktree-clinics-csv-encoding',
            'owner':'elena.silva','due':'2026-11-03','notes':'Review the customer’s requested encoding.'}
    assert anonymous.get('/api/company/tasks').status_code == 401
    assert anonymous.post('/api/company/tasks',json=body).status_code == 401
    client = TestClient(service.app)
    assert client.post('/api/auth/login',json={'token':os.environ['BATON_OPERATOR_TOKEN']}).status_code == 200
    people = client.get('/api/demo').json()['people']
    body['owner'] = next(p['id'] for p in people if p['left_at'] is None and p['id']!='hana.sharma')
    created = client.post('/api/company/tasks',json=body)
    assert created.status_code == 201, created.text
    task = created.json()
    assert task['status']=='todo' and task['created_by']=='local_operator'
    assert client.get('/api/company/tasks').json()['tasks']==[task]
    assert anonymous.patch('/api/company/tasks/'+task['id'],json={'status':'done'}).status_code==401
    done=client.patch('/api/company/tasks/'+task['id'],json={'status':'done'}).json()
    assert done['completed_at'] and done['status']=='done'
    assert client.get('/api/company/tasks').json()['tasks'][0]==done
    assert client.patch('/api/company/tasks/'+task['id'],json={'status':'todo'}).json()['completed_at'] is None
    for change in ({'owner':'hana.sharma'},{'owner':'unknown'},{'work_id':'../../outside'},{'title':' '},{'due':'not-a-date'},{'title':'x'*161}):
        assert client.post('/api/company/tasks',json={**body,**change}).status_code==422
    assert client.patch('/api/company/tasks/'+task['id'],json={'status':'destroy'}).status_code==422
    assert client.post('/api/company/tasks',json=body,headers={'Origin':'https://attacker.invalid'}).status_code==403
    assert len(client.get('/api/company/tasks').json()['tasks'])==1
