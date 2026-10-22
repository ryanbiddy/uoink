"""Lane S: forgiving keyword search, strict compatibility and citation spans."""
import pytest

import corpus_contract
import corpus_provider
import index
import library_resources
import server
import uoink_mcp
import uoink_mcp_tools as tools
from tests.phase4_fixtures import seed_yoink_item


@pytest.mark.parametrize("raw,forgiving,strict", [
    ("show me the lunar lander", '"lunar" OR "lander"*', '"show" "me" "the" "lunar" "lander"*'),
    ("The and OR", '"The" OR "and" OR "OR"*', '"The" "and" "OR"*'),
    ('cat,dog; bird', '"cat" OR "dog" OR "bird"*', '"cat" "dog" "bird"*'),
    ('"cat" ""dog""', '"cat" OR "dog"*', '"cat" "dog"*'),
    ('NEAR(cat dog) AND OR column:term ^foo *bar*',
     '"NEAR" OR "cat" OR "dog" OR "column" OR "term" OR "foo" OR "bar"*',
     '"NEAR" "cat" "dog" "AND" "OR" "column" "term" "foo" "bar"*'),
    ('日本語 cancio\u0301n привет नमस्ते',
     '"日本語" OR "canción" OR "привет" OR "नमस्ते"*',
     '"日本語" "canción" "привет" "नमस्ते"*'),
    ('foo_bar 123', '"foo_bar" OR "123"*', '"foo_bar" "123"*'),
    ('', '', ''), ('"*():{}[]^\x00🙂', '', ''), ('\u0301\u0308', '', ''),
])
def test_query_builder(raw, forgiving, strict):
    assert index._fts_query(raw) == forgiving
    assert index._fts_query(raw, "forgiving") == forgiving
    assert index._fts_query(raw, "strict") == strict


@pytest.fixture
def db(tmp_path, monkeypatch):
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: True)
        monkeypatch.setattr(tools, "_backend", server)
        yield idx


def seed(db, vid, text, *, title=None, timed=False, date="2026-10-01T12:00:00"):
    item = seed_yoink_item(db, db._path.parent, video_id=vid, slug=vid,
                           title=title or "Untitled source", corpus_text=text,
                           yoinked_at=date, source_type="video" if timed else "note",
                           clips=[{"start": 12.5, "end": 24.0, "text": text}] if timed else None)
    db.upsert_yoink(item, content=text)
    return item


def ids(rows):
    return [r["video_id"] for r in rows]


def test_bm25_alone_loses_to_partial_but_all_terms_rank_first(db):
    seed(db, "complete", "lunar lander " + "padding " * 4000)
    seed(db, "partial", "lunar " * 40)
    plain = db._conn.execute(
        "SELECT video_id FROM yoinks_fts WHERE yoinks_fts MATCH ? ORDER BY bm25(yoinks_fts)",
        (index._fts_query("lunar lander"),)).fetchall()
    assert ids(plain)[0] == "partial"  # The fixture proves the guard is needed.
    assert ids(db.search("lunar lander")) == ["complete", "partial"]
    assert ids(db.search("lunar lander", limit=1)) == ["complete"]
    assert ids(db.search("lunar lander", match="strict")) == ["complete"]
    assert ids(db.search_yoinks_for_memory(q="lunar lander")["results"]) == ["complete", "partial"]
    assert ids(db.search_yoinks_for_memory(q="lunar lander", offset=1, limit=1)["results"]) == ["partial"]


def test_dense_search_work_does_not_grow_quadratically(db):
    # Count SQLite work instead of wall time. The old planner choice compared
    # every FTS candidate with every live item, even for a small result page.
    def work():
        steps = 0

        def progress():
            nonlocal steps
            steps += 1
            return 0

        db._conn.set_progress_handler(progress, 100)
        try:
            result = db.search_yoinks_for_memory(q="lunar lander", limit=10)
        finally:
            db._conn.set_progress_handler(None, 0)
        return steps, result["total"]

    for n in range(80):
        seed(db, f"dense{n}", "lunar lander source evidence")
    small, total = work()
    assert total == 80
    for n in range(80, 160):
        seed(db, f"dense{n}", "lunar lander source evidence")
    large, total = work()
    assert total == 160
    assert large < small * 3, (small, large)


@pytest.mark.parametrize("query,title", [("LUNAR LANDER", "Lunar, Lander!"), ("GPT4", "GPT-4")])
def test_exact_title_is_first_even_when_punctuation_changes_tokenization(db, query, title):
    seed(db, "body", (query + " ") * 40)
    seed(db, "exact", "unrelated " * 4000, title=title)
    assert ids(db.search(query, 1)) == ["exact"]
    assert ids(db.search_yoinks_for_memory(q=query, limit=1)["results"]) == ["exact"]
    db.soft_delete_yoink("exact")
    assert ids(db.search(query)) == ["body"]


