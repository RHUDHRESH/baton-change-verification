from fastapi.testclient import TestClient

from baton import amb_demo


def test_original_questions_and_temporal_state(service):
    client = TestClient(service.app)
    final = client.get("/api/amb").json()
    assert final["mode"].startswith("Scripted text parser")
    assert len(final["inbox"]) == 50
    assert "attached logs:" in final["inbox"][0]["text"]
    assert client.get("/api/amb?step=0").json()["edges"] == []
    w = amb_demo.fixture()
    assert len(final["questions"]) == len(w.questions) > 15
    for question in w.questions:
        result = client.get(f"/api/amb/questions/{question.qid}")
        assert result.status_code == 200
        assert result.json()["correct"], result.json()
        assert result.json()["sources"]
        assert all(int(source.split("-")[1]) <= question.after_step for source in result.json()["sources"])
    # Final snapshot must contain exactly the upstream final state, including retractions.
    edges = {(e["data"]["source"], e["data"]["kind"], e["data"]["target"]) for e in final["edges"]}
    expected = {(a,"OWNED_BY",b) for a,b in w.final_state["owner"].items()}
    expected |= {(a,"ON_CALL",b) for a,b in w.final_state["oncall"].items()}
    expected |= {(a,"MEMBER_OF",b) for a,b in w.final_state["members"].items()}
    expected |= {(a,"DEPENDS_ON",b) for a,ds in w.final_state["deps"].items() for b in ds}
    assert edges == expected
    assert client.get("/api/amb").json() == final


def test_acme_bounds_and_query_injection(service):
    client = TestClient(service.app)
    assert client.get("/api/amb?step=51").status_code == 422
    assert client.get("/api/amb?step=-1").status_code == 422
    assert client.get("/api/amb/questions/unknown").status_code == 404
    assert client.post("/api/amb/ask", json={"tool":"raw", "subject":"x"}).status_code == 422
    assert client.post("/api/amb/ask", json={"tool":"owner", "subject":"x"*101}).status_code == 422
    original = client.get("/api/amb").json()
    result = client.post("/api/amb/ask", json={"tool":"owner", "subject":"x'}) DETACH DELETE n //"})
    assert result.status_code == 200 and result.json()["answers"] == []
    assert client.get("/api/amb").json() == original


def test_visible_text_rules_match_every_upstream_event():
    for event, assertions, retractions in amb_demo.parsed_events():
        assert set(assertions) == set(event.asserts), (event.step, event.text, assertions, event.asserts)
        assert set(retractions) == set(event.retracts), (event.step, event.text, retractions, event.retracts)
