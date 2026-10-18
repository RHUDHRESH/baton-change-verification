"""Import and independently verify the approved KAN-2 graph receipt.

CloudShell: python verify_execution.py --report execution.json --output verified.json
Only the existing operator credential is read privately from Lambda configuration.
This performs workspace graph imports; it never contacts Jira or Slack.
"""
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.request


ORIGIN = "https://baton-workspace.vercel.app"
TASK = "task-agent-c108922c16a39ceaa82623d5748c4df0"
ITEM = "FalkorDB/FalkorDB#3246"
DIGEST = "19fd8fbf48e238480400d31e215d13d2b22bf681edbb417137f7a8ab0477bb85"
CHECK_DIGEST = "cc8ea10ab3a651d3d067effc9d318b432f35a54af7c5235d01f22bd91cd7633e"
RECEIPT_DIGEST = "8b16bd88d5f5914b775e9b537ec686bda6590a05a64e20635cf1908508ffe783"
RECEIPT = "execution-kan2-" + DIGEST
EVIDENCE = "https://github.com/RHUDHRESH/baton-graph-workspace/blob/1b76598a72bc1ac878dc46389851a995caef7379/docs/evidence/KAN-2.md"
PATHS = {"/api/auth/login", "/api/public/executions", "/api/public/workspace"}


class VerificationError(ValueError):
    """Static, application-owned diagnostics safe for the terminal."""


def require(value, message):
    if not value:
        raise VerificationError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def approved_manifest(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 50_000 and hashlib.sha256(raw).hexdigest() == DIGEST,
            "Report bytes differ from the approved audited manifest")
    value = raw.decode("utf-8")  # Preserve CRLF bytes inside the submitted string.
    report = json.loads(value)
    require(report.get("status") == "passed" and report.get("task") == "KAN-2" and len(report.get("checks", [])) == 20,
            "Approved report inventory is incomplete")
    return value


def operator_token():
    import boto3
    from botocore.config import Config
    client = boto3.client("lambda", region_name="ap-south-1",
        config=Config(connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 1}))
    config = client.get_function_configuration(FunctionName="baton-workspace")
    token = config.get("Environment", {}).get("Variables", {}).get("BATON_OPERATOR_TOKEN")
    require(isinstance(token, str) and len(token) >= 24, "Existing operator credential is unavailable")
    return token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VerificationError("Workspace redirect was refused")


class Workspace:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(),
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self, path, payload=None):
        require(path in PATHS, "Workspace request path is not approved")
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json", "Origin": ORIGIN}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(ORIGIN + path, data=data, headers=headers,
            method="POST" if data is not None else "GET")
        try:
            with self.opener.open(request, timeout=45) as response:
                require(response.status in (200, 201), "Workspace returned an unexpected status")
                raw = response.read(8_000_001)
                require(len(raw) <= 8_000_000, "Workspace response exceeded its bound")
                value = json.loads(raw)
                require(isinstance(value, dict), "Workspace returned an invalid response")
                return value
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            raise VerificationError("Workspace request failed; no provider error body was printed") from None


def verify_receipt(receipt):
    require(isinstance(receipt, dict) and receipt.get("id") == RECEIPT and receipt.get("task_id") == TASK and
            receipt.get("item_id") == ITEM and receipt.get("report_sha256") == DIGEST and receipt.get("status") == "passed" and
            receipt.get("task_status") == "done", "Execution receipt identity or completed task status differs")
    checks = receipt.get("checks", [])
    require(isinstance(checks, list) and len(checks) == 20 and all(isinstance(c, dict) for c in checks),
            "Execution receipt must contain twenty checks")
    ordered = sorted(checks, key=lambda check: check["name"])
    require(digest(ordered) == CHECK_DIGEST, "Execution check contents differ from the approved canonical checks")
    projection = {key: value for key, value in receipt.items() if key not in ("imported_at", "task_status")}
    projection["checks"] = ordered
    require(digest(projection) == RECEIPT_DIGEST, "Execution summary differs from the approved public receipt")
    return {check["id"] for check in checks}


