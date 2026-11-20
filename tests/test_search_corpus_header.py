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


def test_semantic_chunks_keep_original_word_and_character_offsets():
    content = ("# Example\n\n**URL:** https://example.test\n\n## Description\n\nA small lab.\n"
               "\n## Top Comments\n\n**Viewer** (1 like)\n> Cork walls made the room quiet.")
    passages = word_passages(content)
    assert [p.text for p in passages] == ["A small lab.", "Cork walls made the room quiet."]
    for p in passages:
        lo, hi = p.span["char_start"], p.span["char_end"]
        assert content[lo:hi] == p.text
        assert len(content[:lo].split()) == p.span["word_start"]
