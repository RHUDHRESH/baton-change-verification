"""Contract tests use mocked transport; these are not live inference evidence."""
import io
import json
import urllib.error
from contextlib import nullcontext
from unittest.mock import MagicMock,patch

import pytest
from server import groq_inference as groq
from server import public_workspace as public


def response(output=None, **updates):
    payload={"id":"mock-completion-id","model":"openai/gpt-oss-20b","created":1,
             "choices":[{"finish_reason":"stop","message":{"content":json.dumps(output or {
                 "summary":"Test brief","findings":[],"next_steps":[],"uncertainties":[],"source_ids":["s1"]})}}],
             "usage":{"prompt_tokens":100,"completion_tokens":20}}
    payload.update(updates)
    stream=io.BytesIO(json.dumps(payload).encode())
    stream.headers={"x-request-id":"mock-request-id"}
    return stream


@pytest.fixture
def job(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY","test-only-never-real")
    monkeypatch.delenv("GROQ_MODEL",raising=False)
    return {"prompt":"Test JSON prompt", "source_ids":["s1"]}


def test_missing_key_never_calls_provider(job,monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with patch.object(groq.urllib.request,"urlopen") as network:
        with pytest.raises(RuntimeError,match="not configured"):
            groq.generate(job)
        network.assert_not_called()


def test_provider_receipt_and_strict_schema(job):
    with patch.object(groq.urllib.request,"urlopen",return_value=response()) as network:
        result=groq.generate(job)
    request=network.call_args.args[0]
    body=json.loads(request.data)
    assert request.full_url==groq.ENDPOINT
    assert body["model"]=="openai/gpt-oss-20b"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert result["provider"]=="Groq" and result["provider_response_id"]=="mock-completion-id"
    assert result["provider_request_id"]=="mock-request-id" and result["output_tokens"]==20
    assert "test-only-never-real" not in json.dumps(result)


@pytest.mark.parametrize("refs",[[],["invented-source"]])
def test_unknown_or_missing_citations_rejected(job,refs):
    answer={"summary":"Unsupported","findings":[],"next_steps":[],"uncertainties":[],"source_ids":refs}
    with patch.object(groq.urllib.request,"urlopen",return_value=response(answer)):
        with pytest.raises(ValueError,match="citations"):
            groq.generate(job)


def test_no_automatic_retry_or_secret_echo(job):
    error=urllib.error.HTTPError(groq.ENDPOINT,429,"test-only-never-real",{},None)
    with patch.object(groq.urllib.request,"urlopen",side_effect=error) as network:
        with pytest.raises(RuntimeError,match="HTTP 429") as caught:
            groq.generate(job)
        assert "test-only-never-real" not in str(caught.value)
        assert network.call_count==1


def test_truncated_output_rejected(job):
    with patch.object(groq.urllib.request,"urlopen",return_value=response(choices=[{"finish_reason":"length","message":{"content":"{}"}}])):
        with pytest.raises(ValueError,match="incomplete"):
            groq.generate(job)


def test_usage_required(job):
    with patch.object(groq.urllib.request,"urlopen",return_value=response(usage={})):
        with pytest.raises(ValueError,match="token usage"):
            groq.generate(job)


@pytest.mark.parametrize("used,allowed", [(59,True),(60,False)])
def test_public_brief_shared_daily_limit_preserves_counter_and_blocks_provider(
        monkeypatch,tmp_path,used,allowed):
    monkeypatch.setenv("GROQ_API_KEY","test-only-never-real")
    monkeypatch.setenv("BATON_INFERENCE_MODE","request")
    monkeypatch.setattr(public,"now",lambda:"2026-10-19T00:00:00+00:00")
    item={"id":"repo#1","title":"Captured issue","body":"Observed behavior","state":"open", "kind":"issue",
          "url":"https://github.com/repo/issues/1","author":"contributor","assignees":[],"reviewers":[],"files":[],"source_ids":["s1"]}
    monkeypatch.setattr(public,"snapshot",lambda data:{"id":"snapshot","graph":"source-graph","items":[item]})
    stored={"quotas/2026-10-19.json":{"used":used}}
    monkeypatch.setattr(public,"read",lambda data,key,default=None:stored.get(key,default))
    monkeypatch.setattr(public,"write",lambda data,key,value:stored.update({key:value}))
    db=MagicMock()
    db.set.return_value=True
    db.lock.side_effect=lambda *args,**kwargs:nullcontext()
    monkeypatch.setattr(public,"control_connect",lambda port:db)
    monkeypatch.setattr(public,"poll_run",lambda data,port,identity:{"id":identity,"status":"succeeded"})
    with patch.object(groq,"generate",return_value={"status":"succeeded"}) as provider:
        if allowed:
            assert public.queue_inference(tmp_path,6379,item["id"],"Inspect source")["status"]=="succeeded"
            assert provider.call_count==1
        else:
            with pytest.raises(RuntimeError,match="60 provider calls per UTC day"):
                public.queue_inference(tmp_path,6379,item["id"],"Inspect source")
            provider.assert_not_called()
    assert public.DAILY_INFERENCE_LIMIT==60
    assert stored["quotas/2026-10-19.json"]=={"used":60}
    db.delete.assert_not_called()
    assert not any(call.args[0].startswith("quotas/") for call in db.set.call_args_list)
