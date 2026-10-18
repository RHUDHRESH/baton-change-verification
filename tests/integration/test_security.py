import json
import os
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from baton import commit, graph, load
from server import security


def operator(service, url="http://testserver"):
    client = TestClient(service.app, base_url=url)
    response = client.post("/api/auth/login", json={"token": os.environ["BATON_OPERATOR_TOKEN"]})
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    return client


def plan(client):
    suggested = client.get("/api/cut?seed=7").json()
    assign = {r["duty"]: r["person"] for r in suggested["assignments"]}
    preview = client.post("/api/handover", json={"assign": assign}).json()
    assert preview["accepted"] and not preview["failures_after"]
    return {"assign": assign, "preview_token": preview["preview_token"], "consent_confirmed": True}


def test_authorized_preview_consent_write_retry_logout(service):
    anonymous = TestClient(service.app)
    assert anonymous.post("/api/commit", json={"assign": {}}).status_code == 401
    assert anonymous.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    assert not anonymous.get("/api/auth/status").json()["authenticated"]
    client = operator(service)
    assert client.get("/api/auth/status").json()["authenticated"]
    body = plan(client)
    assert client.post("/api/commit", json={**body, "preview_token": ""}).status_code == 409
    assert client.post("/api/commit", json={**body, "consent_confirmed": False}).status_code == 422
    modified = dict(body["assign"])
    modified.pop(next(iter(modified)))
    assert client.post("/api/commit", json={**body, "assign": modified}).status_code == 409
    other = operator(service)
    assert other.post("/api/commit", json=body).status_code == 409
    response = client.post("/api/commit", json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["ready_to_leave"] and saved["external"]["verified"]
    repeated = client.post("/api/commit", json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["operation_id"] == saved["operation_id"]
    assert repeated.json()["external"]["commit"] == saved["external"]["commit"]
    assert len(client.get("/api/receipts").json()["receipts"]) == 1
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.post("/api/commit", json=body).status_code == 401


def test_expired_preview_session_and_changed_graph(service):
    client = operator(service)
    body = plan(client)
    db = service.auth_db()
    db.delete("baton:preview:" + security.digest(body["preview_token"]))
    assert client.post("/api/commit", json=body).status_code == 409
    body = plan(client)
    directory = service.world_dir(7)
    w = json.loads((directory / "world.json").read_text())
    live, _ = load.ensure(graph.connect(service.PORT), w)
    live.query("MATCH (p:Person) SET p.capacity = p.capacity + 1")
    before = graph.fingerprint(live)
    assert client.post("/api/commit", json=body).status_code == 409
    assert graph.fingerprint(live) == before
    cookie = client.cookies.get(security.COOKIE)
    db.delete("baton:session:" + security.digest(cookie))
    assert client.post("/api/commit", json=body).status_code == 401


def test_host_origin_chunked_body_and_identifier_limits(service, monkeypatch):
    client = operator(service)
    assert client.get("/", headers={"Host":"attacker.invalid"}).status_code == 400
    assert client.post("/api/commit", json={"assign":{}}, headers={"Origin":"https://attacker.invalid"}).status_code == 403
    assert client.post("/api/auth/login", json={"token":os.environ["BATON_OPERATOR_TOKEN"]}, headers={"Origin":"null"}).status_code == 403
    assert client.post("/api/commit", json={"assign":{}}, headers={"Sec-Fetch-Site":"cross-site"}).status_code == 403
    body = (b"x" * 40000 for _ in range(2))
    assert client.post("/api/handover", content=body, headers={"Content-Type":"application/json"}).status_code == 413
    assert client.post("/api/handover", json={"assign":{"a":"x"*121}}).status_code == 422
    service.world_dir(7)
    def forbidden(*args):
        pytest.fail("Unknown assignments must not spawn a CLI")
    monkeypatch.setattr(service, "cli", forbidden)
    assert client.post("/api/handover", json={"assign":{"unknown-duty":"unknown-person"}}).status_code == 422


def test_login_rate_limit_and_https_cookie(service):
    client = operator(service, "https://localhost")
    assert client.cookies.get(security.COOKIE)
    response = client.post("/api/auth/login", json={"token":os.environ["BATON_OPERATOR_TOKEN"]})
    assert "; Secure" in response.headers["set-cookie"]
    for _ in range(8):
        assert client.post("/api/auth/login", json={"token":"wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"token":"wrong"}).status_code == 429


@pytest.mark.parametrize("attack", ["leaf", "dangling", "parent", "journal", "hardlink"])
def test_repository_links_never_write_outside(service, tmp_path, attack):
    repo = tmp_path / "repo"
    subprocess.run(["git","init","-q",str(repo)],check=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("UNCHANGED")
    if attack == "parent":
        (repo / "OWNERS.d").symlink_to(outside, target_is_directory=True)
    elif attack == "journal":
        (repo / ".baton").symlink_to(outside, target_is_directory=True)
    else:
        (repo / "OWNERS.d").mkdir()
        target = repo / "OWNERS.d/halden_7.yaml"
        if attack == "hardlink":
            os.link(sentinel, target)
        else:
            target.symlink_to(sentinel if attack == "leaf" else outside / "absent")
    destination = ".baton/receipts/x.json" if attack == "journal" else "OWNERS.d/halden_7.yaml"
    with pytest.raises((OSError, ValueError)):
        commit._safe_write(repo, destination, "ATTACK")
    assert sentinel.read_text() == "UNCHANGED"
    assert not (outside / "absent").exists()
    assert sorted(p.name for p in outside.iterdir()) == ["sentinel"]


def test_atomic_replace_does_not_follow_a_swapped_leaf(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = tmp_path / "outside"
    sentinel.write_text("UNCHANGED")
    original = os.replace
    def replace(source, destination, **kwargs):
        (repo / "OWNERS.d/halden_7.yaml").symlink_to(sentinel)
        return original(source, destination, **kwargs)
    monkeypatch.setattr(os, "replace", replace)
    commit._safe_write(repo, "OWNERS.d/halden_7.yaml", "SAFE")
    assert sentinel.read_text() == "UNCHANGED"
    assert not (repo / "OWNERS.d/halden_7.yaml").is_symlink()
    assert (repo / "OWNERS.d/halden_7.yaml").read_text() == "SAFE"


def test_forged_topic_and_duplicate_belief_ids_cannot_borrow_relevance(service):
    from baton import generate, rehearse
    directory = service.world_dir(7)
    world, key = generate.build(7)
    genuine = next(b for b in key["true_beliefs"] if b["kind"] == "promise")
    forged = {**genuine, "duty":"redteam-invented-duty", "id":genuine["id"]}
    path = directory / "forged-topic.json"
    path.write_text(json.dumps([forged, genuine]))
    result = rehearse.run(directory, path, world["leaver"], "G", "all", service.PORT)
    assert not any(row["duty"] == forged["duty"] for row in result["failures"])
    assert any(row["duty"] == genuine["duty"] for row in result["failures"])


def test_seed_rejection_does_not_depend_on_model_mode(service, monkeypatch):
    client = TestClient(service.app)
    monkeypatch.setenv("BATON_OFFLINE", "0")
    for route in ("demo", "cut", "graph", "receipts"):
        assert client.get(f"/api/{route}?seed=123456").status_code == 409
    assert not service.DATA.exists()


def test_browser_headers_and_swagger_initializer_hash(service):
    client = TestClient(service.app)
    for path in ("/", "/amb.html", "/api/health", "/missing"):
        response = client.get(path)
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert "'unsafe-inline'" not in response.headers["content-security-policy"].split("script-src ")[1].split(";")[0]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "'sha256-" in docs.headers["content-security-policy"]
    assert "swagger-ui-bundle.js" in docs.text
