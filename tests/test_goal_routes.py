"""Actual HTTP authority boundaries; model/provider calls are mocked here."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from server import goal_agent, goal_graph, security

ID, HASH = "a" * 32, "b" * 64
START = {"goal": "Investigate the public compatibility failure and propose useful follow-up", "idempotency_key": "goal-http-unique-key"}


@pytest.fixture
def http(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    from server import app as service
    token, cookie = "goal-http-test-token-only-" + "x" * 32, "goal-http-test-cookie"
    monkeypatch.setenv("BATON_OPERATOR_TOKEN", token)
    monkeypatch.setattr(service, "DATA", tmp_path)
    auth = MagicMock()
    auth.get.side_effect = lambda key: security.digest(token) if key == "baton:session:" + security.digest(cookie) else None
    monkeypatch.setattr(service, "auth_db", lambda: auth)
    investigate, resume = MagicMock(return_value={"id": ID, "status": "blocked", "proposal": None, "actions": []}), MagicMock(return_value={"id": ID, "status": "needs_continuation"})
    monkeypatch.setattr(goal_agent, "investigate", investigate)
    monkeypatch.setattr(goal_agent, "continue_goal", resume)
    latest, read = MagicMock(return_value=None), MagicMock(return_value={"id": ID, "status": "proposed"})
    monkeypatch.setattr(goal_graph, "latest_goal", latest)
    monkeypatch.setattr(goal_graph, "get_goal", read)
    return SimpleNamespace(client=TestClient(service.app, base_url="http://localhost", raise_server_exceptions=False),
                           cookie=cookie, investigate=investigate, resume=resume, latest=latest, read=read)


def operator(http):
    http.client.cookies.set(security.COOKIE, http.cookie)
    return http.client


@pytest.mark.parametrize("path,body", [("/api/public/goals", START), (f"/api/public/goals/{ID}/act", {"expected_plan_hash": HASH, "approved_actions": ["publish_task"]}),
                                     (f"/api/public/goals/{ID}/continue", {"expected_plan_hash": ""})])
def test_anonymous_cannot_generate_plan_or_act(http, path, body):
    assert http.client.post(path, json=body).status_code == 401
    http.investigate.assert_not_called(); http.resume.assert_not_called()


def test_freeform_goal_is_forwarded_without_keyword_routing_and_no_fake_plan(http):
    r = operator(http).post("/api/public/goals", json=START)
    assert r.status_code == 201 and r.json()["proposal"] is None and r.json()["actions"] == []
    assert http.investigate.call_args.args[2:] == (START["goal"], START["idempotency_key"])
    http.resume.assert_not_called()


@pytest.mark.parametrize("extra", ["commands", "tools", "proposal", "decision", "repository", "provider_key"])
def test_client_cannot_supply_plan_tools_or_completion(http, extra):
    assert operator(http).post("/api/public/goals", json={**START, extra: "untrusted"}).status_code == 422
    http.investigate.assert_not_called()


def test_continuation_before_a_proposal_accepts_empty_hash_but_no_new_permissions(http):
    r = operator(http).post(f"/api/public/goals/{ID}/continue", json={"expected_plan_hash": ""})
    assert r.status_code == 200 and http.resume.call_args.args[2:] == (ID, "")
    assert http.resume.call_args.kwargs == {}
    assert operator(http).post(f"/api/public/goals/{ID}/continue", json={"expected_plan_hash": "", "approved_actions": ["publish_task"]}).status_code == 422


def test_act_uses_exact_stored_hash_and_only_approved_effects(http):
    r = operator(http).post(f"/api/public/goals/{ID}/act", json={"expected_plan_hash": HASH, "approved_actions": ["publish_task"]})
    assert r.status_code == 200 and http.resume.call_args.args[2:] == (ID, HASH)
    assert http.resume.call_args.kwargs["approved_actions"] == ["publish_task"]
    assert callable(http.resume.call_args.kwargs["action_executor"])


@pytest.mark.parametrize("headers", [{"Origin": "https://hostile.invalid"}, {"Sec-Fetch-Site": "cross-site"}])
def test_hostile_origin_cannot_start_ai_work(http, headers):
    assert operator(http).post("/api/public/goals", json=START, headers=headers).status_code == 403
    http.investigate.assert_not_called()


def test_public_reads_never_start_model_or_effects_and_graph_failure_stays_visible(http):
    assert http.client.get("/api/public/goals/latest").json() is None
    assert http.client.get("/api/public/goals/" + ID).json()["id"] == ID
    http.latest.side_effect = RuntimeError("private graph failure")
    r = http.client.get("/api/public/goals/latest")
    assert r.status_code == 503 and "private" not in r.text and "cached plan" in r.text
    http.investigate.assert_not_called(); http.resume.assert_not_called()
