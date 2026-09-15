"""Living Library Phase 1 clip contracts and gates G0, G1, and G3."""

from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import clips
import index as index_mod
import openapi_bridge
import server
import uoink_mcp_tools


ROOT = Path(__file__).resolve().parents[1]
DISALLOWED_IMPORTS = {
    "urllib", "requests", "httpx", "anthropic", "openai",
}


def _cue(seq: int, start: float, end: float, text: str,
         deep_link: str | None = None) -> dict:
    return {
        "kind": "transcript_chunk",
        "seq": seq,
        "timestamp_start": start,
        "timestamp_end": end,
        "text": text,
        "source_deep_link": deep_link,
    }


def _seed_item(index: index_mod.Index, video_id: str, *, slug: str,
               title: str, channel: str, platform: str = "youtube",
               source_type: str = "video", url: str | None = None) -> None:
    index.upsert_yoink({
        "video_id": video_id,
        "slug": slug,
        "title": title,
        "channel": channel,
        "topic": "Tests",
        "hook_type": None,
        "yoinked_at": "2026-09-04T12:00:00",
        "corpus_path": str(index._path.parent / f"{slug}.md"),
        "sidecar_path": str(index._path.parent / f"{slug}.json"),
        "metadata_json": json.dumps({"url": url}),
        "platform": platform,
        "source_type": source_type,
    })


def _clip_rows(index: index_mod.Index) -> list[tuple]:
    return [tuple(row) for row in index._conn.execute(
        "SELECT video_id, seq, start, \"end\", text, speaker, "
        "source_deep_link, cue_count FROM clips ORDER BY video_id, seq"
    ).fetchall()]


def test_cue_overlap_is_deduplicated() -> None:
    merged = clips.merge_cues([
        _cue(0, 0, 30, "alpha beta gamma"),
        _cue(1, 30, 46, "gamma delta epsilon."),
    ])

    assert len(merged) == 1
    assert merged[0]["text"] == "alpha beta gamma delta epsilon."


def test_ten_millisecond_echo_cue_is_dropped() -> None:
    merged = clips.merge_cues([
        _cue(0, 0, 20, "one two three four"),
        _cue(1, 20, 20.01, "two three four"),
        _cue(2, 20.01, 46, "four five six."),
    ])

    assert len(merged) == 1
    assert merged[0]["text"] == "one two three four five six."
    assert merged[0]["cue_count"] == 2


def test_sentence_boundary_closes_window_at_45_seconds() -> None:
    merged = clips.merge_cues([
        _cue(0, 0, 30, "the opening keeps going"),
        _cue(1, 30, 46, "and now it stops."),
        _cue(2, 130, 140, "A separate tail."),
    ])

    assert len(merged) == 2
    assert merged[0]["start"] == 0
    assert merged[0]["end"] == 46


def test_hard_close_at_120_seconds_needs_no_punctuation() -> None:
    merged = clips.merge_cues([
        _cue(0, 0, 60, "a long thought without punctuation"),
        _cue(1, 60, 121, "still going"),
        _cue(2, 130, 140, "A separate tail."),
    ])

    assert len(merged) == 2
    assert merged[0]["end"] == 60
    assert merged[1]["text"].startswith("still going")
    assert all(c["end"] - c["start"] <= 120 for c in merged)


def test_long_cue_splits_text_without_inventing_timestamps() -> None:
    text = "long source paragraph " * 180
    merged = clips.merge_cues([_cue(0, 12, 1053, text)])
    assert len(merged) > 1
    assert "".join(c["text"] for c in merged) == text.strip()
    assert all(len(c["text"]) <= clips.MAX_COARSE_CHARS for c in merged)
    assert all((c["start"], c["end"], c["timing"]) == (12, 1053, "coarse")
               for c in merged)


def test_coarse_timing_survives_storage_and_search(tmp_path) -> None:
    with index_mod.Index.open(tmp_path / "coarse.db") as idx:
        _seed_item(idx, "coarse", slug="coarse", title="Coarse", channel="Test")
        idx.insert_citations("coarse", [_cue(0, 0, 1041, "coarse sentinel " * 200)])
        assert all(c["timing"] == "coarse" for c in idx.get_clips("coarse"))
        assert idx.search_clips("coarse sentinel")[0]["timing"] == "coarse"


