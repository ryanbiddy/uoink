"""Deterministic local capture fixtures. Synthetic data only."""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .constants import (
    CURRENT_SCHEMA_TARGET,
    FORBIDDEN_PORT,
    LEGACY_FIXTURE_VERSION,
    LEGACY_SCHEMA_VERSION,
    SYNTHETIC_AUDIO,
    SYNTHETIC_HOSTNAME,
    SYNTHETIC_TRANSCRIPT,
)
from .hashes import sha256_bytes, sha256_file
from .validation import C22ValidationError, validate_port

REPO_ROOT = Path(__file__).resolve().parents[2]


FEED_VARIANTS = {
    "default": ("c22-entry-1", "C22 standing capture"),
    "one-off": ("c22-one-off-ep-1", "C22 one-off episode"),
    "manual-first": ("c22-manual-ep-1", "C22 manual-first episode"),
    "standing-first": ("c22-standing-ep-1", "C22 standing-first episode"),
    "child-life": ("c22-child-life-ep-1", "C22 child-lifetime episode"),
    "child-interrupt": ("c22-child-interrupt-ep-1", "C22 launch-interrupt episode"),
    "child-regfail": ("c22-child-regfail-ep-1", "C22 registration-failure episode"),
}


class FixtureFeed:
    """Loopback RSS + audio. Never binds 5179.

    Acquisition wrappers map http://c22-fixture.invalid/<variant>/... onto this
    declared loopback fixture. The loopback URL is never registered as a
    standing source.
    """

    def __init__(self, root: Path, port: int):
        self.root = Path(root)
        self.port = validate_port(port)
        self.state = {
            "entry": False,
            "fail_refresh": False,
            "entries": "one",
            "variant": "default",
        }
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.base = ""
        self.audio_path = self.root / "synthetic-audio.bin"
        self.transcript_path = self.root / "synthetic-transcript.json"
        self.audio_path.write_bytes(SYNTHETIC_AUDIO)
        self.transcript_path.write_text(
            json.dumps(SYNTHETIC_TRANSCRIPT, indent=2) + "\n", encoding="utf-8")

    @property
    def feed_url(self) -> str:
        return self.base + "/feed.xml"

    @property
    def audio_url(self) -> str:
        return self.base + "/fixture.mp3"

    @property
    def episode_url(self) -> str:
        return self.base + "/episode"

    @property
    def one_off_url(self) -> str:
        return self.base + "/one-off"

    def synthetic_feed_url(self, variant: str) -> str:
        return f"http://{SYNTHETIC_HOSTNAME}/{variant}/feed.xml"

    def synthetic_audio_url(self, variant: str) -> str:
        return f"http://{SYNTHETIC_HOSTNAME}/{variant}/fixture.mp3"

    def synthetic_episode_url(self, variant: str) -> str:
        return f"http://{SYNTHETIC_HOSTNAME}/{variant}/episode"

    def variant_identity(self, variant: str) -> tuple[str, str]:
        return FEED_VARIANTS.get(variant, FEED_VARIANTS["default"])

    def start(self) -> str:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                parts = [p for p in path.split("/") if p]
                variant = "default"
                leaf = path
                if len(parts) >= 2 and parts[0] in FEED_VARIANTS:
                    variant = parts[0]
                    leaf = "/" + "/".join(parts[1:])
                if owner.state["fail_refresh"] and leaf == "/feed.xml":
                    self.send_error(500, "C22 declared refresh failure")
                    return
                if leaf.endswith("/fixture.mp3") or leaf == "/fixture.mp3":
                    body = SYNTHETIC_AUDIO
                    content_type = "audio/mpeg"
                elif leaf.endswith("/feed.xml") or leaf == "/feed.xml":
                    body = owner._feed_body(variant)
                    content_type = "application/rss+xml"
                elif leaf.startswith("/episode") or leaf.startswith("/one-off"):
                    body = b"C22 fixture episode"
                    content_type = "text/plain"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        class ReuseServer(ThreadingHTTPServer):
            allow_reuse_address = True

        httpd = ReuseServer(("127.0.0.1", self.port), Handler)
        bound = httpd.server_address[1]
        if bound == FORBIDDEN_PORT:
            httpd.server_close()
            raise C22ValidationError("fixture feed bound forbidden port 5179")
        self.port = bound
        self.server = httpd
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.base

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.server = None
        self.thread = None

    def _feed_body(self, variant: str = "default") -> bytes:
        items = []
        guid, title = self.variant_identity(variant)
        episode = self.synthetic_episode_url(variant)
        audio = self.synthetic_audio_url(variant)
        if self.state["entry"] or variant != "default":
            items.append(self._item(guid, title, episode, "Mon, 07 Sep 2026 12:00:00 GMT",
                                    audio_url=audio))
            if self.state["entries"] == "manual_pair":
                items.append(self._item(guid, title, episode,
                                        "Mon, 07 Sep 2026 12:00:00 GMT",
                                        audio_url=audio))
        xml = (
            '<?xml version="1.0"?>'
            '<rss version="2.0"><channel><title>C22 fixture '
            + escape(variant) + '</title>'
            + "".join(items) +
            "</channel></rss>"
        )
        return xml.encode("utf-8")

    def _item(self, guid: str, title: str, link: str, pub: str,
              audio_url: str | None = None) -> str:
        enclosure = audio_url or self.audio_url
        return (
            f"<item><guid>{escape(guid)}</guid><title>{escape(title)}</title>"
            f"<link>{escape(link)}</link>"
            f'<enclosure url="{escape(enclosure)}" type="audio/mpeg"/>'
            f"<pubDate>{escape(pub)}</pubDate></item>"
        )


