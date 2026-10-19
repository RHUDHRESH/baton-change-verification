"""Read-only preflight contracts; all AWS/network boundaries are mocked."""
import base64
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_preflight", ROOT / "deploy/release_preflight.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    raw = b"approved code ZIP boundary fixture"
    environment = {"BATON_CONTROL_DYNAMODB_TABLE": "baton-control", "BATON_CLOUD_STATE_GRAPH": "baton_cloud_state",
        "FALKORDB_HOST": "approved-free.test", "FALKORDB_PORT": "12345", "FALKORDB_TLS": "0", "FALKORDB_USERNAME": "private-user",
        "FALKORDB_PASSWORD": "private-graph-password", "GROQ_API_KEY": "DO-NOT-PRINT-PROVIDER-SECRET"}
    config = {"CodeSha256": base64.b64encode(bytes.fromhex(P.sha(raw))).decode(), "RevisionId": "revision-current",
              "Environment": {"Variables": environment}}
    lambda_client = MagicMock()
    lambda_client.get_function.return_value = {"Configuration": config,
        "Code": {"Location": "https://example.s3.ap-south-1.amazonaws.com/code.zip?X-Amz-Credential=DO-NOT-PRINT-SIGNED-URL"}}
    lambda_client.get_function_configuration.return_value = dict(config)
    dynamo = MagicMock()
    dynamo.describe_table.return_value = {"Table": {"TableStatus": "ACTIVE", "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}}}
    counters = {"release:allowance:2026-10": 0, "autonomous:allowance:2026-10": 4, "lambda:requests:2026-10": 321}
    dynamo.get_item.side_effect = lambda **kwargs: {"Item": {"value": {"N": str(counters[kwargs["Key"]["pk"]["S"]])}}}
    monkeypatch.setattr(P, "clients", lambda: (lambda_client, dynamo))
    requests = []
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def open(self, request, **kwargs):
            requests.append(request)
            return Response(raw)
    monkeypatch.setattr(P.urllib.request, "build_opener", lambda *args: Opener())
    redis = SimpleNamespace(Redis=MagicMock())
    redis.Redis.return_value.execute_command.return_value = [[], [[json.dumps({"used": 17})]], []]
    monkeypatch.setattr(P, "_redis", lambda *args: redis)
    return SimpleNamespace(directory=tmp_path, now=datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc), raw=raw, config=config,
        environment=environment, lambda_client=lambda_client, dynamo=dynamo, redis=redis, requests=requests)


def test_preflight_observes_exact_counter_keys_without_mutation_or_credential_output(boundary):
    result = P.preflight(boundary.directory, boundary.now)
    assert result["status"] == "observed" and result["read_only"] is True
    assert {name: budget["used"] for name, budget in result["budgets"].items()} == {
        "release_matrix": 0, "autonomous_shared": 4, "monthly_app_requests": 321, "shared_groq_daily": 17}
    assert [entry.kwargs["Key"]["pk"]["S"] for entry in boundary.dynamo.get_item.call_args_list] == [
        "release:allowance:2026-10", "autonomous:allowance:2026-10", "lambda:requests:2026-10"]
    assert result["budgets"]["shared_groq_daily"]["key"] == "quotas/2026-10-19.json"
    assert result["dynamodb"]["read_capacity_units"] == result["dynamodb"]["write_capacity_units"] == 5
    target = Path(result["dependency_archive"]["path"])
    assert target.read_bytes() == boundary.raw and P.sha(target.read_bytes()) == result["dependency_archive"]["sha256"]
    assert result["lambda"]["CodeSha256"] == boundary.config["CodeSha256"]
    assert boundary.lambda_client.mock_calls == [call.get_function(FunctionName=P.FUNCTION), call.get_function_configuration(FunctionName=P.FUNCTION)]
    assert all(entry[0] in {"describe_table", "get_item"} for entry in boundary.dynamo.mock_calls)
    assert len(boundary.requests) == 1 and boundary.requests[0].get_method() == "GET"
    assert "Authorization" not in boundary.requests[0].headers
    assert boundary.redis.Redis.return_value.execute_command.call_args.args[0] == "GRAPH.RO_QUERY"
    assert "DO-NOT-PRINT" not in json.dumps(result)
    assert "private-graph-password" not in json.dumps(result)
    assert list(boundary.directory.iterdir()) == [target]


def test_code_downloads_are_unique_and_never_overwrite_an_existing_archive(boundary):
    first = P.current_code(boundary.lambda_client, boundary.directory)[1]
    second = P.current_code(boundary.lambda_client, boundary.directory)[1]
    assert first["path"] != second["path"]
    assert Path(first["path"]).read_bytes() == Path(second["path"]).read_bytes() == boundary.raw


@pytest.mark.parametrize("mutation", ["wrong-code-hash", "changed-readback-hash", "changed-revision", "unsafe-location"])
def test_current_code_identity_must_match_download_and_independent_readback(boundary, mutation):
    if mutation == "wrong-code-hash": boundary.config["CodeSha256"] = base64.b64encode(b"0" * 32).decode()
    elif mutation == "changed-readback-hash": boundary.lambda_client.get_function_configuration.return_value["CodeSha256"] = base64.b64encode(b"0" * 32).decode()
    elif mutation == "changed-revision": boundary.lambda_client.get_function_configuration.return_value["RevisionId"] = "different-revision"
    else: boundary.lambda_client.get_function.return_value["Code"]["Location"] = "https://evil.invalid/code.zip?DO-NOT-PRINT"
    with pytest.raises(P.PreflightError):
        P.current_code(boundary.lambda_client, boundary.directory)
    assert list(boundary.directory.iterdir()) == []


def test_missing_and_expired_counters_are_observed_without_resetting_them():
    dynamo = MagicMock()
    dynamo.get_item.side_effect = [{}, {"Item": {"value": {"N": "8"}, "expires": {"N": "1"}}}]
    missing = P.counter(dynamo, "existing-table", "release:allowance:2026-10", 2, 100)
    expired = P.counter(dynamo, "existing-table", "release:allowance:2026-10", 2, 100)
    assert missing["used"] == expired["used"] == 0
    assert missing["record_present"] is False and expired["record_present"] is True and expired["expired"] is True
    assert all(entry[0] == "get_item" for entry in dynamo.mock_calls)


@pytest.mark.parametrize("rows", [[], [["{}", "extra"]], [[json.dumps({"used": True})]], [["{}"], ["{}"]]])
def test_daily_quota_is_zero_only_for_an_observed_absent_record(boundary, rows):
    boundary.redis.Redis.return_value.execute_command.return_value = [[], rows, []]
    if rows:
        with pytest.raises(P.PreflightError):
            P.daily_usage(boundary.environment, {}, "quotas/2026-10-19.json")
    else:
        result = P.daily_usage(boundary.environment, {}, "quotas/2026-10-19.json")
        assert result["used"] == 0 and result["record_present"] is False
    boundary.redis.Redis.return_value.close.assert_called_once()


def test_preflight_failure_does_not_print_private_environment_or_signed_url(monkeypatch, tmp_path, capsys):
    def stopped(*args):
        raise RuntimeError("DO-NOT-PRINT-PRIVATE-CONFIGURATION")
    monkeypatch.setattr(P, "preflight", stopped)
    output = tmp_path / "preflight.json"
    assert P.main(["--output", str(output)]) == 1
    assert "DO-NOT-PRINT" not in capsys.readouterr().out + output.read_text()
