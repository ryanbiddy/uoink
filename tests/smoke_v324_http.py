"""Offline HTTP smoke for the v3.2.4 routes: screenshot dedupe / suggest /
binary-by-index, and agent detect / connect.

Boots a throwaway ThreadingHTTPServer with server.Handler, monkeypatches the
index + served-file roots + agent spec to temp fixtures (no real DB, no
network, no real config touched), and drives the full path:
dispatch -> token gate -> path parse -> handler -> response.

Run: python tests/smoke_v324_http.py
"""
from __future__ import annotations

import json
import threading
import tempfile
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

PORT = 5193
BASE = f"http://127.0.0.1:{PORT}"


def _has_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _jpeg(path: Path, mode: str, seed: int) -> None:
    """A real JPEG with structure (so dedupe hashing + magic checks work)."""
    from PIL import Image
    w, h = 64, 48
    if mode == "h":
        data = bytes(((x * 4 + seed) % 256) for _y in range(h) for x in range(w))
    else:
        data = bytes(((y * 5 + seed) % 256) for y in range(h) for _x in range(w))
    Image.frombytes("L", (w, h), data).save(path, "JPEG")


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows

    def get_yoink(self, video_id):
        return self._rows.get(video_id)


def _req(method, path, *, token=True, body=None, raw=False):
    headers = {}
    data = None
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    if method == "POST":
        data = json.dumps(body or {}).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = r.read()
            if raw:
                return r.status, payload, r.headers.get("Content-Type")
            return r.status, json.loads(payload.decode())
    except urllib.error.HTTPError as e:
        if raw:
            return e.code, e.read(), None
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    if not _has_pillow():
        print("skip smoke_v324_http: Pillow not installed (dedupe/binary need it)")
        return 0
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        folder = base / "AI" / "clip"
        shots = folder / "screenshots"
        shots.mkdir(parents=True)
        # 3 near-duplicate frames + 1 distinct -> dedupe should drop some.
        _jpeg(shots / "shot_0001.jpg", "h", 0)
        _jpeg(shots / "shot_0002.jpg", "h", 1)
        _jpeg(shots / "shot_0003.jpg", "h", 2)
        _jpeg(shots / "shot_0004.jpg", "v", 0)
        corpus = folder / "clip.md"
        corpus.write_text("# x", encoding="utf-8")
        sidecar = folder / "clip.sidecar.json"
        sidecar.write_text(json.dumps({
            "url": "https://youtu.be/abc", "interval_seconds": 30,
            "screenshots": [
                {"timestamp": f"0:{i:02d}", "filename": f"shot_{i:04d}.jpg",
                 "path": f"screenshots/shot_{i:04d}.jpg"} for i in range(1, 5)],
        }), encoding="utf-8")

        rows = {"known": {"video_id": "known", "title": "Clip",
                          "corpus_path": str(corpus), "sidecar_path": str(sidecar)}}
        server._get_index = lambda: FakeIndex(rows)  # type: ignore
        # Allow serving the temp screenshots for the binary-by-index route.
        orig_roots = server._allowed_roots
        server._allowed_roots = lambda: list(orig_roots()) + [base.resolve()]
        # Point agent-connect at a temp config so we never touch a real one.
        cfg_dir = base / "ClientCfg"
        cfg_dir.mkdir()
        spec = {"name": "claude-desktop", "label": "Claude Desktop",
                "config_path": cfg_dir / "cfg.json", "markers": [cfg_dir]}
        orig_spec = server._agent_client_spec
        server._agent_client_spec = lambda n: spec if n == "claude-desktop" else None

        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            # dedupe
            status, payload = _req("GET", "/yoinks/known/screenshots?dedupe=true")
            _assert(status == 200 and payload.get("ok"), f"dedupe not ok: {status}")
            _assert(payload.get("deduped") is True, "deduped flag missing")
            _assert(payload["count"] < 4, f"dedupe should drop a frame: {payload['count']}")
            _assert(payload.get("dedupe_available") is True, "dedupe_available flag")
            deduped_count = payload["count"]

            # suggest thread on the exact same deduped set as the picker
            status, payload = _req(
                "GET",
                "/yoinks/known/screenshots/suggest"
                "?mode=thread&thread_size=3&dedupe=true")
            _assert(status == 200 and payload.get("ok"), f"suggest not ok: {status} {payload}")
            _assert(payload["mode"] == "thread", f"suggest thread: {payload}")
            _assert(payload["total_available"] == deduped_count,
                    f"suggest must use picker deduped set: {payload}")
            _assert(payload.get("deduped") is True,
                    "suggest response exposes dedupe mode")
            _assert(payload["count"] <= deduped_count,
                    "suggest cannot select outside deduped set")
            _assert(payload["strategy"] == "even_distribution", "thread strategy label")

            # suggest tweet
            status, payload = _req("GET", "/yoinks/known/screenshots/suggest?mode=tweet")
            _assert(status == 200 and payload["count"] == 1, f"suggest tweet: {payload}")

            # binary by index -> real JPEG bytes
            status, body, ctype = _req("GET", "/yoinks/known/screenshots/0.png", raw=True)
            _assert(status == 200, f"binary route status: {status}")
            _assert(body[:2] == b"\xff\xd8", "served bytes are a JPEG (SOI)")
            _assert(ctype and "image" in ctype, f"image content-type: {ctype}")

            # binary out of range -> 404 json
            status, payload = _req("GET", "/yoinks/known/screenshots/99.png")
            _assert(status == 404, f"out-of-range index should 404: {status}")

            # agents detect -- token gate
            status, _ = _req("GET", "/agents/detect", token=False)
            _assert(status == 403, f"detect without token should 403: {status}")
            status, payload = _req("GET", "/agents/detect")
            _assert(status == 200 and len(payload["agents"]) == 4, f"detect: {payload}")

            # agents connect happy + unknown
            status, payload = _req("POST", "/agents/connect/claude-desktop")
            _assert(status == 200 and payload.get("ok"), f"connect: {status} {payload}")
            _assert(payload["action"] in ("added", "updated"), "connect action")
            cfg = json.loads((cfg_dir / "cfg.json").read_text(encoding="utf-8"))
            _assert("uoink" in cfg["mcpServers"], "uoink entry written via HTTP")
            status, payload = _req("POST", "/agents/connect/bogus")
            _assert(status == 404, f"unknown client should 404: {status}")

            print("ok  dedupe / suggest(thread,tweet) / binary-by-index / "
                  "detect(403,200) / connect(200,404)")
            print("\nHTTP SMOKE v3.2.4 PASSED")
        finally:
            httpd.shutdown()
            server._allowed_roots = orig_roots
            server._agent_client_spec = orig_spec
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