def write_settings(profile: Path) -> Path:
    settings = {
        "librarian_apply_enabled": False,
        "diarization_default": False,
        "comment_intelligence_enabled": False,
        "hook_type_enabled": False,
        "entity_extraction_enabled": False,
        "asr_fallback_enabled": False,
        "claim_verification_enabled": False,
        "auto_uoink_enabled": False,
        "notifications_enabled": False,
        "whisper_model": "base",
    }
    path = profile / "settings.json"
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return path


def write_synthetic_taxonomy(profile: Path) -> Path:
    taxonomy = {
        "schema_version": 1,
        "version_id": "c22-synthetic-taxonomy-v1",
        "name": "C22 synthetic taxonomy",
        "status": "approved",
        "nodes": [
            {
                "shelf_id": "c22-fixture",
                "path": ["C22 fixture"],
                "definition": "Synthetic C22 receipt items only.",
                "include": ["c22 fixture"],
                "exclude": [],
            }
        ],
    }
    path = profile / "taxonomy.json"
    path.write_text(json.dumps(taxonomy, indent=2) + "\n", encoding="utf-8")
    return path


def apply_sql_migrations(conn: sqlite3.Connection, *, up_to: int) -> int:
    migrations = REPO_ROOT / "migrations"
    files = []
    for path in sorted(migrations.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= up_to:
            files.append((version, path))
    files.sort()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = 0
    for version, path in files:
        row = conn.execute(
            "SELECT 1 FROM schema_version WHERE version=?", (version,)
        ).fetchone()
        if row:
            applied = version
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, "2026-09-09T00:00:00Z"),
        )
        applied = version
    conn.commit()
    return applied


