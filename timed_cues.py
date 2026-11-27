"""Timed cues read contract v1 (``uoink.cues.read``).

A separate, versioned, read-only HTTP contract for tools that cut clips
(Zing first): timed transcript cues for one saved item, plus a list of items
filtered by show and by original publish date.

    GET /api/cues/v1/items/<id>   one item's cues, timing source and dates
    GET /api/cues/v1/items        item references (q, channel, publish dates)

Corpus read v1 (``uoink.corpus.read``) is untouched: different URL prefix,
different contract name, and this module never imports it. Reads are local
only: the SQLite index and the item's JSON sidecar. Nothing is fetched, no
model runs, and responses never carry file paths.

Pure functions over an index object and plain dicts, so tests drive them
without a running helper. server.py owns the routes and the token gate.
"""
from __future__ import annotations

import json
import transcript_review
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import index as index_mod
from moments import cited_url

CONTRACT = "uoink.cues.read"
VERSION = 1
ITEM_PREFIX = "/api/cues/v1/items"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
ITEM_PARAMS = frozenset({"start", "end", "limit", "offset", "include_words", "include_held"})
# Cues per item response: a multi-hour episode with word timings is several MB.
CUE_DEFAULT_LIMIT = 1000
CUE_MAX_LIMIT = 5000
SEARCH_PARAMS = frozenset({"q", "channel", "published_from", "published_to",
                           "date_from", "date_to", "limit", "offset"})
TIMING_SOURCES = ("captions", "auto_captions", "local_asr")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


class CuesError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def envelope(operation: str, data: dict) -> dict:
    return {"ok": True, "contract": CONTRACT, "version": VERSION,
            "operation": operation, "data": data}


def error_envelope(operation: str, error: CuesError) -> dict:
    return {"ok": False, "contract": CONTRACT, "version": VERSION, "operation": operation,
            "error": {"code": error.code, "message": error.message,
                      "retryable": error.status >= 500}}


# ---------------------------------------------------------------------------
# Field shaping
# ---------------------------------------------------------------------------

def _metadata(row: dict) -> dict:
    try:
        data = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def published_value(*values) -> str | None:
    """The first usable publish date: an ISO 8601 value as stored, or any
    other known shape (yt-dlp's YYYYMMDD, RSS pubDate) as YYYY-MM-DD."""
    for value in values:
        if isinstance(value, str) and _ISO_DAY.match(value.strip()):
            day = index_mod.published_day(value)
            if day:
                return value.strip()
        day = index_mod.published_day(value)
        if day:
            return day
    return None


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def timing_of(sidecar: dict, row: dict, cues: list[dict] | None = None) -> dict:
    """Where the cue timings came from. ``source`` is captions (uploaded by
    the creator), auto_captions (the platform's automatic track), local_asr
    (Whisper on this computer) or None when the item has no transcript.
    ``caption_kind_known`` is false for captions saved before Uoink recorded
    which kind they were. ``word_timings`` is true only when a cue that
    comes back has valid words (``cues``: the item's cues_of)."""
    has_cues = bool(sidecar.get("transcript"))
    source_type = sidecar.get("source_type") or row.get("source_type")
    recorded = sidecar.get("transcript_source")
    source, known = None, True
    if not has_cues:
        source = None
    elif recorded == "asr":
        source = "local_asr"
    elif recorded == "captions":
        kind = sidecar.get("caption_kind")
        if kind in ("captions", "auto_captions"):
            source = kind
        else:
            source, known = "captions", False
    elif source_type == "episode" or sidecar.get("transcript_model"):
        # Podcast episodes are transcribed locally with Whisper.
        source = "local_asr"
    else:
        source, known = None, False
    words = any("words" in cue for cue in (cues if cues is not None else cues_of(sidecar)))
    return {"source": source, "caption_kind_known": known, "word_timings": words}


