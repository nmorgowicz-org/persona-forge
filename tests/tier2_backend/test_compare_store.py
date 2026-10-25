import pytest

from persona_forge import compare_store


def slot(engine, nat, art, ms=1000, seconds=4.0, fav=False, **extra):
    return {"engine": engine, "naturalness": nat, "artifacts": art, "ms": ms, "seconds": seconds,
            "favourite": fav, **extra}


def test_append_load_and_summary(tmp_path):
    p = tmp_path / "c.json"
    compare_store.append([{"text": "hi", "slots": [slot("a", 4, 5, fav=True), slot("b", 2, 3, ms=4000)]}], p)
    compare_store.append([{"text": "yo", "slots": [slot("a", 5, 5, ms=3000, similarity=4)]}], p)
    rows = {r["engine"]: r for r in compare_store.summarise(compare_store.load(p))}
    assert rows["a"]["clips"] == 2 and rows["a"]["natural"] == 4.5 and rows["a"]["favourites"] == 1
    assert rows["a"]["speed_median"] == 0.5 and rows["a"]["speed_worst"] == 0.75
    assert rows["a"]["similarity"] == 4.0 and rows["b"]["similarity"] is None
    assert list(rows)[0] == "a"


def test_unrated_clips_are_not_counted(tmp_path):
    p = tmp_path / "c.json"
    compare_store.append([{"slots": [{"engine": "a"}]}], p)
    assert compare_store.summarise(compare_store.load(p)) == []


@pytest.mark.parametrize("bad", [[], "x", {"slots": []}, {"slots": [1]}, {"slots": [{"engine": ""}]}])
def test_invalid_sessions_rejected(bad, tmp_path):
    with pytest.raises(compare_store.SessionInvalid):
        compare_store.append([bad], tmp_path / "c.json")


def test_out_of_range_ratings_dropped_and_history_capped(tmp_path):
    p = tmp_path / "c.json"
    compare_store.append([{"slots": [{"engine": "a", "naturalness": 9, "artifacts": 3}]}], p)
    assert "naturalness" not in compare_store.load(p)[0]["slots"][0]
    compare_store.append([{"slots": [{"engine": "a"}]}] * (compare_store.MAX_SESSIONS + 5), p)
    assert len(compare_store.load(p)) == compare_store.MAX_SESSIONS


def test_corrupt_file_reads_as_empty_and_clear_works(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{nope")
    assert compare_store.load(p) == []
    compare_store.append([{"slots": [{"engine": "a"}]}], p)
    compare_store.clear(p)
    assert compare_store.load(p) == []


def test_http_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setattr(compare_store, "_path", lambda: tmp_path / "c.json")
    assert client.get("/compare/results").get_json() == {"count": 0, "summary": []}
    ok = client.post("/compare/results", json={"sessions": [{"slots": [slot("a", 4, 4)]}]})
    assert ok.status_code == 200 and ok.get_json()["summary"][0]["engine"] == "a"
    assert client.post("/compare/results", json={"sessions": [{"slots": [3]}]}).status_code == 400
    assert client.post("/compare/results", json={}).status_code == 400
    assert client.delete("/compare/results").get_json()["count"] == 0