def build_empty_profile(profile: Path) -> dict[str, Any]:
    profile.mkdir(parents=True, exist_ok=True)
    write_settings(profile)
    write_synthetic_taxonomy(profile)
    (profile / "output").mkdir(exist_ok=True)
    index = profile / "index.db"
    # Empty profile: no database yet. Helper startup migrates a fresh file.
    meta = {
        "kind": "empty",
        "index_present": False,
        "settings_sha256": sha256_file(profile / "settings.json"),
        "librarian_apply_enabled": False,
    }
    (profile / "fixture_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def build_populated_legacy(profile: Path) -> dict[str, Any]:
    """Clearly versioned schema-27 fixture. Kit-side construction, not installed credit."""
    profile.mkdir(parents=True, exist_ok=True)
    write_settings(profile)
    write_synthetic_taxonomy(profile)
    corpus = profile / "output" / "C22-legacy-timed"
    corpus.mkdir(parents=True, exist_ok=True)
    markdown = corpus / "item.md"
    sidecar = corpus / "item.json"
    markdown.write_text(
        "C22 timed fixture item.\n\nQuoted line for citation.\n",
        encoding="utf-8")
    sidecar.write_text(json.dumps({
        "title": "C22 legacy timed item",
        "url": "http://127.0.0.1/c22-legacy-timed",
        "source_type": "episode",
        "platform": "podcast",
        "timing": {"start": 12.5, "end": 21.75},
        "fixture_version": LEGACY_FIXTURE_VERSION,
    }, indent=2) + "\n", encoding="utf-8")
    text_only = profile / "output" / "C22-legacy-text"
    text_only.mkdir(parents=True, exist_ok=True)
    (text_only / "item.md").write_text("C22 text-only fixture item.\n",
                                       encoding="utf-8")
    (text_only / "item.json").write_text(json.dumps({
        "title": "C22 legacy text-only item",
        "url": "http://127.0.0.1/c22-legacy-text",
        "source_type": "page",
        "platform": "web",
        "timing": None,
        "fixture_version": LEGACY_FIXTURE_VERSION,
    }, indent=2) + "\n", encoding="utf-8")
    index = profile / "index.db"
    conn = sqlite3.connect(str(index))
    conn.execute("PRAGMA foreign_keys=ON")
    applied = 0
    try:
        applied = apply_sql_migrations(conn, up_to=LEGACY_SCHEMA_VERSION)
    except sqlite3.Error:
        conn.close()
        if index.is_file():
            index.unlink()
        conn = sqlite3.connect(str(index))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
            (LEGACY_SCHEMA_VERSION, "2026-09-09T00:00:00Z"))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS yoinks ("
            "video_id TEXT PRIMARY KEY, slug TEXT, channel TEXT, title TEXT, "
            "topic TEXT, yoinked_at TEXT, corpus_path TEXT, sidecar_path TEXT)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS library_work ("
            "work_id TEXT PRIMARY KEY, run_id TEXT, video_id TEXT, "
            "packet_json TEXT, packet_hash TEXT, state TEXT, "
            "created_at TEXT, updated_at TEXT)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS library_runs ("
            "run_id TEXT PRIMARY KEY, version_id TEXT, manifest_hash TEXT, "
            "state TEXT, policy_json TEXT, created_at TEXT)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS library_meta ("
            "singleton INTEGER PRIMARY KEY, projection_revision INTEGER "
            "NOT NULL DEFAULT 0, last_operation_sequence INTEGER NOT NULL "
            "DEFAULT 0, recovery_state TEXT NOT NULL DEFAULT 'ready')")
        applied = LEGACY_SCHEMA_VERSION
    # Identities retained across upgrade/replay.
    _insert_legacy_rows(conn, profile, markdown, sidecar, text_only)
    conn.commit()
    conn.close()
    meta = {
        "kind": "populated_legacy",
        "fixture_version": LEGACY_FIXTURE_VERSION,
        "schema_version": applied,
        "target_schema_after_helper": CURRENT_SCHEMA_TARGET,
        "index_sha256": sha256_file(index),
        "markdown_sha256": sha256_file(markdown),
        "sidecar_sha256": sha256_file(sidecar),
        "timed_video_id": "c22legacytimed000",
        "text_video_id": "c22legacytext00000",
        "work_id": "wk_c22_legacy_1",
        "run_id": "run_c22_legacy_1",
        "librarian_apply_enabled": False,
        "construction": "kit-side SQL 0001-0027; not installed credit",
    }
    (profile / "fixture_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (profile / "legacy_fixture_version.json").write_text(
        json.dumps({"version": LEGACY_FIXTURE_VERSION,
                    "schema_version": applied}, indent=2) + "\n",
        encoding="utf-8")
    return meta


