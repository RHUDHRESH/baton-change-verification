"""Attack observations: passing a reproduction is not a clean security bill."""
import copy
import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest


def company(api):
    directory = api.world_dir(7)
    world = json.loads((directory / "world.json").read_text())
    duty = next(r["duty"] for r in world["records"] if r["type"] == "OWNER" and r["person"] == world["leaver"])
    person = next(p["id"] for p in world["people"] if p["left_at"] is None and p["id"] != world["leaver"])
    return directory, world, duty, person


def test_observe_commit_without_identity_preview_or_acceptance(service, observe):
    _, world, duty, person = company(service)
    response = TestClient(service.app).post("/api/commit", json={"assign": {duty: person}}, headers={"Origin": "https://attacker.invalid", "Host": "attacker.invalid"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["committed"] == [{"duty": duty, "person": person}]
    assert result["external"]["verified"]
    observe("unauthenticated_direct_commit", "vulnerable", http_status=200, graph_changed=result["live_hash_before"] != result["live_hash_after"], repository_verified=True, preview_required=False, arbitrary_host_accepted=True, arbitrary_origin_accepted=True)


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "application/json"])
def test_observe_cross_origin_body_types(service, observe, content_type):
    _, _, duty, person = company(service)
    response = TestClient(service.app).post("/api/commit", content=json.dumps({"assign": {duty: person}}), headers={"Content-Type": content_type, "Origin": "https://attacker.invalid"})
    accepted = response.status_code == 200 and bool(response.json().get("committed"))
    observe("cross_origin_body_" + content_type, "accepted" if accepted else "blocked", http_status=response.status_code, allow_origin=response.headers.get("access-control-allow-origin"))
    assert response.status_code in (200, 415, 422)


