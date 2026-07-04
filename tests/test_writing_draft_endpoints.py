"""Empirical tests for G-03 -- writing draft persistence endpoints.

Run: python tests/test_writing_draft_endpoints.py

Opens a real index.Index on a temp file (so migration 0018_writing_drafts
actually runs), boots server.Handler on 127.0.0.1, and drives:
  - POST /writing/draft             -> insert, returns id + stored draft
  - POST /writing/draft with id     -> updates that draft in place
  - GET  /writing/draft/<id>        -> round-trips the saved body
  - GET  /writing/draft/<unknown>   -> 404
  - GET  /writing/draft (no id)     -> 400 with a draft-specific error
  - POST /writing/draft empty body  -> 400, nothing saved
  - missing token                   -> rejected
No network beyond loopback; no LLM calls.
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

PORT = 5196


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _call(method, path, payload=None, *, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=(json.dumps(payload).encode() if payload is not None else None),
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Insert.
        status, res = _call("POST", "/writing/draft", {
            "source_yoink_id": "v1", "kind": "thread",
            "title": "Working title",
            "body": "1/ LLMs are autocomplete.\n2/ But useful.",
            "source_credit_line": "via @AndrejKarpathy",
        })
        _assert(status == 200 and res["ok"] is True, f"insert: {status} {res}")
        draft_id = res["id"]
        _assert(isinstance(draft_id, int), f"numeric id returned: {res}")
        _assert(res["draft"]["kind"] == "thread", "kind stored")
        print(f"ok  POST /writing/draft: inserted draft {draft_id}")

        # Round-trip.
        status, res = _call("GET", f"/writing/draft/{draft_id}")
        _assert(status == 200 and res["ok"] is True, f"get: {status} {res}")
        _assert(res["body"] == "1/ LLMs are autocomplete.\n2/ But useful.",
                "GET round-trips the exact saved body")
        _assert(res["draft"]["yoink_id"] == "v1", "source id survives")
        _assert(res["draft"]["source_credit_line"] == "via @AndrejKarpathy",
                "credit line survives")
        print("ok  GET /writing/draft/<id>: body + source round-trip")

        # Update in place.
        status, res = _call("POST", "/writing/draft", {
            "id": draft_id, "source_yoink_id": "v1", "kind": "thread",
            "body": "1/ Rewritten opener.\n2/ Same thread.",
        })
        _assert(status == 200 and res["id"] == draft_id,
                f"update keeps the id: {status} {res}")
        status, res = _call("GET", f"/writing/draft/{draft_id}")
        _assert(res["body"].startswith("1/ Rewritten opener."),
                "update replaced the stored body")
        _assert(res["draft"]["updated_at"] >= res["draft"]["created_at"],
                "updated_at moves forward")
        print("ok  POST /writing/draft with id: updates in place")

        # Unknown id -> 404 (GET) and 404 (POST update).
        status, res = _call("GET", "/writing/draft/999999")
        _assert(status == 404 and res["ok"] is False, f"404: {status} {res}")
        status, res = _call("POST", "/writing/draft",
                            {"id": 999999, "body": "x"})
        _assert(status == 404, f"update unknown id -> 404: {status} {res}")
        print("ok  unknown draft id: 404 on GET and update")

        # Missing / junk input -> 400, nothing saved.
        status, res = _call("POST", "/writing/draft", {"body": "   "})
        _assert(status == 400, f"empty body -> 400: {status} {res}")
        status, res = _call("GET", "/writing/draft")
        _assert(status == 400 and "draft" in str(res.get("error", "")),
                f"bare GET -> 400 draft error: {status} {res}")
        status, res = _call("POST", "/writing/draft",
                            {"id": "abc", "body": "x"})
        _assert(status == 400, f"non-integer id -> 400: {status} {res}")
        # G-90 regression: an id beyond SQLite's 64-bit range must be a clean
        # 404, not a 500 from the failed integer bind.
        huge = 10 ** 20
        status, res = _call("POST", "/writing/draft", {"id": huge, "body": "x"})
        _assert(status == 404, f"oversized id update -> 404, not 500: {status} {res}")
        status, res = _call("GET", f"/writing/draft/{huge}")
        _assert(status == 404, f"oversized id GET -> 404, not 500: {status} {res}")
        row = idx._conn.execute(
            "SELECT COUNT(*) AS c FROM writing_drafts").fetchone()
        _assert(row["c"] == 1, f"rejected saves persisted nothing: {row['c']}")
        print("ok  bad input: 400s + oversized id 404 (G-90), nothing extra saved")

        # No token -> rejected.
        status, res = _call("GET", f"/writing/draft/{draft_id}", token=False)
        _assert(status in (401, 403), f"tokenless request rejected: {status}")
        print("ok  token required on draft endpoints")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("\nALL WRITING DRAFT ENDPOINT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