def test_clip_ranking_default_strict_and_passage_identity(db):
    seed(db, "complete", "lunar lander " + "padding " * 1000, timed=True)
    seed(db, "partial", "lunar " * 40, timed=True)
    seed(db, "exact", "unrelated text", title="LUNAR, LANDER!", timed=True)
    rows = db.search_clips("lunar lander")
    assert ids(rows)[:3] == ["exact", "complete", "partial"]
    assert ids(db.search_clips("lunar lander", match="strict")) == ["complete"]
    result = tools.search_clips({"query": "lunar lander"})["results"][0]
    stored = db.get_clips(result["video_id"])[0]
    assert result["clip_id"] == stored["clip_id"]
    assert result["text"] == stored["text"]
    assert result["start"] == 12.5


def test_item_passages_have_verbatim_text_and_source_spans(db):
    text = "opening words " * 30 + "lunar lander evidence " + "ending words " * 30
    seed(db, "text", text)
    passage = tools.search_uoinks({"query": "lunar lander"})["results"][0]["passage"]
    assert passage["video_id"] == "text"
    assert passage["text"] == text[passage["char_start"]:passage["char_end"]]
    assert "lunar lander" in passage["text"]
    seed(db, "timed", "lunar lander evidence", timed=True)
    result = next(r for r in tools.search_uoinks({"query": "lunar lander"})["results"] if r["video_id"] == "timed")
    passage = result["passage"]
    assert passage["clip_id"] == db.get_clips("timed")[0]["clip_id"]
    assert passage["start"] == 12.5


@pytest.mark.parametrize("name", ["search_uoinks", "search_clips"])
def test_mcp_defaults_and_strict_retrieve_different_sets(db, name):
    seed(db, "full", "lunar lander", timed=True)
    seed(db, "part", "lunar terrain", timed=True)
    handler = tools.TOOL_REGISTRY[name].handler
    assert ids(handler({"query": "lunar lander"})["results"]) == ["full", "part"]
    assert ids(handler({"query": "lunar lander", "match": "strict"})["results"]) == ["full"]
    assert handler({"query": "lunar", "match": "unsafe"})["ok"] is False


def test_find_mentions_keeps_entity_lookup_and_adds_forgiving_name_words(db):
    for vid, entity in [("full", "Lunar Lander"), ("part", "Lunar Terrain")]:
        seed(db, vid, entity + " source passage", timed=True)
        db.record_entities(vid, [{"name": entity, "type": "topic", "mentions": [
            {"timestamp": 12.5, "context": entity + " source passage"}]}])
    rows = tools.find_mentions({"entity": "Lunar Lander"})["mentions"]
    assert ids(rows) == ["full", "part"]
    assert ids(tools.find_mentions({"entity": "Lunar Lander", "match": "strict"})["mentions"]) == ["full"]
    assert rows[0]["mention_id"]
    assert rows[0]["timestamp"] == rows[0]["passage"]["start"] == 12.5
    assert rows[0]["passage"]["clip_id"] == db.get_clips("full")[0]["clip_id"]


def test_entity_quote_in_prose_has_exact_offsets(db):
    text = "An opening. Lunar lander source evidence. An ending."
    seed(db, "prose", text)
    db.record_entities("prose", [{"name": "Lunar Lander", "type": "topic", "mentions": [
        {"context": "Lunar lander source evidence."}]}])
    hit = tools.find_mentions({"entity": "Lunar Lander"})["mentions"][0]
    passage = hit["passage"]
    assert passage["video_id"] == "prose"
    assert text[passage["char_start"]:passage["char_end"]] == passage["text"] == hit["context"]


def test_library_default_strict_mixed_ranking_and_citations(db):
    seed(db, "part", "lunar rocks", timed=True)
    seed(db, "full", "lunar lander", timed=True)
    seed(db, "exact", "opening evidence", title="Lunar, Lander!")
    reader = library_resources.LibraryReader(db, data_root=db._path.parent)
    result = library_resources.call_tool("search_library", {"query": "lunar lander"}, reader)
    assert result["ok"], result
    assert [r["item_id"] for r in result["hits"]] == ["exact", "full", "part"]
    assert reader.search("lunar lander", 1)["hits"][0]["item_id"] == "exact"
    strict = library_resources.call_tool("search_library", {"query": "lunar lander", "match": "strict"}, reader)
    assert [r["item_id"] for r in strict["hits"]] == ["full", "exact"]
    for hit in result["hits"]:
        assert hit["excerpt_id"] and hit["source_revision"]
        assert reader.read(hit["uris"]["excerpt"])["contents"]
        if hit["item_id"] != "exact":
            assert hit["clip_id"] and hit["start"] == 12.5


@pytest.mark.parametrize("route", ["memory", "memory_kind", "corpus"])
@pytest.mark.parametrize("mode,count", [(None, 2), ("forgiving", 2), ("strict", 1), ("invalid", 0)])
def test_http_search_routes_default_and_strict(db, route, mode, count):
    seed(db, "full", "lunar lander")
    seed(db, "part", "lunar terrain")
    handler = server.Handler.__new__(server.Handler)
    handler.path = "/api/corpus/v1/search?q=lunar+lander" if route == "corpus" else "/memory/search?q=lunar+lander"
    if route == "memory_kind":
        handler.path += "&kind=notes"
    if mode:
        handler.path += "&match=" + mode
    replies = []
    handler._send_json = lambda code, body: replies.append((code, body))
    handler._corpus_v1_provider = lambda: corpus_provider.UoinkCorpusProvider(db, db._path.parent)
    handler._handle_corpus_v1_search() if route == "corpus" else handler._handle_memory_search()
    code, body = replies[0]
    assert code == (400 if mode == "invalid" else 200), body
    if code == 200:
        rows = body["data"]["items"] if route == "corpus" else body["results"]
        assert len(rows) == count


