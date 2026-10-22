"""Search citations must point to the matched text or the matched stored chunk."""
import pytest

import corpus_contract
import library_resources
import server
import uoink_mcp_tools as tools
from tests.test_semantic_search import db, ready, request
from tests.test_smarter_search import seed
from uoink_core.search_service import citation_fields
from uoink_core.search_service import _hydrate


def results(idx, surface, query, mode):
    args = {"query": query, "mode": mode}
    if surface == "mcp":
        return tools.search_uoinks(args)["results"]
    if surface == "library":
        reader = library_resources.LibraryReader(idx, data_root=idx._path.parent)
        return library_resources.call_tool("search_library", args, reader)["hits"]
    if surface == "memory":
        response = request("GET", f"/memory/search?q={query}&mode={mode}")
        assert response.status == 200, response.payload
        return response.payload["results"]
    if surface == "memory_kind":
        return server._library_search(idx, q=query, filters={}, kind=None, limit=10,
                                      offset=0, sort="relevance", mode=mode)["results"]
    if surface == "corpus":
        response = request("GET", f"/api/corpus/v1/search?q={query}&mode={mode}&search_details=true")
        assert response.status == 200, response.payload
        corpus_contract.validate_data("search", response.payload["data"], search_details=True)
        return response.payload["data"]["items"]
    raise AssertionError(surface)


SURFACES = ["mcp", "library", "memory", "memory_kind", "corpus"]


def assert_unverified(row):
    assert row["passage_verified"] is False
    assert row["citation_reason"]
    assert not any(key in row for key in ("passage", "span", "passage_id", "timestamp_seconds"))
    assert row.get("start") is None and row.get("end") is None
    assert row.get("excerpt_id") is None


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("mode", ["keyword", "hybrid"])
def test_match_outside_all_clips_uses_content_span(db, monkeypatch, surface, mode):
    idx, engine, _ = db
    item = seed(idx, "outside", "Unrelated stored clip.", timed=True)
    content = "Opening prose. Quasar evidence outside every clip. Closing prose."
    idx.upsert_yoink(item, content=content)
    ready(db)
    # Exercise the keyword side of hybrid without an unrelated semantic hit.
    monkeypatch.setattr(engine, "embedding_search", lambda *a, **k: [])
    rows = results(idx, surface, "quasar", mode)
    assert len(rows) == 1
    row = rows[0]
    assert row["passage_verified"] is True
    p = row["passage"]
    assert p["text"] == content[p["char_start"]:p["char_end"]]
    assert "Quasar" in p["text"] and "clip_id" not in p
    assert row.get("timestamp_seconds") is None


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("mode", ["keyword", "hybrid"])
@pytest.mark.parametrize("missing", ["snippet", "body_match"])
def test_missing_verified_passage_keeps_result_without_citation(db, monkeypatch, surface, mode, missing):
    idx, engine, _ = db
    seed(idx, "source", "Quasar evidence." if missing == "snippet" else "Unrelated opening.", title="Quasar")
    ready(db)
    monkeypatch.setattr(engine, "embedding_search", lambda *a, **k: [])
    original = idx._search_passage
    if missing == "snippet":
        def missing_content(row, query, match):
            row["_content"] = "The returned snippet is absent from indexed content."
            return original(row, query, match)
        monkeypatch.setattr(idx, "_search_passage", missing_content)
    rows = results(idx, surface, "quasar", mode)
    assert len(rows) == 1
    assert_unverified(rows[0])


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
def test_normal_verified_passage_survives_all_transports(db, surface, mode):
    idx, _, _ = db
    content = "Quasar evidence in the stored source."
    seed(idx, "source", content)
    ready(db)
    row = results(idx, surface, "quasar", mode)[0]
    assert row["passage_verified"] is True
    p = row["passage"]
    assert p["text"] == content[p["char_start"]:p["char_end"]]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_changed_semantic_chunk_cannot_be_cited(db, monkeypatch, surface, mode):
    idx, engine, _ = db
    seed(idx, "source", "Quasar evidence before edit.", title="Quasar")
    ready(db)
    hits = engine.embedding_search("quasar")
    assert hits
    with idx._lock:
        idx._conn.execute("UPDATE yoinks_fts SET content='An unrelated replacement.' WHERE video_id='source'")
        idx._conn.commit()
    monkeypatch.setattr(engine, "embedding_search", lambda *a, **k: hits)
    rows = results(idx, surface, "quasar", mode)
    assert len(rows) == 1
    assert_unverified(rows[0])


def test_formatter_cannot_recreate_an_unverified_clip_citation():
    row = citation_fields({"video_id": "source", "clip_id": 42, "text": "Unrelated",
                           "start": 12, "end": 24, "passage_verified": False})
    assert_unverified(citation_fields(row))


@pytest.mark.parametrize("kind", ["text", "clip"])
def test_semantic_rejects_changed_coordinates_and_missing_fingerprint(db, kind):
    idx, engine, _ = db
    seed(idx, "source", "Quasar evidence.", timed=kind == "clip")
    ready(db)
    hit = engine.embedding_search("quasar")[0]
    span = {**hit.span, "char_start": 99999} if kind == "text" else {**hit.span, "start": 99999}
    for invalid in (hit._replace(span=span), hit._replace(fingerprint=None)):
        assert_unverified(_hydrate(idx, [invalid])[0])


@pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
def test_clip_tool_verifies_stored_text_and_time(db, mode):
    idx, _, _ = db
    seed(idx, "source", "Quasar evidence.", timed=True)
    ready(db)
    row = tools.search_clips({"query": "quasar", "mode": mode})["results"][0]
    clip = idx.get_clips("source")[0]
    assert row["passage_verified"] is True
    assert row["passage"]["text"] == clip["text"]
    assert row["timestamp_seconds"] == row["start"] == clip["start"]


@pytest.mark.parametrize("mode", ["keyword", "hybrid"])
def test_library_all_terms_across_clips_rank_above_partial_and_cite_best_clip(db, monkeypatch, mode):
    idx, engine, _ = db
    seed(idx, "complete", "An unrelated corpus heading.", timed=True)
    idx.insert_citations("complete", [
        {"kind": "transcript_chunk", "seq": 0, "text": "lunar " + "padding " * 250,
         "timestamp_start": 0, "timestamp_end": 20},
        {"kind": "transcript_chunk", "seq": 1, "text": "lander evidence",
         "timestamp_start": 200, "timestamp_end": 220}])
    seed(idx, "partial", "lunar " * 40, timed=True)
    ready(db)
    monkeypatch.setattr(engine, "embedding_search", lambda *a, **k: [])
    assert len(idx.get_clips("complete")) == 2
    best = idx.search_clips("lunar lander", video_id="complete")[0]
    reader = library_resources.LibraryReader(idx, data_root=idx._path.parent)
    for limit in (1, 5):
        rows = reader.search("lunar lander", limit, mode=mode)["hits"]
        assert len(rows) == len({row["item_id"] for row in rows})
        hit = rows[0]
        assert hit["item_id"] == "complete"
        assert hit["passage_verified"] is True
        assert hit["clip_id"] == best["clip_id"] == hit["passage"]["clip_id"]
        assert hit["passage"]["text"] == best["text"]
        assert hit["start"] == best["start"]
