"""Independent proof uses real runner bytes with mocked read-only endpoints."""
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from scripts import verify_release_gate as P
from server import release_contract as C
from server import release_publication as publisher
from server.release_verifier import verify_artifact


@pytest.fixture
def fixture():
    root = Path(__file__).with_name("fixtures") / "release_verifier"
    files = {p.relative_to(root / "artifact").as_posix(): p.read_bytes() for p in (root / "artifact").rglob("*") if p.is_file()}
    plan = json.loads((root / "plan.json").read_bytes())
    plan.update(id="a" * 32, binding_fingerprint="b" * 64)
    plan["plan_hash"] = C.plan_hash(plan)
    identity, github_id, head = "c" * 32, "123", "a" * 40
    report = json.loads(files["release-report.json"])
    # Only local identity metadata is rebound; original commands/logs/JUnit,
    # source archive, dependency lock and environment measurements stay intact.
    report.update(run_id=identity, plan_id=plan["id"], plan_hash=plan["plan_hash"])
    files["release-report.json"] = (C.encode(report) + "\n").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    package = stream.getvalue()
    run_url = "https://github.com/" + C.RUNNER_REPOSITORY + "/actions/runs/" + github_id
    record = {"id": identity, "plan_id": plan["id"], "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT,
        "runner": {"provider": "GitHub Actions", "run_id": github_id, "workflow_sha": head, "verified": True,
                   "run_url": run_url, "conclusion": "success", "job_id": 456, "artifact_id": 789,
                   "artifact_sha256": C.sha(package)}}
    observed = verify_artifact(plan, record, files)
    record.update(status="completed", evidence_status="verified", evidence_verified=True, decision="blocked", verification_status="failed",
        environments=observed["environments"], results=observed["results"], publish_targets=["jira", "slack"],
        evidence={"url": P.ORIGIN + "/api/public/release-runs/" + identity + "/evidence", "sha256": C.sha(files["release-report.json"])})
    results = [{**check, "check_id": check["id"], "environment_id": env["id"]} for env in observed["environments"] for check in env["checks"]]
    record["graph_receipt"] = {"verified": True, "run_id": identity, "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT,
        "release_passed": False, "checks": 8, "policy_version": C.POLICY_VERSION, "registry_version": C.REGISTRY_VERSION,
        "evidence_sha256": record["evidence"]["sha256"], "results_sha256": C.sha(C.encode(results)), "binding_fingerprint": plan["binding_fingerprint"]}
    title, text = publisher._text(plan, record)
    record["publication"] = {}
    for target in ("jira", "slack"):
        receipt = {"id": "publication-" + C.sha(identity + ":" + target), "target": target, "run_id": identity, "plan_id": plan["id"],
            "title": title, "evidence_text": text, "contract_sha256": "d" * 64, "status": "verified", "graph_linked": True,
            "write_retry_allowed": False, "readback_retry_allowed": True}
        if target == "jira":
            receipt.update(destination="https://example.atlassian.net/KAN", remote_id="KAN-99", url="https://example.atlassian.net/browse/KAN-99")
        else:
            receipt.update(destination="C123456", remote_id="1792334785.098199", url="https://example.slack.com/archives/C123456/p1792334785098199",
                message_text=text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        record["publication"][target] = receipt
    metadata = {"id": 123, "status": "completed", "conclusion": "success", "run_attempt": 1, "event": "workflow_dispatch", "head_sha": head,
        "repository": {"full_name": C.RUNNER_REPOSITORY}, "display_title": "Baton verification " + identity,
        "path": ".github/workflows/baton-verify.yml", "html_url": run_url}
    jobs = {"jobs": [{"id": 456, "name": "execute", "status": "completed", "conclusion": "success"},
                     {"id": 457, "name": "finalization", "status": "completed", "conclusion": "success"}]}
    artifacts = {"artifacts": [{"id": 789, "name": "baton-verify-" + identity, "expired": False,
        "workflow_run": {"id": 123, "head_sha": head}, "digest": "sha256:" + C.sha(package)}]}
    state = SimpleNamespace(identity=identity, plan=plan, files=files, package=package, record=record, metadata=metadata,
                            jobs=jobs, artifacts=artifacts, overrides={}, calls=[])
    class Reader:
        def json(self, path, github=False):
            state.calls.append(("GET", path, github))
            if path == "/api/public/release-runs/" + identity:
                return copy.deepcopy(record)
            if path == "/api/public/release-plans/" + plan["id"]:
                return copy.deepcopy(plan)
            base = P.PREFIX + "runs/123"
            return copy.deepcopy({base: metadata, base + "/jobs?per_page=30": jobs, base + "/artifacts?per_page=30": artifacts}[path])
        def raw(self, path, github=False, archive=False):
            state.calls.append(("GET", path, github))
            if path in state.overrides:
                return state.overrides[path]
            if archive:
                return state.package
            return files["release-report.json"] if path.endswith("/evidence") else files[path.split("/logs/", 1)[1]]
    state.reader = Reader()
    return state


def test_independent_proof_preserves_actual_failed_release_and_verifies_every_public_byte(fixture):
    result = P.verify(fixture.identity, fixture.reader)
    assert result["status"] == "verified_failure" and result["release_decision"] == "blocked"
    assert (result["total"], result["passed"], result["failed"], result["errors"], result["skipped"]) == (8, 6, 2, 0, 0)
    assert result["source_unchanged"] is True
    assert len(result["public_raw_hashes"]) == 9
    assert all(method == "GET" for method, _, _ in fixture.calls)
    assert all(path.startswith(P.PREFIX) for _, path, github in fixture.calls if github)
    assert all(receipt["provider_get_performed"] is False for receipt in result["publication"].values())
    assert any("provider GETs were not performed" in line for line in result["limits"])
    assert "BATON_COMMAND" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["head", "workflow", "repository", "attempt", "artifact-digest", "artifact-head", "expired", "job", "execute-receipt"])
