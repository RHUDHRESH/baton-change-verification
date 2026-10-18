"""Mock only external I/O while exercising the real repair endpoint and diff gate."""
from contextlib import nullcontext
import copy
import io
import json
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from server import autonomous_workflow as workflow
from scripts import autonomous_worker as worker


# The actual constructor expression from pinned d8190da5, with a small enclosing
# production region. No model, Docker, network or provider mutation is performed.
OLD = """        let pack_ceiling = match record_cap {
            Some(cap) if cap < BATCH_SIZE => cap.max(1),
            _ => BATCH_SIZE,
        };"""
NEW = "        let pack_ceiling = record_cap.unwrap_or(BATCH_SIZE).clamp(1, BATCH_SIZE);"
SOURCE = "// Source documentation\nfn production() {\n" + OLD + "\n}\n#[cfg(test)]\nmod tests { unchanged(); }\n"


@pytest.fixture
def repair_fixture(monkeypatch, tmp_path):
    record = {"id": "a" * 32, "status": "running", "repair_responses": {}, "repairs": [],
              "investigation": {"action": {"reason": "Verify grow-only tensor resize and unchanged tests"}},
              "stages": [{"id": "repair", "status": "pending"}]}
    control = SimpleNamespace(lock=lambda *args, **kwargs: nullcontext(), incr=lambda *args: 1, expire=lambda *args: True)
    monkeypatch.setattr(workflow, "connect", lambda port: control)
    monkeypatch.setattr(workflow, "_read", lambda *args: record)
    monkeypatch.setattr(workflow, "_save", MagicMock())
    monkeypatch.setattr(workflow, "bind_run", MagicMock())
    monkeypatch.setattr(workflow, "original_source", lambda: SOURCE)
    monkeypatch.setenv("GROQ_API_KEY", "private-test-model-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    output = {"old": OLD, "new": NEW, "explanation": "Express the same upper and lower clamp explicitly."}
    calls = []
    headers = []

    def provider(request, timeout):
        calls.append(json.loads(request.data))
        headers.append(dict(request.header_items()))
        raw = {"id": "chatcmpl-measured-repair", "model": "openai/gpt-oss-20b",
               "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
               "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
        return io.BytesIO(json.dumps(raw).encode())

    monkeypatch.setattr(workflow.urllib.request, "urlopen", provider)
    prefix, _, tail = SOURCE.partition("#[cfg(test)]")
    body = {"attempt": 1, "github_run_id": "123", "source_commit": workflow.SOURCE_COMMIT,
            "editable_source": {"path": workflow.EDITABLE, "sha256": workflow.sha(prefix), "text": prefix},
            "test_region_sha256": workflow.sha("#[cfg(test)]" + tail),
            "failed_check": {"name": "graph_library_initial", "argv": worker.LIBRARY_ARGV, "exit_code": 101,
                             "log_sha256": "d" * 64, "log_tail": "cap_at_or_above_batch_size_is_ignored left:1025 right:1024"}}
    return SimpleNamespace(record=record, output=output, calls=calls, headers=headers, body=body, data=tmp_path)


def repair(fixture):
    return workflow.repair(fixture.data, 6379, fixture.record["id"], fixture.body)


def test_endpoint_constructs_valid_diff_from_measured_model_edit_and_exact_original(repair_fixture):
    answer = repair(repair_fixture)
    patch = worker.validate_patch(answer["patch"])
    assert worker.sha(patch) == answer["patch_sha256"]
    assert worker.measured_receipt(answer["provider_receipt"])
    assert "-        let pack_ceiling = match record_cap {" in answer["patch"]
    assert "+" + NEW in answer["patch"]
    assert "#[cfg(test)]" not in answer["patch"]
    assert "private-test-model-key" not in json.dumps(repair_fixture.record)
    assert len(repair_fixture.calls) == 1
    assert repair(repair_fixture) == answer and len(repair_fixture.calls) == 1


def test_runner_cannot_supply_an_invented_first_production_region(repair_fixture):
    source = repair_fixture.body["editable_source"]
    source["text"] += "fn invented() {}\n"
    source["sha256"] = workflow.sha(source["text"])
    with pytest.raises(workflow.WorkflowError):
        repair(repair_fixture)
    assert repair_fixture.calls == []


def test_repair_uses_the_same_identifying_transport_header_as_working_graph_agent(repair_fixture):
    repair(repair_fixture)
    assert repair_fixture.headers[0]["User-agent"] == "Baton-Agent/0.3"
    assert repair_fixture.headers[0]["Content-type"] == "application/json"


def test_provider_403_is_recordable_without_relaying_its_body_or_credentials(repair_fixture, monkeypatch):
    def denied(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "private error reason", {}, io.BytesIO(b"private-test-model-key"))
    monkeypatch.setattr(workflow.urllib.request, "urlopen", denied)
    with pytest.raises(workflow.WorkflowError, match="Groq repair returned HTTP 403") as caught:
        repair(repair_fixture)
    assert "private" not in str(caught.value)
    assert repair_fixture.record["repair_responses"] == {}


@pytest.mark.parametrize("old", ["does not exist", "", " "])
def test_model_edit_must_match_one_nonempty_exact_original_substring(repair_fixture, old):
    repair_fixture.output["old"] = old
    with pytest.raises(workflow.WorkflowError):
        repair(repair_fixture)
    assert repair_fixture.record["repair_responses"] == {}


def test_model_cannot_modify_test_region(repair_fixture):
    repair_fixture.output.update(old="unchanged();", new="ignored();")
    with pytest.raises(workflow.WorkflowError):
        repair(repair_fixture)


def test_unsafe_model_edit_is_rejected_before_worker_execution(repair_fixture):
    repair_fixture.output["new"] = NEW + "\n        unsafe { bypass(); }"
    try:
        response = repair(repair_fixture)
    except workflow.WorkflowError:
        return
    with pytest.raises(ValueError, match="unsafe"):
        worker.validate_patch(response["patch"])


def test_replay_cannot_replace_the_original_failure_input(repair_fixture):
    repair(repair_fixture)
    repair_fixture.body["failed_check"]["log_tail"] += "changed"
    with pytest.raises(workflow.WorkflowError, match="replay"):
        repair(repair_fixture)
    assert len(repair_fixture.calls) == 1
