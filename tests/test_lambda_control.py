"""DynamoDB and Lambda adapter contracts, using Moto; not live AWS evidence."""
import os
import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def control(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION","ap-south-1")
    with mock_aws():
        boto3.resource("dynamodb").create_table(TableName="baton-test",KeySchema=[{"AttributeName":"pk","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"pk","AttributeType":"S"}],ProvisionedThroughput={"ReadCapacityUnits":5,"WriteCapacityUnits":5})
        from server.dynamo_control import DynamoControl
        yield DynamoControl("baton-test")


def test_session_expiration_and_nonce(control):
    assert control.set("session","opaque",nx=True,ex=30)
    assert control.get("session")=="opaque"
    assert not control.set("session","replacement",nx=True,ex=30)
    with patch("server.dynamo_control.time.time",return_value=time.time()+60):
        assert control.get("session") is None
        assert control.set("session","new",nx=True,ex=30)
    assert control.get("session")=="new"
    control.delete("session")
    assert control.get("session") is None


def test_atomic_counter_resets_expired_item(control):
    assert control.incr("attempts")==1
    assert control.incr("attempts")==2
    control.expire("attempts",1)
    with patch("server.dynamo_control.time.time",return_value=time.time()+5):
        assert control.incr("attempts")==1
    assert control.incr("attempts")==2


def test_lease_excludes_other_operations_and_releases(control):
    with control.lock("task",blocking_timeout=0):
        with pytest.raises(RuntimeError,match="busy"):
            with control.lock("task",blocking_timeout=0):
                pass
    with control.lock("task",blocking_timeout=0):
        assert control.get("lease:task")
    assert control.get("lease:task") is None


def test_expired_lease_owner_cannot_remove_replacement(control):
    with control.lock("task",timeout=1):
        with patch("server.dynamo_control.time.time",return_value=time.time()+10):
            assert control.set("lease:task","replacement",nx=True,ex=60)
    assert control.get("lease:task")=="replacement"


def test_function_url_serves_real_app_and_rejects_monthly_overage(control,monkeypatch):
    monkeypatch.setenv("BATON_ALLOWED_HOSTS","test.lambda-url.ap-south-1.on.aws")
    for key,value in {"BATON_DATA":"/tmp/baton","BATON_CLOUD_STATE_GRAPH":"test-state","BATON_INFERENCE_MODE":"request"}.items():
        monkeypatch.setenv(key,value)
    # Import with intended environment; no network requests for this static page.
    from server import lambda_entry
    event={"version":"2.0","routeKey":"$default","rawPath":"/","rawQueryString":"",
           "headers":{"host":"test.lambda-url.ap-south-1.on.aws","x-forwarded-proto":"https"},
           "requestContext":{"accountId":"test","domainName":"test.lambda-url.ap-south-1.on.aws",
                             "http":{"method":"GET","path":"/","protocol":"HTTP/1.1","sourceIp":"127.0.0.1","userAgent":"contract-test"}},
           "isBase64Encoded":False}
    with patch.object(lambda_entry,"connect",return_value=control):
        result=lambda_entry.handler(event,{})
        assert result["statusCode"]==200
        assert "FalkorDB" in result["body"]
        with patch.object(control,"incr",return_value=5001):
            rejected=lambda_entry.handler(event,{})
        assert rejected["statusCode"]==429


def test_lambda_auth_and_cross_site_writes(control,monkeypatch,tmp_path):
    from server import lambda_entry,app as api
    from server import public_workspace
    monkeypatch.setenv("BATON_CONTROL_DYNAMODB_TABLE","baton-test")
    monkeypatch.setenv("BATON_OPERATOR_TOKEN","test-operator-"+"x"*32)
    monkeypatch.setattr(api,"DATA",tmp_path)
    def call(path,method="GET",body=None,cookies=None,origin=None):
        import json
        headers={"host":"test.lambda-url.ap-south-1.on.aws","x-forwarded-proto":"https","content-type":"application/json"}
        if origin:
            headers["origin"]=origin
        event={"version":"2.0","routeKey":"$default","rawPath":path,"rawQueryString":"","headers":headers,
               "requestContext":{"domainName":headers["host"],"http":{"method":method,"path":path,"protocol":"HTTP/1.1","sourceIp":"127.0.0.1"}},
               "body":json.dumps(body) if body else "","isBase64Encoded":False,"cookies":cookies or []}
        with patch.object(lambda_entry,"connect",return_value=control):
            return lambda_entry.handler(event,{})
    assert call("/api/public/tasks","POST",{"item_id":"x","title":"x"})["statusCode"]==401
    assert call("/api/auth/login","POST",{"token":os.environ["BATON_OPERATOR_TOKEN"]},origin="https://evil.example")["statusCode"]==403
    monkeypatch.setenv("BATON_ALLOWED_ORIGIN","https://baton-test.vercel.app")
    assert call("/api/auth/login","POST",{"token":os.environ["BATON_OPERATOR_TOKEN"]},origin="https://baton-test.vercel.app")["statusCode"]==200
    assert call("/api/auth/login","POST",{"token":os.environ["BATON_OPERATOR_TOKEN"]},origin="https://baton-test.vercel.app.evil.example")["statusCode"]==403
    monkeypatch.setenv("BATON_PREVIEW_ORIGIN","https://baton-preview.vercel.app")
    assert call("/api/auth/login","POST",{"token":os.environ["BATON_OPERATOR_TOKEN"]},origin="https://baton-preview.vercel.app")["statusCode"]==200
    assert call("/api/mcp","POST",{"jsonrpc":"2.0","id":1,"method":"tools/list"})["statusCode"]==401
    login=call("/api/auth/login","POST",{"token":os.environ["BATON_OPERATOR_TOKEN"]})
    assert login["statusCode"]==200
    cookie=login["cookies"][0]
    catalog=call("/api/mcp","POST",{"jsonrpc":"2.0","id":1,"method":"tools/list"},cookies=[cookie.split(";")[0]])
    assert catalog["statusCode"]==200 and 'follow_connections' in catalog["body"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=strict" in cookie.lower()
    with patch.object(public_workspace,"read",return_value=[]):
        export=call("/api/public/tasks.csv",cookies=[cookie.split(";")[0]])
    assert export["statusCode"]==200 and "Summary" in export["body"]
