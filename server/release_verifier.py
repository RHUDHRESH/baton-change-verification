"""Independent artifact validation for the approved Python client release case.

The caller must first establish the workflow SHA, completed execute job, and
artifact identity using GitHub. A runner callback alone is never evidence.
"""
from __future__ import annotations

import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET

from . import release_contract as C

MAX_ARTIFACT_FILE = 4 * 1024 * 1024
LOCK_PATH = Path(__file__).with_name("release_dependency_lock.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dependencies(redis_version):
    require(redis_version in {row["redis_version"] for row in C.ENVIRONMENTS}, "Unapproved redis version")
    return {**C.DEPENDENCIES, "redis": redis_version}


def dependency_lock(redis_version):
    expected = dependencies(redis_version)
    registry = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    rows = {(name, version): wheels for name, version, wheels in registry}
    lines = []
    for name, version in sorted(expected.items(), key=lambda row: row[0].lower()):
        wheels = rows.get((name, version), [])
        require(wheels and all(re.fullmatch(r"[a-f0-9]{64}", wheel["sha256"]) for wheel in wheels),
                "Reviewed dependency wheel hash is missing")
        lines.append(name + "==" + version + " " + " ".join("--hash=sha256:" + x["sha256"] for x in wheels))
    return ("\n".join(lines) + "\n").encode()


def test_argv():
    return ["python", "-m", "pytest", "-v", "-o", "addopts=", "-p", "no:cacheprovider",
            "--junitxml=/out/junit.xml", *C.CHECK_IDS]


def install_argv():
    return ["python", "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-deps",
            "--only-binary=:all:", "--require-hashes", "-r", "/work/requirements.lock"]


def source_hashes(raw):
    require(isinstance(raw, bytes) and C.sha(raw) == C.SOURCE_ARCHIVE_SHA256,
            "Source archive does not match the approved commit")
    prefix = "falkordb-py-" + C.SOURCE_COMMIT + "/"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            require(len(rows) < 5000 and sum(x.file_size for x in rows) < 16 * 1024 * 1024,
                    "Source archive exceeds its bound")
            result = {}
            for item in rows:
                path = PurePosixPath(item.filename)
                require(item.filename.startswith(prefix) and not path.is_absolute() and ".." not in path.parts and
                        "\\" not in item.filename,
                        "Unsafe source archive path")
                if not item.is_dir():
                    relative = item.filename[len(prefix):]
                    require(relative and relative not in result, "Duplicate source archive entry")
                    result[relative] = C.sha(archive.read(item))
            require(result and all(result.get(path) == digest for path, digest in C.SOURCE_HASHES.items()),
                    "Source blobs differ from the approved registry")
            return result
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise ValueError("Invalid source archive") from error


def validate_plan(plan):
    require(isinstance(plan, dict), "Sealed plan is missing")
    for key, expected in (("schema_version", C.SCHEMA_VERSION), ("registry_version", C.REGISTRY_VERSION),
                          ("policy_version", C.POLICY_VERSION), ("change_id", C.CHANGE_ID), ("plan_status", "ready")):
        require(plan.get(key) == expected, "Plan " + key + " differs from the approved registry")
    require(C.selected_ids(plan) == list(C.CHECK_IDS), "Plan checks differ from the approved registry")
    require(plan.get("environments") == list(C.ENVIRONMENTS), "Plan environments differ from the approved registry")
    for key, expected in (("source_commit", C.SOURCE_COMMIT), ("source_archive_sha256", C.SOURCE_ARCHIVE_SHA256),
                          ("source_hashes", C.SOURCE_HASHES), ("python_version", C.PYTHON_VERSION),
                          ("python_image", C.PYTHON_IMAGE), ("falkordb_image", C.FALKORDB_IMAGE)):
        require(plan.get(key) == expected, "Plan " + key + " differs from the approved registry")
    require(re.fullmatch(r"[a-f0-9]{64}", plan.get("plan_hash", "")), "Sealed plan hash is missing")
    require(C.plan_hash(plan) == plan["plan_hash"], "Sealed plan content hash differs")
    return plan


def junit_results(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) < MAX_ARTIFACT_FILE and b"<!DOCTYPE" not in raw.upper() and
            b"<!ENTITY" not in raw.upper(), "Invalid JUnit document")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("Malformed JUnit document") from error
    require(root.tag == "testsuites" and len(root) == 1 and root[0].tag == "testsuite", "Unexpected JUnit suite structure")
    suite = root[0]
    cases = list(suite)
    require(len(cases) == len(C.CHECK_IDS) and all(case.tag == "testcase" for case in cases),
            "JUnit must contain exactly four regression cases")
    results = []
    for case in cases:
        classname, name = case.get("classname", ""), case.get("name", "")
        identity = classname.replace(".", "/") + ".py::" + name
        require(identity in C.CHECK_IDS, "JUnit includes an unapproved test identity")
        outcomes = [child for child in case if child.tag in {"failure", "error", "skipped"}]
        require(len(outcomes) <= 1 and all(child.tag in {"failure", "error", "skipped", "system-out", "system-err", "properties"}
                                         for child in case), "JUnit case has ambiguous outcomes")
        require(not outcomes or outcomes[0].tag != "skipped", "Skipped regression tests do not establish verification")
        status = {"failure": "failed", "error": "error"}.get(outcomes[0].tag, "passed") if outcomes else "passed"
        excerpt = outcomes[0].get("message", "")[:500] if outcomes else ""
        results.append({"id": identity, "status": status, "classname": classname, "name": name, "failure_excerpt": excerpt})
    require([row["id"] for row in results] == list(C.CHECK_IDS), "JUnit test identities are missing, duplicated, or reordered")
    counts = {"total": len(results), "passed": sum(x["status"] == "passed" for x in results),
              "failed": sum(x["status"] == "failed" for x in results),
              "errors": sum(x["status"] == "error" for x in results), "skipped": 0}
    for xml_name, key in (("tests", "total"), ("failures", "failed"), ("errors", "errors"), ("skipped", "skipped")):
        require(suite.get(xml_name) == str(counts[key]), "JUnit suite counters contradict individual cases")
    return counts, results


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON property")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (json.JSONDecodeError, UnicodeError, TypeError) as error:
        raise ValueError("Invalid release report JSON") from error


