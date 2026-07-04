"""G-02 -- the Writing Save button issues a real persistence request.

Run: python tests/test_writing_save_real.py

Two halves:
1. Static dashboard contract: Save is wired to saveWritingDraft (which
   POSTs /writing/draft), the lying "Draft saved locally" toast is gone,
   and a reload path (restoreWritingDraft, called from loadWriting) GETs
   the draft back.
2. Empirical round-trip: the exact payload shape saveWritingDraft sends is
   POSTed against a live server.Handler + real Index, then fetched back the
   way restoreWritingDraft does -- save, "reload", recover.

Red on the pre-fix dashboard: Save showed "Draft saved locally with its
source credit." while sending no request at all (QA #32).
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")
PORT = 5197


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _section(start, end):
    _assert(start in DASHBOARD, f"marker missing: {start}")
    body = DASHBOARD.split(start, 1)[1]
    _assert(end in body, f"end marker missing after {start}: {end}")
    return body.split(end, 1)[0]


def test_save_button_sends_a_real_request():
    _assert("Draft saved locally" not in DASHBOARD,
            "Save still claims a local save without sending anything")
    _assert('addEventListener("click", saveWritingDraft)' in DASHBOARD,
            "Save button is not wired to saveWritingDraft")
    fn = _section("async function saveWritingDraft()",
                  "async function restoreWritingDraft()")
    _assert('authFetch("/writing/draft", { method: "POST"' in fn,
            "saveWritingDraft must POST /writing/draft")
    _assert("state.writingDraftId = data.id" in fn,
            "saved draft id must be kept for update-in-place")
    _assert('localStorage.setItem("uoink.writingDraftId"' in fn,
            "draft id must survive a reload")
    print("ok  Save button: wired to a real POST /writing/draft")


def test_reload_recovers_the_draft():
    fn = _section("async function restoreWritingDraft()",
                  "async function copyWritingText()")
    _assert("authFetch(`/writing/draft/${savedId}`)" in fn,
            "restore must GET the saved draft back")
    _assert("setWritingOutput(data.body)" in fn,
            "restored body must land in the composer")
    load = _section("async function loadWriting()",
                    "async function loadStyleAnchors()")
    _assert("restoreWritingDraft()" in load,
            "loadWriting must attempt draft recovery")
    print("ok  reload path: loadWriting recovers the saved draft")


def _call(method, path, payload=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=(json.dumps(payload).encode() if payload is not None else None),
        headers={"Content-Type": "application/json",
                 "X-Uoink-Token": server.TOKEN},
        method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def test_dashboard_payload_round_trips():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Exactly the shape saveWritingDraft builds.
        saved = _call("POST", "/writing/draft", {
            "source_yoink_id": "v1",
            "kind": "tweet",
            "source_credit_line": "via @AndrejKarpathy",
            "body": "LLMs are autocomplete, and that's the useful part.",
        })
        _assert(saved["ok"] is True and isinstance(saved["id"], int),
                f"POST fired and persisted: {saved}")
        # What restoreWritingDraft does after a reload.
        recovered = _call("GET", f"/writing/draft/{saved['id']}")
        _assert(recovered["body"] ==
                "LLMs are autocomplete, and that's the useful part.",
                "reload recovers the exact saved draft body")
        _assert(recovered["draft"]["source_credit_line"] ==
                "via @AndrejKarpathy", "credit line survives the reload")
        print("ok  round-trip: dashboard payload saves and reloads intact")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


def main():
    test_save_button_sends_a_real_request()
    test_reload_recovers_the_draft()
    test_dashboard_payload_round_trips()
    print("\nALL G-02 REAL-SAVE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
