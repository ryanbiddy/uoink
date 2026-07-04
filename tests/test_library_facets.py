"""G-12 -- corpus-wide Library facets endpoint (/library/facets).

Run: python tests/test_library_facets.py

Boots server.Handler against a real index.Index and asserts the endpoint
returns every distinct facet value present in the corpus (QA #14: the UI
listed 14 of 21 channels because it derived filters from loaded cards), with
a count and a human `label` (QA #15: screen_recording -> "Screen recording"),
plus the yoinked_at date bounds.

Red before the fix: there was no /library/facets route (404).
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402

PORT = 5199


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _seed(idx, video_id, channel, fmt, when):
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel,
        "title": f"{channel} clip", "topic": "ai",
        "hook_type": "curiosity_gap", "yoinked_at": when,
        "corpus_path": "", "sidecar_path": "", "source_type": "youtube",
    })
    idx.set_facets(video_id, format=fmt, length_bucket="long")


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Empty corpus: endpoint answers cleanly with empty facets + null bounds.
        status, res = _get("/library/facets")
        _assert(status == 200 and res["ok"], f"empty ok: {status} {res}")
        _assert(res["facets"]["channel"] == [], "empty corpus has no channels")
        _assert(res["date_bounds"] == {"min": None, "max": None},
                f"empty bounds are null: {res['date_bounds']}")
        print("ok  empty corpus -> clean empty facets")

        # Seed a corpus where one channel dominates (so counts/order matter)
        # and formats include a raw enum that needs humanizing.
        _seed(idx, "vid00000001", "Karpathy", "talking_head", "2026-05-01T10:00:00")
        _seed(idx, "vid00000002", "Karpathy", "screen_recording", "2026-06-01T10:00:00")
        _seed(idx, "vid00000003", "Karpathy", "talking_head", "2026-06-15T10:00:00")
        _seed(idx, "vid00000004", "Fireship", "screen_recording", "2026-04-01T10:00:00")

        status, res = _get("/library/facets")
        _assert(status == 200 and res["ok"], f"populated ok: {res}")
        channels = res["facets"]["channel"]
        _assert({c["value"] for c in channels} == {"Karpathy", "Fireship"},
                f"every corpus channel present: {channels}")
        kar = next(c for c in channels if c["value"] == "Karpathy")
        _assert(kar["count"] == 3, f"channel counts are corpus-wide: {kar}")
        # Count-desc ordering: Karpathy (3) before Fireship (1).
        _assert(channels[0]["value"] == "Karpathy",
                f"facets ordered by count desc: {channels}")
        print("ok  channels: corpus-wide values with counts, count-desc order")

        formats = {f["value"]: f["label"] for f in res["facets"]["format"]}
        _assert(formats.get("screen_recording") == "Screen recording",
                f"raw enum humanized: {formats}")
        _assert(formats.get("talking_head") == "Talking head",
                f"talking_head humanized: {formats}")
        print("ok  formats: raw enums carry human labels")

        bounds = res["date_bounds"]
        _assert(bounds["min"].startswith("2026-04-01"), f"min bound: {bounds}")
        _assert(bounds["max"].startswith("2026-06-15"), f"max bound: {bounds}")
        print("ok  date_bounds span the whole corpus")

        # Token required.
        status, _ = _get("/library/facets", token=False)
        _assert(status in (401, 403), f"token required: {status}")
        print("ok  token required on /library/facets")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("\nALL LIBRARY FACETS TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
