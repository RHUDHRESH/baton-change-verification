"""Submit exactly one fresh Groq brief and verify stored output and graph citations.

CloudShell: python verify_live_brief.py --output verified-live-brief.json
No tasks or provider messages are created. A failed POST is never repeated.
"""
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

ORIGIN = "https://baton-workspace.vercel.app"
ITEM = "FalkorDB/FalkorDB#3246"
QUESTION = "Summarize the reported tensor issue and proposed grow-only fix. Cite captured source evidence and distinguish reported claims from executed verification."
ARCHIVE_SHA256 = "c08c71044f76a487737059bef34cce6caf2785ae9788829a3c8a7d71ac3dfe20"


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def lambda_environment():
    import boto3
    from botocore.config import Config
    config = boto3.client("lambda", region_name="ap-south-1", config=Config(connect_timeout=3,
        read_timeout=10, retries={"total_max_attempts": 1})).get_function_configuration(FunctionName="baton-workspace")
    return config.get("Environment", {}).get("Variables", {})


def operator_token(environment):
    token = environment.get("BATON_OPERATOR_TOKEN")
    require(isinstance(token, str) and len(token) >= 24, "Existing operator credential is unavailable")
    return token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VerificationError("Workspace redirect was refused")


class Workspace:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self, path, payload=None):
        require(path in ("/api/auth/login", "/api/public/workspace", "/api/public/inference") or
                re.fullmatch(r"/api/public/inference/[a-f0-9]{32}", path), "Workspace request path is not approved")
        headers = {"Origin": ORIGIN, "Accept": "application/json"}
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(ORIGIN + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with self.opener.open(request, timeout=115) as response:
                expected = 202 if path == "/api/public/inference" and payload is not None else 200
                require(response.status == expected, "Workspace returned an unexpected status")
                raw = response.read(8_000_001)
                require(len(raw) <= 8_000_000, "Workspace response exceeded its bound")
                result = json.loads(raw)
                require(isinstance(result, dict), "Workspace response is invalid")
                return result
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            raise VerificationError("Workspace request failed; the inference POST was not automatically retried") from None


def check_run(run, source_ids):
    require(run.get("status") == "succeeded" and run.get("provider") == "Groq" and run.get("item_id") == ITEM and
            run.get("cached") is False, "Fresh Groq inference did not succeed")
    require(isinstance(run.get("id"), str) and re.fullmatch(r"[a-f0-9]{32}", run["id"]), "Inference identity is invalid")
    for field in ("model", "provider_response_id"):
        require(isinstance(run.get(field), str) and re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", run[field]), "Groq provider receipt is incomplete")
    require(all(type(run.get(key)) is int and run[key] > 0 for key in ("input_tokens", "output_tokens")),
            "Groq token usage is missing or zero")
    for field in ("input_sha256", "output_sha256", "provider_response_sha256"):
        require(isinstance(run.get(field), str) and re.fullmatch(r"[a-f0-9]{64}", run[field]), "Inference evidence hash is invalid")
    raw = run.get("raw_output")
    require(isinstance(raw, str) and hashlib.sha256(raw.encode()).hexdigest() == run["output_sha256"], "Inference output hash does not match stored bytes")
    output = run.get("output", {})
    require(json.loads(raw) == output and isinstance(output.get("summary"), str) and output["summary"] and
            isinstance(output.get("findings"), list), "Stored inference output does not match its JSON evidence")
    refs = output.get("source_ids", [])
    require(isinstance(refs, list) and refs and len(refs) == len(set(refs)) and set(refs).issubset(source_ids) and
            set(run.get("source_ids", [])).issubset(source_ids), "Inference cites missing or unrelated captured source evidence")
    return refs


def check_graph(workspace, run, refs):
    nodes = [row["data"] for row in workspace.get("nodes", [])]
    edges = [row["data"] for row in workspace.get("edges", [])]
    runs = [node for node in nodes if node.get("id") == run["id"] and node.get("kind") == "InferenceRun"]
    require(len(runs) == 1, "Stored graph inference node is missing or duplicated")
    props = runs[0].get("properties", {})
    require(all(props.get(key) == run.get(key) for key in ("provider", "model", "input_sha256", "output_sha256", "input_tokens", "output_tokens")),
            "Stored graph inference receipt differs from the provider readback")
    require(any(edge.get("kind") == "ANALYZED" and edge.get("source") == run["id"] and edge.get("target") == ITEM for edge in edges),
            "Stored graph inference does not analyze the requested root issue")
    claims = {run["id"] + "-claim-" + str(index): text for index, text in enumerate([run["output"]["summary"]] + run["output"]["findings"])}
    actual = {node["id"]: node.get("properties", {}).get("text") for node in nodes if node.get("kind") == "AIClaim" and node.get("id", "").startswith(run["id"] + "-claim-")}
    require(actual == claims, "Stored graph claims differ from the generated brief")
    produced = [edge for edge in edges if edge.get("kind") == "PRODUCED" and edge.get("source") == run["id"]]
    require(len(produced) == len(claims) and {edge.get("target") for edge in produced} == set(claims), "Stored graph claim relationships are incomplete")
    graph = workspace.get("graph")
    require(isinstance(graph, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", graph), "Workspace source graph is invalid")
    require(graph == run.get("graph"), "Inference source graph differs from the displayed workspace")
    return graph, claims


def check_citations(environment, archive, graph, run_id, claims, refs):
    # The public graph projection deliberately omits Source nodes/CITES edges.
    # Query only those relationships privately and read-only in the real graph.
    path = Path(archive)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == ARCHIVE_SHA256, "Approved Lambda dependency archive hash differs")
    sys.path.insert(0, str(path.resolve()))
    import redis
    host = environment.get("FALKORDB_HOST")
    port = int(environment.get("FALKORDB_PORT", "6379"))
    require(isinstance(host, str) and host and 1 <= port <= 65535, "Private graph connection configuration is unavailable")
    setting = environment.get("FALKORDB_TLS")
    require(isinstance(setting, str) and (setting == "0" or setting.lower() in ("1", "true", "yes")),
            "Private graph transport configuration must explicitly select the approved mode")
    tls = setting.lower() in ("1", "true", "yes")
    transport = {"ssl": tls}
    if tls:
        transport.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    connection = redis.Redis(host=host, port=port, username=environment.get("FALKORDB_USERNAME") or None,
        password=environment.get("FALKORDB_PASSWORD") or None,
        socket_connect_timeout=3, socket_timeout=15, decode_responses=True, **transport)
    require(re.fullmatch(r"[a-f0-9]{32}", run_id) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", graph), "Read-only graph identity is invalid")
    query = "MATCH (r:InferenceRun {id:'" + run_id + "'})-[:PRODUCED]->(c:AIClaim)-[:CITES]->(s:Source) RETURN c.id,s.id"
    try:
        response = connection.execute_command("GRAPH.RO_QUERY", graph, query)
    finally:
        connection.close()
    require(isinstance(response, list) and len(response) >= 2 and isinstance(response[1], list), "Read-only graph citation response is invalid")
    rows = response[1]
    expected = {(claim, ref) for claim in claims for ref in refs}
    require(all(isinstance(row, list) and len(row) == 2 for row in rows) and len(rows) == len(expected) and
            {tuple(row) for row in rows} == expected, "Actual graph citation relationships are missing or unrelated")
    return len(rows)


def verify(archive="Baton_lambda_1c137fb.zip", client=None):
    client = client or Workspace()
    before = client.request("/api/public/workspace")
    items = [item for item in before.get("items", []) if item.get("id") == ITEM]
    require(len(items) == 1 and items[0].get("source_ids"), "Captured root issue evidence is unavailable")
    sources = set(items[0]["source_ids"])
    require(all(isinstance(source, str) and re.fullmatch(r"[A-Za-z0-9_:/#.-]{1,200}", source) for source in sources), "Captured source identity is invalid")
    environment = lambda_environment()
    token = operator_token(environment)
    login = client.request("/api/auth/login", {"token": token})
    del token
    require(login.get("authenticated") is True, "Operator login was not confirmed")
    # Exactly one inference POST. Polling is read-only, never a resubmission.
    run = client.request("/api/public/inference", {"item_id": ITEM, "question": QUESTION})
    require(isinstance(run.get("id"), str) and re.fullmatch(r"[a-f0-9]{32}", run["id"]), "Inference POST returned no valid run identity; do not resubmit blindly")
    path = "/api/public/inference/" + run["id"]
    for _ in range(12):
        if run.get("status") not in ("queued", "running"):
            break
        time.sleep(2)
        run = client.request(path)
    refs = check_run(run, sources)
    stored = client.request(path)
    check_run(stored, sources)
    require(all(stored.get(key) == run.get(key) for key in ("id", "provider", "model", "provider_response_id", "provider_response_sha256",
        "input_sha256", "output_sha256", "input_tokens", "output_tokens", "output")), "Independent inference readback differs from the submitted run")
    graph, claims = check_graph(client.request("/api/public/workspace"), stored, refs)
    cites = check_citations(environment, archive, graph, stored["id"], claims, refs)
    del environment
    return {"status": "verified", "run_id": stored["id"], "item_id": ITEM, "provider": "Groq", "model": stored["model"],
        "provider_response_id": stored["provider_response_id"], "provider_response_sha256": stored["provider_response_sha256"],
        "input_sha256": stored["input_sha256"], "output_sha256": stored["output_sha256"], "input_tokens": stored["input_tokens"],
        "output_tokens": stored["output_tokens"], "source_ids": sorted(refs), "source_graph": graph, "inference_nodes": 1,
        "claim_nodes": len(claims), "citation_links": cites, "inference_posts": 1, "citation_verification": "actual_graph_ro_query"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--lambda-archive", default="Baton_lambda_1c137fb.zip")
    args = parser.parse_args()
    try:
        result = verify(args.lambda_archive)
    except VerificationError as error:
        result = {"status": "failed", "error": str(error)}
    except Exception:
        result = {"status": "failed", "error": "Live brief verification failed; no private configuration or output text was printed"}
    text = json.dumps(result, sort_keys=True)
    if args.output:
        try:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError:
            result = {"status": "failed", "error": "Verification output could not be saved"}
            text = json.dumps(result)
    print(text)
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
