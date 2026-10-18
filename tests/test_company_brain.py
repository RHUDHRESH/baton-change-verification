"""Company context contracts with captured public records and mocked graph I/O."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json

import pytest

from server import company_brain as company


@pytest.fixture
def captured(tmp_path):
    repo = "FalkorDB/FalkorDB"
    first, second = repo + "#1", repo + "#2"
    sources = [{"id": "issues", "url": "https://api.github.com/repos/" + repo + "/issues", "sha256": "a" * 64,
                "fetched_at": "2026-10-18T00:00:00Z"},
               {"id": "files1", "url": "https://api.github.com/repos/" + repo + "/pulls/1/files?per_page=80"},
               {"id": "files2", "url": "https://api.github.com/repos/" + repo + "/pulls/2/files?per_page=80"},
               {"id": "reviews", "url": "https://api.github.com/repos/" + repo + "/pulls/1/reviews?per_page=50"}]
    items = [{"id": identity, "repo": repo, "number": number, "kind": "pull_request", "state": "open",
              "title": "Captured work " + identity, "url": "https://github.com/" + repo + "/pull/" + str(number),
              "author": author, "author_type": "Bot" if author.endswith("[bot]") else "User",
              "assignees": [], "source_ids": ["issues", file_id],
              "files": [{"path": "src/main.c"}], "reviewers": []}
             for identity, file_id, number, author in ((first, "files1", 1, "public-contributor"),
                                                       (second, "files2", 2, "automation[bot]"))]
    snap = {"id": "snap", "graph": "public-graph", "captured_at": "2026-10-18T00:00:00Z",
            "sources": sources, "items": items, "repositories": [{"id": repo, "url": "https://github.com/" + repo}],
            "scope": "Two public repository samples"}
    def row(identity, login, ids, kind="pull_request", assigned=None, account_type="User"):
        return [{"id": login, "url": "https://github.com/" + login, "account_type": account_type},
                {"id": identity, "title": "Captured work " + identity, "url": "https://github.com/" + identity.replace("#", "/pull/"),
                 "kind": kind, "state": "open"}, repo, ids, assigned or []]
    rows = [row(first, "public-contributor", ["issues", "files1"]),
            row(second, "automation[bot]", ["issues", "files2"], account_type="Bot")]
    graph = MagicMock()
    graph.ro_query.side_effect = lambda query: SimpleNamespace(result_set=rows if query == company.CONTRIBUTION_QUERY else
                                    [[first, second, "src/main.c", "public-contributor", "automation[bot]"]])
    with patch.object(company.public, "snapshot", return_value=snap), patch.object(company.G, "connect") as connect:
        connect.return_value.select_graph.return_value = graph
        yield tmp_path, snap, rows, graph


def test_company_contributors_have_source_backed_paths_and_bot_types(captured):
    path, snap, rows, graph = captured
    result = company.overview(path, 6379)
    assert result["company"]["name"] == "FalkorDB"
    assert result["people"][0]["account_type"] == "Bot"
    assert result["people"][1]["authored_items"] == [snap["items"][0]["id"]]
    assert result["paths"][0]["relations"] == ["AUTHORED", "IN_REPOSITORY"]
    assert result["sources"][2]["sha256"] == "a" * 64
    assert any("employment" in text for text in result["limits"])
    assert graph.ro_query.call_count == 2
    graph.query.assert_not_called()


def test_uncaptured_reviews_are_unknown_rather_than_missing_reviewers(captured):
    path, snap, rows, graph = captured
    result = company.overview(path, 6379)
    review_gaps = [gap for gap in result["gaps"] if gap["kind"].startswith("review")]
    assert len(review_gaps) == 2
    assert all(gap["kind"] == "review_evidence_missing" for gap in review_gaps)
    assert all("not captured" in gap["detail"] for gap in review_gaps)
    assert all(gap["source_ids"] for gap in result["gaps"])


def test_review_capture_empty_is_distinguished_and_assigned_work_is_not_gap(captured):
    path, snap, rows, graph = captured
    snap["items"][0]["source_ids"].append("reviews")
    rows[0][3].append("reviews")
    rows[0][4].append("recorded-assignee")
    snap["items"][0]["assignees"].append("recorded-assignee")
    result = company.overview(path, 6379)
    first_gaps = [g for g in result["gaps"] if g["item_id"] == snap["items"][0]["id"]]
    assert [g["kind"] for g in first_gaps] == ["no_reviews_in_capture"]
    assert first_gaps[0]["source_ids"] == ["reviews"]


def test_unknown_graph_records_or_unprovenanced_rows_are_not_company_facts(captured):
    path, snap, rows, graph = captured
    rows[0][3][:] = ["unrecognized-source"]
    rows[1][1]["id"] = "FalkorDB/FalkorDB#unknown"
    result = company.overview(path, 6379)
    assert result["work"] == result["people"] == result["paths"] == result["gaps"] == []
    assert result["shared_file_paths"] == []


def test_shared_file_paths_require_both_captured_file_endpoints(captured):
    path, snap, rows, graph = captured
    result = company.overview(path, 6379)
    assert result["shared_file_paths"][0]["source_ids"] == ["files1", "files2"]
    assert "do not prove a dependency" in result["shared_file_paths"][0]["limit"]
    snap["items"][1]["files"] = []
    assert company.overview(path, 6379)["shared_file_paths"] == []


def test_graph_failure_propagates_instead_of_substituting_company_demo(captured):
    path, snap, rows, graph = captured
    graph.ro_query.side_effect = RuntimeError("graph unavailable")
    with pytest.raises(RuntimeError, match="graph unavailable"):
        company.overview(path, 6379)


def test_display_uses_captured_values_and_rejects_wrong_contributor(captured):
    path, snap, rows, graph = captured
    rows[0][1].update(title="Uncaptured graph title", state="closed")
    rows[1][0]["id"] = "unproven-contributor"
    result = company.overview(path, 6379)
    assert [item["title"] for item in result["work"]] == [snap["items"][0]["title"]]
    assert result["work"][0]["state"] == "open"
    assert result["diagnostics"]["rejected_rows"]["contributions"] == 1
    assert result["shared_file_paths"] == []


def test_duplicate_rows_do_not_duplicate_people_paths_or_gaps(captured):
    path, snap, rows, graph = captured
    rows.extend([rows[0]] * 20)
    result = company.overview(path, 6379)
    assert len(result["work"]) == len(result["paths"]) == len(result["people"]) == 2
    assert len(result["gaps"]) == 4
    assert graph.ro_query.call_count == 2


def test_single_source_deletion_is_audited_and_never_preserves_unbacked_path(captured):
    path, snap, rows, graph = captured
    result = company.overview(path, 6379)
    robustness = result["shared_file_paths"][0]["evidence_robustness"]
    assert robustness["single_source_cuts"] == ["files1", "files2"]
    assert not robustness["survives_any_single_source_loss"]
    for index in (0, 1):
        before = list(rows[index][3])
        rows[index][3][:] = ["issues"]
        assert company.overview(path, 6379)["shared_file_paths"] == []
        rows[index][3][:] = before


def test_wrong_endpoint_does_not_prove_shared_file_or_review(captured):
    path, snap, rows, graph = captured
    snap["sources"][1]["url"] = snap["sources"][1]["url"].replace("/pulls/1/", "/pulls/999/")
    snap["items"][0]["source_ids"].append("reviews")
    rows[0][3].append("reviews")
    snap["sources"][3]["url"] = snap["sources"][3]["url"].replace("/pulls/1/", "/pulls/999/")
    result = company.overview(path, 6379)
    assert result["shared_file_paths"] == []
    assert len([gap for gap in result["gaps"] if gap["kind"] == "review_evidence_missing"]) == 2


def test_projection_uses_only_consumed_fields_and_fixed_read_queries(captured):
    path, snap, rows, graph = captured
    company.overview(path, 6379)
    assert "properties(" not in company.CONTRIBUTION_QUERY
    assert "LIMIT 100" in company.CONTRIBUTION_QUERY
    assert "LIMIT 50" in company.SHARED_FILE_QUERY
    assert [call.args[0] for call in graph.ro_query.call_args_list] == [
        company.CONTRIBUTION_QUERY, company.SHARED_FILE_QUERY]
    assert "not database scan work" in company.overview(path, 6379)["diagnostics"]["limit_semantics"]


def test_returned_row_caps_are_reported_honestly(captured):
    path, snap, rows, graph = captured
    rows.extend([rows[0]] * 100)
    result = company.overview(path, 6379)
    assert result["diagnostics"]["contribution_limit_reached"]
    assert len(result["work"]) == 2
    assert result["query_count"] == 2


def test_projection_payload_benchmark(captured):
    """Reproducible serialized-byte measurement, without simulated RTT timings."""
    path, snap, rows, graph = captured
    baseline, projected = [], []
    for index in range(32):
        account, work, repo, refs, assigned = rows[index % 2]
        full_account = {**account, "name": account["id"]}
        full_work = {**work, "repo": repo, "number": index + 1,
                     "updated_at": "2026-10-18T00:00:00Z", "source_ids": refs}
        baseline.append([full_account, full_work, repo, refs, assigned])
        projected.append([{"id": account["id"]}, {"id": work["id"]}, repo, refs, assigned])
    full_bytes = len(json.dumps(baseline, separators=(",", ":")).encode())
    projected_bytes = len(json.dumps(projected, separators=(",", ":")).encode())
    assert projected_bytes < full_bytes
    # This is a declared per-item-read baseline, not a prior production profile.
    result = company.overview(path, 6379)
    print(json.dumps({"measurement": "synthetic_32_row_company_context",
                      "full_property_json_bytes": full_bytes,
                      "projected_json_bytes": projected_bytes,
                      "per_item_read_baseline_calls": 33,
                      "bulk_read_calls": graph.ro_query.call_count,
                      "source_deletion_cases_suppressed": len(
                          result["shared_file_paths"][0]["evidence_robustness"]["single_source_cuts"])}))
