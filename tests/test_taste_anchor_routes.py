"""G-42 / E2E D3 -- the helper serves /taste/anchors and /resurface/today.

Run: python tests/test_taste_anchor_routes.py

The extension has called these since Sprint 3 (popup.js posts taste
judgments, setup.js lists/removes anchors, the popup's resurface card
reads today's picks). No helper build ever served them, so every popup
open logged 404 console errors and the extension quietly fell back to a
chrome.storage.local mirror that never left the browser.

Red on unpatched main: GET /taste/anchors -> 404, GET /resurface/today
-> 404, DELETE -> 501 (no do_DELETE at all).

Green with the fix:
  GET    /taste/anchors        {ok, anchors:{best, worst, admired_channels}}
  POST   /taste/anchors        {video_id, anchor_type: best|worst, title?}
  DELETE /taste/anchors/<id>   removes by video_id or channel name
  GET    /resurface/today      {ok, items:[...]} engagement-scored uoinks
                               idle >= 14 days, top 3 by value_score
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
import memory_layer  # noqa: E402
import server  # noqa: E402

PORT = 5205


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _request(method, path, body=None, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data, headers=headers,
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except json.JSONDecodeError:
            return e.code, {}


def _seed_yoink(idx, root, video_id, title, yoinked_at):
    folder = Path(root) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": "TestChannel",
        "title": title, "topic": "AI and ML", "hook_type": "curiosity_gap",
        "yoinked_at": yoinked_at,
        "corpus_path": str(folder / "corpus.md"),
        "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} transcript body")


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # ---- /taste/anchors ------------------------------------------
        # 1. Token gate.
        status, _ = _request("GET", "/taste/anchors", token=False)
        _assert(status == 403, f"GET without token must 403, got {status}")

        # 2. Route exists; empty store returns the full shape.
        status, res = _request("GET", "/taste/anchors")
        _assert(status == 200,
                f"GET /taste/anchors must exist (red on main: 404), "
                f"got {status}")
        _assert(res["ok"] and res["anchors"] == {
            "best": [], "worst": [], "admired_channels": []},
            f"empty anchors shape: {res}")
        print("ok  GET /taste/anchors -> empty shape, token-gated")

        # 3. POST best/worst; title backfills from the corpus.
        _seed_yoink(idx, tmp.name, "vidbest00001", "Great hook study",
                    "2026-06-01T09:00:00")
        status, res = _request("POST", "/taste/anchors", {
            "video_id": "vidbest00001", "anchor_type": "best", "title": ""})
        _assert(status == 200 and res["ok"], f"POST best: {status} {res}")
        _assert(res["anchors"]["best"] == [
            {"video_id": "vidbest00001", "title": "Great hook study"}],
            f"title backfilled from corpus: {res['anchors']}")
        status, res = _request("POST", "/taste/anchors", {
            "video_id": "vidworst0001", "anchor_type": "worst",
            "title": "Clickbait mess"})
        _assert(status == 200 and len(res["anchors"]["worst"]) == 1,
                f"POST worst: {res}")
        print("ok  POST /taste/anchors -> best + worst persisted")

        # 4. Re-judging a video moves it, never duplicates it.
        status, res = _request("POST", "/taste/anchors", {
            "video_id": "vidbest00001", "anchor_type": "worst"})
        _assert(res["anchors"]["best"] == [], f"moved out of best: {res}")
        _assert(len(res["anchors"]["worst"]) == 2, f"moved into worst: {res}")
        print("ok  re-judging moves an anchor between lists")

        # 5. Validation.
        status, _ = _request("POST", "/taste/anchors", {
            "video_id": "x", "anchor_type": "meh"})
        _assert(status == 400, f"bad anchor_type must 400, got {status}")
        status, _ = _request("POST", "/taste/anchors", {
            "anchor_type": "best"})
        _assert(status == 400, f"missing video_id must 400, got {status}")
        print("ok  POST validation -> 400s")

        # 6. DELETE by video_id (red on main: no do_DELETE, 501).
        status, res = _request("DELETE", "/taste/anchors/vidworst0001")
        _assert(status == 200 and res.get("removed") is True,
                f"DELETE must work (red on main: 501), got {status} {res}")
        status, res = _request("GET", "/taste/anchors")
        _assert([a["video_id"] for a in res["anchors"]["worst"]]
                == ["vidbest00001"], f"row removed: {res['anchors']}")
        status, _ = _request("DELETE", "/taste/anchors/vidworst0001")
        _assert(status == 404, f"missing anchor must 404, got {status}")
        status, _ = _request("DELETE", "/taste/anchors/vidbest00001",
                             token=False)
        _assert(status == 403, f"DELETE without token must 403, got {status}")
        print("ok  DELETE /taste/anchors/<id> -> removes, 404s, token-gated")

        # 7. Admired channels stored as plain strings are removable too.
        memory_layer._write_taste_anchors(idx, {
            **memory_layer.get_taste_anchors(idx),
            "admired_channels": ["ThursdAI"]})
        status, _ = _request("DELETE", "/taste/anchors/ThursdAI")
        _assert(status == 200, f"channel removal: {status}")
        print("ok  admired channel removal by name")

        # ---- /resurface/today ----------------------------------------
        status, _ = _request("GET", "/resurface/today", token=False)
        _assert(status == 403, f"today without token must 403, got {status}")
        status, res = _request("GET", "/resurface/today")
        _assert(status == 200,
                f"GET /resurface/today must exist (red on main: 404), "
                f"got {status}")
        _assert(res["ok"] and res["items"] == [],
                f"no engagement -> empty items: {res}")

        # Idle scored uoink appears; fresh one does not; ghosts never do.
        _seed_yoink(idx, tmp.name, "vidfresh0001", "Fresh video",
                    "2026-07-01T09:00:00")
        idx.log_engagement("vidbest00001", "cite", "popup",
                           ts_utc="2026-06-01T10:00:00")   # idle > 14 days
        idx.log_engagement("vidfresh0001", "opened", "popup",
                           ts_utc="2026-07-04T06:00:00")   # fresh
        idx.log_engagement("vidgoneeeee1", "cite", "popup",
                           ts_utc="2026-05-01T10:00:00")   # not in corpus
        status, res = _request("GET", "/resurface/today")
        ids = [i["video_id"] for i in res["items"]]
        _assert(ids == ["vidbest00001"],
                f"only idle, corpus-backed uoinks qualify: {ids}")
        item = res["items"][0]
        _assert(item["title"] == "Great hook study", f"title: {item}")
        _assert(item["folder"] and item["folder"].endswith("vidbest00001"),
                f"folder for click-to-open: {item}")
        _assert((item["value_score"] or 0) > 0, f"score: {item}")
        print("ok  GET /resurface/today -> idle scored uoinks only")

        print("\nall green")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
