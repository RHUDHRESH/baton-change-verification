"""Read existing release budgets and download the current approved Lambda code.

CloudShell helper: no inference, dispatch, counter increments, resets, resource
creation, or provider writes. Lambda environment and signed URLs stay in memory.
Only a uniquely named code ZIP and optional non-secret proof JSON are written.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request

FUNCTION, REGION = "baton-workspace", "ap-south-1"
MAX_CODE_BYTES = 49 * 1024 * 1024


class PreflightError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PreflightError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PreflightError("Code download redirect refused")


def clients():
    import boto3
    from botocore.config import Config
    config = Config(connect_timeout=3, read_timeout=15, retries={"total_max_attempts": 1})
    return (boto3.client("lambda", region_name=REGION, config=config),
            boto3.client("dynamodb", region_name=REGION, config=config))


def current_code(client, directory):
    metadata = client.get_function(FunctionName=FUNCTION)
    configuration = metadata.get("Configuration", {})
    digest_b64, revision = configuration.get("CodeSha256", ""), configuration.get("RevisionId", "")
    try:
        digest_bytes = base64.b64decode(digest_b64, validate=True)
    except (ValueError, TypeError):
        raise PreflightError("Lambda code hash metadata is invalid") from None
    require(len(digest_bytes) == 32 and isinstance(revision, str) and re.fullmatch(r"[A-Za-z0-9-]{1,100}", revision),
            "Lambda code hash or revision is unavailable")
    location = metadata.get("Code", {}).get("Location", "")
    try:
        parsed = urllib.parse.urlsplit(location)
        allowed = (parsed.scheme == "https" and parsed.hostname and parsed.username is None and parsed.password is None and
                   parsed.port in (None, 443) and not parsed.fragment and parsed.hostname.endswith((".amazonaws.com", ".amazonaws.com.cn")))
    except (ValueError, TypeError):
        allowed = False
    require(allowed, "Lambda code download is outside approved AWS storage")
    try:
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(urllib.request.Request(location, method="GET"), timeout=40) as response:
            raw = response.read(MAX_CODE_BYTES + 1)
    except PreflightError:
        raise
    except Exception:
        raise PreflightError("Current Lambda code download was not confirmed; signed URL was not printed") from None
    digest = digest_bytes.hex()
    require(len(raw) <= MAX_CODE_BYTES and sha(raw) == digest, "Downloaded Lambda code differs from CodeSha256")
    readback = client.get_function_configuration(FunctionName=FUNCTION)
    require(readback.get("CodeSha256") == digest_b64 and readback.get("RevisionId") == revision,
            "Lambda code or configuration changed during read-only preflight")
    target = Path(directory).resolve()
    require(target.is_dir(), "Choose an existing local directory for the dependency archive")
    handle, filename = tempfile.mkstemp(prefix="baton-release-current-", suffix=".zip", dir=str(target))
    with os.fdopen(handle, "wb") as stream:
        stream.write(raw)
    private = configuration.get("Environment", {}).get("Variables", {})
    require(isinstance(private, dict), "Existing Lambda configuration is unavailable")
    keys = ("BATON_CONTROL_DYNAMODB_TABLE", "BATON_CLOUD_STATE_GRAPH", "FALKORDB_HOST", "FALKORDB_PORT", "FALKORDB_TLS",
            "FALKORDB_USERNAME", "FALKORDB_PASSWORD")
    environment = {key: private.get(key, "") for key in keys}
    return ({"function": FUNCTION, "CodeSha256": digest_b64, "RevisionId": revision},
            {"path": str(Path(filename).resolve()), "sha256": digest, "bytes": len(raw)}, environment)


def _number(attribute):
    require(isinstance(attribute, dict) and len(attribute) == 1 and next(iter(attribute)) in {"S", "N"}, "Stored counter has an unsupported type")
    value = next(iter(attribute.values()))
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{1,13}", value), "Stored counter is not a nonnegative integer")
    return int(value)


def counter(client, table, key, limit, epoch):
    response = client.get_item(TableName=table, Key={"pk": {"S": key}}, ConsistentRead=True)
    row = response.get("Item")
    expiry = _number(row["expires"]) if row and row.get("expires") else 0
    expired = bool(expiry and expiry <= epoch)
    used = _number(row["value"]) if row and not expired else 0
    return {"key": key, "used": used, "limit": limit, "remaining": max(0, limit - used),
            "record_present": bool(row), "expired": expired}


def _redis(archive):
    path = Path(archive["path"]).resolve()
    require(path.is_file() and sha(path.read_bytes()) == archive["sha256"], "Current dependency ZIP hash changed before import")
    prefix = str(path).replace("\\", "/") + "/redis/"
    for name, module in tuple(sys.modules.items()):
        if name == "redis" or name.startswith("redis."):
            require(str(getattr(module, "__file__", "")).replace("\\", "/").startswith(prefix), "An unrelated Redis client is already loaded")
    sys.path.insert(0, str(path))
    module = importlib.import_module("redis")
    require(str(getattr(module, "__file__", "")).replace("\\", "/").startswith(prefix), "Redis client was not imported from the current approved ZIP")
    return module


def daily_usage(environment, archive, key):
    graph, host, port, setting = (environment.get("BATON_CLOUD_STATE_GRAPH", ""), environment.get("FALKORDB_HOST", ""),
                                 environment.get("FALKORDB_PORT") or "6379", environment.get("FALKORDB_TLS"))
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,120}", graph) and re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", host) and
            re.fullmatch(r"[0-9]{1,5}", str(port)) and 1 <= int(port) <= 65535 and isinstance(setting, str) and
            (setting == "0" or setting.lower() in {"1", "true", "yes"}) and re.fullmatch(r"quotas/[0-9]{4}-[0-9]{2}-[0-9]{2}\.json", key),
            "Configured graph state storage or explicit transport mode is unavailable; daily usage is unknown")
    redis = _redis(archive)
    transport = {"ssl": setting != "0"}
    if transport["ssl"]:
        transport.update(ssl_cert_reqs="required", ssl_check_hostname=True)
    connection = redis.Redis(host=host, port=int(port), username=environment.get("FALKORDB_USERNAME") or None,
        password=environment.get("FALKORDB_PASSWORD") or None, socket_connect_timeout=3, socket_timeout=10, decode_responses=True, **transport)
    try:
        response = connection.execute_command("GRAPH.RO_QUERY", graph,
            "MATCH (s:WorkspaceRecord {id:'" + key + "'}) RETURN s.json LIMIT 2", "TIMEOUT", 5000)
        require(isinstance(response, list) and len(response) >= 2 and isinstance(response[1], list) and len(response[1]) <= 1,
                "Shared Groq daily quota record is missing its unique identity")
        rows = response[1]
        require(not rows or (isinstance(rows[0], list) and len(rows[0]) == 1 and isinstance(rows[0][0], str)),
                "Shared Groq daily usage returned an invalid record")
        record = json.loads(rows[0][0]) if rows else {"used": 0}
        used = record.get("used")
        require(type(used) is int and used >= 0, "Shared Groq daily usage is not a nonnegative integer")
        return {"key": key, "used": used, "limit": 60, "remaining": max(0, 60 - used), "record_present": bool(rows),
                "read_only_command": "GRAPH.RO_QUERY"}
    finally:
        connection.close()


def preflight(directory, now=None):
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, "Preflight time must have an explicit timezone")
    now = now.astimezone(timezone.utc)
    lambda_client, dynamo = clients()
    function, archive, environment = current_code(lambda_client, directory)
    try:
        table = environment.get("BATON_CONTROL_DYNAMODB_TABLE", "")
        require(isinstance(table, str) and re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table), "Configured existing DynamoDB control table is unavailable")
        description = dynamo.describe_table(TableName=table).get("Table", {})
        capacity = description.get("ProvisionedThroughput", {})
        month = now.strftime("%Y-%m")
        budgets = {name: counter(dynamo, table, key + month, limit, int(now.timestamp())) for name, key, limit in (
            ("release_matrix", "release:allowance:", 2), ("autonomous_shared", "autonomous:allowance:", 10),
            ("monthly_app_requests", "lambda:requests:", 5000))}
        budgets["shared_groq_daily"] = daily_usage(environment, archive, "quotas/" + now.strftime("%Y-%m-%d") + ".json")
        return {"status": "observed", "read_only": True, "as_of_utc": now.isoformat(), "lambda": function, "dependency_archive": archive,
            "budgets": budgets, "dynamodb": {"billing_mode": description.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED"),
                "status": description.get("TableStatus"), "read_capacity_units": capacity.get("ReadCapacityUnits"),
                "write_capacity_units": capacity.get("WriteCapacityUnits")},
            "limits": ["Only current Lambda metadata/code download, DynamoDB GET/describe, and GRAPH.RO_QUERY were performed.",
                "No counter reset/increment, inference, dispatch, resource creation, or provider writes occurred.",
                "The downloaded file contains Lambda code only; its private environment and signed download URL were not saved."]}
    finally:
        environment.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-dir", default=tempfile.gettempdir())
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = preflight(args.download_dir)
    except PreflightError as error:
        result = {"status": "unconfirmed", "read_only": True, "error": str(error)}
    except Exception:
        result = {"status": "unconfirmed", "read_only": True,
                  "error": "Read-only preflight stopped; no private configuration, signed URL, or credential was printed"}
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
