import pytest

import index
import library_resources
import server
import uoink_cli
import uoink_mcp_tools
from tests.phase4_fixtures import seed_yoink_item
from tests.test_dashboard_library_search import search
from uoink_core.local_search import word_passages


@pytest.mark.parametrize("query", ["office", "acoustics", "art"])
def test_no_captions_search_previews_description(tmp_path, monkeypatch, query):
    description = "The acoustics lab has walls made of particleboard."
    content = ("# Office art tour\n\n**Channel:** Example Studio\n**URL:** https://example.test\n"
               "\n---\n\n## Thumbnail\n\n![Thumbnail](thumbnail.jpg)\n"
               f"\n## Description\n\n{description}\n\n## Tags\n\nNo tags")
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="office", slug="office",
                               title="Office art tour", corpus_text=content)
        idx.upsert_yoink(item, content=content)
        row, = idx.search(query)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(uoink_mcp_tools, "_backend", server)
        assert search({"q": query, "mode": "keyword"})["results"][0]["snippet"] == description
        assert uoink_mcp_tools.search_uoinks({"query": query})["results"][0]["snippet"] == description
        reader = library_resources.LibraryReader(idx, data_root=tmp_path)
        result = library_resources.call_tool("search_library", {"query": query}, reader)
        assert result["hits"][0]["preview"]["text"] == description
        assert description in uoink_cli.human(result, index=idx)
    assert row["_snippet"] == description
    if query != "acoustics":
        assert not row["passage_verified"]
    else:
        passage = row["passage"]
        assert description == content[passage["char_start"]:passage["char_end"]]


@pytest.mark.parametrize("header", ["URL", "Source"])
@pytest.mark.parametrize("has_body", [True, False])
def test_repeated_title_term_returns_exact_body_passage(tmp_path, header, has_body):
    description = "background " * 46 + "office acoustics " + "resonance " * 37
    content = f"# Office\n\n**{header}:** https://example.test\n**Platform:** example\n"
    if has_body:
        content += "\n## Description\n\n" + description
    content += "\n## Transcript\n\n_No transcript available (site did not expose subtitles / yt-dlp could not parse)._"
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="office", slug="office", title="Office", corpus_text=content)
        idx.upsert_yoink(item, content=content)
        row, = idx.search("office")
    assert row["passage_verified"] is has_body
    if has_body:
        p = row["passage"]
        start, end = p["char_start"], p["char_end"]
        assert row["_snippet"] == p["text"] == content[start:end]
        assert "office acoustics" in p["text"]
        assert content[start - 1].isspace() and content[end].isspace()
    else:
        assert row["_snippet"] == "Office"


def test_empty_clip_cannot_quote_the_header(tmp_path):
    content = "# Café\n\n**URL:** https://example.test\n\n## Description\n\nOur café has cork walls."
    with index.Index.open(tmp_path / "index.db") as idx:
        marked = index._MATCH_START + "Café" + index._MATCH_END
        row = idx._search_passage({"video_id": "fixture", "_content": content, "_snippet": "# " + marked,
                                   "_matched_clip": {"clip_id": 1, "text": ""}}, "cafe", "forgiving")
    assert row["_snippet"] == row["passage"]["text"] == "Our café has cork walls."
    assert row["passage_verified"] and row["passage"]["char_start"] == content.index("Our")


def test_verified_clip_keeps_full_citation_and_short_whole_word_preview(tmp_path):
    text = "acoustics " * 80
    content = "# Acoustics\n\n**URL:** https://example.test\n\n## Transcript\n\n" + text
    with index.Index.open(tmp_path / "index.db") as idx:
        row = idx._search_passage({"video_id": "fixture", "_content": content, "_snippet": "",
                                   "_matched_clip": {"clip_id": 1, "text": text}}, "acoustics", "forgiving")
    assert row["passage"]["text"] == text
    assert row["_snippet"].endswith("acoustics") and len(row["_snippet"]) <= 250


def test_semantic_chunks_keep_original_word_and_character_offsets():
    content = ("# Example\n\n**URL:** https://example.test\n\n## Description\n\nA small lab.\n"
               "\n## Top Comments\n\n**Viewer** (1 like)\n> Cork walls made the room quiet.")
    passages = word_passages(content)
    assert [p.text for p in passages] == ["A small lab.", "Cork walls made the room quiet."]
    for p in passages:
        lo, hi = p.span["char_start"], p.span["char_end"]
        assert content[lo:hi] == p.text
        assert len(content[:lo].split()) == p.span["word_start"]


