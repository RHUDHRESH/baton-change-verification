"""Portable M01 CLI fixture; no database process or network access is needed."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def baton(*args, check=True):
    result = subprocess.run(
        [sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT,
        capture_output=True, text=True, timeout=30,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def write_beliefs(directory, beliefs, name="beliefs.json"):
    path = Path(directory) / name
    path.write_text(json.dumps(beliefs), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def worlds(tmp_path_factory):
    cache = {}

    def get(seed):
        if seed not in cache:
            directory = tmp_path_factory.mktemp(f"w{seed}")
            baton("generate", "--seed", seed, "--out", directory)
            cache[seed] = (
                directory,
                json.loads((directory / "world.json").read_text(encoding="utf-8")),
                json.loads((directory / "answer_key.json").read_text(encoding="utf-8")),
            )
        return cache[seed]

    return get
