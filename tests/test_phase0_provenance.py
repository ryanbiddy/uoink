from __future__ import annotations

import json

import index as index_mod
import provenance


def _record(video_id: str, **overrides) -> dict:
    record = {
        "video_id": video_id,
        "slug": video_id,
        "channel": "source",
        "title": video_id,
        "topic": "Uncategorized",
        "hook_type": None,
        "yoinked_at": "2026-09-04T00:00:00",
        "corpus_path": "",
        "sidecar_path": "",
        "health_score_json": None,
        "metadata_json": "{}",
        "platform": None,
        "author": None,
    }
    record.update(overrides)
    return record


def test_derive_source_type_uses_kind_platform_and_url(tmp_path):
    sidecar = tmp_path / "note.json"
    sidecar.write_text(json.dumps({"kind": "note"}), encoding="utf-8")

    assert provenance.derive_source_type(sidecar_path=sidecar) == "note"
    assert provenance.derive_source_type(platform="podcast") == "episode"
    assert provenance.derive_source_type(platform="image") == "image"
    assert provenance.derive_source_type(
        metadata_json=json.dumps({"url": "https://x.com/a/status/1"})
    ) == "x_thread"
    assert provenance.derive_source_type(
        metadata_json=json.dumps({"url": "https://x.com/i/article/1"})
    ) == "x_article"
    assert provenance.derive_source_type(
        metadata_json=json.dumps({"url": "https://reddit.com/r/test/comments/1"})
    ) == "reddit_thread"
    assert provenance.derive_source_type(
        metadata_json=json.dumps({"url": "https://example.com/post"})
    ) == "page"
    assert provenance.derive_source_type(
        metadata_json=json.dumps({"url": "https://youtube.com/shorts/abc"})
    ) == "short_video"
    assert provenance.derive_source_type(platform="youtube") == "video"


def test_upsert_sets_source_type_at_write_time(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        idx.upsert_yoink(_record(
            "x-post",
            platform="x",
            metadata_json=json.dumps({"url": "https://x.com/a/status/1"}),
        ))
        assert idx.get_yoink("x-post")["source_type"] == "x_thread"
    finally:
        idx.close()


def test_migration_and_python_backfill_leave_no_nulls(tmp_path):
    db_path = tmp_path / "index.db"
    sidecar = tmp_path / "saved-note.json"
    sidecar.write_text(json.dumps({"source_type": "note"}), encoding="utf-8")

    idx = index_mod.Index.open(db_path)
    try:
        idx.upsert_yoink(_record(
            "legacy-x",
            platform="x",
            metadata_json=json.dumps({"url": "https://x.com/a/status/1"}),
        ))
        idx.upsert_yoink(_record("legacy-note", sidecar_path=str(sidecar)))
        with idx.write_transaction() as conn:
            conn.execute(
                "UPDATE yoinks SET source_type=NULL "
                "WHERE video_id IN ('legacy-x', 'legacy-note')"
            )
            conn.execute("DELETE FROM schema_version WHERE version=25")
    finally:
        idx.close()

    repaired = index_mod.Index.open(db_path)
    try:
        assert repaired.schema_version() == 25
        assert repaired.get_yoink("legacy-x")["source_type"] == "x_thread"
        assert repaired.get_yoink("legacy-note")["source_type"] == "note"
        assert repaired._conn.execute(
            "SELECT COUNT(*) FROM yoinks WHERE source_type IS NULL"
        ).fetchone()[0] == 0
    finally:
        repaired.close()
