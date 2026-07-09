"""Quick notes / musings capture -- a note is a first-class uoink.

First item-model extension toward the context layer (handoff/
CONTEXT-LAYER-VISION-2026-07-08.md, build sequence item 1). A note is the
user's own text (markdown), authored by them, landing in the same corpus as
everything else: the same platform / source-type / author / topic taxonomy
v3.5.0 shipped, queryable over MCP and via search with no special-casing.

This module owns the pure note logic:
- validate the {text, title?} the user jots,
- derive a title from the first line when none is given,
- persist it as a yoink row plus a readable corpus folder under the
  configured output root (NOT %LOCALAPPDATA%).

Transport (the POST /notes route + token gate) is owned by server.py. Topic
classification is injected by the caller (server._classify_topic) so this
module stays standalone and unit-testable. Persist reuses the same index
machinery every capture uses (idx.upsert_yoink + a corpus/sidecar pair), so a
note reads back through /recent, /memory/search, /library/facets, and the MCP
tools exactly like a page, video, or thread.

Voice DNA applies to every user-visible string here.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# The taxonomy helpers (platform + source-type vocabulary) live in
# page_extractor so every source agrees on one set of tags. A note is
# source_type='note' on platform='note'.
from page_extractor import PLATFORM_NOTE

log = logging.getLogger("uoink.notes")

# Source-type tag persisted on the yoink row. Parallels 'page', 'x_article',
# 'reddit_thread', 'episode', 'video'.
SOURCE_TYPE = "note"
PLATFORM = PLATFORM_NOTE
EXTRACTION_ENGINE = "note"

# The default "who" when the corpus has no user identity configured. A note is
# authored by the person who wrote it; until an identity setting exists, that
# is plainly "You". The caller may override with an explicit author.
DEFAULT_AUTHOR = "You"

# A note with no real text is a no-op, not a junk uoink. Below one non-blank
# character we fail honestly.
MIN_TEXT_CHARS = 1
# Hard cap so a runaway paste can't blow up the row / FTS entry.
MAX_TEXT_CHARS = 200_000
MAX_TITLE_CHARS = 200

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
# Leading markdown heading / quote / list markers to strip when deriving a
# title from the first line.
_LEAD_MARKER_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s+|[-*+]\s+|\d+\.\s+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _slugify(value: str, *, max_len: int = 40) -> str:
    """Lowercase, ASCII-ish, hyphen-joined slug for a readable folder name.
    Empty / all-punctuation input returns ''."""
    text = _SLUG_STRIP_RE.sub("-", str(value or "").lower()).strip("-")
    return text[:max_len].strip("-")


def derive_title(text: str) -> str:
    """Title from the note body: the first non-blank line, stripped of any
    leading markdown marker (# heading, > quote, - list), trimmed to a sane
    length. Falls back to 'Untitled note' when there is no usable line."""
    for raw_line in (text or "").splitlines():
        line = _LEAD_MARKER_RE.sub("", raw_line).strip()
        if line:
            if len(line) > MAX_TITLE_CHARS:
                line = line[:MAX_TITLE_CHARS].rstrip() + "..."
            return line
    return "Untitled note"


def build_note(text: str, title: str | None = None,
               author: str | None = None) -> dict:
    """Validate a jotted note and shape it for persist_note.

    Returns {ok: True, ...} with a stable id + readable slug, or
    {ok: False, code, error} when the text is empty (nothing gets saved).
    """
    body = (text or "").strip()
    if len(body) < MIN_TEXT_CHARS:
        return {"ok": False, "code": "empty",
                "error": "A note needs some text. Nothing was saved."}
    if len(body) > MAX_TEXT_CHARS:
        body = body[:MAX_TEXT_CHARS]

    clean_title = (title or "").strip()
    if len(clean_title) > MAX_TITLE_CHARS:
        clean_title = clean_title[:MAX_TITLE_CHARS].rstrip() + "..."
    if not clean_title:
        clean_title = derive_title(body)

    who = (author or "").strip() or DEFAULT_AUTHOR

    note_uuid = uuid.uuid4().hex
    video_id = f"note_{note_uuid[:11]}"
    slug = f"{_slugify(clean_title) or 'note'}-{note_uuid[:8]}"

    return {
        "ok": True,
        "video_id": video_id,
        "slug": slug,
        "title": clean_title,
        "author": who,
        "markdown": body,
        "yoinked_at": _now_iso(),
    }


def persist_note(idx, note: dict, *, data_root: Path | None = None,
                 subfolder: str = "Notes",
                 topic_classifier=None) -> str | None:
    """Persist a built note as a yoink row + a readable corpus folder.

    Mirrors page_extractor.persist_page_yoink: writes <data_root>/Notes/<slug>/
    <slug>.md (title + body) and a <slug>.json sidecar, then upserts the row so
    it surfaces in /recent, /memory/search, /library/facets, and MCP with no
    special-casing. The corpus file is named after the folder slug so the
    disk-walk fallback (_resolve_corpus_path / MCP _iter_yoink_folders) finds it
    too, not just the index. Returns the video_id, or None if the note is
    invalid or the upsert fails.
    """
    if not isinstance(note, dict) or not note.get("ok"):
        return None

    video_id = note["video_id"]
    slug = note["slug"]
    title = note["title"]
    author = note["author"]
    md = note["markdown"]
    yoinked_at = note.get("yoinked_at") or _now_iso()

    # Classify a topic over the note text so notes join the topic facet instead
    # of piling into Uncategorized. The caller injects the classifier so this
    # module stays standalone; a classify failure never blocks the save.
    topic = None
    if topic_classifier is not None:
        try:
            topic = topic_classifier({
                "title": title or "",
                "description": (md or "")[:2000],
                "channel": author or "",
            }) or None
        except Exception as e:  # defensive: never block a save on classify
            log.warning("persist_note topic classify failed: %s", e)
            topic = None

    corpus_path = None
    sidecar_path = None
    if data_root is not None:
        folder = Path(data_root) / subfolder / slug
        folder.mkdir(parents=True, exist_ok=True)
        corpus_path = folder / f"{slug}.md"
        sidecar_path = folder / f"{slug}.json"
        corpus_path.write_text(f"# {title}\n\n" + (md or ""), encoding="utf-8")
        sidecar_path.write_text(json.dumps({
            "schema_version": 2,
            "source_type": SOURCE_TYPE,
            "platform": PLATFORM,
            "author": author,
            "title": title,
            "note": md,
            "extraction_engine": EXTRACTION_ENGINE,
            "yoinked_at": yoinked_at,
            "extracted_at": yoinked_at,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    metadata_json = json.dumps({
        "author": author,
        "platform": PLATFORM,
        "source_type": SOURCE_TYPE,
        "note": True,
    }, ensure_ascii=False)

    try:
        idx.upsert_yoink({
            "video_id": video_id,
            "slug": slug,
            # `channel` stays populated for every path that still reads it
            # (search, the channel/author picker): the note's author.
            "channel": author,
            "platform": PLATFORM,
            "author": author,
            "title": title[:240] if title else None,
            "topic": topic,
            "yoinked_at": yoinked_at,
            "corpus_path": str(corpus_path) if corpus_path else None,
            "sidecar_path": str(sidecar_path) if sidecar_path else None,
            "metadata_json": metadata_json,
            "source_type": SOURCE_TYPE,
        }, content=md[:65000])
    except Exception as e:
        log.warning("persist_note upsert failed: %s", e)
        return None
    return video_id