def verify_workspace(workspace, check_ids):
    graph = workspace.get("graph")
    require(isinstance(graph, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", graph), "Workspace source graph is invalid")
    nodes = [row["data"] for row in workspace.get("nodes", [])]
    receipts = [node for node in nodes if node.get("kind") == "ExecutionReceipt"]
    checks = [node for node in nodes if node.get("kind") == "ExecutionCheck"]
    require(len(receipts) == 1 and receipts[0].get("id") == RECEIPT and len(checks) == 20 and
            {node.get("id") for node in checks} == check_ids, "Workspace graph execution node inventory differs")
    receipt_props = receipts[0].get("properties", {})
    require(receipt_props.get("report_sha256") == DIGEST and receipt_props.get("task_id") == TASK and
            receipt_props.get("item_id") == ITEM and receipt_props.get("status") == "passed", "Workspace graph receipt properties differ")
    for node in checks:
        props = node.get("properties", {})
        baseline = props.get("name", "").startswith("before_grow_only_")
        require(props.get("matched_expectation") is True and props.get("exit_code") == (101 if baseline else 0),
                "Workspace graph check outcome differs")
    edges = [row["data"] for row in workspace.get("edges", [])]
    has_execution = [e for e in edges if e.get("kind") == "HAS_EXECUTION"]
    validates = [e for e in edges if e.get("kind") == "VALIDATES"]
    has_checks = [e for e in edges if e.get("kind") == "HAS_CHECK"]
    require(len(has_execution) == 1 and (has_execution[0].get("source"), has_execution[0].get("target")) == (TASK, RECEIPT),
            "Workspace task-to-execution relationship differs")
    require(len(validates) == 1 and (validates[0].get("source"), validates[0].get("target")) == (RECEIPT, ITEM),
            "Workspace execution-to-source relationship differs")
    require(len(has_checks) == 20 and all(e.get("source") == RECEIPT for e in has_checks) and
            {e.get("target") for e in has_checks} == check_ids, "Workspace execution-to-check relationships differ")
    require(any(e.get("kind") == "TRACKS" and e.get("source") == TASK and e.get("target") == ITEM for e in edges),
            "Workspace task-to-source relationship is missing")
    tasks = [task for task in workspace.get("tasks", []) if task.get("id") == TASK]
    require(len(tasks) == 1 and tasks[0].get("status") == "done", "Workspace task is not independently confirmed done")
    return graph


def verify(report_path, workspace=None):
    raw = approved_manifest(report_path)
    client = workspace or Workspace()
    token = operator_token()
    login = client.request("/api/auth/login", {"token": token})
    del token
    require(login.get("authenticated") is True, "Operator login was not confirmed")
    payload = {"task_id": TASK, "evidence_url": EVIDENCE, "manifest_json": raw}
    first = client.request("/api/public/executions", payload)
    check_ids = verify_receipt(first)
    second = client.request("/api/public/executions", payload)
    verify_receipt(second)
    require(first == second, "Repeated import changed the execution receipt")
    public = client.request("/api/public/executions")
    receipts = public.get("executions", [])
    require(isinstance(receipts, list) and len(receipts) == 1, "Independent public read did not return exactly one execution")
    verify_receipt(receipts[0])
    require(receipts[0] == second, "Independent public receipt differs from import readback")
    graph = verify_workspace(client.request("/api/public/workspace"), check_ids)
    return {"status": "verified", "task_id": TASK, "task_status": "done", "receipt_id": RECEIPT,
        "report_sha256": DIGEST, "source_graph": graph, "execution_receipts": 1, "execution_checks": 20,
        "has_execution_links": 1, "validates_links": 1, "has_check_links": 20, "idempotent_import": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = verify(args.report)
    except VerificationError as error:
        result = {"status": "failed", "error": str(error)}
    except Exception:
        result = {"status": "failed", "error": "Execution verification failed; no private configuration or provider payload was printed"}
    encoded = json.dumps(result, sort_keys=True)
    if args.output:
        try:
            Path(args.output).write_text(encoded + "\n", encoding="utf-8")
        except OSError:
            result = {"status": "failed", "error": "Verification output could not be saved"}
            encoded = json.dumps(result, sort_keys=True)
    print(encoded)
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