@pytest.mark.parametrize("query", ["memory leak", '"memory leak"'])
def test_search_prefers_passage_covering_query(tmp_path, query):
    content = ("# Memory leak\n\n**URL:** https://example.test\n\n## Description\n\nMemory foam. "
               + "background " * 60 + "\n\n## Transcript\n\nWe traced the memory leak to a buffer.")
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="trace", slug="trace", title="Memory leak", corpus_text=content)
        idx.upsert_yoink(item, content=content)
        row, = idx.search(query)
    passage = row["passage"]
    assert "memory leak to a buffer" in row["_snippet"]
    assert passage["text"] == content[passage["char_start"]:passage["char_end"]]


@pytest.mark.parametrize(("query", "body"), [
    ('"memory leak"', "Memory foam and a leaky pipe."),
    ("C++", "A C program."), (".NET", "A net result."), ("@handle", "A door handle."),
])
def test_header_only_literal_cannot_verify_a_body_quote(tmp_path, query, body):
    literal = query.strip('"')
    content = f"# {literal}\n\n**URL:** https://example.test\n\n## Description\n\n{body}"
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="literal", slug="literal", title=literal, corpus_text=content)
        idx.upsert_yoink(item, content=content)
        row, = idx.search(query)
        assert not row["passage_verified"] and "passage" not in row
        idx.upsert_yoink(item, content=content + " Here is " + literal + ".")
        row, = idx.search(query)
        assert row["passage_verified"] and literal in row["passage"]["text"]


def test_large_corpus_bounds_scan_and_word_snapping(tmp_path, monkeypatch):
    from uoink_core import search_service
    ranges = search_service.corpus_body_ranges
    lengths = []
    def observe(text):
        lengths.append(len(text))
        return ranges(text)
    monkeypatch.setattr(search_service, "corpus_body_ranges", observe)
    body = "壁" * 1500 + "/match/" + "壁" * 500000
    content = "# Match\n\n**URL:** https://example.test\n\n## Transcript\n\n" + body
    with index.Index.open(tmp_path / "index.db") as idx:
        row = idx._search_passage({"video_id": "fixture", "_content": content}, "match", "forgiving")
        assert row["passage_verified"] and "/match/" in row["_snippet"]
        assert len(row["_snippet"]) <= 304
        assert max(lengths) <= 65536
        row = idx._search_passage({"video_id": "fixture", "_content": content,
                                   "_matched_clip": {"clip_id": 1, "text": body}}, "match", "forgiving")
        assert len(row["_snippet"]) <= 272 and "/match/" in row["_snippet"]
        assert row["passage"]["text"] == body


def test_exact_phrase_mode_and_clip_require_literal_phrase(tmp_path):
    content = "# Memory leak\n\n**URL:** https://example.test\n\n## Transcript\n\nMemory leakage."
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="trace", slug="trace", title="Memory leak", corpus_text=content)
        idx.upsert_yoink(item, content=content)
        row, = idx.search("memory leak", match="exact")
        assert not row["passage_verified"]
        row = idx._search_passage({"video_id": "trace", "_content": content,
                                   "_matched_clip": {"clip_id": 1, "text": "Memory leakage."}},
                                  '"memory leak"', "forgiving")
        assert not row["passage_verified"]


def test_scan_limit_cannot_turn_a_long_header_into_a_quote(tmp_path):
    content = "# Memory leak\n\n**URL:** https://example.test\n" + "padding " * 10000
    content += "\n## Description\n\nMemory foam."
    marked = index._MATCH_START + "Memory leak" + index._MATCH_END
    with index.Index.open(tmp_path / "index.db") as idx:
        row = idx._search_passage({"video_id": "trace", "title": "Memory leak", "_content": content,
                                   "_snippet": "# " + marked}, '"memory leak"', "forgiving")
    assert not row["passage_verified"]


def test_scan_boundary_is_not_an_exact_word_ending(tmp_path):
    header = "# Leak\n\n**URL:** https://example.test\n\n## Description\n\n"
    content = header + " " * (65536 - len(header) - 4) + "leakage"
    with index.Index.open(tmp_path / "index.db") as idx:
        row = idx._search_passage({"video_id": "trace", "_content": content}, '"leak"', "forgiving")
    assert not row["passage_verified"]


def test_quoted_search_picks_clip_containing_phrase(tmp_path):
    content = "# Memory leak\n\n**URL:** https://example.test\n\n## Description\n\nDebugging notes."
    phrase_clip = "After much investigation we found a memory leak. " + "details " * 60
    with index.Index.open(tmp_path / "index.db") as idx:
        item = seed_yoink_item(idx, tmp_path, video_id="trace", slug="trace", title="Memory leak",
                               corpus_text=content, clips=[
                                   {"text": "Memory usage. Leak found.", "start": 0, "end": 5},
                                   {"text": phrase_clip, "start": 200, "end": 260}])
        idx.upsert_yoink(item, content=content)
        assert len(idx.get_clips("trace")) == 2
        row, = idx.search('"memory leak"')
    assert row["passage_verified"] and row["passage"]["start"] == 200