def _insert_legacy_rows(conn: sqlite3.Connection, profile: Path,
                        markdown: Path, sidecar: Path,
                        text_only: Path) -> None:
    def has_table(name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone()
        return row is not None

    if has_table("yoinks"):
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(yoinks)")
        }
        timed = {
            "video_id": "c22legacytimed000",
            "slug": "c22-legacy-timed",
            "channel": "c22-fixture",
            "title": "C22 legacy timed item",
            "topic": "c22",
            "yoinked_at": "2026-09-01T00:00:00Z",
            "corpus_path": str(markdown),
            "sidecar_path": str(sidecar),
        }
        text = {
            "video_id": "c22legacytext00000",
            "slug": "c22-legacy-text",
            "channel": "c22-fixture",
            "title": "C22 legacy text-only item",
            "topic": "c22",
            "yoinked_at": "2026-09-01T00:00:01Z",
            "corpus_path": str(text_only / "item.md"),
            "sidecar_path": str(text_only / "item.json"),
        }
        for row in (timed, text):
            usable = {k: v for k, v in row.items() if k in columns}
            placeholders = ",".join("?" for _ in usable)
            conn.execute(
                f"INSERT OR REPLACE INTO yoinks ({','.join(usable)}) "
                f"VALUES ({placeholders})",
                tuple(usable.values()),
            )
    if has_table("citations"):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(citations)")}
        citation = {
            "citation_id": 1,
            "video_id": "c22legacytimed000",
            "kind": "transcript_chunk",
            "seq": 1,
            "timestamp_start": 12.5,
            "timestamp_end": 21.75,
            "text": "Quoted line for citation.",
            "youtube_deep_link": "http://127.0.0.1/c22-legacy-timed",
            "source_url": "http://127.0.0.1/c22-legacy-timed",
            "source_deep_link": "http://127.0.0.1/c22-legacy-timed#t=12",
        }
        usable = {k: v for k, v in citation.items() if k in cols}
        if usable:
            try:
                conn.execute(
                    f"INSERT OR REPLACE INTO citations ({','.join(usable)}) "
                    f"VALUES ({','.join('?' for _ in usable)})",
                    tuple(usable.values()),
                )
            except sqlite3.IntegrityError:
                pass
    if has_table("library_meta"):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO library_meta(singleton) VALUES (1)")
        except sqlite3.IntegrityError:
            pass
    if has_table("library_runs"):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(library_runs)")}
        run = {
            "run_id": "run_c22_legacy_1",
            "version_id": "c22-synthetic-taxonomy-v1",
            "manifest_hash": sha256_bytes(b"c22-legacy-manifest"),
            "state": "review",
            "policy_json": "{}",
            "created_at": "2026-09-01T00:00:00Z",
        }
        usable = {k: v for k, v in run.items() if k in cols}
        if usable:
            try:
                conn.execute(
                    f"INSERT OR REPLACE INTO library_runs ({','.join(usable)}) "
                    f"VALUES ({','.join('?' for _ in usable)})",
                    tuple(usable.values()),
                )
            except sqlite3.IntegrityError:
                pass
    if has_table("library_work"):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(library_work)")}
        work = {
            "work_id": "wk_c22_legacy_1",
            "run_id": "run_c22_legacy_1",
            "video_id": "c22legacytimed000",
            "packet_json": "{}",
            "packet_hash": sha256_bytes(b"c22-legacy-packet"),
            "state": "ready",
            "created_at": "2026-09-01T00:00:00Z",
            "updated_at": "2026-09-01T00:00:00Z",
        }
        usable = {k: v for k, v in work.items() if k in cols}
        if usable:
            try:
                conn.execute(
                    f"INSERT OR REPLACE INTO library_work ({','.join(usable)}) "
                    f"VALUES ({','.join('?' for _ in usable)})",
                    tuple(usable.values()),
                )
            except sqlite3.IntegrityError:
                pass


def rewrite_embedded_paths(profile: Path, *, from_root: str,
                           to_root: str) -> int:
    """Point SQL/sidecar/embedded paths into the receipt profile."""
    changed = 0
    for path in profile.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt", ".sql"}:
            continue
        data = path.read_text(encoding="utf-8")
        if from_root in data:
            path.write_text(data.replace(from_root, to_root), encoding="utf-8")
            changed += 1
    index = profile / "index.db"
    if index.is_file():
        conn = sqlite3.connect(str(index))
        try:
            tables = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                cols = [row[1] for row in conn.execute(
                    f"PRAGMA table_info({table})")]
                text_cols = [c for c in cols if c.endswith("_path")
                             or c in {"corpus_path", "sidecar_path",
                                      "markdown_path", "audio_local_path"}]
                for col in text_cols:
                    rows = conn.execute(
                        f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL"
                    ).fetchall()
                    for rowid, value in rows:
                        if isinstance(value, str) and from_root in value:
                            conn.execute(
                                f"UPDATE {table} SET {col}=? WHERE rowid=?",
                                (value.replace(from_root, to_root), rowid))
                            changed += 1
            conn.commit()
        finally:
            conn.close()
    return changed
