"""Disposable full HTTP/FalkorDB stack for browser security regression checks.

Run inside graphhacks-checks, publishing container port 8000 as host 8001.
All fixture changes stay under /tmp and disappear with the test container.
"""
import os
from pathlib import Path
import subprocess
import sys
import time

import redis

directory = Path("/tmp/baton-security-e2e")
directory.mkdir(exist_ok=True)
engine = subprocess.Popen([os.environ["BATON_TEST_REDIS"], "--port", "6381", "--dir", str(directory),
                           "--loadmodule", os.environ["BATON_TEST_MODULE"], "--save", "", "--logfile", str(directory / "redis.log")])
server = None
try:
    client = redis.Redis(port=6381)
    for _ in range(100):
        try:
            client.ping()
            break
        except redis.ConnectionError:
            time.sleep(.1)
    else:
        raise RuntimeError("Disposable engine failed to start")
    environment = dict(os.environ, FALKORDB_HOST="localhost", FALKORDB_PORT="6381", BATON_DATA=str(directory), BATON_OFFLINE="1")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"], env=environment)
    raise SystemExit(server.wait())
finally:
    if server is not None and server.poll() is None:
        server.terminate()
        server.wait(timeout=10)
    engine.terminate()
    engine.wait(timeout=10)
