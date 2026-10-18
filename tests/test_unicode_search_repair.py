"""Exercise Unicode retrieval through disposable indexes and the real FTS engine."""

import unicodedata

import pytest

import index


def seed(db, video_id, content):
    db.upsert_yoink({"video_id": video_id, "slug": video_id, "title": video_id,
                     "channel": "fixture", "source_type": "text",
                     "corpus_path": str(db._path.parent / (video_id + ".md")),
                     "sidecar_path": str(db._path.parent / (video_id + ".json")),
                     "yoinked_at": "2026-09-11T12:00:00"}, content=content)


@pytest.mark.parametrize("term", ["日本語", "canción", "Привет", "مرحبا", "नमस्ते", "cancio\u0301n"])
def test_unicode_terms_remain_intact_and_find_their_content(tmp_path, term):
    assert index._fts_query(term) == '"' + unicodedata.normalize("NFC", term) + '"*'
    with index.Index.open(tmp_path / "index.db") as db:
        seed(db, "wanted", term + " language lesson")
        seed(db, "unrelated", "different vocabulary")
        assert [row["video_id"] for row in db.search(term)] == ["wanted"]


@pytest.mark.parametrize("query", ["canción", "cancio\u0301n", "canció", "cancio\u0301"])
def test_composed_decomposed_and_prefix_queries_find_existing_accented_text(tmp_path, query):
    with index.Index.open(tmp_path / "index.db") as db:
        seed(db, "wanted", "canción")
        assert [row["video_id"] for row in db.search(query)] == ["wanted"]


def test_unicode_clips_are_retrievable_with_the_existing_clip_index(tmp_path):
    with index.Index.open(tmp_path / "index.db") as db:
        seed(db, "wanted", "日本語")
        db.insert_citations("wanted", [{"kind": "transcript_chunk", "seq": 0,
            "timestamp_start": 0, "timestamp_end": 12, "text": "日本語 lesson"}])
        assert [row["video_id"] for row in db.search_clips("日本語")] == ["wanted"]


def test_boolean_keywords_remain_literal_words_in_mixed_language_search(tmp_path):
    with index.Index.open(tmp_path / "index.db") as db:
        seed(db, "wanted", "日本語 OR canción")
        seed(db, "japanese-only", "日本語")
        seed(db, "spanish-only", "canción")
        assert [row["video_id"] for row in db.search('日本語 OR "canción"')] == ["wanted"]
        assert index._fts_query('title:日本語 NOT canción*') == '"title" "日本語" "NOT" "canción"*'


@pytest.mark.parametrize("query", ["", '"*():{}[]', "\u0301\u0308", "\x00\n\t", "🙂"])
def test_separator_only_queries_stay_empty(query):
    assert index._fts_query(query) == ""


def test_existing_ascii_and_numeric_query_behavior_is_preserved():
    assert index._fts_query('foo_bar 123 hooks') == '"foo_bar" "123" "hooks"*'
