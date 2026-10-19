"""App-owned verification orchestration. A callback is never completion proof."""
import base64
import hmac
import io
import json
import re
import secrets
import time
import zipfile

from . import release_contract as C
from . import public_workspace as public
from .control import connect
from .autonomous_workflow import github

ORIGIN = "https://baton-workspace.vercel.app"
TERMINAL = {"completed", "partial", "error"}


class ReleaseError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ReleaseError(message)


def _identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value), "Invalid release identity")
    return value


def _read(port, kind, identity):
    raw = connect(port).get("release:" + kind + ":" + _identity(identity))
    require(raw, "Release " + kind + " not found")
    return json.loads(raw)


def _save(port, kind, value):
    raw = C.encode(value)
    require(len(raw.encode()) < 350000, "Release record exceeds its storage bound")
    require(connect(port).set("release:" + kind + ":" + _identity(value["id"]), raw), "Release state could not be persisted")


def read_plan(port, identity=None):
    identity = identity or connect(port).get("release:latest-plan")
    require(identity, "No app verification plan has been created")
    return _read(port, "plan", identity)


def read_run(port, identity):
    record = _read(port, "run", identity)
    return {key: value for key, value in record.items() if key not in {"expected_workflow_sha", "last_sequence"}}


def create_plan(data, port, change_id):
    from . import release_graph
    require(change_id == C.CHANGE_ID, "Select the reviewed FalkorDB Python-client change")
    with connect(port).lock("release:create-plan", timeout=170, blocking_timeout=2):
        plan = release_graph.build_plan(data, port, change_id, investigate=True)
        require(plan.get("plan_hash") == C.plan_hash(plan), "Graph plan binding was not confirmed")
        plan.update(id=secrets.token_hex(16), created_at=public.now(), latest_run_id=None)
        _save(port, "plan", plan)
        require(connect(port).set("release:latest-plan", plan["id"]), "Latest plan pointer was not persisted")
        return plan


def _current(data, port, plan):
    from . import release_graph
    require(plan.get("plan_status") == "ready", "Required graph coverage is incomplete")
    require(plan.get("plan_hash") == C.plan_hash(plan), "Stored plan hash changed")
    require(release_graph.revalidate(data, port, plan) is not False, "Relevant graph or source evidence changed; create a new plan")


def execute(data, port, identity, expected_plan_hash, targets):
    require(isinstance(targets, list) and len(targets) == 2 and set(targets) == {"jira", "slack"},
            "Select the approved Jira and Slack destinations")
    control = connect(port)
    with control.lock("release:dispatch", timeout=150, blocking_timeout=2):
        plan = read_plan(port, identity)
        require(hmac.compare_digest(str(expected_plan_hash), plan["plan_hash"]), "Plan changed; investigate again")
        if plan.get("latest_run_id"):
            # Replayed browser POSTs read their original run; they do not spend another dispatch.
            return read_run(port, plan["latest_run_id"])
        active = control.get("release:active")
        if active:
            previous = _read(port, "run", active)
            require(previous["status"] in TERMINAL or time.time() - previous["created_epoch"] > 1800,
                    "A verification run is already active")
        _current(data, port, plan)
        require(plan.get("investigation", {}).get("status") == "succeeded",
                "Actual Groq investigation did not succeed; no execution was dispatched")
        head = github("/repos/" + C.RUNNER_REPOSITORY + "/git/ref/heads/main")["object"]["sha"]
        require(re.fullmatch(r"[a-f0-9]{40}", head), "Runner source commit is invalid")
        month = time.strftime("%Y-%m", time.gmtime())
        require(control.incr("release:allowance:" + month) <= 2, "The two-run matrix allowance is exhausted")
        control.expire("release:allowance:" + month, 65 * 86400)
        require(control.incr("autonomous:allowance:" + month) <= 10, "The shared monthly execution guard is exhausted")
        control.expire("autonomous:allowance:" + month, 65 * 86400)
        run_id, callback = secrets.token_hex(16), secrets.token_urlsafe(36)
        record = {"id": run_id, "plan_id": identity, "plan_hash": plan["plan_hash"], "change_id": C.CHANGE_ID,
                  "source_commit": C.SOURCE_COMMIT, "created_at": public.now(), "created_epoch": time.time(),
                  "status": "queued", "evidence_status": "unconfirmed", "verification_status": "running",
                  "decision": "unconfirmed", "environments": [], "publication": {}, "publish_targets": targets,
                  "expected_workflow_sha": head, "last_sequence": -1,
                  "runner": {"provider": "GitHub Actions", "verified": False, "workflow_sha": head},
                  "limits": {"new_matrix_runs": 2, "shared_monthly_runs": 10, "repair": False},
                  "limitations": ["Verification of a merged upstream change; no source repair or upstream merge.",
                                  "Both declared environments are required; a passing row cannot override a failed row."]}
        require(control.set("release:callback:" + run_id, C.sha(callback), ex=7200), "Callback capability was not persisted")
        _save(port, "run", record)
        plan["latest_run_id"] = run_id
        _save(port, "plan", plan)
        control.set("release:active", run_id, ex=1800)
        try:
            github("/repos/" + C.RUNNER_REPOSITORY + "/actions/workflows/" + C.WORKFLOW + "/dispatches", "POST",
                   {"ref": "main", "inputs": {"execution_id": run_id, "callback_token": callback,
                                                "plan_id": identity, "plan_hash": plan["plan_hash"]}})
        except Exception:
            record.update(status="error", verification_status="unconfirmed",
                          error="Dispatch was not confirmed. Inspect this run; it will not be dispatched again automatically.")
            _save(port, "run", record)
        return read_run(port, run_id)


