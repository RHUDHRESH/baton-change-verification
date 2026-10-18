"""Own an isolated engine for transport tests; run with deploy/Dockerfile.checks."""
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest
import redis


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    directory = tmp_path_factory.mktemp("transport-engine")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen([
        os.environ["BATON_TEST_REDIS"], "--port", str(port), "--dir", str(directory),
        "--loadmodule", os.environ["BATON_TEST_MODULE"], "--save", "", "--logfile", str(directory / "redis.log"),
    ])
    client = redis.Redis(port=port, socket_connect_timeout=1)
    try:
        for _ in range(100):
            try:
                client.ping()
                break
            except redis.ConnectionError:
                time.sleep(.1)
        else:
            pytest.fail("Test engine did not start")
        yield port, client
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def service(engine, monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    monkeypatch.setenv("BATON_OPERATOR_TOKEN", "test-only-operator-credential-" + "x" * 32)
    from server import app as api
    port, client = engine
    client.flushall()  # This fixture exclusively owns this freshly spawned engine.
    monkeypatch.setattr(api, "PORT", port)
    monkeypatch.setattr(api, "HOST", "localhost")
    monkeypatch.setattr(api, "DATA", tmp_path / "companies")
    monkeypatch.setenv("BATON_OFFLINE", "1")
    monkeypatch.setenv("FALKORDB_HOST", "localhost")
    monkeypatch.setenv("FALKORDB_PORT", str(port))
    monkeypatch.setenv("BATON_DATA", str(api.DATA))
    return api