def cues_of(sidecar: dict, *, start: float | None = None,
            end: float | None = None) -> list[dict]:
    """Stored cues as ``{start, end, text}`` in time order, plus ``speaker``,
    ``deep_link`` and ``words`` only where the stored cue has them. With a
    window, only cues that overlap [start, end] come back."""
    out: list[dict] = []
    for seg in sidecar.get("transcript") or []:
        if isinstance(seg, dict):
            s, e, text = _number(seg.get("start")), _number(seg.get("end")), seg.get("text")
        elif isinstance(seg, (list, tuple)) and len(seg) >= 3:
            s, e, text = _number(seg[0]), _number(seg[1]), seg[2]
            seg = {}
        else:
            continue
        if s is None or not isinstance(text, str) or not text.strip():
            continue
        e = e if e is not None and e >= s else s
        if start is not None and e < start:
            continue
        if end is not None and s > end:
            continue
        cue: dict[str, Any] = {"start": round(s, 3), "end": round(e, 3), "text": text.strip()}
        if "held_line" in seg:
            cue.update(held_line=seg["held_line"], held_reason=seg.get("held_reason"))
        speaker = seg.get("speaker")
        if isinstance(speaker, str) and speaker.strip() and isinstance(seg.get("speaker_provenance"), dict):
            cue["speaker"] = speaker.strip()
        link = seg.get("source_deep_link") or seg.get("youtube_deep_link")
        if isinstance(link, str) and link.startswith(("http://", "https://")):
            cue["deep_link"] = cited_url(link, cue.get("start"))
        words = []
        for word in seg.get("words") or []:
            if not isinstance(word, dict):
                continue
            ws, we = _number(word.get("start")), _number(word.get("end"))
            wt = word.get("word") if isinstance(word.get("word"), str) else word.get("text")
            if ws is None or not isinstance(wt, str) or not wt.strip():
                continue
            words.append({"start": round(ws, 3), "end": round(we if we is not None and we >= ws else ws, 3),
                          "text": wt.strip()})
        if words:
            cue["words"] = sorted(words, key=lambda w: (w["start"], w["end"]))
        out.append(cue)
    out.sort(key=lambda c: (c["start"], c["end"]))
    return out


def item_of(row: dict, sidecar: dict) -> dict:
    meta = _metadata(row)
    duration = _number(sidecar.get("duration_seconds"))
    if duration is None:
        duration = _number(meta.get("duration_seconds"))
    description = sidecar.get("description")
    return {
        "id": row.get("video_id"),
        "title": sidecar.get("episode_title") or sidecar.get("title") or row.get("title") or "",
        "channel": sidecar.get("channel") or row.get("channel"),
        "platform": row.get("platform") or sidecar.get("platform") or meta.get("platform"),
        "source_type": row.get("source_type") or sidecar.get("source_type") or "video",
        "source_url": sidecar.get("source_url") or sidecar.get("url") or meta.get("url"),
        "published_at": published_value(sidecar.get("published_at"), meta.get("published_at"),
                                        sidecar.get("upload_date"), meta.get("upload_date")),
        "duration_seconds": duration,
        "captured_at": row.get("yoinked_at") or sidecar.get("yoinked_at"),
        "description": description if isinstance(description, str) and description else None,
    }


def ref_of(row: dict) -> dict:
    """A list entry, from the index row alone (no sidecar read per row)."""
    meta = _metadata(row)
    return {
        "id": row.get("video_id"),
        "title": row.get("title") or "",
        "channel": row.get("channel"),
        "platform": row.get("platform") or meta.get("platform"),
        "source_type": row.get("source_type") or "video",
        "source_url": meta.get("url"),
        "published_at": published_value(meta.get("published_at"), meta.get("upload_date")),
        "duration_seconds": _number(meta.get("duration_seconds")),
        "captured_at": row.get("yoinked_at"),
        "cues_url": f"{ITEM_PREFIX}/{quote(str(row.get('video_id') or ''), safe='')}",
    }


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def _single(query: dict, allowed: frozenset) -> dict[str, str]:
    unknown = sorted(set(query) - allowed)
    if unknown:
        raise CuesError("invalid_request", f"unknown parameter: {unknown[0]}", 400)
    out = {}
    for key, values in query.items():
        values = values if isinstance(values, list) else [values]
        if len(values) != 1:
            raise CuesError("invalid_request", f"{key} must be given once", 400)
        value = str(values[0]).strip()
        if value:
            out[key] = value
    return out


def _day(params: dict, key: str) -> str | None:
    value = params.get(key)
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise CuesError("invalid_request", f"{key} must be YYYY-MM-DD", 400) from None


def _seconds(params: dict, key: str) -> float | None:
    if key not in params:
        return None
    value = _number(params[key])
    if value is None:
        raise CuesError("invalid_request", f"{key} must be a number of seconds, 0 or more", 400)
    return value