def authenticate(port, identity, authorization):
    expected = connect(port).get("release:callback:" + _identity(identity))
    supplied = authorization[7:] if isinstance(authorization, str) and authorization.startswith("Bearer ") else ""
    require(expected and hmac.compare_digest(expected, C.sha(supplied)), "Invalid or expired verification callback")


def _bind(record, run_id):
    require(re.fullmatch(r"[0-9]{1,20}", str(run_id)), "Invalid GitHub run identity")
    run = github("/repos/" + C.RUNNER_REPOSITORY + "/actions/runs/" + str(run_id))
    require(run.get("event") == "workflow_dispatch" and run.get("run_attempt") == 1 and
            run.get("head_sha") == record["expected_workflow_sha"] and
            run.get("repository", {}).get("full_name") == C.RUNNER_REPOSITORY and
            run.get("display_title") == "Baton verification " + record["id"] and
            run.get("path", "").split("@", 1)[0] == ".github/workflows/" + C.WORKFLOW,
            "GitHub run does not match this app dispatch")
    require(record["runner"].get("run_id") in {None, str(run_id)}, "Callback attempted to switch runs")
    record["runner"].update(run_id=str(run_id), run_url=run["html_url"])
    return run


def event(data, port, identity, body):
    with connect(port).lock("release:run:" + identity, timeout=40, blocking_timeout=2):
        record = _read(port, "run", identity)
        require(record["status"] not in TERMINAL and record["evidence_status"] != "verified", "Run already finalized")
        sequence = body.get("sequence")
        require(type(sequence) is int and 0 <= sequence <= 100, "Invalid callback sequence")
        if sequence <= record["last_sequence"]:
            return {"accepted": False, "duplicate": True}
        _bind(record, body.get("github_run_id"))
        require(body.get("stage") in {"started", "environment-started", "environment-completed", "artifact-ready", "failed"},
                "Unknown verification stage")
        record.update(status="verifying" if body["stage"] == "artifact-ready" else "running", last_sequence=sequence,
                      latest_event={"stage": body["stage"], "message": str(body.get("message", ""))[:600],
                                    "environment_id": body.get("environment_id"), "at": public.now()})
        _save(port, "run", record)
        return {"accepted": True}


def _files(raw):
    require(len(raw) <= 2000000, "Artifact exceeds its compressed bound")
    result = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            require(len(rows) <= 40 and sum(row.file_size for row in rows) <= 3000000, "Artifact exceeds its expanded bound")
            for row in rows:
                if row.is_dir():
                    continue
                require("\\" not in row.orig_filename and re.fullmatch(r"[a-zA-Z0-9_.\-/]+", row.filename) and not row.filename.startswith("/") and
                        ".." not in row.filename.split("/") and row.filename not in result and not row.flag_bits & 1 and
                        row.file_size < 300000, "Artifact contains an unsafe, duplicate or oversized member")
                result[row.filename] = archive.read(row)
    except (zipfile.BadZipFile, RuntimeError):
        raise ReleaseError("Invalid verification artifact") from None
    require("release-report.json" in result, "Artifact report is missing")
    return result


def complete(data, port, identity, body):
    try:
        return _complete(data, port, identity, body)
    except Exception as error:
        with connect(port).lock("release:run:" + identity, timeout=30, blocking_timeout=2):
            record = _read(port, "run", identity)
            if record["status"] not in TERMINAL:
                record.update(status="error", decision="unconfirmed",
                              error=str(error) if isinstance(error, ValueError) else "Independent GitHub verification was not confirmed")
                _save(port, "run", record)
        return read_run(port, identity)


