"""uoink Recall hook for Claude Code (UserPromptSubmit).

Reads the hook payload on stdin, searches the user's local uoink library for
what they just typed, and prints a short "you already have this" block that
Claude Code injects as additional context. Read-only. No network. No model.

Install (project or user settings.json):
  "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
      "command": "python E:/AI/projects/uoink/checkouts/Yoink-library/scripts/recall_hook.py"}]}]}

Env: UOINK_INDEX_PATH overrides the index location (default %LOCALAPPDATA%/Uoink/index.db).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

STOP = set("""a an the and or but if then than so to of in on at for from by with about into over under
is are was were be been being am do does did have has had can could should would will shall may might
i me my mine we us our you your he she it they them their this that these those what which who whom how
when where why not no yes ok okay please just like get make want need think know help let go use using
via up down out off also too very really there here now new some any all more most much many""".split())

MIN_WORDS = 4
MAX_HITS = 5


def _index_path() -> Path:
    env = os.environ.get("UOINK_INDEX_PATH")
    if env:
        return Path(env)
    return Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "Uoink" / "index.db"


def _terms(prompt: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_\-]{2,}", prompt.lower())
    seen: list[str] = []
    for w in words:
        w = w.strip("-")
        if w in STOP or w in seen or len(w) < 3:
            continue
        seen.append(w)
    return seen[:8]


def _fts(terms: list[str]) -> str:
    # OR the terms so a long prompt still hits; FTS5 handles ranking.
    return " OR ".join(f'"{t}"' for t in terms)


def _hms(seconds) -> str:
    try:
        s = int(float(seconds or 0))
    except (TypeError, ValueError):
        s = 0
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def search(conn: sqlite3.Connection, terms: list[str]) -> tuple[str, list[dict]]:
    match = _fts(terms)
    have_clips = conn.execute("SELECT name FROM sqlite_master WHERE name='clips_fts'").fetchone() is not None
    if have_clips:
        rows = conn.execute(
            "SELECT c.video_id, y.title, y.channel, c.start, c.text, c.source_deep_link, "
            "bm25(clips_fts) AS score FROM clips_fts f JOIN clips c ON c.clip_id = f.rowid "
            "JOIN yoinks y ON y.video_id = c.video_id "
            "WHERE clips_fts MATCH ? AND y.deleted_at IS NULL ORDER BY score LIMIT 40",
            (match,),
        ).fetchall()
        # One best clip per item, then top N items.
        best: dict[str, sqlite3.Row] = {}
        for r in rows:
            if r["video_id"] not in best:
                best[r["video_id"]] = r
        hits = [dict(r) for r in list(best.values())[:MAX_HITS]]
        return "clips", hits
    rows = conn.execute(
        "SELECT y.video_id, y.title, y.channel, NULL AS start, "
        "snippet(yoinks_fts, 6, '', '', '…', 14) AS text, "
        "json_extract(y.metadata_json, '$.url') AS source_deep_link, bm25(yoinks_fts) AS score "
        "FROM yoinks_fts f JOIN yoinks y ON y.video_id = f.video_id "
        "WHERE yoinks_fts MATCH ? AND y.deleted_at IS NULL ORDER BY score LIMIT ?",
        (match, MAX_HITS),
    ).fetchall()
    return "items", [dict(r) for r in rows]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Claude Code reads UTF-8; Windows defaults to cp1252
    except (AttributeError, ValueError):
        pass
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    prompt = str(payload.get("prompt") or "")
    terms = _terms(prompt)
    if len(prompt.split()) < MIN_WORDS or len(terms) < 2:
        return 0
    path = _index_path()
    if not path.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        level, hits = search(conn, terms)
    except sqlite3.Error:
        return 0
    if not hits:
        return 0
    total = conn.execute("SELECT count(*) FROM yoinks WHERE deleted_at IS NULL").fetchone()[0]
    lines = [f"[uoink recall] You have {len(hits)}{'+' if len(hits) >= MAX_HITS else ''} saved items related to this (library: {total} items, matched on: {', '.join(terms[:5])}). Cite them if useful; the user may have forgotten they saved them."]
    for h in hits:
        where = f" @ {_hms(h['start'])}" if h.get("start") is not None else ""
        text = re.sub(r"\s+", " ", str(h.get("text") or "")).strip()[:160]
        link = h.get("source_deep_link") or ""
        lines.append(f"- {h['title']} ({h.get('channel') or 'unknown'}){where}: \"{text}\" {link}".rstrip())
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
