"""G-24 -- recovery endpoints for dead-end empty states.

Run: python tests/test_yoink_recovery_endpoints.py

QA #18/#19/#40: the detail + Evidence surfaces dead-end. The transcript
preview promised an "open saved markdown" action that did not exist, and a
"local detail needs another moment" state had no recovery. This adds the
missing per-yoink markdown backend:

  GET /yoinks/<id>/markdown       corpus markdown text for the detail preview
  GET /yoinks/<id>/open-markdown  open that markdown in the OS viewer

Retry-extraction (POST /yoinks/<id>/reyoink) and claims (POST /claims/extract,
GET /claims/<id>) already exist and are documented in the PR for CW; this test
covers the new markdown endpoints plus their sandbox + 404 behavior.
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

PORT = 5201


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


def main():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    # DESKTOP_ROOT is the sandbox boundary for the markdown path.
    server.DESKTOP_ROOT = root
    idx = index_mod.Index.open(root / "index.db")
    server._get_index = lambda: idx  # type: ignore

    # A yoink whose markdown exists on disk inside the root.
    folder = root / "ai" / "intro-llms"
    folder.mkdir(parents=True)
    md = folder / "intro-llms.md"
    md.write_text("# Intro to LLMs\n\nTranscript body here.\n", encoding="utf-8")
    idx.upsert_yoink({
        "video_id": "vidmd00001", "slug": "intro-llms", "channel": "Karpathy",
        "title": "Intro to LLMs", "topic": "ai", "hook_type": "curiosity_gap",
        "yoinked_at": "2026-06-01T10:00:00", "corpus_path": str(md),
        "sidecar_path": "", "source_type": "youtube",
    })
    # A yoink with no corpus_path (never finished) -> clean no_markdown state.
    idx.upsert_yoink({
        "video_id": "vidmd00002", "slug": "half", "channel": "Karpathy",
        "title": "Half", "topic": "ai", "hook_type": "", "yoinked_at":
        "2026-06-02T10:00:00", "corpus_path": "", "sidecar_path": "",
        "source_type": "youtube",
    })

    # Don't actually launch an app during the open test.
    opened = {"path": None}
    server._platform.open_in_os = lambda p: opened.__setitem__("path", str(p))

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Read markdown.
        status, res = _get("/yoinks/vidmd00001/markdown")
        _assert(status == 200 and res["ok"], f"read ok: {status} {res}")
        _assert("Transcript body here." in res["markdown"],
                f"returns the real markdown: {res['markdown'][:60]}")
        _assert(res["video_id"] == "vidmd00001", "echoes video_id")
        print("ok  GET /yoinks/<id>/markdown: returns corpus text")

        # Open markdown (side-effect mocked).
        status, res = _get("/yoinks/vidmd00001/open-markdown")
        _assert(status == 200 and res["ok"], f"open ok: {status} {res}")
        _assert(opened["path"] and opened["path"].endswith("intro-llms.md"),
                f"opened the right file: {opened['path']}")
        print("ok  GET /yoinks/<id>/open-markdown: opens the file")

        # Unknown yoink -> 404.
        status, res = _get("/yoinks/nope/markdown")
        _assert(status == 404 and res["ok"] is False, f"unknown -> 404: {res}")
        print("ok  unknown yoink -> 404")

        # Yoink with no markdown -> clean 404 no_markdown state, not a crash.
        status, res = _get("/yoinks/vidmd00002/markdown")
        _assert(status == 404 and res.get("state") == "no_markdown",
                f"no corpus_path -> no_markdown state: {res}")
        print("ok  no-markdown yoink -> state=no_markdown (recoverable)")

        # Missing file on disk (path set but file gone) -> no_markdown.
        md.unlink()
        status, res = _get("/yoinks/vidmd00001/markdown")
        _assert(status == 404 and res.get("state") == "no_markdown",
                f"missing file -> no_markdown: {res}")
        print("ok  missing markdown file -> state=no_markdown")

        # Token gate.
        s1, _ = _get("/yoinks/vidmd00001/markdown", token=False)
        _assert(s1 in (401, 403), f"token required: {s1}")
        print("ok  token required")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("\nALL YOINK RECOVERY ENDPOINT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
