"""Typed tools over the same CLI used by the website. No arbitrary query tool."""
import json

from fastapi import HTTPException
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from server import app as api

mcp = MCPServer("Baton")
READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _error(operation):
    try:
        return operation()
    except HTTPException as err:
        return {"error": str(err.detail), "exit_code": 3 if err.status_code == 503 else 4 if err.status_code == 409 else 1}
    except ValueError as err:
        return {"error": str(err), "exit_code": 2}


@mcp.tool(annotations=READ)
def rehearse(seed: int = 7, lane: str = "G") -> dict:
    """Simulate departure, returning sourced events and unchanged-live-graph hashes."""
    if lane not in ("W", "R", "G"):
        return {"error": "lane must be W, R or G", "exit_code": 2}

    def operation():
        with api.LOCK:
            directory = api.world_dir(seed)
            world = json.loads((directory / "world.json").read_text())
            return api.cli("rehearse", "--world", directory, "--beliefs", directory / "beliefs.json",
                           "--leaver", world["leaver"], "--lane", lane, "--confirm", "all", "--port", api.PORT)
    return _error(operation)


@mcp.tool(annotations=READ)
def ask(question: str, seed: int = 7) -> dict:
    """Answer a company question using a fixed tool catalogue, with sources."""
    if not question.strip() or len(question) > 2000:
        return {"error": "question must contain 1 to 2000 characters", "exit_code": 2}
    return _error(lambda: api.ask(api.Ask(seed=seed, question=question)))


@mcp.tool(annotations=READ)
def handover(assign: dict[str, str], seed: int = 7) -> dict:
    """Preview accepted successors and replay on a temporary fork; leaves live ownership unchanged."""
    return _error(lambda: api.handover(api.Handover(seed=seed, assign=assign)))


@mcp.tool(annotations=READ)
def cut(seed: int = 7) -> dict:
    """Check whether staff capacity can absorb uncovered duties and explain the shortfall."""
    return _error(lambda: api.cut(seed))


if __name__ == "__main__":
    mcp.run()