def get_item(idx, item_id: str, query: dict | None = None) -> dict:
    """``data`` for GET /api/cues/v1/items/<id>: at most ``limit`` cues of
    the window from ``offset``, with a page block like the list call.
    ``include_words=0`` leaves word timings out. Raises CuesError."""
    params = _single(query or {}, ITEM_PARAMS)
    start, end = _seconds(params, "start"), _seconds(params, "end")
    if start is not None and end is not None and start > end:
        raise CuesError("invalid_request", "start is after end", 400)
    try:
        limit = int(params.get("limit", CUE_DEFAULT_LIMIT))
        offset = int(params.get("offset", 0))
    except ValueError:
        raise CuesError("invalid_request", "limit and offset must be whole numbers", 400) from None
    if not 1 <= limit <= CUE_MAX_LIMIT or offset < 0:
        raise CuesError("invalid_request", f"limit is 1 to {CUE_MAX_LIMIT} and offset 0 or more", 400)
    include_words = params.get("include_words", "1").lower()
    if include_words not in ("0", "1", "true", "false"):
        raise CuesError("invalid_request", "include_words is 0 or 1", 400)
    item_id = (item_id or "").strip()
    if not item_id or "/" in item_id or len(item_id) > 200:
        raise CuesError("invalid_request", "item id is missing or malformed", 400)
    row = idx.get_yoink(item_id)
    if not row or row.get("deleted_at"):
        raise CuesError("not_found", "item not found", 404)
    sidecar: dict = {}
    sidecar_path = row.get("sidecar_path")
    if sidecar_path:
        try:
            loaded = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
            sidecar = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            sidecar = {}
    held = sidecar.get("held_transcript_lines") or []
    include_held = params.get("include_held", "0").lower()
    if include_held not in ("0", "1", "true", "false"):
        raise CuesError("invalid_request", "include_held is 0 or 1", 400)
    if held and include_held in ("1", "true"):
        flagged = [dict(h, segment=dict(h["segment"], held_line=h["line"], held_reason=h["reason"]))
                   for h in held]
        sidecar = dict(sidecar, transcript=transcript_review.all_rows(sidecar.get("transcript", []), flagged))
    every = cues_of(sidecar)
    window = [cue for cue in every
              if (start is None or cue["end"] >= start) and (end is None or cue["start"] <= end)]
    cues = window[offset:offset + limit]
    if include_words in ("0", "false"):
        cues = [{key: value for key, value in cue.items() if key != "words"} for cue in cues]
    shown = offset + len(cues)
    return {
        "item": item_of(row, sidecar),
        **({"held_count": len(held), "review_note": transcript_review.notice(held)} if held else {}),
        "timing": timing_of(sidecar, row, every),
        "range": {"start": start, "end": end},
        "cue_count": len(cues),
        "page": {"limit": limit, "offset": offset, "total": len(window),
                 "next_offset": shown if shown < len(window) else None},
        "cues": cues,
    }


def search(idx, query: dict | None = None) -> dict:
    """``data`` for GET /api/cues/v1/items: saved items filtered by words,
    show (channel) and publish date range, newest capture first without q."""
    params = _single(query or {}, SEARCH_PARAMS)
    try:
        limit = int(params.get("limit", DEFAULT_LIMIT))
        offset = int(params.get("offset", 0))
    except ValueError:
        raise CuesError("invalid_request", "limit and offset must be whole numbers", 400) from None
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise CuesError("invalid_request", f"limit is 1 to {MAX_LIMIT} and offset 0 or more", 400)
    bounds = {key: _day(params, key) for key in ("published_from", "published_to", "date_from", "date_to")}
    for low, high in (("published_from", "published_to"), ("date_from", "date_to")):
        if bounds[low] and bounds[high] and bounds[low] > bounds[high]:
            raise CuesError("invalid_request", f"{low} is after {high}", 400)
    result = idx.search_yoinks_for_memory(
        q=params.get("q"), channel=params.get("channel"),
        date_from=bounds["date_from"], date_to=bounds["date_to"],
        published_from=bounds["published_from"], published_to=bounds["published_to"],
        limit=limit, offset=offset, passages=False)
    rows = result.get("results") or []
    total = int(result.get("total") or 0)
    return {
        "filters": {"q": params.get("q"), "channel": params.get("channel"), **bounds},
        "page": {"limit": limit, "offset": offset, "total": total,
                 "next_offset": offset + len(rows) if offset + len(rows) < total else None},
        "items": [ref_of(dict(row)) for row in rows],
    }


# ---------------------------------------------------------------------------
# OpenAPI (merged into /openapi/v1/spec.json by server.py)
# ---------------------------------------------------------------------------

def _query_param(name: str, description: str, schema: dict) -> dict:
    return {"name": name, "in": "query", "required": False,
            "description": description, "schema": schema}


_CUE_SCHEMA = {
    "type": "object",
    "required": ["start", "end", "text"],
    "properties": {
        "start": {"type": "number", "description": "Seconds from the start of the source."},
        "end": {"type": "number"},
        "text": {"type": "string"},
        "held_line": {"type": "integer", "description": "Original line number for --restore."},
        "held_reason": {"type": "string", "description": "Why this line is held back."},
        "speaker": {"type": "string", "description": "Only when the stored cue has an attributed speaker."},
        "deep_link": {"type": "string", "description": "Source link that opens at this cue, when stored."},
        "words": {"type": "array", "description": "Word timings, only when the stored transcript has them.",
                  "items": {"type": "object", "properties": {
                      "start": {"type": "number"}, "end": {"type": "number"}, "text": {"type": "string"}}}},
    },
}

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"}, "title": {"type": "string"},
        "channel": {"type": ["string", "null"]}, "platform": {"type": ["string", "null"]},
        "source_type": {"type": "string"}, "source_url": {"type": ["string", "null"]},
        "published_at": {"type": ["string", "null"],
                         "description": "Original publish date (ISO 8601), not the capture time."},
        "duration_seconds": {"type": ["number", "null"]},
        "captured_at": {"type": ["string", "null"], "description": "When Uoink saved it."},
        "description": {"type": ["string", "null"]},
    },
}


