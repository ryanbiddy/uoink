"""Synthetic installed helper for labeled C22 instrument checks.

Not installed credit. Accepts the declared isolation flags, refuses 5179,
serves the production HTTP paths the kit drives, and keeps a sqlite ledger
so scenarios and the evidence collector can run without Inno or server.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FORBIDDEN_PORT = 5179


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-profile", required=True)
    parser.add_argument("--isolated-port", required=True, type=int)
    return parser.parse_args(argv)


def fail_closed(profile: Path, port: int) -> None:
    if not profile.is_absolute():
        raise SystemExit("stub helper: isolated-profile must be absolute")
    if port == FORBIDDEN_PORT:
        raise SystemExit("stub helper: port 5179 is forbidden")
    if port < 1024 or port > 65535:
        raise SystemExit("stub helper: port out of range")
    live = (os.environ.get("C22_FORBIDDEN_LIVE") or "").replace("\\", "/").lower()
    if live and live in str(profile).replace("\\", "/").lower():
        raise SystemExit("stub helper: profile collides with live index")


def open_db(profile: Path) -> sqlite3.Connection:
    profile.mkdir(parents=True, exist_ok=True)
    path = profile / "index.db"
    existed = path.is_file()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    current = conn.execute(
        "SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
    current = int(current) if current is not None else 0
    if current == 0 and not existed:
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (30, ?)",
            (_now(),))
        current = 30
        conn.execute(
            "CREATE TABLE IF NOT EXISTS c22_migrations("
            "from_version INTEGER, to_version INTEGER, applied_at TEXT)")
        conn.execute(
            "INSERT INTO c22_migrations VALUES (0, 30, ?)", (_now(),))
    elif 0 < current < 30:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS c22_migrations("
            "from_version INTEGER, to_version INTEGER, applied_at TEXT)")
        conn.execute(
            "INSERT INTO c22_migrations VALUES (?, 30, ?)", (current, _now()))
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version, applied_at) "
            "VALUES (30, ?)", (_now(),))
        current = 30
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_subscriptions (
            source_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            url TEXT,
            consent_state TEXT NOT NULL DEFAULT 'off',
            revision INTEGER NOT NULL DEFAULT 0,
            consent_epoch INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS source_capture_starts (
            start_id TEXT PRIMARY KEY,
            source_id TEXT,
            capture_key TEXT,
            state TEXT,
            charged INTEGER NOT NULL DEFAULT 0,
            origin TEXT,
            item_id TEXT
        );
        CREATE TABLE IF NOT EXISTS source_items (
            item_id TEXT PRIMARY KEY,
            source_id TEXT,
            entry_id TEXT,
            capture_key TEXT,
            outcome TEXT
        );
        CREATE TABLE IF NOT EXISTS source_consent_receipts (
            operation_key TEXT PRIMARY KEY,
            source_id TEXT,
            old_state TEXT,
            new_state TEXT,
            after_revision INTEGER
        );
        CREATE TABLE IF NOT EXISTS yoinks (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            corpus_path TEXT,
            sidecar_path TEXT
        );
        CREATE TABLE IF NOT EXISTS library_work (
            work_id TEXT PRIMARY KEY,
            run_id TEXT,
            video_id TEXT,
            state TEXT
        );
        CREATE TABLE IF NOT EXISTS library_runs (
            run_id TEXT PRIMARY KEY,
            state TEXT
        );
        CREATE TABLE IF NOT EXISTS library_manifest (
            run_id TEXT,
            video_id TEXT,
            disposition TEXT
        );
        CREATE TABLE IF NOT EXISTS library_attempts (
            attempt_token TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS item_shelves (
            video_id TEXT,
            shelf_id TEXT
        );
        CREATE TABLE IF NOT EXISTS c22_children (
            start_id TEXT,
            pid INTEGER,
            created_ms INTEGER,
            unresolved_launch INTEGER NOT NULL DEFAULT 0
        );
        """)
    conn.commit()
    return conn


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class State:
    def __init__(self, profile: Path, port: int):
        self.profile = profile
        self.port = port
        self.conn = open_db(profile)
        self.token = "c22-synthetic-token"
        (profile / "token.txt").write_text(self.token, encoding="utf-8")
        self.identity = {
            "pid": os.getpid(),
            "created_ms": int(time.time() * 1000),
        }
        (profile / "helper_identity.json").write_text(
            json.dumps(self.identity, indent=2) + "\n", encoding="utf-8")
        self.httpd: ThreadingHTTPServer | None = None
        self.children: list = []
        self.lock = threading.Lock()
        self.inject = os.environ.get("C22_INJECT") or ""
        self.sources: dict[str, dict] = {}

    def snapshot(self) -> dict:
        cur = self.conn
        def rows(sql: str) -> list[dict]:
            return [dict(r) for r in cur.execute(sql)]
        schema = cur.execute(
            "SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
        return {
            "schema_version": schema,
            "sources": rows("SELECT * FROM source_subscriptions"),
            "starts": rows("SELECT * FROM source_capture_starts"),
            "items": rows("SELECT * FROM source_items"),
            "receipts": rows("SELECT * FROM source_consent_receipts"),
            "yoinks": rows("SELECT * FROM yoinks"),
            "work": rows("SELECT * FROM library_work"),
            "children": rows("SELECT * FROM c22_children"),
            "identity": self.identity,
            "port": self.port,
            "profile": str(self.profile),
            "synthetic": True,
        }


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self) -> bool:
            token = self.headers.get("X-Uoink-Token")
            if token != state.token:
                self._json(403, {"ok": False, "error": "missing or invalid token"})
                return False
            return True

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/health", "/ping"):
                return self._json(200, {"ok": True, "synthetic": True,
                                        "port": state.port})
            if parsed.path == "/dashboard":
                body = b"<html><body>C22 synthetic dashboard</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/token":
                return self._json(200, {"ok": True, "token": state.token})
            if not self._auth():
                return
            if parsed.path == "/sources":
                rows = [dict(r) for r in state.conn.execute(
                    "SELECT * FROM source_subscriptions")]
                return self._json(200, {"ok": True, "sources": rows})
            if parsed.path == "/sources/status":
                qs = urllib.parse.parse_qs(parsed.query)
                sid = (qs.get("source_id") or [None])[0]
                snap = state.snapshot()
                items = [i for i in snap["items"]
                         if sid is None or i["source_id"] == sid]
                starts = [s for s in snap["starts"]
                          if sid is None or s["source_id"] == sid]
                source = next((s for s in snap["sources"]
                               if sid is None or s["source_id"] == sid), None)
                return self._json(200, {
                    "ok": True, "source": source, "items": items,
                    "starts": starts, "snapshot": snap,
                })
            if parsed.path == "/c22/snapshot":
                return self._json(200, {"ok": True, **state.snapshot()})
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                body = {}
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/helper/quit":
                if not self._auth():
                    return
                self._json(200, {"ok": True, "stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if not self._auth():
                return
            if parsed.path == "/sources":
                return self._register(body)
            if parsed.path == "/sources/consent-intent":
                return self._json(200, {
                    "ok": True, "user_intent_token": "c22-intent",
                })
            if parsed.path == "/sources/consent":
                return self._consent(body)
            if parsed.path == "/extract":
                return self._extract(body)
            if parsed.path == "/sources/refresh":
                return self._refresh(body)
            self._json(404, {"ok": False, "error": "not found"})

        def _register(self, body: dict):
            url = body.get("url") or "http://127.0.0.1/feed.xml"
            kind = body.get("kind") or "podcast_rss"
            sid = "src_" + str(abs(hash(url)) % 10**12)
            with state.lock:
                existing = state.conn.execute(
                    "SELECT * FROM source_subscriptions WHERE source_id=?",
                    (sid,)).fetchone()
                if existing is None:
                    state.conn.execute(
                        "INSERT INTO source_subscriptions"
                        "(source_id, kind, url, consent_state, revision, "
                        "consent_epoch) VALUES (?,?,?,?,0,0)",
                        (sid, kind, url, "off"))
                    state.conn.commit()
                row = dict(state.conn.execute(
                    "SELECT * FROM source_subscriptions WHERE source_id=?",
                    (sid,)).fetchone())
            return self._json(200, {"ok": True, "source": row})

        def _consent(self, body: dict):
            sid = body.get("source_id")
            new_state = body.get("consent_state") or "on"
            with state.lock:
                row = state.conn.execute(
                    "SELECT * FROM source_subscriptions WHERE source_id=?",
                    (sid,)).fetchone()
                if row is None:
                    return self._json(404, {"ok": False, "error": "missing source"})
                row = dict(row)
                revision = int(row["revision"]) + (
                    0 if row["consent_state"] == new_state else 1)
                epoch = int(row["consent_epoch"]) + (
                    1 if new_state == "on" and row["consent_state"] != "on" else 0)
                state.conn.execute(
                    "UPDATE source_subscriptions SET consent_state=?, revision=?, "
                    "consent_epoch=? WHERE source_id=?",
                    (new_state, revision, epoch, sid))
                key = body.get("operation_key") or f"op-{revision}"
                state.conn.execute(
                    "INSERT OR REPLACE INTO source_consent_receipts"
                    "(operation_key, source_id, old_state, new_state, "
                    "after_revision) VALUES (?,?,?,?,?)",
                    (key, sid, row["consent_state"], new_state, revision))
                state.conn.commit()
                updated = dict(state.conn.execute(
                    "SELECT * FROM source_subscriptions WHERE source_id=?",
                    (sid,)).fetchone())
            if new_state == "on":
                self._standing_capture(sid, url=updated.get("url"))
            return self._json(200, {"ok": True, "source": updated})

        def _extract(self, body: dict):
            url = body.get("url") or ""
            source_id = body.get("source_id")
            origin = "one_off" if body.get("one_off") or not source_id else "manual"
            capture_key = "podcast:" + str(abs(hash(url)) % 10**12)
            with state.lock:
                existing = state.conn.execute(
                    "SELECT * FROM source_capture_starts WHERE capture_key=?",
                    (capture_key,)).fetchone()
                if existing:
                    row = dict(existing)
                    return self._json(200, {
                        "ok": True, "deduped": True, "start": row,
                        "publication": "existing",
                    })
                start_id = "st_" + capture_key[-10:]
                item_id = "si_" + capture_key[-10:]
                charged = 0 if origin == "one_off" else 0
                if origin == "manual":
                    standing = state.conn.execute(
                        "SELECT consent_state FROM source_subscriptions "
                        "WHERE source_id=?", (source_id,)).fetchone()
                    if standing and standing["consent_state"] == "on":
                        # manual after standing: no second charge
                        charged = 0
                        origin = "manual_after_standing"
                    else:
                        origin = "manual"
                state.conn.execute(
                    "INSERT INTO source_capture_starts"
                    "(start_id, source_id, capture_key, state, charged, origin, "
                    "item_id) VALUES (?,?,?,?,?,?,?)",
                    (start_id, source_id, capture_key, "succeeded", charged,
                     origin, item_id))
                state.conn.execute(
                    "INSERT OR REPLACE INTO source_items"
                    "(item_id, source_id, entry_id, capture_key, outcome) "
                    "VALUES (?,?,?,?,?)",
                    (item_id, source_id, "c22-entry-1", capture_key, "committed"))
                video_id = "vid_" + capture_key[-8:]
                corpus = str(state.profile / "output" / video_id / "item.md")
                Path(corpus).parent.mkdir(parents=True, exist_ok=True)
                Path(corpus).write_text("C22 synthetic publication\n",
                                        encoding="utf-8")
                state.conn.execute(
                    "INSERT OR REPLACE INTO yoinks(video_id, title, corpus_path, "
                    "sidecar_path) VALUES (?,?,?,?)",
                    (video_id, "C22 capture", corpus, corpus.replace(".md", ".json")))
                if os.environ.get("C22_ENQUEUE_CLASSIFICATION") == "1":
                    state.conn.execute(
                        "INSERT INTO library_work(work_id, run_id, video_id, state) "
                        "VALUES (?,?,?,?)",
                        ("wk_" + video_id, "run_" + video_id, video_id, "ready"))
                self._maybe_child(start_id)
                state.conn.commit()
            return self._json(200, {
                "ok": True, "deduped": False,
                "start": {"start_id": start_id, "capture_key": capture_key,
                          "origin": origin, "charged": charged,
                          "state": "succeeded"},
                "video_id": video_id,
                "publication": "created",
            })

        def _standing_capture(self, source_id: str, url: str | None = None):
            body = {"url": url or f"standing:{source_id}", "source_id": source_id}
            # Standing capture charges once.
            capture_key = "podcast:" + str(abs(hash(body["url"])) % 10**12)
            existing = state.conn.execute(
                "SELECT * FROM source_capture_starts WHERE capture_key=?",
                (capture_key,)).fetchone()
            if existing:
                return
            start_id = "st_stand_" + source_id[-6:]
            item_id = "si_stand_" + source_id[-6:]
            video_id = "vid_stand_" + source_id[-6:]
            state.conn.execute(
                "INSERT INTO source_capture_starts"
                "(start_id, source_id, capture_key, state, charged, origin, "
                "item_id) VALUES (?,?,?,?,1,'standing',?)",
                (start_id, source_id, capture_key, "succeeded", item_id))
            state.conn.execute(
                "INSERT INTO source_items"
                "(item_id, source_id, entry_id, capture_key, outcome) "
                "VALUES (?,?,?,?,?)",
                (item_id, source_id, "c22-entry-1", capture_key, "committed"))
            corpus = str(state.profile / "output" / video_id / "item.md")
            Path(corpus).parent.mkdir(parents=True, exist_ok=True)
            Path(corpus).write_text("C22 standing publication\n", encoding="utf-8")
            state.conn.execute(
                "INSERT OR REPLACE INTO yoinks(video_id, title, corpus_path, "
                "sidecar_path) VALUES (?,?,?,?)",
                (video_id, "C22 standing", corpus, corpus.replace(".md", ".json")))
            self._maybe_child(start_id)
            state.conn.commit()

        def _refresh(self, body: dict):
            return self._json(200, {"ok": True, "refreshed": True})

        def _maybe_child(self, start_id: str):
            inject = state.inject
            if inject == "launch_interrupt":
                state.conn.execute(
                    "INSERT INTO c22_children(start_id, pid, created_ms, "
                    "unresolved_launch) VALUES (?,?,?,1)",
                    (start_id, 0, int(time.time() * 1000)))
                return
            if inject == "registration_failure":
                sleeper = _spawn_sleeper()
                state.children.append(sleeper)
                state.conn.execute(
                    "INSERT INTO c22_children(start_id, pid, created_ms, "
                    "unresolved_launch) VALUES (?,?,?,1)",
                    (start_id, sleeper.pid, int(time.time() * 1000)))
                return
            if inject == "spawn_child" or os.environ.get("C22_SPAWN_CHILD") == "1":
                sleeper = _spawn_sleeper()
                state.children.append(sleeper)
                state.conn.execute(
                    "INSERT INTO c22_children(start_id, pid, created_ms, "
                    "unresolved_launch) VALUES (?,?,?,0)",
                    (start_id, sleeper.pid, int(time.time() * 1000)))

        def log_message(self, *args):
            return

    return Handler


def _spawn_sleeper():
    import subprocess
    seconds = os.environ.get("C22_SLEEPER_SECONDS") or "8"
    return subprocess.Popen(
        [sys.executable, "-B", "-c", f"import time; time.sleep({seconds})"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    profile = Path(args.isolated_profile)
    port = int(args.isolated_port)
    fail_closed(profile, port)
    state = State(profile, port)
    class ReuseServer(ThreadingHTTPServer):
        allow_reuse_address = True

    httpd = ReuseServer(("127.0.0.1", port), make_handler(state))
    if httpd.server_address[1] == FORBIDDEN_PORT:
        httpd.server_close()
        raise SystemExit("stub helper bound 5179")
    state.httpd = httpd
    pid_file = Path.cwd() / "server.pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    try:
        httpd.serve_forever()
    finally:
        for child in state.children:
            if child.poll() is None:
                child.kill()
        httpd.server_close()
        state.conn.close()
        pid_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