def test_open_repairs_old_oversize_clips_once(tmp_path, monkeypatch):
    path = tmp_path / "legacy-clips.db"
    with index_mod.Index.open(path) as idx:
        _seed_item(idx, "legacy", slug="legacy", title="Legacy", channel="Test")
        idx.insert_citations("legacy", [_cue(0, 0, 1041, "legacy paragraph " * 200)])
        with idx.write_transaction() as conn:
            conn.execute("DELETE FROM clips")
            conn.execute("INSERT INTO clips(video_id, seq, start, end, text, cue_count) VALUES('legacy', 0, 0, 1041, ?, 1)",
                         ("legacy paragraph " * 200,))
    with index_mod.Index.open(path) as idx:
        assert len(idx.get_clips("legacy")) > 1
        assert all(len(c["text"]) <= 1200 for c in idx.get_clips("legacy"))
    def unexpected_rebuild(*args):
        raise AssertionError("already repaired clips must not rebuild on open")
    monkeypatch.setattr(clips, "rebuild_all_clips", unexpected_rebuild)
    with index_mod.Index.open(path) as idx:
        assert idx.search_clips("legacy paragraph")


def test_stale_track_rewind_stops_the_walk() -> None:
    merged = clips.merge_cues([
        _cue(0, 0, 50, "current track opening"),
        _cue(1, 50, 100, "current track ending."),
        _cue(2, 10, 15, "stale track must disappear."),
    ])

    assert len(merged) == 1
    assert "stale" not in merged[0]["text"]


def test_deep_links_preserve_youtube_and_podcast_sources() -> None:
    youtube = clips.merge_cues([
        _cue(0, 12, 60, "YouTube passage.",
             "https://youtube.com/watch?v=yt-test&t=12s"),
    ], {"video_id": "yt-test", "platform": "youtube"})
    podcast = clips.merge_cues([
        _cue(0, 34, 90, "Podcast passage.",
             "https://show.example/episodes/7#t=34"),
    ], {
        "video_id": "pod-test",
        "platform": "podcast",
        "url": "https://show.example/episodes/7",
    })

    assert youtube[0]["source_deep_link"] == (
        "https://youtube.com/watch?v=yt-test&t=12s"
    )
    assert podcast[0]["source_deep_link"] == (
        "https://show.example/episodes/7#t=34"
    )


def test_rebuild_all_clips_is_idempotent(tmp_path: Path) -> None:
    index = index_mod.Index.open(tmp_path / "index.db")
    try:
        _seed_item(
            index, "idempotent", slug="idempotent", title="Idempotent",
            channel="Test channel",
        )
        index.insert_citations("idempotent", [
            _cue(0, 0, 50, "first stable segment"),
            _cue(1, 50, 90, "second stable segment."),
        ])

        first = index.rebuild_clips()
        first_rows = _clip_rows(index)
        second = index.rebuild_clips()
        second_rows = _clip_rows(index)

        assert first["clip_count"] == second["clip_count"] == 1
        assert first_rows == second_rows
    finally:
        index.close()


def test_clips_fts_delete_trigger_follows_yoink_cascade(
        tmp_path: Path) -> None:
    index = index_mod.Index.open(tmp_path / "index.db")
    try:
        _seed_item(
            index, "cascade", slug="cascade", title="Cascade",
            channel="Test channel",
        )
        index.insert_citations("cascade", [
            _cue(0, 0, 50, "cascade sentinel phrase.",
                 "https://youtube.com/watch?v=cascade&t=0s"),
        ])
        assert index.search_clips("cascade sentinel")

        index.delete_yoink("cascade")

        assert index._conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 0
        assert index.search_clips("cascade sentinel") == []
    finally:
        index.close()


def test_g0_populated_pre_0024_upgrade_is_idempotent_and_rebuilds_fts(
        tmp_path: Path, monkeypatch, caplog) -> None:
    real_migrations = index_mod._MIGRATIONS_DIR
    old_migrations = tmp_path / "migrations-through-23"
    old_migrations.mkdir()
    for source in real_migrations.glob("*.sql"):
        if int(source.name.split("_", 1)[0]) <= 23:
            shutil.copy2(source, old_migrations / source.name)

    db_path = tmp_path / "upgrade.db"
    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", old_migrations)
    old_index = index_mod.Index.open(db_path)
    _seed_item(
        old_index, "upgrade", slug="upgrade", title="Upgrade fixture",
        channel="Test channel",
    )
    old_index._conn.execute(
        "INSERT INTO citations "
        "(video_id, kind, seq, timestamp_start, timestamp_end, text, "
        "source_url, source_deep_link) "
        "VALUES (?, 'transcript_chunk', 0, 5, 55, ?, ?, ?)",
        (
            "upgrade",
            "upgrade sentinel sentence.",
            "https://youtube.com/watch?v=upgrade",
            "https://youtube.com/watch?v=upgrade&t=5s",
        ),
    )
    old_index._conn.commit()
    old_index.close()

    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", real_migrations)
    caplog.set_level(logging.INFO, logger="uoink.index")
    upgraded = index_mod.Index.open(db_path)
    try:
        # The upgrade lands on whatever the newest shipped migration is
        # (0024 introduced clips; later migrations must not break this path).
        newest = max(v for v, _ in index_mod._discover_migrations())
        assert newest >= 24
        assert upgraded._conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0] == newest
        assert upgraded.search_clips("upgrade sentinel")[0][
            "source_deep_link"
        ].endswith("&t=5s")
        assert "clip upgrade backfill" in caplog.text

        before = [row["clip_id"] for row in upgraded.search_clips(
            "upgrade sentinel"
        )]
        upgraded._conn.execute(
            "INSERT INTO clips_fts(clips_fts) VALUES('rebuild')"
        )
        after = [row["clip_id"] for row in upgraded.search_clips(
            "upgrade sentinel"
        )]
        assert after == before
        original_rows = _clip_rows(upgraded)
    finally:
        upgraded.close()

    # Simulate a crash after 0024's DDL but before its version marker. Every
    # statement in the migration must tolerate the replay.
    conn = sqlite3.connect(db_path)
    # Drop 0024's marker and every later one: the runner keys off MAX(version),
    # so 0024 only replays when nothing newer is recorded; later migrations
    # replay too and must cope.
    conn.execute("DELETE FROM schema_version WHERE version>=24")
    conn.commit()
    conn.close()

    replayed = index_mod.Index.open(db_path)
    try:
        assert replayed._conn.execute(
            "SELECT COUNT(*) FROM schema_version WHERE version=24"
        ).fetchone()[0] == 1
        assert _clip_rows(replayed) == original_rows
        assert replayed.search_clips("upgrade sentinel")
    finally:
        replayed.close()