def _envelope_schema(data: dict) -> dict:
    return {"type": "object", "required": ["ok", "contract", "version", "operation"],
            "properties": {"ok": {"type": "boolean"}, "contract": {"const": CONTRACT},
                           "version": {"const": VERSION}, "operation": {"type": "string"},
                           "data": data, "error": {"type": "object"}}}


def openapi_paths() -> dict:
    """The two GET operations, for the helper's OpenAPI document."""
    errors = {
        "400": {"description": "invalid_request: an unknown or malformed parameter."},
        "403": {"description": "Missing or invalid X-Uoink-Token."},
        "404": {"description": "not_found: no saved item has that id."},
    }
    item_data = {"type": "object", "properties": {
        "item": _ITEM_SCHEMA,
        "timing": {"type": "object", "properties": {
            "source": {"type": ["string", "null"], "enum": [*TIMING_SOURCES, None]},
            "caption_kind_known": {"type": "boolean"},
            "word_timings": {"type": "boolean"}}},
        "range": {"type": "object"},
        "cue_count": {"type": "integer", "description": "Cues in this response."},
        "held_count": {"type": "integer", "description": "Total held lines in this saved item."},
        "review_note": {"type": "string", "description": "Why transcript lines were held back."},
        "page": {"type": "object", "description": "limit, offset, total cues in the window, next_offset."},
        "cues": {"type": "array", "items": _CUE_SCHEMA},
    }}
    list_data = {"type": "object", "properties": {
        "filters": {"type": "object"}, "page": {"type": "object"},
        "items": {"type": "array", "items": {"type": "object"}}}}
    day = {"type": "string", "format": "date"}
    return {
        ITEM_PREFIX: {"get": {
            "operationId": "list_timed_cue_items",
            "summary": "List saved items by show and original publish date",
            "description": ("Saved items filtered by words, show (channel), original publish "
                            "date and capture date, with a cues_url for each. Local reads only."),
            "parameters": [
                _query_param("q", "Words to search for.", {"type": "string"}),
                _query_param("channel", "Exact show or channel name.", {"type": "string"}),
                _query_param("published_from", "Earliest original publish date, inclusive.", day),
                _query_param("published_to", "Latest original publish date, inclusive.", day),
                _query_param("date_from", "Earliest capture date, inclusive.", day),
                _query_param("date_to", "Latest capture date, inclusive.", day),
                _query_param("limit", f"1 to {MAX_LIMIT} (default {DEFAULT_LIMIT}).",
                             {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}),
                _query_param("offset", "Start position.", {"type": "integer", "minimum": 0}),
            ],
            "responses": {"200": {"description": "uoink.cues.read v1 list envelope.",
                                  "content": {"application/json": {"schema": _envelope_schema(list_data)}}},
                          **{k: v for k, v in errors.items() if k != "404"}},
            "security": [{"UoinkToken": []}],
        }},
        ITEM_PREFIX + "/{id}": {"get": {
            "operationId": "get_timed_cues",
            "summary": "Timed transcript cues for one saved item",
            "description": ("Cues as {start, end, text} in seconds, where the timings came from "
                            "(captions, auto_captions or local_asr), the original publish date, "
                            "duration and source URL. Local reads only."),
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string"},
                 "description": "Item id from search, recent or the list call."},
                _query_param("start", "Only cues that overlap from this second.", {"type": "number", "minimum": 0}),
                _query_param("end", "Only cues that overlap up to this second.", {"type": "number", "minimum": 0}),
                _query_param("limit", f"Most cues, 1 to {CUE_MAX_LIMIT} (default {CUE_DEFAULT_LIMIT}).",
                             {"type": "integer", "minimum": 1, "maximum": CUE_MAX_LIMIT}),
                _query_param("offset", "Start position in the window. Use page.next_offset.",
                             {"type": "integer", "minimum": 0}),
                _query_param("include_words", "0 leaves word timings out (default 1).",
                             {"type": "string", "enum": ["0", "1", "true", "false"]}),
                _query_param("include_held", "1 includes held lines in this export (default 0).",
                             {"type": "string", "enum": ["0", "1", "true", "false"]}),
            ],
            "responses": {"200": {"description": "uoink.cues.read v1 item envelope.",
                                  "content": {"application/json": {"schema": _envelope_schema(item_data)}}},
                          **errors},
            "security": [{"UoinkToken": []}],
        }},
    }
