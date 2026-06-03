"""Empirical tests for Fix 4B -- BYO-key direct generation (Path C).

Run: python tests/test_path_c_byo.py
Builds an in-memory SQLite index (style_anchors + writing_pieces tables),
binds it as the MCP backend, stubs server._anthropic_messages with a canned
response, and drives uoink_mcp_tools.write_tweet / write_blog through the
Path C branch (generate=True / compute_mode=byo_key). Verifies:
  - no key  -> a clear _err, no crash
  - tweet   -> persisted with mode=byo_key, credit + Voice DNA applied
  - missing credit in model output -> credit auto-appended
  - blog    -> JSON {title,dek,body,tags} parsed and persisted
No network (the only outbound call is stubbed).
"""
from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
import uoink_mcp_tools as tools  # noqa: E402
import writing_studio as ws  # noqa: E402
import voice_dna  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


YOINK = {
    "video_id": "v1",
    "title": "Intro to LLMs",
    "channel": "Andrej Karpathy",
    "channel_url": "https://www.youtube.com/@AndrejKarpathy",
    "url": "https://youtu.be/abc",
    "corpus_path": "",
    "sidecar_path": "",
}


class MemIndex:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE style_anchors(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT, source_type TEXT, source_url TEXT, raw_text TEXT,
              active INTEGER, added_at TEXT);
            CREATE TABLE writing_pieces(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              yoink_id TEXT, kind TEXT, version INTEGER, parent_id INTEGER,
              title TEXT, dek TEXT, body TEXT, tags TEXT,
              source_credit_line TEXT, voice_warnings TEXT,
              style_anchor_ids TEXT, mode TEXT, generated_at TEXT,
              angle TEXT, target_length INTEGER);
            """
        )

    def get_yoink(self, vid):
        return dict(YOINK) if vid == "v1" else None


def _install_backend(monkey, *, key="sk-test", reply=""):
    idx = MemIndex()
    tools.bind_backend(server)
    monkey["idx"] = idx
    server._get_index = lambda: idx
    server._read_settings = lambda: {}
    server._saved_anthropic_key = lambda: key
    server._mark_anthropic_key_invalid = lambda: None
    server._anthropic_messages = lambda *a, **k: {
        "content": [{"type": "text", "text": reply}]}
    return idx


def _restore(saved):
    for name, fn in saved.items():
        setattr(server, name, fn)


def _snapshot():
    return {n: getattr(server, n) for n in (
        "_get_index", "_read_settings", "_saved_anthropic_key",
        "_mark_anthropic_key_invalid", "_anthropic_messages")}


def test_extract_json():
    _assert(tools._byo_extract_json('{"a":1}') == {"a": 1}, "plain json")
    fenced = "```json\n{\"title\":\"T\",\"body\":\"B\"}\n```"
    _assert(tools._byo_extract_json(fenced)["title"] == "T", "fenced json")
    prose = 'Here you go:\n{"body":"hello"}\nThanks!'
    _assert(tools._byo_extract_json(prose)["body"] == "hello", "prose-wrapped")
    _assert(tools._byo_extract_json("no json here") is None, "garbage -> None")
    print("ok  _byo_extract_json: plain / fenced / prose / garbage")


def test_prompts_carry_voice_and_credit():
    grounding = ws.assemble_grounding(MemIndex(), "v1")
    system, user, credit = tools._byo_build_prompts(
        ws.KIND_TWEET, grounding, angle="contrarian",
        target_length=None, source_text="the source transcript text")
    if voice_dna.VOICE_DNA_PROMPT:
        _assert(voice_dna.VOICE_DNA_PROMPT.strip()[:40] in system,
                "Voice DNA must be prepended to the system prompt")
    _assert(credit and credit in system, "credit line embedded in system prompt")
    _assert("contrarian" in user, "angle carried into user prompt")
    _assert("the source transcript text" in user, "source text in user prompt")
    print("ok  _byo_build_prompts: voice DNA + credit + angle + source")


def test_no_key_errors():
    saved = _snapshot()
    try:
        _install_backend({}, key=None)
        res = tools.write_tweet({"source_yoink_id": "v1", "generate": True})
        _assert(res["ok"] is False, "no key -> ok:false")
        _assert("Anthropic key" in res["error"] or "agent" in res["error"],
                f"helpful no-key message: {res['error']}")
    finally:
        _restore(saved)
    print("ok  write_tweet Path C: no key -> clear error, no crash")


def test_tweet_generates_and_persists():
    saved = _snapshot()
    try:
        reply = "LLMs are just next-token predictors. via @AndrejKarpathy https://youtu.be/abc"
        idx = _install_backend({}, reply=reply)
        res = tools.write_tweet({"source_yoink_id": "v1",
                                 "compute_mode": "byo_key"})
        _assert(res["ok"] is True, f"tweet generated: {res}")
        _assert(res["compute_path"] == "byo_key", "compute_path flagged byo_key")
        _assert(res["generated_via"] == "byo_key", "generated_via flagged")
        _assert(res["mode"] == "persisted", "phase indicator is persisted")
        _assert("via @AndrejKarpathy" in res["body"], "credit present in body")
        row = idx._conn.execute(
            "SELECT mode, kind FROM writing_pieces WHERE id=?",
            (res["id"],)).fetchone()
        _assert(row["mode"] == ws.COMPUTE_MODE_BYO_KEY,
                f"DB records compute mode byo_key, got {row['mode']}")
        _assert(row["kind"] == "tweet", "persisted as tweet")
    finally:
        _restore(saved)
    print("ok  write_tweet Path C: generates, persists, mode=byo_key in DB")


def test_credit_auto_appended():
    saved = _snapshot()
    try:
        # Model 'forgot' the credit -> Path C must append it so the piece
        # never ships without attribution (and persist's check passes).
        reply = "LLMs are just fancy autocomplete. No credit here."
        idx = _install_backend({}, reply=reply)
        res = tools.write_tweet({"source_yoink_id": "v1", "generate": True})
        _assert(res["ok"] is True, f"should still persist: {res}")
        _assert("youtu.be/abc" in res["body"] or "@AndrejKarpathy" in res["body"],
                "credit auto-appended when the model omitted it")
    finally:
        _restore(saved)
    print("ok  write_tweet Path C: missing credit auto-appended")


def test_blog_json_parsed():
    saved = _snapshot()
    try:
        reply = ('```json\n{"title":"Why LLMs Matter","dek":"A short take",'
                 '"body":"Long form body. Source: Intro to LLMs by Andrej '
                 'Karpathy -- https://youtu.be/abc","tags":["ai","llm"]}\n```')
        idx = _install_backend({}, reply=reply)
        res = tools.write_blog({"source_yoink_id": "v1", "generate": True})
        _assert(res["ok"] is True, f"blog generated: {res}")
        _assert(res["title"] == "Why LLMs Matter", "blog title parsed")
        _assert(res["dek"] == "A short take", "blog dek parsed")
        _assert(res["tags"] == ["ai", "llm"], f"blog tags parsed: {res['tags']}")
        _assert(res["compute_path"] == "byo_key", "blog flagged byo_key")
        row = idx._conn.execute(
            "SELECT kind, mode FROM writing_pieces WHERE id=?",
            (res["id"],)).fetchone()
        _assert(row["kind"] == "blog" and row["mode"] == ws.COMPUTE_MODE_BYO_KEY,
                "persisted as blog/byo_key")
    finally:
        _restore(saved)
    print("ok  write_blog Path C: JSON title/dek/body/tags parsed + persisted")


def main():
    test_extract_json()
    test_prompts_carry_voice_and_credit()
    test_no_key_errors()
    test_tweet_generates_and_persists()
    test_credit_auto_appended()
    test_blog_json_parsed()
    print("\nALL PATH C (BYO-KEY) TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
