"""C-03 (CRIT-3) -- durability: commits, corpus export/import, index rebuild.

Run: python tests/test_c03_durability.py  (also collected by pytest tests/)

"Own your data" was ~70% true: 4 write paths never committed (a process
kill silently dropped engagement events, facets, tags, and taste anchors),
there was no export/backup for the six SQLite-only tables, and an index
rebuild came back empty.

Red on unpatched main:
- the visibility tests fail (uncommitted rows are invisible to a second
  connection on the same database file, which is exactly what a kill loses),
- Index.export_payload / import_payload don't exist,
- rebuild_index_from_disk doesn't exist.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _second_connection(db_path: Path) -> sqlite3.Connection:
    """An independent reader: sees only COMMITTED data, like the process
    that reopens the database after a kill."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _seed_row(idx, video_id="vidcommit01"):
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": "TestChannel",
        "title": "Commit test", "topic": "AI and ML", "hook_type": "demo",
        "yoinked_at": "2026-07-01T10:00:00",
        "corpus_path": "", "sidecar_path": "", "source_type": "youtube",
    }, content="body")


# ---- the four commits ------------------------------------------------------

def test_writes_survive_without_a_second_commit():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "index.db"
        idx = index_mod.Index.open(db)
        try:
            _seed_row(idx)

            idx.log_engagement("vidcommit01", "cite", "dashboard")
            reader = _second_connection(db)
            n = reader.execute(
                "SELECT COUNT(*) AS n FROM engagement_events").fetchone()["n"]
            reader.close()
            _assert(n == 1, f"engagement event must be committed, reader saw {n}")
            print("ok  log_engagement commits")

            idx.set_facets("vidcommit01", format="screen_recording")
            reader = _second_connection(db)
            row = reader.execute(
                "SELECT format FROM yoinks WHERE video_id='vidcommit01'"
            ).fetchone()
            reader.close()
            _assert(row["format"] == "screen_recording",
                    f"facets must be committed, reader saw {dict(row)}")
            print("ok  set_facets commits")

            idx.add_tags("vidcommit01", ["MCP", "agents"])
            reader = _second_connection(db)
            n = reader.execute(
                "SELECT COUNT(*) AS n FROM yoink_tags").fetchone()["n"]
            reader.close()
            _assert(n == 2, f"tags must be committed, reader saw {n}")
            print("ok  add_tags commits")

            memory_layer.set_anchor(idx, "avoid", "Write like a sharp human.")
            reader = _second_connection(db)
            row = reader.execute(
                "SELECT value FROM memory_layer WHERE key='taste.avoid'"
            ).fetchone()
            reader.close()
            _assert(row and "sharp human" in row["value"],
                    f"taste anchor must be committed, reader saw {row}")
            print("ok  taste set_anchor commits")
        finally:
            idx.close()


# ---- export / import -------------------------------------------------------

def _populate_everything(idx):
    _seed_row(idx, "videxporta1")
    idx.log_engagement("videxporta1", "cite", "dashboard",
                       ts_utc="2026-06-01T10:00:00")
    idx.add_tags("videxporta1", ["mcp"])
    memory_layer.set_anchor(idx, "avoid", "Short and concrete.")
    idx._conn.execute(
        "INSERT INTO writing_drafts (yoink_id, kind, title, body, "
        "source_credit_line, created_at, updated_at) "
        "VALUES ('videxporta1','tweet','t','draft body','via @x',"
        "'2026-06-01T10:00:00','2026-06-01T10:00:00')")
    idx._conn.execute(
        "INSERT INTO workspaces (id, created_at, updated_at, format, topic, "
        "hook_target, your_channel, n_examples, assembled_yoinks, notes) "
        "VALUES ('ws1','2026-06-01','2026-06-01','tweet','AI','demo','me',"
        "3,'[]','')")
    idx._conn.execute(
        "INSERT INTO style_anchors (id, name, source_type, source_url, "
        "raw_text, active, added_at, is_default) "
        "VALUES (7001,'My voice','text','','sample',1,'2026-06-01',0)")
    idx._conn.commit()


