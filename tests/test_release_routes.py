"""Real FastAPI release boundaries; provider and control I/O are mocked."""
import copy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from server import release_contract as C
from server import release_gate as gate
from server import security

ID = 'a' * 32
RUN = 'b' * 32
HASH = 'c' * 64
PLAN_BODY = {'change_id': C.CHANGE_ID}
EXECUTE_BODY = {'expected_plan_hash': HASH, 'publish_targets': ['jira', 'slack']}
REAL_EXECUTE = gate.execute
REAL_AUTHENTICATE = gate.authenticate


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    # Import only after test hosts are configured; other suites share this app.
    monkeypatch.setenv('BATON_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
    from server import app as service
    token, cookie = 'test-release-operator-' + 'x' * 32, 'mock-release-session'
    monkeypatch.setenv('BATON_OPERATOR_TOKEN', token)
    monkeypatch.setattr(service, 'DATA', tmp_path)
    auth_db = MagicMock()
    auth_db.get.side_effect = lambda key: security.digest(token) if key == 'baton:session:' + security.digest(cookie) else None
    monkeypatch.setattr(service, 'auth_db', lambda: auth_db)
    plan = {'id': ID, 'change_id': C.CHANGE_ID, 'source_commit': C.SOURCE_COMMIT, 'plan_hash': HASH,
            'plan_status': 'ready', 'required_checks': list(C.CHECKS.values()), 'environments': list(C.ENVIRONMENTS),
            'source_versions': [{'id': 'source-real', 'sha256': 'd' * 64}], 'witness_paths': [{'id': 'witness-real'}],
            'investigation': {'status': 'succeeded', 'receipts': [{'id': 'groq-real'}]}, 'latest_run_id': None}
    create = MagicMock(return_value=plan)
    execute = MagicMock(return_value={'id': RUN, 'plan_id': ID, 'status': 'queued'})
    read_plan = MagicMock(return_value=plan)
    read_run = MagicMock(return_value={'id': RUN, 'plan_id': ID, 'status': 'completed', 'decision': 'blocked'})
    evidence = MagicMock(return_value=b'{"verified":true}\r\n')
    auth = MagicMock(side_effect=gate.ReleaseError('secret callback mismatch'))
    operations = {name: MagicMock(return_value={'id': RUN, 'status': 'verifying'}) for name in ('event', 'complete', 'publish_result')}
    for name, mock in [('create_plan', create), ('execute', execute), ('read_plan', read_plan), ('read_run', read_run), ('evidence', evidence), ('authenticate', auth), *operations.items()]:
        monkeypatch.setattr(gate, name, mock)
    client = TestClient(service.app, base_url='http://localhost', raise_server_exceptions=False)
    return SimpleNamespace(service=service, client=client, cookie=cookie, plan=plan, create=create, execute=execute,
                           read_plan=read_plan, read_run=read_run, evidence=evidence, auth=auth, operations=operations)


def operator(boundary):
    boundary.client.cookies.set(security.COOKIE, boundary.cookie)
    return boundary.client


@pytest.mark.parametrize('path,body', [('/api/public/release-plans', PLAN_BODY), (f'/api/public/release-plans/{ID}/execute', EXECUTE_BODY)])
@pytest.mark.parametrize('cookie', [None, 'forged-cookie'])
def test_anonymous_or_forged_operator_cannot_investigate_or_dispatch(boundary, path, body, cookie):
    if cookie:
        boundary.client.cookies.set(security.COOKIE, cookie)
    assert boundary.client.post(path, json=body).status_code == 401
    boundary.create.assert_not_called(); boundary.execute.assert_not_called()


def test_operator_creates_one_sealed_plan_with_exact_selected_change(boundary):
    response = operator(boundary).post('/api/public/release-plans', json=PLAN_BODY)
    assert response.status_code == 201
    boundary.create.assert_called_once_with(boundary.service.DATA, boundary.service.PORT, C.CHANGE_ID)
    assert response.json() == boundary.plan
    assert {'source_commit', 'plan_hash', 'required_checks', 'environments', 'source_versions', 'witness_paths'} <= response.json().keys()
    boundary.execute.assert_not_called()


def test_operator_execute_forwards_only_sealed_hash_and_approved_destinations(boundary):
    response = operator(boundary).post(f'/api/public/release-plans/{ID}/execute', json=EXECUTE_BODY)
    assert response.status_code == 202
    boundary.execute.assert_called_once_with(boundary.service.DATA, boundary.service.PORT, ID, HASH, ['jira', 'slack'])
    boundary.create.assert_not_called()


@pytest.mark.parametrize('extra', ['source_commit', 'required_checks', 'source_versions', 'witness_paths', 'plan_hash', 'command', 'repository', 'decision'])
def test_plan_client_cannot_supply_or_replace_server_sealed_fields(boundary, extra):
    response = operator(boundary).post('/api/public/release-plans', json={**PLAN_BODY, extra: 'attacker supplied'})
    assert response.status_code == 422
    boundary.create.assert_not_called()


@pytest.mark.parametrize('mutation', ['missing-hash', 'wrong-hash', 'uppercase-hash', 'extra-command', 'extra-source', 'missing-target', 'unknown-target', 'extra-target'])
def test_invalid_execution_schema_cannot_reach_dispatch(boundary, mutation):
    body = copy.deepcopy(EXECUTE_BODY)
    if mutation == 'missing-hash': del body['expected_plan_hash']
    elif mutation == 'wrong-hash': body['expected_plan_hash'] = 'not-a-hash'
    elif mutation == 'uppercase-hash': body['expected_plan_hash'] = HASH.upper()
    elif mutation == 'extra-command': body['command'] = 'arbitrary shell'
    elif mutation == 'extra-source': body['source_commit'] = 'substitute'
    elif mutation == 'missing-target': body['publish_targets'] = ['jira']
    elif mutation == 'unknown-target': body['publish_targets'] = ['jira', 'email']
    else: body['publish_targets'] = ['jira', 'slack', 'jira']
    assert operator(boundary).post(f'/api/public/release-plans/{ID}/execute', json=body).status_code == 422
    boundary.execute.assert_not_called()


@pytest.mark.parametrize('path,body', [('/api/public/release-plans', PLAN_BODY), (f'/api/public/release-plans/{ID}/execute', EXECUTE_BODY), (f'/api/public/release-runs/{RUN}/publish', {})])
@pytest.mark.parametrize('headers', [{'Origin': 'https://evil.invalid'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_cross_site_state_changes_are_denied_before_provider_or_callback_auth(boundary, path, body, headers):
    assert operator(boundary).post(path, json=body, headers=headers).status_code == 403
    boundary.create.assert_not_called(); boundary.execute.assert_not_called(); boundary.auth.assert_not_called()
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize('path', ['/api/public/release-plans', f'/api/public/release-plans/{ID}/execute', f'/api/public/release-runs/{RUN}/complete'])
def test_body_limit_precedes_all_auth_and_privileged_work(boundary, path):
    assert operator(boundary).post(path, json={'payload': 'x' * 66000}).status_code == 413
    boundary.create.assert_not_called(); boundary.execute.assert_not_called(); boundary.auth.assert_not_called()
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize('operation', ['events', 'complete', 'publish'])
def test_callback_missing_or_invalid_capability_cannot_reach_effects(boundary, operation):
    response = operator(boundary).post(f'/api/public/release-runs/{RUN}/{operation}', json={'decision': 'passed'})
    assert response.status_code == 401
    assert 'secret' not in response.text
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize('operation,function', [('events', 'event'), ('complete', 'complete'), ('publish', 'publish_result')])
def test_exact_valid_run_capability_needs_no_operator_session(boundary, monkeypatch, operation, function):
    monkeypatch.setattr(gate, 'authenticate', REAL_AUTHENTICATE)
    control = MagicMock()
    control.get.side_effect = lambda key: C.sha('valid-run-token') if key == 'release:callback:' + RUN else None
    monkeypatch.setattr(gate, 'connect', lambda port: control)
    payload = {'github_run_id': '123', 'sequence': 1}
    response = boundary.client.post(f'/api/public/release-runs/{RUN}/{operation}', json=payload, headers={'Authorization': 'Bearer valid-run-token'})
    assert response.status_code == 200
    boundary.operations[function].assert_called_once_with(boundary.service.DATA, boundary.service.PORT, RUN, payload)
    boundary.create.assert_not_called(); boundary.execute.assert_not_called()


@pytest.mark.parametrize('identity,bearer', [(RUN, 'forged'), (ID, 'valid-run-token'), (RUN, ''), (RUN, 'Bearer valid-run-token')])
def test_capability_is_bound_to_exact_run_and_bearer_format(boundary, monkeypatch, identity, bearer):
    monkeypatch.setattr(gate, 'authenticate', REAL_AUTHENTICATE)
    control = MagicMock()
    control.get.side_effect = lambda key: C.sha('valid-run-token') if key == 'release:callback:' + RUN else None
    monkeypatch.setattr(gate, 'connect', lambda port: control)
    # The final case deliberately supplies a nested Bearer prefix.
    response = boundary.client.post(f'/api/public/release-runs/{identity}/complete', json={}, headers={'Authorization': 'Bearer ' + bearer})
    assert response.status_code == 401
    for mock in boundary.operations.values(): mock.assert_not_called()


def test_unknown_callback_operation_is_not_callable(boundary):
    assert boundary.client.post(f'/api/public/release-runs/{RUN}/repair', json={}).status_code == 422
    boundary.auth.assert_not_called()
    for mock in boundary.operations.values(): mock.assert_not_called()


@pytest.mark.parametrize('operation,function', [('events', 'event'), ('complete', 'complete'), ('publish', 'publish_result')])
def test_unexpected_callback_crash_is_sanitized_and_cannot_claim_completion(boundary, operation, function):
    boundary.auth.side_effect = None
    boundary.operations[function].side_effect = RuntimeError('provider-secret-do-not-expose')
    response = boundary.client.post(f'/api/public/release-runs/{RUN}/{operation}', json={})
    assert response.status_code == 503
    assert 'no completion is implied' in response.text and 'provider-secret' not in response.text
    assert boundary.operations[function].call_count == 1


@pytest.mark.parametrize('path,method,args', [('/api/public/release-plans/latest', 'read_plan', ()), (f'/api/public/release-plans/{ID}', 'read_plan', (ID,)), (f'/api/public/release-runs/{RUN}', 'read_run', (RUN,))])
def test_anonymous_receipts_are_public_uncached_reads(boundary, path, method, args):
    response = boundary.client.get(path)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    getattr(boundary, method).assert_called_once_with(boundary.service.PORT, *args)
    boundary.create.assert_not_called(); boundary.execute.assert_not_called(); boundary.auth.assert_not_called()
    for mock in boundary.operations.values(): mock.assert_not_called()


def test_public_evidence_preserves_exact_hash_sensitive_bytes(boundary):
    response = boundary.client.get(f'/api/public/release-runs/{RUN}/evidence')
    assert response.status_code == 200 and response.content == b'{"verified":true}\r\n'
    assert response.headers['content-type'].startswith('application/json')
    assert response.headers['cache-control'] == 'no-store'
    boundary.evidence.assert_called_once_with(boundary.service.PORT, RUN)


def test_public_raw_logs_are_plain_text_not_executable_markup(boundary):
    raw = b'<script>not executable</script>\n'
    boundary.evidence.return_value = raw
    response = boundary.client.get(f'/api/public/release-runs/{RUN}/logs/redis-8.1.0/pytest.log')
    assert response.status_code == 200 and response.content == raw
    assert response.headers['content-type'].startswith('text/plain')
    assert response.headers['x-content-type-options'] == 'nosniff'
    boundary.evidence.assert_called_once_with(boundary.service.PORT, RUN, 'redis-8.1.0/pytest.log')


def test_unconfirmed_plan_creation_is_sanitized_and_not_retried(boundary):
    boundary.create.side_effect = RuntimeError('secret provider response')
    response = operator(boundary).post('/api/public/release-plans', json=PLAN_BODY)
    assert response.status_code == 503 and 'no substitute plan' in response.text
    assert 'secret provider' not in response.text
    assert boundary.create.call_count == 1


@pytest.mark.parametrize('investigation', [{}, {'status': 'failed'}, {'status': 'not_requested'}, {'status': 'running'}])
def test_actual_execute_route_requires_successful_groq_investigation_before_dispatch(boundary, monkeypatch, investigation):
    monkeypatch.setattr(gate, 'execute', REAL_EXECUTE)
    boundary.plan['investigation'] = investigation
    database = MagicMock()
    database.get.return_value = None
    database.lock.side_effect = lambda *args, **kwargs: nullcontext()
    monkeypatch.setattr(gate, 'connect', lambda port: database)
    current = MagicMock(); github = MagicMock()
    monkeypatch.setattr(gate, '_current', current)
    monkeypatch.setattr(gate, 'github', github)
    response = operator(boundary).post(f'/api/public/release-plans/{ID}/execute', json=EXECUTE_BODY)
    assert response.status_code == 409 and 'Actual Groq investigation did not succeed' in response.text
    current.assert_called_once_with(boundary.service.DATA, boundary.service.PORT, boundary.plan)
    github.assert_not_called(); database.incr.assert_not_called(); database.set.assert_not_called()


def test_successful_groq_investigation_can_reach_exactly_one_approved_dispatch(boundary, monkeypatch):
    monkeypatch.setattr(gate, 'execute', REAL_EXECUTE)
    database = MagicMock()
    database.get.return_value = None
    database.lock.side_effect = lambda *args, **kwargs: nullcontext()
    database.incr.return_value = 1
    database.set.return_value = True
    monkeypatch.setattr(gate, 'connect', lambda port: database)
    monkeypatch.setattr(gate, '_current', MagicMock())
    monkeypatch.setattr(gate.secrets, 'token_hex', lambda length: RUN)
    github = MagicMock(side_effect=[{'object': {'sha': 'd' * 40}}, None])
    monkeypatch.setattr(gate, 'github', github)
    response = operator(boundary).post(f'/api/public/release-plans/{ID}/execute', json=EXECUTE_BODY)
    assert response.status_code == 202
    writes = [call for call in github.call_args_list if len(call.args) > 1 and call.args[1] == 'POST']
    assert len(writes) == 1
    assert writes[0].args[0] == '/repos/' + C.RUNNER_REPOSITORY + '/actions/workflows/' + C.WORKFLOW + '/dispatches'
    assert writes[0].args[2]['inputs']['plan_hash'] == HASH
    assert writes[0].args[2]['inputs']['plan_id'] == ID
    assert writes[0].args[2]['inputs']['execution_id'] == RUN


def test_real_execute_rejects_duplicate_targets_before_any_dispatch(boundary, monkeypatch):
    monkeypatch.setattr(gate, 'execute', REAL_EXECUTE)
    github = MagicMock(); monkeypatch.setattr(gate, 'github', github)
    response = operator(boundary).post(f'/api/public/release-plans/{ID}/execute', json={'expected_plan_hash': HASH, 'publish_targets': ['jira', 'jira']})
    assert response.status_code == 409 and 'approved Jira and Slack' in response.text
    github.assert_not_called()
