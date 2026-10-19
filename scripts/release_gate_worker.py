"""Trusted host orchestrator for the immutable Python release verification plan.

The source runs only in disposable Docker containers. No host mounts, Docker
socket, callback capability, or provider credentials cross into those containers.
The host uploads evidence even when a required environment observes test failures.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import release_contract as C
from server.release_verifier import dependency_lock, dependencies, junit_results, source_hashes, test_argv, validate_plan

API_BASE = "https://kdeokfokg2d4jygx4ul3xwso5a0injxf.lambda-url.ap-south-1.on.aws"
MAX_BYTES = 4 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(path):
    request = urllib.request.Request(API_BASE + path, headers={"User-Agent": "Baton-Release-Verifier"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Public plan exceeds its bound")
    return json.loads(raw)


def callback(run_id, token, suffix, payload):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id) or not token:
        raise ValueError("Run callback capability is missing")
    request = urllib.request.Request(API_BASE + "/api/public/release-runs/" + run_id + "/" + suffix,
        data=C.encode(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "Baton-Release-Verifier"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=120 if suffix == "publish" else 150 if suffix == "complete" else 30) as response:
            return json.loads(response.read(MAX_BYTES))
    except urllib.error.HTTPError as error:
        # Never echo response bodies, request URLs, or the capability to logs.
        raise RuntimeError("Release callback returned HTTP " + str(error.code)) from None


def docker(*args, timeout=240, check=True):
    result = subprocess.run(["docker", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("Disposable container operation failed: " + args[0])
    return result


def client_script():
    """Static program copied to the source container; no host environment read."""
    return r'''
import hashlib, importlib.metadata, io, json, os, pathlib, subprocess, sys, zipfile
sys.dont_write_bytecode=True
def sha(raw): return hashlib.sha256(raw).hexdigest()
def hashes(root): return {str(p.relative_to(root)).replace('\\','/'):sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
cfg=json.loads(pathlib.Path('/work/config.json').read_text())
assert '.'.join(map(str,sys.version_info[:3])) == cfg['python_version']
raw=pathlib.Path('/work/source.zip').read_bytes();assert sha(raw)==cfg['archive_sha256']
base=pathlib.Path('/work/unpacked');base.mkdir()
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 for n in z.namelist():
  assert not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts and '\\' not in n
 z.extractall(base)
source=base/('falkordb-py-'+cfg['source_commit']);before=hashes(source);assert before==cfg['source_hashes']
out=pathlib.Path('/out');out.mkdir()
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'}
install=['python','-m','pip','install','--disable-pip-version-check','--no-cache-dir','--no-deps','--only-binary=:all:','--require-hashes','-r','/work/requirements.lock']
p=subprocess.run(install,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
setup=b'BATON_SETUP_COMMAND '+json.dumps(install,separators=(',',':')).encode()+b'\n'+p.stdout
(out/'setup.log').write_bytes(setup)
assert p.returncode==0, 'Hash-locked dependency installation failed'
actual={k:importlib.metadata.version(k) for k in cfg['dependencies']};assert actual==cfg['dependencies']
os.chdir(source);sys.path.insert(0,str(source))
import falkordb
assert pathlib.Path(falkordb.__file__).resolve()==source/'falkordb'/'__init__.py'
setup+=b'\nBATON_ENVIRONMENT '+json.dumps({'python_version':cfg['python_version'],'dependencies':actual,'imported_source':str(pathlib.Path(falkordb.__file__).resolve())},sort_keys=True,separators=(',',':')).encode()+b'\n'
(out/'setup.log').write_bytes(setup)
argv=cfg['argv'];p=subprocess.run(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
log=b'BATON_COMMAND '+json.dumps(argv,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()+b'\n'+p.stdout+b'\nBATON_EXIT_CODE '+str(p.returncode).encode()+b'\n'
(out/'pytest.log').write_bytes(log)
after=hashes(source)
(out/'metadata.json').write_text(json.dumps({'python_version':cfg['python_version'],'dependencies':actual,'source_hashes_before':before,'source_hashes_after':after,'exit_code':p.returncode},sort_keys=True))
assert before==after,'Source changed during execution'
assert p.returncode in (0,1),'Pytest infrastructure/collection error'
'''.lstrip().encode()


def inspect_isolation(name):
    info = json.loads(docker("inspect", name).stdout)[0]
    if info.get("Mounts") or info["HostConfig"].get("Privileged") or info["HostConfig"].get("PortBindings"):
        raise ValueError("Disposable source/database isolation was not established")
    network = info["HostConfig"].get("NetworkMode", "")
    if network != "bridge" and not network.startswith("container:"):
        raise ValueError("Disposable container uses an unapproved network")
    if info["Config"].get("Image") not in {C.PYTHON_IMAGE, C.FALKORDB_IMAGE}:
        raise ValueError("Disposable container image differs from the registry pin")
    environment = info["Config"].get("Env", [])
    if any(any(word in row.split("=", 1)[0].upper() for word in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY")) for row in environment):
        raise ValueError("A credential entered the disposable environment")


def execute_environment(run_id, approved, out, archive_path, all_source):
    env_id = approved["id"]
    target = out / env_id
    target.mkdir()
    lock = dependency_lock(approved["redis_version"])
    (target / "requirements.lock").write_bytes(lock)
    transient = out / (".staging-" + env_id)
    transient.mkdir()
    (transient / "client.py").write_bytes(client_script())
    (transient / "config.json").write_text(C.encode({"source_commit": C.SOURCE_COMMIT,
        "archive_sha256": C.SOURCE_ARCHIVE_SHA256, "source_hashes": all_source, "argv": test_argv(),
        "python_version": C.PYTHON_VERSION, "dependencies": dependencies(approved["redis_version"])}), encoding="utf-8")
    unique = C.sha((run_id + env_id + str(time.time_ns())).encode())[:16]
    db, client = "baton-release-db-" + unique, "baton-release-client-" + unique
    try:
        docker("create", "--name", db, "--platform", "linux/amd64", "--network", "bridge", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
               "--entrypoint", "redis-server", C.FALKORDB_IMAGE, "--loadmodule", "/var/lib/falkordb/bin/falkordb.so",
               "--save", "", "--appendonly", "no")
        inspect_isolation(db)
        docker("start", db)
        for attempt in range(45):
            ready = docker("exec", db, "redis-cli", "ping", timeout=10, check=False)
            if ready.returncode == 0 and ready.stdout.strip() == b"PONG":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Disposable database did not become ready")
        docker("create", "--name", client, "--platform", "linux/amd64", "--network", "container:" + db,
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "2",
               "--pids-limit", "256", "--workdir", "/work", "--entrypoint", "python", C.PYTHON_IMAGE, "/work/client.py")
        inspect_isolation(client)
        for path, destination in ((archive_path, "source.zip"), (target / "requirements.lock", "requirements.lock"),
                                  (transient / "client.py", "client.py"), (transient / "config.json", "config.json")):
            docker("cp", str(path.resolve()), client + ":/work/" + destination)
        executed = docker("start", "--attach", client, timeout=420, check=False)
        for filename in ("setup.log", "pytest.log", "junit.xml", "metadata.json"):
            copied = docker("cp", client + ":/out/" + filename, str((target / filename).resolve()), check=False)
            if copied.returncode:
                raise RuntimeError("Required disposable test evidence is missing")
            copied_path = target / filename
            if copied_path.is_symlink() or not copied_path.is_file() or copied_path.resolve().parent != target.resolve() or copied_path.stat().st_size > MAX_BYTES:
                raise ValueError("Disposable evidence is not a bounded regular file")
        if executed.returncode:
            raise RuntimeError("Disposable Python setup or test collection failed")
        metadata = json.loads((target / "metadata.json").read_text())
        (target / "metadata.json").unlink()
        if metadata.get("source_hashes_before") != all_source or metadata.get("source_hashes_after") != all_source:
            raise ValueError("The pinned source changed during test execution")
        counts, cases = junit_results((target / "junit.xml").read_bytes())
        return {"id": env_id, "redis_version": approved["redis_version"], "python_version": metadata["python_version"],
            "python_image": C.PYTHON_IMAGE, "falkordb_image": C.FALKORDB_IMAGE,
            "dependencies": metadata["dependencies"], "source_hashes_before": all_source, "source_hashes_after": all_source,
            "dependency_lock_sha256": C.sha(lock), "setup_log_sha256": C.sha((target / "setup.log").read_bytes()),
            "test_results": cases,
            "checks": [{"id": "py211-regressions", "argv": test_argv(), "exit_code": metadata["exit_code"], **counts,
                "log_file": env_id + "/pytest.log", "log_sha256": C.sha((target / "pytest.log").read_bytes()),
                "junit_file": env_id + "/junit.xml", "junit_sha256": C.sha((target / "junit.xml").read_bytes())}]}
    finally:
        docker("rm", "--force", client, db, timeout=35, check=False)
        # Only these two known staging files are removed; no recursive path deletion.
        for name in ("client.py", "config.json"):
            (transient / name).unlink(missing_ok=True)
        transient.rmdir()


def run_plan(plan, run_id, workflow_sha, out, emit=None):
    validate_plan(plan)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id) or not re.fullmatch(r"[a-f0-9]{40}", workflow_sha):
        raise ValueError("Run or workflow identity is invalid")
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Artifact directory must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen("https://codeload.github.com/" + C.REPOSITORY + "/zip/" + C.SOURCE_COMMIT, timeout=45) as response:
        raw = response.read(MAX_BYTES + 1)
    all_source = source_hashes(raw)
    archive = out / "source.zip"
    archive.write_bytes(raw)
    for image in (C.PYTHON_IMAGE, C.FALKORDB_IMAGE):
        docker("pull", "--platform", "linux/amd64", image, timeout=240)
    report = {"schema_version": C.SCHEMA_VERSION, "run_id": run_id, "plan_id": plan.get("id", plan.get("plan_id")),
        "plan_hash": plan["plan_hash"], "source_commit": C.SOURCE_COMMIT, "source_archive_sha256": C.SOURCE_ARCHIVE_SHA256,
        "workflow_sha": workflow_sha, "source_hashes": all_source, "environments": [], "source_unchanged": True}
    infrastructure = []
    for approved in C.ENVIRONMENTS:
        if emit:
            emit("environment-started", "Executing the approved regressions in a disposable database", approved["id"], "running")
        try:
            environment = execute_environment(run_id, approved, out, archive, all_source)
            report["environments"].append(environment)
            check = environment["checks"][0]
            status = "blocked" if check["failed"] or check["errors"] else "passed"
            if emit:
                emit("environment-completed", "Approved regression results captured", approved["id"], status)
        except Exception as error:
            # Continue the other required environment. Never fabricate a JUnit pass.
            infrastructure.append({"environment_id": approved["id"], "error": type(error).__name__})
            if emit:
                emit("failed", "Disposable environment did not produce complete evidence", approved["id"], "failed")
    if infrastructure:
        report["infrastructure_errors"] = infrastructure
        report["source_unchanged"] = False
    (out / "release-report.json").write_text(C.encode(report) + "\n", encoding="utf-8")
    if infrastructure:
        raise RuntimeError("One or more required environments did not produce complete evidence")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan-id", default=os.environ.get("BATON_PLAN_ID", ""))
    parser.add_argument("--plan-hash", default=os.environ.get("BATON_PLAN_HASH", ""))
    parser.add_argument("--out", default="release-artifact")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--local-plan", help="Offline smoke testing only; still enforces the immutable registry")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.run_id):
        raise ValueError("Invalid run identity")
    token = os.environ.get("BATON_CALLBACK_TOKEN", "")
    github_run_id = os.environ.get("GITHUB_RUN_ID", "")
    if args.finalize:
        completed = callback(args.run_id, token, "complete", {"github_run_id": github_run_id, "artifact_name": "baton-verify-" + args.run_id})
        if (not isinstance(completed, dict) or completed.get("evidence_status") != "verified" or
                completed.get("graph_receipt", {}).get("verified") is not True or
                completed.get("status") not in {"publishing", "completed", "partial"}):
            raise ValueError("Independent evidence and graph completion were not confirmed; publication blocked")
        callback(args.run_id, token, "publish", {"github_run_id": github_run_id})
        return 0
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.plan_id) or not re.fullmatch(r"[a-f0-9]{64}", args.plan_hash):
        raise ValueError("Invalid sealed plan identity")
    if not args.local_plan and not token:
        raise ValueError("Run callback capability is missing")
    plan = json.loads(Path(args.local_plan).read_text()) if args.local_plan else public_get("/api/public/release-plans/" + args.plan_id)
    validate_plan(plan)
    if plan.get("id", plan.get("plan_id")) != args.plan_id or plan["plan_hash"] != args.plan_hash:
        raise ValueError("Dispatched plan identity or hash differs")
    sequence = 0
    def emit(stage, message, environment_id="", status="running"):
        nonlocal sequence
        sequence += 1
        payload = {"github_run_id": github_run_id, "sequence": sequence, "stage": stage, "message": message,
                   "environment_id": environment_id, "status": status}
        print(C.encode(payload), flush=True)
        if not args.local_plan:
            try:
                callback(args.run_id, token, "events", payload)
            except Exception:
                # Status callbacks are advisory. Independent finalization still
                # authenticates the workflow and reads back every artifact byte.
                print("Release progress callback unavailable; evidence collection continues", flush=True)
    report = run_plan(plan, args.run_id, os.environ.get("GITHUB_SHA", ""), args.out, emit)
    failed = sum(row["checks"][0]["failed"] + row["checks"][0]["errors"] for row in report["environments"])
    emit("artifact-ready", "Complete raw verification evidence is ready for independent validation", status="blocked" if failed else "passed")
    # Observed regression failures are a valid completed execution, not an infra failure.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("Release worker failed: " + type(error).__name__, file=sys.stderr)
        sys.exit(2)
