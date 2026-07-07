"""R-02 -- GET /resume serves the "resume where you left off" open-loop.

Run: python tests/test_resume_route.py  (or via pytest tests/)

The dashboard's loadResume() calls authFetch("/resume") on launch to render
the top-of-Library resume card. This route reads two local signals and
nothing else:

  last_source  the most recently saved uoink (yoinks, newest first)
  last_draft   the most recently touched writing draft, with its linked
               source resolved to a title/channel when present
  suggested    {action} -- "continue_draft" when a draft is in flight,
               else "write_from_source", else "none"

Red on unpatched main: GET /resume -> 404.

Green with the fix: token-gated route returning {ok, resume:{...}} with the
exact keys renderResumeCard() reads, an empty-but-valid shape on an empty
corpus, a source-only shape after a save, and a draft-led shape (source
resolved) once a draft exists. Also asserts the body preview is truncated.
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

PORT = 5211


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(host, path, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(f"{host}{path}", headers=headers)
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


def test_resume_route():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    prev_get_index = server._get_index
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    host = f"http://127.0.0.1:{PORT}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # 1. Route exists and is token-gated.
        status, _res = _get(host, "/resume", token=False)
        _assert(status == 403, f"no token must 403, got {status}")

        # 2. Empty corpus -> empty-but-valid payload, not an error.
        status, res = _get(host, "/resume")
        _assert(status == 200,
                f"/resume must exist (red on main: 404), got {status}")
        _assert(res.get("ok") is True, f"ok flag: {res}")
        payload = res.get("resume") or {}
        _assert(payload.get("last_draft") is None,
                f"empty corpus: no draft, got {payload.get('last_draft')}")
        _assert(payload.get("last_source") is None,
                f"empty corpus: no source, got {payload.get('last_source')}")
        _assert(payload["suggested"]["action"] == "none",
                f"empty corpus: action none, got {payload['suggested']}")

        # 3. A saved source with no draft -> source-led "write_from_source".
        _seed_yoink(idx, tmp.name, "vidoldsource", "Older save",
                    "AI and ML", "2026-05-01T09:00:00")
        _seed_yoink(idx, tmp.name, "vidnewsource", "Newest save",
                    "AI and ML", "2026-07-01T09:00:00")
        status, res = _get(host, "/resume")
        payload = res["resume"]
        _assert(payload["last_draft"] is None,
                f"still no draft: {payload['last_draft']}")
        src = payload["last_source"]
        _assert(src and src["video_id"] == "vidnewsource",
                f"newest save is the last source: {src}")
        _assert(src["title"] == "Newest save", f"source title: {src}")
        _assert(payload["suggested"]["action"] == "write_from_source",
                f"source-only action: {payload['suggested']}")
        _assert(payload["suggested"]["video_id"] == "vidnewsource",
                f"suggested carries the deep-link id: {payload['suggested']}")

        # 4. A saved draft linked to a source -> draft-led "continue_draft"
        #    with the source resolved to title/channel.
        long_body = "First line of the draft. " + ("x" * 400)
        idx.save_writing_draft(
            yoink_id="vidoldsource", kind="thread",
            title="Draft in progress",
            body=long_body,
            source_credit_line="via TestChannel")
        status, res = _get(host, "/resume")
        payload = res["resume"]
        draft = payload["last_draft"]
        _assert(draft and draft["kind"] == "thread", f"draft kind: {draft}")
        _assert(draft["title"] == "Draft in progress", f"draft title: {draft}")
        _assert(draft["source"] and draft["source"]["video_id"] == "vidoldsource",
                f"draft source resolved: {draft.get('source')}")
        _assert(draft["source"]["channel"] == "TestChannel",
                f"draft source channel resolved: {draft['source']}")
        _assert(len(draft["body_preview"]) <= server._RESUME_BODY_PREVIEW_CHARS + 3,
                f"body preview truncated: len={len(draft['body_preview'])}")
        _assert(draft["body_preview"].endswith("..."),
                f"long body preview ends with ellipsis: {draft['body_preview']!r}")
        _assert(payload["suggested"]["action"] == "continue_draft",
                f"draft-led action: {payload['suggested']}")
        _assert(payload["suggested"]["draft_id"] == draft["id"],
                f"suggested carries the draft id: {payload['suggested']}")
        _assert(payload["suggested"]["video_id"] == "vidoldsource",
                f"suggested carries the draft source id: {payload['suggested']}")
        # last_source is still the newest save, independent of the draft.
        _assert(payload["last_source"]["video_id"] == "vidnewsource",
                f"last_source stays newest save: {payload['last_source']}")

        # 5. A draft with no linked source -> draft-led, source is None.
        idx.save_writing_draft(
            yoink_id=None, kind="tweet",
            title=None, body="Freestanding thought, no source.")
        status, res = _get(host, "/resume")
        payload = res["resume"]
        _assert(payload["last_draft"]["source"] is None,
                f"unlinked draft has no source: {payload['last_draft']}")
        _assert(payload["last_draft"]["title"] is None,
                f"unlinked draft title None: {payload['last_draft']}")
        _assert(payload["suggested"]["action"] == "continue_draft",
                f"unlinked draft still continue_draft: {payload['suggested']}")
        _assert(payload["suggested"]["video_id"] is None,
                f"unlinked draft suggested video_id None: {payload['suggested']}")
    finally:
        httpd.shutdown()
        idx.close()
        server._get_index = prev_get_index  # type: ignore
        tmp.cleanup()


if __name__ == "__main__":
    test_resume_route()
    print("\nall green")