def test_g1_http_registry_handlers_and_coverage(
        tmp_path: Path, monkeypatch) -> None:
    index = index_mod.Index.open(tmp_path / "index.db")
    youtube_link = "https://youtube.com/watch?v=yt-g1&t=12s"
    podcast_link = "https://show.example/episodes/g1#t=34"
    try:
        _seed_item(
            index, "yt-g1", slug="youtube-g1", title="YouTube G1",
            channel="Video channel", url="https://youtube.com/watch?v=yt-g1",
        )
        _seed_item(
            index, "pod-g1", slug="podcast-g1", title="Podcast G1",
            channel="Audio channel", platform="podcast",
            source_type="podcast", url="https://show.example/episodes/g1",
        )
        _seed_item(
            index, "empty-g1", slug="empty-g1", title="No citations",
            channel="Silent channel",
        )
        index.insert_citations("yt-g1", [
            _cue(0, 12, 60, "quasar needle video passage.", youtube_link),
        ])
        index.insert_citations("pod-g1", [
            _cue(0, 34, 90, "harbor signal podcast passage.", podcast_link),
        ])

        monkeypatch.setattr(server, "_get_index", lambda: index)
        uoink_mcp_tools.bind_backend(server)

        spec = openapi_bridge.build_spec(
            "http://127.0.0.1:5179",
            tool_registry=uoink_mcp_tools.TOOL_REGISTRY,
            version="test",
        )
        assert "/tools/search_clips" in spec["paths"]
        assert "/tools/get_evidence_card" in spec["paths"]

        class Probe:
            def _send_json(self, status: int, payload: dict) -> None:
                self.status = status
                self.payload = payload

        youtube_probe = Probe()
        server.Handler._handle_tools_call_http(
            youtube_probe,
            "/tools/search_clips",
            {"query": "quasar needle"},
        )
        assert youtube_probe.status == 200
        assert youtube_probe.payload["result"]["results"][0][
            "video_id"
        ] == "yt-g1"
        assert youtube_probe.payload["result"]["results"][0][
            "deep_link"
        ] == youtube_link

        podcast = uoink_mcp_tools.call_tool(
            "search_clips", {"query": "harbor signal"}
        )
        assert podcast["results"][0]["deep_link"] == podcast_link

        by_slug = uoink_mcp_tools.call_tool(
            "get_evidence_card", {"slug": "youtube-g1"}
        )
        by_video_id = uoink_mcp_tools.call_tool(
            "get_evidence_card", {"video_id": "pod-g1"}
        )
        assert by_slug["clips"][0]["deep_link"] == youtube_link
        assert by_slug["video_id"] == "yt-g1"
        assert by_video_id["clips"][0]["deep_link"] == podcast_link
        assert by_video_id["slug"] == "podcast-g1"

        assert index.clip_coverage() == {
            "items_with_clips": 2,
            "items_without_clips": 1,
            "clip_count": 2,
        }
    finally:
        index.close()


def test_g3_clip_modules_have_no_network_or_llm_imports() -> None:
    for path in (ROOT / "clips.py", ROOT / "scripts" / "recall_hook.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0]
                               for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        assert imports.isdisjoint(DISALLOWED_IMPORTS), (path, imports)


def test_g3_importing_clips_is_stdio_clean() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    completed = subprocess.run(
        [sys.executable, "-c", "import clips"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
