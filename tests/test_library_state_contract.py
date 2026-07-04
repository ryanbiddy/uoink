"""G-11 / G-12 (date half) -- the /memory/search Library state contract.

Run: python tests/test_library_state_contract.py

Boots server.Handler against a real index.Index on a temp file and asserts
the endpoint hands the frontend four distinguishable states so it never has
to guess (and never falls back to job records dressed as uoinks, QA #12):

  matches       total>0
  no_matches    corpus has uoinks, this query matched 0
  empty_corpus  nothing saved yet
  unavailable   backend/index error -> 503, state:"unavailable"

Plus G-12/QA #13: a from>to date range is rejected 400 server-side instead
of falling through to a silent empty result.

Red before the fix: the endpoint returned only {ok,total,results} with no
state field, so no_matches and empty_corpus were both just total:0, and an
index error was a bare 500 the frontend treated as "show job records."
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

PORT = 5198


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        headers={"X-Uoink-Token": server.TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _seed_yoink(idx, video_id, title, channel):
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel,
        "title": title, "topic": "ai", "hook_type": "curiosity_gap",
        "yoinked_at": "2026-06-01T12:00:00", "corpus_path": "",
        "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} {channel} transcript body")


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # 1. Empty corpus -- nothing saved yet.
        status, res = _get("/memory/search")
        _assert(status == 200 and res["ok"], f"empty query ok: {status} {res}")
        _assert(res["state"] == "empty_corpus",
                f"empty library must report empty_corpus: {res}")
        _assert(res["corpus_total"] == 0, "empty corpus_total is 0")
        print("ok  empty corpus -> state=empty_corpus")

        # Seed some uoinks.
        _seed_yoink(idx, "vid0000001a", "Intro to LLMs", "Karpathy")
        _seed_yoink(idx, "vid0000002b", "Diffusion models", "Karpathy")

        # 2. Matches.
        status, res = _get("/memory/search")
        _assert(res["state"] == "matches", f"populated -> matches: {res}")
        _assert(res["total"] == 2 and res["corpus_total"] == 2,
                f"totals reflect the corpus: {res}")
        print("ok  populated corpus -> state=matches")

        # 3. No matches -- corpus has uoinks, this query matched nothing.
        status, res = _get("/memory/search?q=zzzznotamatchquery")
        _assert(res["state"] == "no_matches",
                f"unmatched query must be no_matches, not empty_corpus: {res}")
        _assert(res["total"] == 0 and res["corpus_total"] == 2,
                f"no_matches keeps corpus_total>0: {res}")
        print("ok  unmatched query -> state=no_matches (corpus_total>0)")

        # 4. Impossible date range -> 400 (G-12 / QA #13).
        status, res = _get(
            "/memory/search?date_from=2026-06-03&date_to=2026-01-01")
        _assert(status == 400 and res["ok"] is False,
                f"from>to must 400: {status} {res}")
        _assert(res.get("state") == "invalid_range",
                f"backwards range flagged invalid_range: {res}")
        print("ok  from>to date range -> 400 invalid_range")

        # A valid equal-day range is still fine.
        status, res = _get(
            "/memory/search?date_from=2026-06-01&date_to=2026-06-01")
        _assert(status == 200 and res["ok"], f"equal-day range ok: {res}")
        print("ok  equal-day range accepted")

        # 5. Backend unavailable -> 503, state:"unavailable".
        good = server._get_index

        class Broken:
            def search_yoinks_for_memory(self, **_kw):
                raise RuntimeError("index locked")

            def count_corpus(self):
                raise RuntimeError("index locked")

        server._get_index = lambda: Broken()  # type: ignore
        try:
            status, res = _get("/memory/search")
        finally:
            server._get_index = good  # type: ignore
        _assert(status == 503, f"index error -> 503, got {status}: {res}")
        _assert(res.get("state") == "unavailable",
                f"index error must signal unavailable, not empty: {res}")
        print("ok  index error -> 503 state=unavailable")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("\nALL LIBRARY STATE CONTRACT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