def test_independent_github_provenance_divergence_is_rejected(fixture, mutation):
    if mutation == "head": fixture.metadata["head_sha"] = "e" * 40
    elif mutation == "workflow": fixture.metadata["path"] = ".github/workflows/baton-execute.yml"
    elif mutation == "repository": fixture.metadata["repository"]["full_name"] = "other/repository"
    elif mutation == "attempt": fixture.metadata["run_attempt"] = 2
    elif mutation == "artifact-digest": fixture.artifacts["artifacts"][0]["digest"] = "sha256:" + "0" * 64
    elif mutation == "artifact-head": fixture.artifacts["artifacts"][0]["workflow_run"]["head_sha"] = "e" * 40
    elif mutation == "expired": fixture.artifacts["artifacts"][0]["expired"] = True
    elif mutation == "job": fixture.jobs["jobs"].pop()
    else: fixture.record["runner"]["conclusion"] = "failure"
    with pytest.raises(P.ProofError):
        P.verify(fixture.identity, fixture.reader)


def test_actual_github_job_failure_is_preserved_without_inventing_a_green_workflow(fixture):
    fixture.metadata["conclusion"] = "failure"
    fixture.jobs["jobs"][0]["conclusion"] = fixture.record["runner"]["conclusion"] = "failure"
    fixture.jobs["jobs"][1]["conclusion"] = "failure"
    result = P.verify(fixture.identity, fixture.reader)
    assert result["status"] == "verified_failure"
    assert result["github"]["conclusion"] == result["github"]["execute_conclusion"] == result["github"]["finalization_conclusion"] == "failure"


@pytest.mark.parametrize("name", ["release-report.json", "source.zip", "redis-8.0.0/pytest.log", "redis-8.1.0/junit.xml",
                                  "redis-8.1.0/setup.log", "redis-8.0.0/requirements.lock"])