def _complete(data, port, identity, body):
    from . import release_graph, release_verifier
    with connect(port).lock("release:run:" + identity, timeout=220, blocking_timeout=2):
        record = _read(port, "run", identity)
        if record["status"] in TERMINAL:
            return read_run(port, identity)
        _bind(record, body.get("github_run_id"))
        require(body.get("artifact_name") == "baton-verify-" + identity, "Wrong verification artifact name")
        prefix = "/repos/" + C.RUNNER_REPOSITORY + "/actions/"
        jobs = github(prefix + "runs/" + record["runner"]["run_id"] + "/jobs?per_page=30").get("jobs", [])
        jobs = [job for job in jobs if job.get("name") == "execute"]
        require(len(jobs) == 1 and jobs[0].get("status") == "completed" and jobs[0].get("conclusion") in {"success", "failure"},
                "The execute job is not independently complete")
        artifacts = github(prefix + "runs/" + record["runner"]["run_id"] + "/artifacts?per_page=30").get("artifacts", [])
        artifacts = [row for row in artifacts if row.get("name") == body["artifact_name"] and row.get("expired") is False and
                     str(row.get("workflow_run", {}).get("id")) == record["runner"]["run_id"]]
        require(len(artifacts) == 1, "No unique unexpired artifact belongs to this run")
        artifact = artifacts[0]
        raw = github(prefix + "artifacts/" + str(artifact["id"]) + "/zip", binary=True)
        require(not artifact.get("digest") or artifact["digest"] == "sha256:" + C.sha(raw), "Artifact digest mismatch")
        plan = read_plan(port, record["plan_id"])
        try:
            files = _files(raw)
            verified = release_verifier.verify_artifact(plan, record, files)
            require(verified.get("verified") is True, "Artifact did not establish valid evidence")
            for name, content in files.items():
                try:
                    value = {"name": name, "sha256": C.sha(content), "text": content.decode("utf-8")}
                except UnicodeDecodeError:
                    value = {"name": name, "sha256": C.sha(content), "encoding": "base64", "data": base64.b64encode(content).decode()}
                require(connect(port).set("release:file:" + identity + ":" + name, C.encode(value)),
                        "Evidence bytes were not preserved")
            record.update(evidence_status="verified", verification_status="passed" if verified["status"] == "passed" else "failed",
                          decision="passed" if verified["status"] == "passed" else "blocked", environments=verified["environments"],
                          results=verified.get("results", []), evidence_verified=True,
                          evidence={"url": ORIGIN + "/api/public/release-runs/" + identity + "/evidence",
                                    "sha256": C.sha(files["release-report.json"])}, completed_at=public.now())
            record["runner"].update(verified=True, conclusion=jobs[0]["conclusion"], job_id=jobs[0]["id"],
                                    artifact_id=artifact["id"], artifact_sha256=C.sha(raw))
            _current(data, port, plan)
            receipt = release_graph.record_result(data, port, plan, record)
            require(isinstance(receipt, dict) and receipt.get("verified") is True, "Graph completion certificate was not read back")
            record["graph_receipt"] = receipt
            record["status"] = "verifying"
            _save(port, "run", record)
        except Exception as error:
            record.update(status="error", decision="unconfirmed",
                          error=str(error) if isinstance(error, ValueError) else "Independent verification was not confirmed; publication blocked")
            _save(port, "run", record)
            return read_run(port, identity)
        record["status"] = "publishing"
        _save(port, "run", record)
        return read_run(port, identity)


def publish_result(data, port, identity, body):
    from .release_publication import publish
    with connect(port).lock("release:run:" + identity, timeout=160, blocking_timeout=2):
        record = _read(port, "run", identity)
        require(str(body.get("github_run_id")) == record.get("runner", {}).get("run_id"), "Publication callback references another run")
        require(record.get("evidence_status") == "verified" and record.get("graph_receipt", {}).get("verified") is True and
                record.get("decision") in {"blocked", "passed"}, "Publication requires verified execution evidence and graph certificate")
        if record["status"] == "completed":
            return read_run(port, identity)
        require(record["status"] in {"publishing", "partial"}, "Run cannot publish before verification")
        plan = read_plan(port, record["plan_id"])
        _current(data, port, plan)
        record["publication"] = {}
        for target in record["publish_targets"]:
            try:
                record["publication"][target] = publish(data, port, plan, record, target)
            except Exception:
                record["publication"][target] = {"status": "pending", "message": "Publication not confirmed; inspect the durable intent before reconciliation"}
            _save(port, "run", record)
        record["status"] = "completed" if all(row.get("status") == "verified" and row.get("graph_linked") is True
                                                for row in record["publication"].values()) else "partial"
        _save(port, "run", record)
        return read_run(port, identity)


def evidence(port, identity, name="release-report.json"):
    record = _read(port, "run", identity)
    require(record.get("evidence_status") == "verified", "No independently verified evidence is available")
    require(re.fullmatch(r"[a-zA-Z0-9_.\-/]+", name) and ".." not in name.split("/"), "Invalid evidence filename")
    raw = connect(port).get("release:file:" + identity + ":" + name)
    require(raw, "Evidence file not found")
    value = json.loads(raw)
    content = base64.b64decode(value["data"], validate=True) if value.get("encoding") == "base64" else value["text"]
    require(C.sha(content) == value["sha256"], "Stored evidence hash mismatch")
    return content
