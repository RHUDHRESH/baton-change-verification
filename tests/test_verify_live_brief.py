"""Fresh-brief verifier failure gates, without provider or graph connections."""
import copy
import hashlib
import importlib.util
import json
import ssl
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_live_brief", ROOT / "deploy/verify_live_brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)


@pytest.fixture
def fixture(monkeypatch):
    identity = "a" * 32
    output = {"summary": "private-model-output", "findings": ["reported claim"], "source_ids": ["source-1"]}
    raw = json.dumps(output)
    run = {"id": identity, "item_id": brief.ITEM, "graph": "baton_test", "status": "succeeded", "provider": "Groq",
        "cached": False, "model": "openai/gpt-oss-20b", "provider_response_id": "chatcmpl-test", "input_tokens": 80,
        "output_tokens": 40, "input_sha256": "1" * 64, "provider_response_sha256": "2" * 64,
        "output_sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw_output": raw, "output": output, "source_ids": ["source-1"]}
    claims = {identity + "-claim-0": output["summary"], identity + "-claim-1": output["findings"][0]}
    graph = {"graph": "baton_test", "items": [{"id": brief.ITEM, "source_ids": ["source-1"]}], "nodes": [
        {"data": {"id": identity, "kind": "InferenceRun", "properties": run}}] + [
        {"data": {"id": key, "kind": "AIClaim", "properties": {"text": value}}} for key, value in claims.items()],
        "edges": [{"data": {"kind": "ANALYZED", "source": identity, "target": brief.ITEM}}] + [
            {"data": {"kind": "PRODUCED", "source": identity, "target": key}} for key in claims]}
    monkeypatch.setattr(brief, "lambda_environment", lambda: {"BATON_OPERATOR_TOKEN": "private-token-" + "x" * 30})
    citations = MagicMock(return_value=2)
    monkeypatch.setattr(brief, "check_citations", citations)
    client = MagicMock()
    client.request.side_effect = [copy.deepcopy(graph), {"authenticated": True}, copy.deepcopy(run), copy.deepcopy(run), graph]
    return run, graph, client, citations


def test_one_fresh_post_independent_readback_and_graph_citations_without_output_echo(fixture):
    run, graph, client, citations = fixture
    result = brief.verify(client=client)
    assert result["status"] == "verified" and result["citation_links"] == 2 and result["claim_nodes"] == 2
    assert result["inference_posts"] == 1 and result["provider_response_id"] == run["provider_response_id"]
    calls = [call for call in client.request.call_args_list if call.args[0] == "/api/public/inference"]
    assert len(calls) == 1 and calls[0].args[1]["question"] == brief.QUESTION
    assert "private-model-output" not in json.dumps(result) and "private-token" not in json.dumps(result)
    assert citations.call_args.args[2:4] == ("baton_test", run["id"])


@pytest.mark.parametrize("mutation", ["tokens", "provider", "raw-hash", "citations", "cached"])
def test_fabricated_or_incomplete_receipts_are_rejected(fixture, mutation):
    run, _, _, _ = fixture
    if mutation == "tokens": run["input_tokens"] = 0
    elif mutation == "provider": run["provider"] = "Substitute"
    elif mutation == "raw-hash": run["raw_output"] += " "
    elif mutation == "cached": run["cached"] = True
    else:
        run["output"]["source_ids"] = ["unrelated-source"]
        run["raw_output"] = json.dumps(run["output"])
        run["output_sha256"] = hashlib.sha256(run["raw_output"].encode()).hexdigest()
    with pytest.raises(brief.VerificationError):
        brief.check_run(run, {"source-1"})


def test_graph_claim_tampering_is_rejected(fixture):
    run, graph, _, _ = fixture
    graph["nodes"][1]["data"]["properties"]["text"] = "forged"
    with pytest.raises(brief.VerificationError, match="claims"):
        brief.check_graph(graph, run, ["source-1"])


def test_bad_dependency_archive_stops_before_loading_or_connecting(tmp_path):
    archive = tmp_path / "unapproved.zip"
    archive.write_bytes(b"untrusted")
    with pytest.raises(brief.VerificationError, match="archive hash"):
        brief.check_citations({}, archive, "baton_test", "a" * 32, {}, [])


def test_post_transport_failure_is_never_resubmitted(fixture):
    _, graph, client, _ = fixture
    client.request.side_effect = [graph, {"authenticated": True}, brief.VerificationError("POST ambiguous")]
    with pytest.raises(brief.VerificationError, match="ambiguous"):
        brief.verify(client=client)
    assert len([call for call in client.request.call_args_list if call.args[0] == "/api/public/inference"]) == 1


def graph_transport(monkeypatch, tmp_path, setting):
    archive = tmp_path / "approved.zip"
    archive.write_bytes(b"approved dependency fixture")
    monkeypatch.setattr(brief, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    redis = MagicMock()
    monkeypatch.setitem(sys.modules, "redis", redis)
    redis.Redis.return_value.execute_command.return_value = [[], [["claim", "source"]], []]
    environment = {"FALKORDB_HOST": "approved-free.test", "FALKORDB_PORT": "6379", "FALKORDB_TLS": setting,
        "FALKORDB_PASSWORD": "private-password"}
    return archive, redis, environment


def test_approved_free_explicit_zero_uses_existing_plaintext_mode(monkeypatch, tmp_path):
    archive, redis, environment = graph_transport(monkeypatch, tmp_path, "0")
    assert brief.check_citations(environment, archive, "baton_test", "a" * 32, {"claim": "text"}, ["source"]) == 1
    options = redis.Redis.call_args.kwargs
    assert options["ssl"] is False and "ssl_cert_reqs" not in options and "ssl_check_hostname" not in options
    assert redis.Redis.return_value.execute_command.call_args.args[0] == "GRAPH.RO_QUERY"
    redis.Redis.assert_called_once()


def test_tls_failure_never_downgrades_or_reconnects(monkeypatch, tmp_path):
    archive, redis, environment = graph_transport(monkeypatch, tmp_path, "1")
    redis.Redis.return_value.execute_command.side_effect = ssl.SSLError("certificate failure")
    with pytest.raises(ssl.SSLError):
        brief.check_citations(environment, archive, "baton_test", "a" * 32, {"claim": "text"}, ["source"])
    redis.Redis.assert_called_once()
    options = redis.Redis.call_args.kwargs
    assert options["ssl"] is True and options["ssl_cert_reqs"] == "required" and options["ssl_check_hostname"] is True
    redis.Redis.return_value.close.assert_called_once()


@pytest.mark.parametrize("setting", [None, "false", "", "unexpected"])
def test_plaintext_requires_explicit_zero_configuration(monkeypatch, tmp_path, setting):
    archive, redis, environment = graph_transport(monkeypatch, tmp_path, setting)
    with pytest.raises(brief.VerificationError, match="explicitly"):
        brief.check_citations(environment, archive, "baton_test", "a" * 32, {"claim": "text"}, ["source"])
    redis.Redis.assert_not_called()
