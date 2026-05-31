"""Offline HTTP smoke test for the D-20 screenshot + re-yoink routes.

Boots a throwaway ThreadingHTTPServer with server.Handler on a test port,
monkeypatches server._get_index to a fake index (no real DB, no network),
and exercises the full request path: dispatch -> token gate -> path parse ->
handler -> JSON response. Re-yoink is tested only on the no-source-link
branch so it never shells out to yt-dlp.

Run: python tests/smoke_screenshots_http.py
"""
from __future__ import annotations

import json
import struct
import threading
import tempfile
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

PORT = 5191
BASE = f"http://127.0.0.1:{PORT}"


def _minimal_jpeg(path: Path, w: int, h: int) -> None:
    soi = b"\xff\xd8"
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    body = bytes([8]) + struct.pack(">HH", h, w) + bytes([1, 1, 0x11, 0])
    sof0 = b"\xff\xc0" + struct.pack(">H", len(body) + 2) + body
    path.write_bytes(soi + app0 + sof0 + b"\xff\xd9")


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows

    def get_yoink(self, video_id):
        return self._rows.get(video_id)


def _req(method, path, *, token=True, body=None):
    data = None
    headers = {}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    if method == "POST":
        data = json.dumps(body or {}).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        folder = base / "AI" / "clip"
        shots = folder / "screenshots"
        shots.mkdir(parents=True)
        _minimal_jpeg(shots / "shot_0001.jpg", 1280, 720)
        corpus = folder / "clip.md"
        corpus.write_text("# x", encoding="utf-8")
        sidecar = folder / "clip.sidecar.json"
        sidecar.write_text(json.dumps({
            "url": "https://youtu.be/abc", "interval_seconds": 30,
            "screenshots": [{"timestamp": "0:00", "filename": "shot_0001.jpg",
                             "path": "screenshots/shot_0001.jpg"}],
        }), encoding="utf-8")

        rows = {
            "known": {"video_id": "known", "title": "Clip",
                      "corpus_path": str(corpus), "sidecar_path": str(sidecar)},
            "nourl": {"video_id": "nourl", "title": "Manual",
                      "corpus_path": str(corpus),
                      "sidecar_path": str(base / "missing.json")},
        }
        server._get_index = lambda: FakeIndex(rows)  # type: ignore

        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            # 1. no token -> 403
            status, _ = _req("GET", "/yoinks/known/screenshots", token=False)
            _assert(status == 403, f"expected 403 without token, got {status}")

            # 2. known id -> 200 with one screenshot
            status, payload = _req("GET", "/yoinks/known/screenshots")
            _assert(status == 200 and payload.get("ok"), f"known GET not ok: {status} {payload}")
            _assert(payload["count"] == 1, f"expected 1 screenshot, got {payload['count']}")
            _assert(payload["screenshots"][0]["width"] == 1280, "dims missing in HTTP payload")
            _assert(payload["screenshots"][0]["file_url"].startswith("/file?path="), "file_url shape")

            # 3. unknown id -> 404
            status, payload = _req("GET", "/yoinks/ghost/screenshots")
            _assert(status == 404 and not payload.get("ok"), f"unknown GET should 404: {status}")

            # 4. reyoink unknown -> 404
            status, payload = _req("POST", "/yoinks/ghost/reyoink")
            _assert(status == 404, f"reyoink unknown should 404: {status}")

            # 5. reyoink with no saved source link -> 400 (never shells out)
            status, payload = _req("POST", "/yoinks/nourl/reyoink")
            _assert(status == 400 and not payload.get("ok"), f"reyoink no-url should 400: {status} {payload}")
            _assert("source link" in payload.get("error", ""), "expected source-link copy")

            print("ok  403 no-token / 200 known / 404 unknown / 404+400 reyoink branches")
            print("\nHTTP SMOKE PASSED")
        finally:
            httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
