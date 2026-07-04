"""G-41 / E2E D2 -- GET /resurface serves the For You payload.

Run: python tests/test_resurface_route.py

The dashboard's loadForYou() has always called authFetch("/resurface");
before this fix no such route existed, so every For You load logged a
silent 404 (twice) and fell back to a client-side approximation computed
from the loaded Library page only.

Red on unpatched main: GET /resurface -> 404 and the first assert fails.

Green with the fix: the route returns {ok, resurface} where resurface
carries the exact keys renderForYou() reads:

  worth_revisiting  engagement-scored uoinks idle >= 14 days, or the
                    oldest saved uoinks when no engagement data exists
  connections       [{topic, a, b, reason}] pairs of same-topic uoinks
  corpus_gaps       [{topic, count}] topics with <= 2 saved uoinks
  anchors           top engagement-scored uoinks
  source            "engagement memory" | "local library"

Also asserts the route is token-gated (403 without the header) and that
an empty corpus returns an empty-but-valid shape, not an error.
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

PORT = 5203


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _seed_yoink(idx, root, video_id, title, topic, yoinked_at):
    folder = Path(root) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": "TestChannel",
        "title": title, "topic": topic, "hook_type": "curiosity_gap",
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
        # 1. Route exists and is token-gated.
        status, _res = _get("/resurface", token=False)
        _assert(status == 403, f"no token must 403, got {status}")
        print("ok  /resurface without token -> 403")

        # 2. Empty corpus -> empty-but-valid payload, not an error.
        status, res = _get("/resurface")
        _assert(status == 200,
                f"/resurface must exist (red on main: 404), got {status}")
        _assert(res.get("ok") is True, f"ok flag: {res}")
        payload = res.get("resurface") or {}
        for key in ("worth_revisiting", "connections", "corpus_gaps",
                    "anchors"):
            _assert(payload.get(key) == [],
                    f"empty corpus: {key} must be [], got {payload.get(key)}")
        print("ok  empty corpus -> empty-but-valid payload")

        # Seed: 3 uoinks sharing a topic, 1 uoink alone on another topic.
        _seed_yoink(idx, tmp.name, "vidaaaaaaaa", "Old deep dive",
                    "AI and ML", "2026-01-05T09:00:00")
        _seed_yoink(idx, tmp.name, "vidbbbbbbbb", "Newer take",
                    "AI and ML", "2026-06-20T09:00:00")
        _seed_yoink(idx, tmp.name, "vidcccccccc", "Newest take",
                    "AI and ML", "2026-07-01T09:00:00")
        _seed_yoink(idx, tmp.name, "viddddddddd", "Lone career video",
                    "Job Hunt", "2026-03-10T09:00:00")

        # 3. Corpus without engagement -> local library source, oldest
        #    saves resurface first.
        status, res = _get("/resurface")
        payload = res["resurface"]
        _assert(payload["source"] == "local library",
                f"no-engagement source: {payload['source']}")
        worth_ids = [r["video_id"] for r in payload["worth_revisiting"]]
        _assert(worth_ids[0] == "vidaaaaaaaa",
                f"oldest save resurfaces first, got {worth_ids}")
        _assert(len(worth_ids) == 3, f"worth capped at 3: {worth_ids}")
        topics = [c["topic"] for c in payload["connections"]]
        _assert(topics == ["AI and ML"], f"connections topics: {topics}")
        pair = {payload["connections"][0]["a"]["video_id"],
                payload["connections"][0]["b"]["video_id"]}
        _assert(pair == {"vidbbbbbbbb", "vidcccccccc"},
                f"pair must be the 2 most recent same-topic rows: {pair}")
        _assert(payload["connections"][0]["reason"],
                "connection carries a reason")
        gap_topics = {g["topic"]: g["count"] for g in payload["corpus_gaps"]}
        _assert(gap_topics == {"Job Hunt": 1},
                f"gaps must be low-coverage topics only: {gap_topics}")
        _assert(payload["anchors"] == [], "no engagement -> no anchors")
        print("ok  corpus without engagement -> local library payload")

        # 4. With engagement events: idle high-value uoinks lead worth_
        #    revisiting; fresh ones appear in anchors only.
        idx.log_engagement("vidaaaaaaaa", "cite", "dashboard",
                           ts_utc="2026-06-01T10:00:00")  # idle > 14 days
        idx.log_engagement("vidcccccccc", "opened", "dashboard",
                           ts_utc="2026-07-04T08:00:00")  # fresh
        status, res = _get("/resurface")
        payload = res["resurface"]
        _assert(payload["source"] == "engagement memory",
                f"engagement source: {payload['source']}")
        worth_ids = [r["video_id"] for r in payload["worth_revisiting"]]
        _assert(worth_ids == ["vidaaaaaaaa"],
                f"only the idle scored uoink resurfaces: {worth_ids}")
        worth = payload["worth_revisiting"][0]
        _assert(worth.get("title") == "Old deep dive",
                f"merged corpus metadata: {worth.get('title')}")
        _assert((worth.get("value_score") or 0) > 0,
                f"merged value_score: {worth.get('value_score')}")
        anchor_ids = {r["video_id"] for r in payload["anchors"]}
        _assert(anchor_ids == {"vidaaaaaaaa", "vidcccccccc"},
                f"anchors are the scored uoinks: {anchor_ids}")
        print("ok  engagement events -> idle uoinks resurface, anchors fill")

        # 5. Engagement rows for deleted uoinks never produce ghost cards.
        idx.log_engagement("vidgoneeeee", "cite", "dashboard",
                           ts_utc="2026-05-01T10:00:00")
        status, res = _get("/resurface")
        payload = res["resurface"]
        all_ids = {r["video_id"] for r in
                   payload["worth_revisiting"] + payload["anchors"]}
        _assert("vidgoneeeee" not in all_ids,
                f"ghost row leaked into the payload: {all_ids}")
        print("ok  engagement for a missing uoink -> no ghost card")

        print("\nall green")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
