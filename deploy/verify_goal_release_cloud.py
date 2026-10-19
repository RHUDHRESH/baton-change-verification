"""Read-only independent goal-to-release verification proof.

Run from a reviewed source checkout beside verify_goal_cloud.py and
verify_release_cloud.py. Requires the existing scripts/verify_release_gate.py,
scripts/verify_autonomous_release.py, server/release_contract.py,
server/release_verifier.py and server/release_dependency_lock.json. Uses only
public/provider/GitHub GET, Lambda configuration reads, DynamoDB GetItem and
GRAPH.RO_QUERY; never calls a model, dispatches, posts or repairs graph state.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time

import verify_goal_cloud as goal
import verify_release_cloud as release
from verify_release_cloud import AuditError, encode, get, require, sha


def selected_action(record, step_id=None):
    proposal = record.get("proposal") or {}
    require(re.fullmatch(r"[a-f0-9]{32}", record.get("id", "")) and
            re.fullmatch(r"[a-f0-9]{64}", proposal.get("hash", "")), "Goal or current model plan identity is invalid")
    steps = [s for s in proposal.get("steps", []) if s.get("tool_name") == "verify_release" and
             (step_id is None or s.get("id") == step_id)]
    require(len(steps) == 1 and "verify_release" in record.get("approved_actions", []),
            "Select exactly one explicitly approved current-plan verify_release step")
    step = steps[0]
    require(step.get("args") == {"change_id": release.CHANGE}, "Model step is outside the approved immutable release profile")
    actions = [a for a in record.get("actions", []) if a.get("kind") == "verify_release" and
               a.get("step_id") == step["id"] and a.get("plan_hash") == proposal["hash"]]
    require(actions, "No current-plan verification action exists")
    action = actions[-1]  # Earlier queued/partial observations remain honest history.
    detail = action.get("result") or {}
    require(action.get("status") == "verified" and action.get("read_back_verified") is True and
            detail.get("evidence_graph_verified") is True and detail.get("publication_graph_verified") is True and
            detail.get("publication_state") == "verified", "Latest verification action lacks fresh evidence and publication readbacks")
    run_id = detail.get("run_id", "")
    require(re.fullmatch(r"[a-f0-9]{32}", run_id) and action.get("id") == "goal-verification-" + run_id and
            action.get("url") == goal.ORIGIN + "/api/public/release-runs/" + run_id,
            "Goal action release run identity is invalid")
    require(all(a.get("result", {}).get("run_id") == run_id for a in actions),
            "One goal step refers to multiple execution identities")
    return step, action


def binding_audit(record, step, action, plan, run, intent, durable_plan, durable_run):
    detail = action["result"]
    require(plan.get("id") == run.get("plan_id") == intent and
            plan.get("plan_hash") == run.get("plan_hash") and plan.get("latest_run_id") == run.get("id") == detail["run_id"],
            "Goal intent, exact release plan and run bindings differ")
    origin = plan.get("investigation") or {}
    require(origin.get("status") == "succeeded" and origin.get("origin") == "goal_agent" and
            origin.get("goal_id") == record["id"] and origin.get("goal_plan_hash") == record["proposal"]["hash"],
            "Durable release plan is not bound to this actual goal revision")
    require(durable_plan == plan and {k: v for k, v in durable_run.items() if k not in {"expected_workflow_sha", "last_sequence"}} == run,
            "Public release material differs from its independently read durable records")
    require(run.get("status") == "completed" and run.get("evidence_status") == "verified" and
            run.get("evidence_verified") is True and run.get("graph_receipt", {}).get("verified") is True and
            set(run.get("publish_targets", [])) == {"jira", "slack"}, "Release execution or required deliveries are incomplete")
    for key, actual in (("decision", run.get("decision")), ("evidence_status", run.get("evidence_status")),
                        ("verification_status", run.get("verification_status")), ("environments", run.get("environments")),
                        ("run_status", run.get("status")), ("publications", run.get("publication"))):
        require(detail.get(key) == actual, "Goal action contains stale or different release results")
    cited = {e.get("source_id") for e in record.get("plan_evidence", record.get("evidence", []))
             if e.get("kind") == "source" and e.get("id") in step.get("evidence_ids", [])}
    require(cited.intersection(s.get("id") for s in plan.get("source_versions", [])),
            "Verification step does not cite actually inspected pinned-release source evidence")
    return {"goal_id": record["id"], "goal_plan_hash": record["proposal"]["hash"], "step_id": step["id"],
            "action_id": action["id"], "release_plan_id": plan["id"], "release_plan_hash": plan["plan_hash"],
            "release_run_id": run["id"], "durable_intent_and_records_reread": True,
            "action_matches_exact_execution_and_deliveries": True}


def private_environment():
    import boto3
    from botocore.config import Config
    response = boto3.client("lambda", region_name="ap-south-1", config=Config(connect_timeout=3, read_timeout=10,
        retries={"total_max_attempts": 1})).get_function_configuration(FunctionName="baton-workspace")
    values = response.get("Environment", {}).get("Variables", {})
    return {key: values.get(key, "") for key in ("BATON_CONTROL_DYNAMODB_TABLE", "BATON_GITHUB_TOKEN")}


def durable_reader(settings):
    import boto3
    from botocore.config import Config
    table = settings.get("BATON_CONTROL_DYNAMODB_TABLE", "")
    require(re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table), "Configured durable DynamoDB table is unavailable")
    client = boto3.client("dynamodb", region_name="ap-south-1", config=Config(connect_timeout=3, read_timeout=10,
        retries={"total_max_attempts": 1}))
    def read(key):
        require(re.fullmatch(r"goal:verification:[a-f0-9]{64}|release:(?:plan|run):[a-f0-9]{32}", key),
                "Durable GET is outside this goal verification scope")
        row = client.get_item(TableName=table, Key={"pk": {"S": key}}, ConsistentRead=True).get("Item", {})
        expiry = row.get("expires", {}).get("N")
        require(not expiry or float(expiry) > time.time(), "Durable record has expired")
        value = row.get("value", {}).get("S")
        require(isinstance(value, str) and len(value.encode()) < 350000, "Durable goal intent or release record is missing or too large")
        return value
    return read


def github_audit(run_id, settings):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts import verify_release_gate as github
    except ImportError:
        raise AuditError("Reviewed source checkout with existing GitHub artifact verifier is required") from None
    token = settings.get("BATON_GITHUB_TOKEN")
    require(isinstance(token, str) and token, "Existing private GitHub read credential is unavailable")
    reader = github.Reader(token)
    try:
        return github.verify(run_id, reader)
    except github.ProofError:
        raise AuditError("Independent GitHub artifact, source, command or JUnit validation failed") from None
    finally:
        reader.github.token = ""


def verify(identity, archive, archive_sha, commit, step_id=None):
    native = goal.verify(identity, archive, archive_sha, commit)
    record = json.loads(get(goal.ORIGIN + "/api/public/goals/" + identity))
    step, action = selected_action(record, step_id)
    require(native.get("status") == "verified" and native.get("goal_id") == identity and
            native.get("proposal_hash") == record["proposal"]["hash"], "Native goal proof does not bind the selected revision")
    plan, run, _, _ = release.public_evidence(action["result"]["run_id"])
    settings = private_environment()
    try:
        read = durable_reader(settings)
        intent_key = "goal:verification:" + sha(encode([identity, record["proposal"]["hash"], step["id"]]))
        intent = read(intent_key)
        require(re.fullmatch(r"[a-f0-9]{32}", intent), "Durable goal intent identity is invalid")
        binding = binding_audit(record, step, action, plan, run, intent,
                                json.loads(read("release:plan:" + intent)), json.loads(read("release:run:" + run["id"])))
        github = github_audit(run["id"], settings)
        cloud = release.verify(run["id"], archive, archive_sha)
        expected_status = "verified_failure" if run["decision"] == "blocked" else "verified"
        require(run["decision"] in {"blocked", "passed"} and github.get("status") == cloud.get("status") == expected_status and
                github.get("run_id") == cloud.get("run_id") == run["id"] and
                github.get("plan_hash") == cloud.get("plan_hash") == plan["plan_hash"] and
                github.get("report_sha256") == cloud.get("report_sha256") == run["evidence"]["sha256"] and
                github.get("release_decision") == cloud.get("release_decision") == run["decision"],
                "Composed independent release proofs disagree on the exact execution or matrix decision")
        for key in ("total", "passed", "failed", "errors", "skipped"):
            require(github.get(key) == cloud.get(key), "Independent release proof counts disagree")
        require(json.loads(get(goal.ORIGIN + "/api/public/goals/" + identity)) == record,
                "Goal changed during independent verification; rerun this read-only audit")
        return {"status": expected_status, "read_only": True, "source_commit": commit,
                "lambda_archive_sha256": archive_sha, **binding, "release_decision": run["decision"],
                "code_matrix_passed": run["decision"] == "passed", "native_goal_proof": native,
                "github_artifact_proof": github, "release_cloud_proof": cloud,
                "limits": ["Verified failure means the observed code matrix failed; it is not a code pass or completed repair.",
                           "This ties the observed model goal plan to real execution and delivery evidence; semantic usefulness is not certified.",
                           "Only existing-record reads occurred; no model call, dispatch, provider write, state repair or graph mutation was performed."]}
    finally:
        settings.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-id", required=True)
    parser.add_argument("--step-id")
    parser.add_argument("--lambda-archive", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = verify(args.goal_id, args.lambda_archive, args.archive_sha256, args.source_commit, args.step_id)
    except AuditError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True, "error": "Independent goal-release audit stopped; no private configuration or provider body was printed"}
    encoded = encode(result)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] in {"verified", "verified_failure"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