def test_library_http_filters_sorts_and_pagination(db):
    seed(db, "full", "lunar lander", date="2026-10-01T12:00:00")
    seed(db, "part", "lunar terrain", date="2026-10-02T12:00:00")
    seed(db, "exact", "other", title="Lunar lander", date="2026-10-03T12:00:00")
    args = dict(q="lunar lander", filters={}, kind="notes", limit=1, offset=0)
    assert ids(server._library_search(db, sort="relevance", **args)["results"]) == ["exact"]
    assert ids(server._library_search(db, sort="oldest", **args)["results"]) == ["full"]
    assert server._library_search(db, sort="newest", match="strict", **args)["total"] == 2
    args["offset"] = 2
    assert ids(server._library_search(db, sort="relevance", **args)["results"]) == ["part"]


@pytest.mark.parametrize("name,arg", [("search_uoinks", "query"), ("search_clips", "query"),
                                      ("search_library", "query"), ("find_mentions", "entity")])
def test_stdio_wrappers_forward_match(monkeypatch, name, arg):
    calls = []
    monkeypatch.setattr(tools, "call_tool", lambda n, a: calls.append((n, a)) or {})
    getattr(uoink_mcp, name)("lunar lander")
    getattr(uoink_mcp, name)("lunar lander", match="strict")
    assert calls[0][1].get("match", "forgiving") == "forgiving"
    assert calls[1][1]["match"] == "strict"
    assert calls[1][1][arg] == "lunar lander"


def test_schemas_add_only_optional_match():
    # Original fields and requirements stay intact, including frozen tools.
    old_fields = {"search_uoinks": {"query", "limit", "channel", "hook_type"},
                  "search_clips": {"query", "limit", "video_id", "channel"},
                  "find_mentions": {"entity", "limit"}, "search_library": {"query", "limit"}}
    old_properties = {
        "query": {"type": "string"},
        "channel": {"type": "string", "description": "Filter results to one channel. Optional."},
        "hook_type": {"type": "string", "description": "Filter results to one hook type. Optional."},
        "video_id": {"type": "string", "description": "Restrict results to one item by video_id. Optional."},
        "entity": {"type": "string", "description": "Entity name to look up (case-insensitive)."},
    }
    old_limits = {"search_uoinks": (50, 10), "search_clips": (50, 20),
                  "find_mentions": (200, 50), "search_library": (20, 5)}
    for name, fields in old_fields.items():
        spec = tools.TOOL_REGISTRY[name]
        schema = spec.input_schema
        assert set(schema["properties"]) == fields | {"match"} | ({"mode"} if name != "find_mentions" else set())
        assert schema["required"] == (["entity"] if name == "find_mentions" else ["query"])
        assert schema["additionalProperties"] is False
        assert schema["properties"]["match"]["enum"] == ["forgiving", "strict"]
        assert schema["properties"]["match"]["default"] == "forgiving"
        assert tools.client_input_schema(schema) == schema
        maximum, default = old_limits[name]
        expected = {field: old_properties[field] for field in fields - {"limit"}}
        expected["limit"] = {"type": "integer", "minimum": 1, "maximum": maximum, "default": default}
        if name == "search_library":
            expected["query"] = {"type": "string", "description": "Search text, at most 512 characters."}
            expected["limit"]["description"] = "Maximum hits, 1-20 (default 5)."
        assert {k: v for k, v in schema["properties"].items() if k not in ("match", "mode")} == expected
    assert tools.TOOL_REGISTRY["search_library"].input_schema == library_resources.TOOL_SCHEMAS["search_library"]
    assert corpus_contract.SearchRequest.from_query({}).match == "forgiving"


@pytest.mark.parametrize("query", ['NEAR(lunar lander)', 'title:lunar OR * ^lander', '"lunar" AND "lander"', 'lunar NOT lander'])
def test_user_fts_operators_are_data_in_real_match(db, query):
    seed(db, "full", "NEAR title lunar OR AND NOT lander")
    seed(db, "other", "totally unrelated")
    assert ids(db.search(query)) == ["full"]
    assert ids(db.search(query, match="strict")) == ["full"]


def test_stopwords_fallback_prefix_and_invalid_mode_in_real_match(db):
    seed(db, "lunar", "lunar landers")
    seed(db, "stopwords", "the and or")
    assert ids(db.search("show me the lunar land")) == ["lunar"]
    assert ids(db.search("the and or")) == ["stopwords"]
    assert db.search('"*^') == []
    with pytest.raises(ValueError, match="match must be"):
        db.search("lunar", match="invalid")