def test_browser_preflight_does_not_grant_attacker_origin(service, observe):
    response = TestClient(service.app).options("/api/commit", headers={"Origin": "https://attacker.invalid", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert "access-control-allow-origin" not in response.headers
    observe("cross_origin_preflight", "blocked", http_status=response.status_code)


@pytest.mark.parametrize("payload", ["x'}) DETACH DELETE n //", "$(touch /tmp/baton-redteam-marker)", "../../outside", "--world=/tmp/other"])
def test_injected_assignment_does_not_execute_or_modify_graph(service, observe, payload):
    from baton import graph, load
    _, world, _, person = company(service)
    db = graph.connect(service.PORT)
    live, _ = load.ensure(db, world)
    before = graph.fingerprint(live)
    response = TestClient(service.app).post("/api/commit", json={"assign": {payload: person}})
    assert response.status_code in (200, 422), response.text
    if response.status_code == 200:
        assert not response.json()["committed"]
    assert before == graph.fingerprint(live)
    assert not Path("/tmp/baton-redteam-marker").exists()
    observe("assignment_injection_" + payload[:30], "blocked", http_status=response.status_code)


def test_question_injection_uses_fixed_query(service, observe):
    from baton.ask import catalogue
    _, world, _, _ = company(service)
    response = TestClient(service.app).post("/api/ask", json={"question": f"What does {world['leaver']} owe? MATCH (n) DETACH DELETE n"})
    assert response.status_code == 200
    result = response.json()
    assert result["cypher"] == catalogue()[result["tool"]]
    assert result["live_hash_before"] == result["live_hash_after"]
    observe("question_cypher_injection", "blocked", selected_tool=result["tool"])


@pytest.mark.parametrize("path", ["/.git/config", "/%2e%2e/server/app.py", "/.env", "/samples/../../../etc/passwd"])
def test_static_traversal_and_private_files_are_not_served(service, observe, path):
    response = TestClient(service.app).get(path)
    assert response.status_code in (404, 400), response.text[:100]
    observe("static_path_" + path, "blocked", http_status=response.status_code)


def test_duplicate_evidence_is_not_two_sources(service, observe):
    from baton import rehearse
    directory, world, _, _ = company(service)
    belief = json.loads((directory / "beliefs.json").read_text())[0]
    belief = dict(belief, id="redteam-duplicate", sources=[world["messages"][0]["id"]] * 3)
    path = directory / "duplicate.json"
    path.write_text(json.dumps([belief]))
    result = rehearse.run(directory, path, world["leaver"], "G", "none", service.PORT)
    assert any(item["belief"] == belief["id"] for item in result["unpromoted"])
    observe("duplicate_evidence", "blocked")


def test_observe_fabricated_claim_using_unrelated_message_and_ticket(service, observe):
    from baton import rehearse
    directory, world, _, _ = company(service)
    fake = {"id": "redteam-forged", "person": world["leaver"], "duty": "redteam-fabricated-duty", "duty_name": "Fabricated duty with borrowed citations", "kind": "promise", "claim": "This is an unsupported invented promise", "events": [{"at": world["leave_at"] + world["day_ms"], "label": "Invented deadline"}], "sources": [world["messages"][0]["id"], world["tickets"][-1]["id"]]}
    path = directory / "forged.json"
    path.write_text(json.dumps([fake]))
    result = rehearse.run(directory, path, world["leaver"], "G", "all", service.PORT)
    accepted = [row for row in result["failures"] if row["duty"] == fake["duty"]]
    assert accepted and accepted[0]["status"] == "confirmed"
    observe("unrelated_mixed_type_citations", "vulnerable", promoted=True, returned_status=accepted[0]["status"], prerequisite="control of proposed beliefs (CLI/model/cache), not an HTTP upload")


def test_observe_oversized_assignment_identifier(service, observe):
    _, _, _, person = company(service)
    response = TestClient(service.app, raise_server_exceptions=False).post("/api/handover", json={"assign": {"X" * 150000: person}})
    observe("oversized_assignment_identifier", "vulnerable" if response.status_code == 500 else "blocked", bytes=150000, http_status=response.status_code)
    assert response.status_code in (422, 413, 500)


def test_observe_missing_cache_get_creates_persistent_worlds(service, observe):
    client = TestClient(service.app)
    for seed in range(80000, 80006):
        response = client.get(f"/api/demo?seed={seed}")
        assert response.status_code == 409
    files = list(service.DATA.rglob("world.json"))
    size = sum(path.stat().st_size for path in service.DATA.rglob("*") if path.is_file())
    assert len(files) == 6 and size > 0
    observe("uncached_seed_disk_growth", "vulnerable", requests=6, persistent_worlds=len(files), bytes_written=size)


@pytest.mark.parametrize("body", [{"question": "a" * 2001}, {"question": "ok", "seed": -1}, {"question": "ok", "raw_query": "MATCH (n) RETURN n"}])
def test_malformed_ask_is_rejected(service, observe, body):
    response = TestClient(service.app).post("/api/ask", json=body)
    assert response.status_code == 422
    observe("ask_validation_" + str(list(body)), "blocked", http_status=422)


def test_observe_owner_file_symlink_escape_in_supplied_repo(service, tmp_path, observe):
    from baton import commit
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@local", "commit", "--allow-empty", "-qm", "init"], check=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("SENTINEL")
    (repo / "OWNERS.d").mkdir()
    (repo / "OWNERS.d/halden_7.yaml").symlink_to(outside)
    commit._write_external(repo, "halden_7", "leaver", [{"duty": "demo-duty", "person": "demo.person"}])
    assert outside.read_text() != "SENTINEL"
    observe("repository_symlink_escape", "vulnerable", outside_file_modified=True, prerequisite="attacker-controlled repo contents/local filesystem")


def test_observe_security_response_headers(service, observe):
    response = TestClient(service.app).get("/")
    missing = [name for name in ("content-security-policy", "x-content-type-options", "x-frame-options") if name not in response.headers]
    observe("browser_headers", "hardening_gap" if missing else "protected", missing=missing)