def _verify_artifact(plan, run, files):
    """Return normalized test observations, or reject missing/substituted evidence.

    Test failures produce ``status=blocked`` with verified evidence. They must
    never be converted to infrastructure errors or a successful release.
    """
    validate_plan(plan)
    require(isinstance(run, dict) and isinstance(files, dict), "Run or artifact files are missing")
    require(all(isinstance(path, str) and not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts and
                "\\" not in path and isinstance(raw, bytes) and len(raw) < MAX_ARTIFACT_FILE for path, raw in files.items()),
            "Unsafe artifact entry")
    require("release-report.json" in files and "source.zip" in files, "Release report or source archive is missing")
    report = _json(files["release-report.json"])
    require(isinstance(report, dict) and type(report.get("schema_version")) is int and
            report["schema_version"] == C.SCHEMA_VERSION, "Unsupported release report")
    run_id = run.get("id", run.get("run_id"))
    plan_id = plan.get("id", plan.get("plan_id"))
    require(run_id and plan_id and report.get("run_id") == run_id and report.get("plan_id") == plan_id,
            "Artifact belongs to another run or plan")
    require(run.get("plan_id", plan_id) == plan_id and run.get("source_commit", C.SOURCE_COMMIT) == C.SOURCE_COMMIT,
            "Run source or plan binding differs")
    require(report.get("plan_hash") == plan["plan_hash"] == run.get("plan_hash"), "Artifact plan hash differs")
    expected_sha = run.get("runner", {}).get("workflow_sha") or run.get("workflow_sha")
    require(isinstance(expected_sha, str) and re.fullmatch(r"[a-f0-9]{40}", expected_sha) and
            report.get("workflow_sha") == expected_sha, "Artifact workflow SHA differs from GitHub")
    all_source = source_hashes(files["source.zip"])
    for key, expected in (("source_commit", C.SOURCE_COMMIT), ("source_archive_sha256", C.SOURCE_ARCHIVE_SHA256),
                          ("source_hashes", all_source)):
        require(report.get(key) == expected, "Artifact " + key + " binding differs")
    require(report.get("source_unchanged") is True and not report.get("infrastructure_errors"), "Source integrity was not established")
    environments = report.get("environments")
    require(isinstance(environments, list) and [row.get("id") for row in environments] == [row["id"] for row in C.ENVIRONMENTS],
            "Artifact environments are missing, duplicated, or substituted")
    normalized, flat_results, expected_files = [], [], {"release-report.json", "source.zip"}
    for environment, approved in zip(environments, C.ENVIRONMENTS):
        env_id = approved["id"]
        for key, expected in (("redis_version", approved["redis_version"]), ("python_version", C.PYTHON_VERSION),
                              ("python_image", C.PYTHON_IMAGE), ("falkordb_image", C.FALKORDB_IMAGE),
                              ("dependencies", dependencies(approved["redis_version"])),
                              ("source_hashes_before", all_source), ("source_hashes_after", all_source)):
            require(environment.get(key) == expected, "Environment " + key + " binding differs")
        lock_path = env_id + "/requirements.lock"
        require(files.get(lock_path) == dependency_lock(approved["redis_version"]), "Dependency lock was substituted")
        require(environment.get("dependency_lock_sha256") == C.sha(files[lock_path]), "Dependency lock hash differs")
        checks = environment.get("checks")
        require(isinstance(checks, list) and len(checks) == 1, "Approved test command is missing or duplicated")
        check = checks[0]
        require(check.get("id") == "py211-regressions" and check.get("argv") == test_argv(), "Unapproved test command")
        log_path, xml_path = env_id + "/pytest.log", env_id + "/junit.xml"
        require(check.get("log_file") == log_path and check.get("junit_file") == xml_path and
                log_path in files and xml_path in files, "Raw check artifacts are missing")
        raw_log, raw_xml = files[log_path], files[xml_path]
        require(check.get("log_sha256") == C.sha(raw_log) and check.get("junit_sha256") == C.sha(raw_xml), "Raw artifact hash differs")
        counts, cases = junit_results(raw_xml)
        require(all(type(check.get(key)) is int and check[key] == value for key, value in counts.items()),
                "Reported check counters contradict JUnit")
        exit_code = check.get("exit_code")
        require(type(exit_code) is int and exit_code == (1 if counts["failed"] or counts["errors"] else 0),
                "Test exit status contradicts JUnit")
        command_line = ("BATON_COMMAND " + C.encode(test_argv()) + "\n").encode()
        require(raw_log.startswith(command_line) and raw_log.endswith(("\nBATON_EXIT_CODE " + str(exit_code) + "\n").encode()),
                "Raw log command/exit binding differs")
        log = raw_log.decode("utf-8", "replace")
        require(re.search(r"\bcollected 4 items\b", log), "Raw log does not establish positive collection")
        for case in cases:
            require(case["id"] + " " + {"passed": "PASSED", "failed": "FAILED", "error": "ERROR"}[case["status"]] in log,
                    "Raw log contradicts the individual JUnit result")
        if "test_results" in environment:
            require(environment["test_results"] == cases, "Reported per-test observations contradict JUnit")
        normalized.append({"id": env_id, "redis_version": approved["redis_version"], "checks": cases, **counts})
        flat_results.extend({"check_id": row["id"], "environment_id": env_id, **{k: v for k, v in row.items() if k != "id"}}
                            for row in cases)
        expected_files.update({lock_path, log_path, xml_path, env_id + "/setup.log"})
        require(env_id + "/setup.log" in files and environment.get("setup_log_sha256") == C.sha(files[env_id + "/setup.log"]),
                "Environment setup log is missing or changed")
        setup = files[env_id + "/setup.log"]
        require(setup.startswith(("BATON_SETUP_COMMAND " + C.encode(install_argv()) + "\n").encode()),
                "Dependency install did not use the reviewed hash-locked command")
        marker = b"\nBATON_ENVIRONMENT "
        require(setup.count(marker) == 1 and setup.endswith(b"\n"), "Raw environment measurement is missing")
        measured = _json(setup.split(marker)[1].strip())
        require(measured == {"python_version": C.PYTHON_VERSION, "dependencies": dependencies(approved["redis_version"]),
                             "imported_source": "/work/unpacked/falkordb-py-" + C.SOURCE_COMMIT + "/falkordb/__init__.py"},
                "Raw environment measurements contradict the approved bindings")
        require("Python " + C.PYTHON_VERSION + ", pytest-" + C.DEPENDENCIES["pytest"] in log,
                "Raw test runtime differs from the approved environment")
    require(set(files) == expected_files, "Artifact contains unapproved or missing files")
    totals = {key: sum(row[key] for row in normalized) for key in ("passed", "failed", "errors", "skipped", "total")}
    return {"verified": True, "evidence_verified": True, "status": "blocked" if totals["failed"] or totals["errors"] else "passed",
            "id": run_id, "run_id": run_id, "plan_id": plan_id, "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT,
            "artifact_sha256": C.sha(files["release-report.json"]), "source_unchanged": True,
            "environments": normalized, "results": flat_results, **totals}


def verify_artifact(plan, run, files):
    """Reject malformed/incomplete evidence with a stable ValueError boundary."""
    try:
        return _verify_artifact(plan, run, files)
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed release verification artifact") from error
