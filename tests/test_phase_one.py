"""Additional portability, data integrity and phase-boundary checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from baton.generate import build

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run([sys.executable, "-m", "baton", *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)


def test_supplied_assertions_and_reference_remain_unchanged():
    manifest = json.loads((ROOT / "tests/locked/MANIFEST.json").read_text())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("args", [(), ("generate",), ("generate", "--seed", "x", "--out", "unused"),
                                  ("unknown-command",)])
def test_missing_invalid_or_future_commands_are_rejected(args):
    result = cli(*args)
    assert result.returncode == 2
    assert not result.stdout


@pytest.mark.parametrize("scale", ["0", "65"])
def test_invalid_scale_creates_no_output(tmp_path, scale):
    directory = tmp_path / "must-not-exist"
    result = cli("generate", "--seed", "7", "--scale", scale, "--out", str(directory))
    assert result.returncode == 2
    assert not directory.exists()


def test_unicode_nested_output_is_utf8_and_has_lf_newlines(tmp_path):
    directory = tmp_path / "Baton données" / "company"
    result = cli("generate", "--seed", "7", "--out", str(directory))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["graph"] == "halden_7"
    for name in ("world.json", "answer_key.json"):
        raw = (directory / name).read_bytes()
        assert b"\r\n" not in raw
        assert json.loads(raw.decode("utf-8"))


@pytest.mark.parametrize("scale", [1, 4, 8])
def test_generated_objects_match_supplied_snapshot(scale):
    path = ROOT / "reference/Baton_build_pack/repo_snapshot/baton/generate.py"
    spec = importlib.util.spec_from_file_location("supplied_generator", path)
    supplied = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supplied)
    assert build(7, scale) == supplied.build(7, scale)


def test_world_references_and_departure_invariant_across_sixty_seeds():
    for seed in range(60):
        world, key = build(seed)
        people = {p["id"] for p in world["people"]}
        duties = {d["id"] for d in world["duties"]}
        rotas = {r["rota"] for r in world["records"] if r["type"] == "ROUTES_TO"}
        for collection in ("people", "duties", "events", "records", "messages", "joblogs", "tickets"):
            ids = [row["id"] for row in world[collection]]
            assert len(ids) == len(set(ids)), (seed, collection)
        for event in world["events"]:
            assert event["duty"] in duties
            assert isinstance(event["at"], int)
        for record in world["records"]:
            if "person" in record:
                assert record["person"] in people
            if "duty" in record:
                assert record["duty"] in duties
            if "rota" in record:
                assert record["rota"] in rotas
            if record["type"] == "ESCALATES_TO":
                assert record["from_person"] in people and record["to_person"] in people
                assert record["from_person"] != world["leaver"]
        assert world["label"] == "FIXTURE"
        assert key["leaver"] == world["leaver"]


def test_product_imports_only_standard_library_and_never_imports_grading_code():
    import ast
    for path in [ROOT / "baton/generate.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                assert node.module.split(".")[0] in sys.stdlib_module_names
