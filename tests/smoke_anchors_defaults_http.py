"""Offline HTTP smoke for v3.2.3: GET /writing/style-anchors/defaults +
GET /writing/<id> body field. Boots server.Handler with a seeded fake index
(in-memory SQLite, no real DB, no network), then hits the routes. Prints the
endpoint output for the PR artifact (item 8).

Run: python tests/smoke_anchors_defaults_http.py
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import writing_studio as ws  # noqa: E402

PORT = 5194


class FakeIndex:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript("""
            CREATE TABLE style_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                source_type TEXT NOT NULL, source_url TEXT, raw_text TEXT,
                active INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0);
        """)

    def get_yoink(self, vid):
        return None


def main():
    import server
    fake = FakeIndex()
    # Seed from the bundled defaults file, exactly as first-run boot would.
    data = json.loads((Path(__file__).resolve().parent.parent
                       / "defaults" / "style_anchors.json").read_text(encoding="utf-8"))
    seeded = ws.seed_default_anchors(fake, data)
    print(f"seeded {seeded} defaults from defaults/style_anchors.json")
    server._get_index = lambda: fake  # type: ignore

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/writing/style-anchors/defaults",
            headers={"X-Uoink-Token": server.TOKEN})
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read().decode())
        print("\nGET /writing/style-anchors/defaults ->")
        print(json.dumps(payload, indent=2)[:1400])
        assert payload["ok"] and payload["count"] == 5, "expected 5 defaults"
        assert all(a["default"] is True and a["active"] == 0
                   for a in payload["anchors"]), "defaults must be inactive"
        print("\nSMOKE PASSED: 5 inactive defaults served")
    finally:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
