import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest


def demo(client, seed=7):
    response = client.get(f"/api/demo?seed={seed}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("seed", [7, 101, 202, 303])
def test_http_rehearsal_cache_and_graph_integrity(service, seed):
    client = TestClient(service.app)
    data = demo(client, seed)
    counts = [len(data["lanes"][lane]["failures"]) for lane in "WRG"]
    assert counts[0] < counts[1] < counts[2]
    assert data["live_hash_before"] == data["live_hash_after"]
    assert data["fixture"] and data["mode"] == "live"
    assert data["extraction"]["cached"]
    assert all(data["lanes"][lane]["cypher"] for lane in "WRG")
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_http_ask_unknown_question_and_query_catalogue(service):
    client = TestClient(service.app)
    data = demo(client)
    response = client.post("/api/ask", json={"seed": 7, "question": f"What does {data['leaver_name']} owe?"})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["tool"] == "owes" and answer["rows"] and answer["sources"]
    assert answer["cypher"] == client.get("/api/catalogue").json()["owes"]
    unknown = client.post("/api/ask", json={"question": "What is the price of gold?"}).json()
    assert unknown["tool"] == "none" and unknown["sources"] == []


def test_http_validation_and_cache_miss_fail_visibly(service):
    client = TestClient(service.app)
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/handover", json={"assign": {"x": []}}).status_code == 422
    assert client.post("/api/handover", json={"assign": {}, "seed": -1}).status_code == 422
    missing = client.get("/api/demo?seed=12345")
    assert missing.status_code == 409 and "no cached extraction" in missing.text


def test_http_preview_then_real_git_write_and_read_back(service):
    client = TestClient(service.app)
    data = demo(client)
    duties = sorted({row["duty"] for row in data["lanes"]["G"]["failures"]})
    people = [p["id"] for p in data["people"] if p["id"] != data["leaver"] and p["left_at"] is None]
    assign = {duty: people[i % len(people)] for i, duty in enumerate(duties)}
    preview = client.post("/api/handover", json={"seed": 7, "assign": assign}).json()
    assert preview["failures_after"] == []
    assert preview["live_hash_before"] == preview["live_hash_after"]
    result = client.post("/api/commit", json={"seed": 7, "assign": assign})
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["ready_to_leave"] and result["external"]["verified"]
    assert result["external"]["read_back"] == result["committed"]
    assert not demo(client)["lanes"]["G"]["failures"]


def test_http_capacity_returns_verifiable_min_cut(service):
    response = TestClient(service.app).get("/api/cut?seed=7")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["flow"] <= data["demand"]
    assert data["certificate"]["equals_flow"]
    assert data["live_hash_before"] == data["live_hash_after"]


def test_http_reports_graph_down_with_no_fake_success(service, monkeypatch):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        dead = listener.getsockname()[1]
    monkeypatch.setattr(service, "PORT", dead)
    client = TestClient(service.app)
    assert client.get("/api/health").status_code == 503
    result = client.get("/api/demo?seed=7")
    assert result.status_code == 503 and "FalkorDB" in result.text
    assert "failures" not in result.json()


def structured(result):
    data = getattr(result, "structured_content", None)
    return data if data is not None else json.loads(result.content[0].text)


def test_mcp_stdio_lists_fixed_tools_and_matches_cli(service):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    directory = service.world_dir(7)
    world = json.loads((directory / "world.json").read_text())
    expected = service.cli("rehearse", "--world", directory, "--beliefs", directory / "beliefs.json",
                           "--leaver", world["leaver"], "--lane", "G", "--confirm", "all", "--port", service.PORT)

    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "baton.mcp_server"], env=dict(os.environ))
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {"rehearse", "ask", "handover", "cut"}
                result = structured(await session.call_tool("rehearse", arguments={"seed": 7}))
                assert result["failures"] == expected["failures"]
                question = f"What does {world['leaver']} owe?"
                answer = structured(await session.call_tool("ask", arguments={"seed": 7, "question": question}))
                direct = service.ask(service.Ask(seed=7, question=question))
                assert (answer["rows"], answer["cypher"]) == (direct["rows"], direct["cypher"])
                preview = structured(await session.call_tool("handover", arguments={"seed": 7, "assign": {}}))
                assert preview["live_hash_before"] == preview["live_hash_after"]
                capacity = structured(await session.call_tool("cut", arguments={"seed": 7}))
                assert capacity["certificate"]["equals_flow"]
    asyncio.run(run())


def test_mcp_no_raw_queries_and_cli_needs_no_mcp(service, tmp_path):
    root = service.ROOT
    source = (root / "baton/mcp_server.py").read_text()
    for forbidden in ("MATCH", "CREATE", "MERGE", "CALL "):
        assert forbidden not in source
    result = subprocess.run([sys.executable, "-S", "-m", "baton", "generate", "--seed", "11", "--out", str(tmp_path / "bare")], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_mcp_graph_down_is_a_clear_tool_result(service, monkeypatch):
    from baton import mcp_server
    service.world_dir(7)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        dead = listener.getsockname()[1]
    monkeypatch.setattr(service, "PORT", dead)
    result = mcp_server.rehearse(7)
    assert result["exit_code"] == 3 and "FalkorDB" in result["error"]
    assert "failures" not in result


def test_external_failure_is_retryable_without_duplicate_graph_or_git_writes(service, monkeypatch):
    from baton import commit
    client = TestClient(service.app)
    data = demo(client)
    duty = data["lanes"]["G"]["failures"][0]["duty"]
    person = next(p["id"] for p in data["people"] if p["id"] != data["leaver"] and p["left_at"] is None)
    directory = service.world_dir(7)
    repo = service.DATA / "fault-injection-repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@local", "commit", "--allow-empty", "-qm", "init"], check=True)
    original = commit._write_external

    def unavailable(*args):
        raise RuntimeError("injected repository outage")

    monkeypatch.setattr(commit, "_write_external", unavailable)
    arguments = (directory, directory / "beliefs.json", data["leaver"], [f"{duty}={person}"], repo, service.PORT)
    pending = commit.run(*arguments)
    assert pending["state"] == "external_pending" and pending["committed"]
    assert pending["external"]["retryable"]
    monkeypatch.setattr(commit, "_write_external", original)
    recovered = commit.run(*arguments)
    assert recovered["state"] == "verified" and recovered["external"]["verified"]
    assert recovered["live_hash_after"] == pending["live_hash_after"]
    repeated = commit.run(*arguments)
    assert repeated["external"]["commit"] == recovered["external"]["commit"]
    assert repeated["operation_id"] == recovered["operation_id"]


def test_concurrent_rehearsals_have_isolated_forks(service):
    from concurrent.futures import ThreadPoolExecutor
    from baton import rehearse
    directory = service.world_dir(7)
    world = json.loads((directory / "world.json").read_text())

    def run(_):
        return rehearse.run(directory, directory / "beliefs.json", world["leaver"], "G", "all", service.PORT)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert all(len(result["failures"]) == 37 for result in results)
    assert all(result["live_hash_before"] == result["live_hash_after"] for result in results)