def test_export_import_round_trip():
    with tempfile.TemporaryDirectory() as d:
        source = index_mod.Index.open(Path(d) / "source.db")
        target = index_mod.Index.open(Path(d) / "target.db")
        try:
            _populate_everything(source)
            # Video-keyed tables (tags) FK onto yoinks; the real restore
            # flow rebuilds yoinks from sidecars BEFORE importing. Mirror
            # that here.
            _seed_row(target, "videxporta1")
            payload = source.export_payload()
            _assert(payload["format"] == "uoink-corpus-export"
                    and payload["format_version"] == 1,
                    f"payload header: {payload.get('format')}")
            for table in index_mod.Index.EXPORT_TABLES:
                _assert(table in payload["tables"], f"{table} missing")
            _assert(len(payload["tables"]["engagement_events"]) == 1
                    and len(payload["tables"]["style_anchors"]) == 1,
                    "seeded rows must be in the payload")

            report = target.import_payload(payload)
            for table in ("engagement_events", "yoink_tags", "memory_layer",
                          "writing_drafts", "workspaces", "style_anchors"):
                _assert(report[table]["imported"] == 1,
                        f"{table} must import 1: {report[table]}")
            row = target._conn.execute(
                "SELECT value FROM memory_layer WHERE key='taste.avoid'"
            ).fetchone()
            _assert("Short and concrete" in row["value"], "taste restored")
            print("ok  export -> import restores all six tables")

            # Idempotent: importing again changes nothing.
            report = target.import_payload(payload)
            for table, counts in report.items():
                _assert(counts["imported"] == 0,
                        f"second import must skip everything: {table} {counts}")
            print("ok  re-import is a no-op (conservative merge)")

            # Never clobber newer local data.
            memory_layer.set_anchor(target, "avoid", "Newer local truth.")
            target.import_payload(payload)
            row = target._conn.execute(
                "SELECT value FROM memory_layer WHERE key='taste.avoid'"
            ).fetchone()
            _assert("Newer local truth" in row["value"],
                    f"older import must not clobber newer local: {row['value']}")
            print("ok  older imports never clobber newer local rows")

            try:
                target.import_payload({"format": "something-else"})
                raise AssertionError("junk payload must be rejected")
            except ValueError:
                print("ok  junk payloads rejected")
        finally:
            source.close()
            target.close()


# ---- rebuild from sidecars --------------------------------------------------

def _write_corpus_folder(root: Path, topic: str, slug: str, video_id: str):
    folder = root / topic / slug
    folder.mkdir(parents=True)
    (folder / f"{slug}.md").write_text(f"# {slug}\ntranscript body\n",
                                       encoding="utf-8")
    (folder / f"{slug}.json").write_text(json.dumps({
        "video_id": video_id, "title": slug.replace("_", " "),
        "channel": "TestChannel", "topic": topic, "hook_type": "demo",
        "yoinked_at": "2026-06-15T10:00:00",
        "url": f"https://youtube.com/watch?v={video_id}",
    }), encoding="utf-8")


def test_rebuild_from_sidecars_plus_export():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        corpus_root = base / "corpus"
        _write_corpus_folder(corpus_root, "AI and ML", "First_Video", "vidrbaaaaa1")
        _write_corpus_folder(corpus_root, "AI and ML", "Second_Video", "vidrbbbbbb2")
        _write_corpus_folder(corpus_root, "Career", "Third_Video", "vidrbcccc3")

        # An export from the "old life" sits in the corpus folder, the way
        # --export-corpus leaves it.
        donor = index_mod.Index.open(base / "donor.db")
        _populate_everything(donor)
        exports_dir = corpus_root / "_exports"
        exports_dir.mkdir()
        payload = donor.export_payload()
        (exports_dir / "uoink-export-20260615-000000.json").write_text(
            json.dumps(payload), encoding="utf-8")
        donor.close()

        # Fresh index (the "index.db died" scenario).
        idx = index_mod.Index.open(base / "fresh.db")
        original_index = server._get_index
        server._get_index = lambda: idx
        try:
            report = server.rebuild_index_from_disk(root=corpus_root)
            _assert(report["rows_before"] == 0 and report["rows_after"] == 3,
                    f"3 sidecar folders must index: {report}")
            _assert(report["indexed"] == 3, f"indexed count: {report}")
            row = idx.get_yoink("vidrbaaaaa1")
            _assert(row and row["topic"] == "AI and ML"
                    and Path(row["corpus_path"]).exists(),
                    f"rebuilt row must point at the real file: {row}")
            restored = report.get("restored") or {}
            _assert(restored.get("ok") is True,
                    f"newest export must be restored: {restored}")
            _assert(restored["report"]["style_anchors"]["imported"] == 1,
                    f"SQLite-only tables restored too: {restored['report']}")
            print("ok  rebuild indexes sidecars AND restores the export")
        finally:
            server._get_index = original_index
            idx.close()


def test_cli_and_routes_wired():
    src = (Path(__file__).resolve().parent.parent / "server.py").read_text(
        encoding="utf-8")
    for marker in ('"--export-corpus" in argv', '"--import-corpus" in argv',
                   '"--rebuild-index" in argv', '"/corpus/export"',
                   '"/corpus/import"'):
        _assert(marker in src, f"missing wiring: {marker}")
    print("ok  CLI flags + routes wired")


def main():
    test_writes_survive_without_a_second_commit()
    test_export_import_round_trip()
    test_rebuild_from_sidecars_plus_export()
    test_cli_and_routes_wired()
    print("\nall green")


if __name__ == "__main__":
    main()
