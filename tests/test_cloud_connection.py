from unittest.mock import Mock, patch

import pytest
from baton import graph


def test_managed_connection_uses_credentials_and_verifies_tls(monkeypatch):
    monkeypatch.setenv("FALKORDB_HOST","example.falkordb.cloud")
    monkeypatch.setenv("FALKORDB_USERNAME","graph-user")
    monkeypatch.setenv("FALKORDB_PASSWORD","test-secret")
    monkeypatch.setenv("FALKORDB_TLS","1")
    with patch("falkordb.FalkorDB") as client:
        graph.connect(12345)
    args=client.call_args.kwargs
    assert args["username"]=="graph-user" and args["password"]=="test-secret"
    assert args["host"]=="example.falkordb.cloud" and args["port"]==12345
    assert args["ssl"] and args["ssl_check_hostname"] and args["ssl_cert_reqs"]=="required"


def test_connection_failure_does_not_echo_provider_secrets(monkeypatch):
    monkeypatch.setenv("FALKORDB_PASSWORD","test-secret")
    with patch("falkordb.FalkorDB",side_effect=RuntimeError("test-secret")):
        with pytest.raises(graph.Unreachable) as error:
            graph.connect(6379)
    assert "test-secret" not in str(error.value)
