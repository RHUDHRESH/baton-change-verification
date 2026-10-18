"""Reuse isolated engine fixtures; never attack the running application database."""
import importlib.util
import json
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "integration" / "conftest.py"
spec = importlib.util.spec_from_file_location("redteam_isolation", path)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
engine = fixtures.engine
service = fixtures.service


@pytest.fixture(scope="session")
def observe():
    observations = []

    def record(name, outcome, **details):
        observations.append({"name": name, "outcome": outcome, **details})

    yield record
    output = Path(__file__).resolve().parents[2] / "artifacts/redteam-observations.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