def test_public_raw_bytes_must_equal_the_actual_artifact(fixture, name):
    path = "/api/public/release-runs/" + fixture.identity + ("/evidence" if name == "release-report.json" else "/logs/" + name)
    fixture.overrides[path] = b"substituted bytes"
    with pytest.raises(P.ProofError):
        P.verify(fixture.identity, fixture.reader)


@pytest.mark.parametrize("mutation", ["counts", "test-status", "graph-report-hash", "graph-results-hash", "graph-decision", "graph-fingerprint", "decision"])
def test_public_matrix_and_graph_receipt_must_match_independent_junit(fixture, mutation):
    if mutation == "counts": fixture.record["environments"][1]["passed"] = 4
    elif mutation == "test-status": fixture.record["results"][6]["status"] = "passed"
    elif mutation == "graph-report-hash": fixture.record["graph_receipt"]["evidence_sha256"] = "e" * 64
    elif mutation == "graph-results-hash": fixture.record["graph_receipt"]["results_sha256"] = "e" * 64
    elif mutation == "graph-decision": fixture.record["graph_receipt"]["release_passed"] = True
    elif mutation == "graph-fingerprint": fixture.record["graph_receipt"]["binding_fingerprint"] = "e" * 64
    else: fixture.record["decision"] = "passed"
    with pytest.raises(P.ProofError):
        P.verify(fixture.identity, fixture.reader)


@pytest.mark.parametrize("mutation", ["run", "evidence", "message", "url", "graph-link", "pending"])
def test_saved_provider_receipt_divergence_is_rejected(fixture, mutation):
    receipt = fixture.record["publication"]["slack"]
    if mutation == "run": receipt["run_id"] = "e" * 32
    elif mutation == "evidence": receipt["evidence_text"] += "extra"
    elif mutation == "message": receipt["message_text"] += "extra"
    elif mutation == "url": receipt["url"] += "?unverified"
    elif mutation == "graph-link": receipt["graph_linked"] = False
    else: receipt["status"] = "pending"
    with pytest.raises(P.ProofError):
        P.verify(fixture.identity, fixture.reader)


def test_partial_publication_is_reported_as_unconfirmed_provider_effect_not_a_test_success(fixture):
    fixture.record["status"] = "partial"
    fixture.record["publication"]["slack"] = {"status": "pending", "message": "Outcome not confirmed"}
    result = P.verify(fixture.identity, fixture.reader)
    assert result["status"] == "verified_failure" and result["publication_status"] == "partial"
    assert result["publication"]["slack"] == {"status": "pending", "app_saved_readback_claim": False, "provider_get_performed": False}


@pytest.mark.parametrize("path,github", [("/api/public/release-plans/" + "a" * 32 + "/execute", False),
    ("/api/public/release-runs/" + "a" * 32 + "/logs/../secret", False),
    ("/repos/other/repo/actions/runs/123", True), ("/repos/" + C.RUNNER_REPOSITORY + "/issues/1", True)])
def test_reader_rejects_actions_outside_exact_get_scope(path, github):
    reader = P.Reader("credential-never-sent")
    with pytest.raises(P.ProofError):
        reader.raw(path, github=github)


def test_public_reader_never_forwards_the_github_credential():
    requests = []
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def open(self, request, **kwargs):
            requests.append(request)
            return Response(b"{}")
    reader = P.Reader("credential-never-sent")
    reader.opener = Opener()
    reader.raw("/api/public/release-runs/" + "a" * 32)
    assert requests[0].get_method() == "GET"
    assert "Authorization" not in requests[0].headers
    assert "credential-never-sent" not in repr(requests[0].headers)


def test_invalid_cli_identity_does_not_load_a_credential(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(P, "credential", lambda: pytest.fail("Invalid input must not access GCM"))
    output = tmp_path / "proof.json"
    assert P.main(["--run-id", "invalid", "--output", str(output)]) == 1
    assert json.loads(output.read_text())["status"] == "unconfirmed"
    assert "invalid" not in capsys.readouterr().out.lower()
