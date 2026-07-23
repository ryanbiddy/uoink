"""v3.2 Writing Studio — tweets, threads, blogs grounded in any uoink.

Suite-split ownership: this is a live Uoink product surface. `server.py` and
`uoink_mcp_tools.py` call it, and `build.ps1` stages it into the installer.
Writer is a separate product; removing this module requires an explicit
decision to remove Uoink's in-app Writing Studio and its HTTP/MCP callers.

Per PROMPT-V3.2-CC-BACKEND.md Deliverable 1. Sibling of scripts.py;
shares the same two-phase contract pattern (Phase 1 = grounding, Phase 2
= persist agent output) and the same Voice DNA enforcement (prepend at
generation time, scan post-generation, structured warnings, NEVER
auto-block).

Locked answers (per Ryan in the prompt):
1. Substack-style anchors: capped at 10, accept URL OR raw text, user
   names each. URL ingestion uses extract_page (universal site PR) when
   available -- falls back gracefully when it isn't.
2. Voice DNA: SOFT WARN, not auto-block. Structured warnings returned
   alongside the output. Settings keys honour user preference.
3. Creator credit non-suppressible. 400 on suppression attempt.
4. Compute: model-agnostic. Agent does LLM work via MCP; helper persists
   structure + scans + builds grounding payload.

Module surface mirrors scripts.py + claims.py shape.
Transport (HTTP + MCP) is owned by server.py + uoink_mcp_tools.py."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import voice_dna

log = logging.getLogger("uoink.writing_studio")

KIND_TWEET = "tweet"
KIND_THREAD = "thread"
KIND_BLOG = "blog"
_KINDS = (KIND_TWEET, KIND_THREAD, KIND_BLOG)

COMPUTE_MODE_AGENT = "agent"
COMPUTE_MODE_BYO_KEY = "byo_key"
_MODES = (COMPUTE_MODE_AGENT, COMPUTE_MODE_BYO_KEY)

ANCHOR_SOURCE_URL = "url"
ANCHOR_SOURCE_TEXT = "text"
_ANCHOR_SOURCES = (ANCHOR_SOURCE_URL, ANCHOR_SOURCE_TEXT)

STYLE_ANCHOR_CAP = 10  # Ryan's locked answer #4

# v3.2.3 hook-type lens (generation intent). The redesigned Generate tab shows
# these 9 as quick-fill chips for tweet / thread / blog / script. This is the
# GENERATION lens, distinct from server.HOOK_TYPES (the classification taxonomy
# the hook detector emits); they intentionally differ. Each value maps to a
# one-line directive folded into the grounding so the agent biases the opening
# toward that style. Free-form `angle` still works alongside it.
HOOK_LENS_TYPES = {
    "informative": "Lead with the single most useful fact, stated plainly.",
    "engagement_bait": "Open with a line built to pull a reply or a save.",
    "disappointment_contrarian": "Open by overturning a common belief the audience holds.",
    "curiosity_gap": "Open with a gap the reader needs the rest to close.",
    "stakes": "Open by naming what's at risk if they get this wrong.",
    "success_case_study": "Open on a concrete win and the result it produced.",
    "failure_lesson": "Open on a specific failure and the lesson it taught.",
    "question_open_loop": "Open with a question that stays unanswered until the payoff.",
    "frame_shift": "Open by reframing the topic so it reads in a new light.",
}


def normalize_hook_lens(value) -> str | None:
    """Validate a hook_type_lens value against HOOK_LENS_TYPES. Returns the
    lens key (or None when unset/empty). Raises ValueError with `.http_status`
    on an unrecognized non-empty value so the transport returns 400."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or value.strip() not in HOOK_LENS_TYPES:
        e = ValueError(
            "hook_type_lens must be one of " + ", ".join(sorted(HOOK_LENS_TYPES)))
        e.http_status = 400
        raise e
    return value.strip()


def hook_lens_grounding(lens: str | None) -> dict | None:
    """Shape a hook lens into the grounding payload: {type, directive}. None
    when no lens is set."""
    if not lens:
        return None
    return {"type": lens, "directive": HOOK_LENS_TYPES[lens]}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


# ---- style anchors -----------------------------------------------------
def _shape_anchor(row) -> dict | None:
    """Shape a style_anchors row for the API. Maps the `is_default` column
    (migration 0016) to a clean `default` boolean. Tolerant of pre-0016 rows
    that lack the column (defaults to False)."""
    if row is None:
        return None
    d = dict(row)
    d["default"] = bool(d.pop("is_default", 0))
    return d


def list_style_anchors(idx, *, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM style_anchors"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY added_at DESC"
    rows = idx._conn.execute(sql).fetchall()
    return [_shape_anchor(r) for r in rows]


def list_default_anchors(idx) -> list[dict]:
    """The curated default anchors (is_default=1), for the 'Browse defaults'
    UI. Includes each one's current active flag so the toggle reflects state."""
    rows = idx._conn.execute(
        "SELECT * FROM style_anchors WHERE is_default = 1 ORDER BY name"
    ).fetchall()
    return [_shape_anchor(r) for r in rows]


def get_style_anchor(idx, anchor_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM style_anchors WHERE id=?", (anchor_id,)).fetchone()
    return _shape_anchor(row)


def style_anchor_count(idx) -> int:
    row = idx._conn.execute(
        "SELECT COUNT(*) AS c FROM style_anchors").fetchone()
    return int(row["c"]) if row else 0


def active_style_anchor_count(idx) -> int:
    """The cap (STYLE_ANCHOR_CAP) counts ACTIVE anchors, not total. Inactive
    seeded defaults don't consume a user's slots; activating one does."""
    row = idx._conn.execute(
        "SELECT COUNT(*) AS c FROM style_anchors WHERE active = 1").fetchone()
    return int(row["c"]) if row else 0


def seed_default_anchors(idx, anchors: list[dict]) -> int:
    """Seed the curated defaults idempotently, per anchor. Inserts any default
    that is missing (matched by is_default=1 + name) and leaves existing rows
    untouched, so it runs safely on every boot. Returns how many were newly
    inserted.

    Critically this is NOT gated on the whole table being empty: an upgrading
    user who already has custom anchors still gets the five defaults seeded
    alongside them (the "Browse defaults" UI needs real DB ids to toggle).
    Defaults seed inactive (active=0), so they don't count against the cap and
    never override a user's curation. A default the user has already activated
    keeps its active state because we skip names that already exist as defaults.
    """
    if not anchors:
        return 0
    seeded = 0
    with idx._lock:
        existing = {
            (r["name"] or "") for r in idx._conn.execute(
                "SELECT name FROM style_anchors WHERE is_default = 1").fetchall()
        }
        for a in anchors:
            if not isinstance(a, dict):
                continue
            name = (a.get("name") or "").strip()[:80]
            if not name or name in existing:
                continue
            source_type = a.get("source_type") or ANCHOR_SOURCE_TEXT
            if source_type not in _ANCHOR_SOURCES:
                source_type = ANCHOR_SOURCE_TEXT
            idx._conn.execute(
                "INSERT INTO style_anchors "
                "(name, source_type, source_url, raw_text, active, "
                " is_default, added_at) VALUES (?, ?, ?, ?, 0, 1, ?)",
                (name, source_type, a.get("source_url"),
                 a.get("raw_text"), _now_iso()))
            existing.add(name)
            seeded += 1
    if seeded:
        log.info("seeded %d default style anchors", seeded)
    return seeded


def add_style_anchor(idx, *, name: str, source_type: str,
                       source_value: str,
                       url_to_prose=None) -> dict:
    """Insert a new anchor. Caps at STYLE_ANCHOR_CAP. Raises ValueError
    with a 422-shaped error tag when the cap is exceeded so the
    transport can map it to HTTP 422.

    `url_to_prose` is an optional callable (helper-supplied) that takes
    a URL and returns extracted prose. When source_type='url' and
    url_to_prose is provided, raw_text gets populated with the extracted
    prose. Falls back to leaving raw_text NULL when the callable raises
    or isn't supplied -- the anchor still saves, just without
    pre-extracted text. The dashboard surfaces a 'no preview' state."""
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    if len(name) > 80:
        raise ValueError("name too long (max 80 chars)")
    if source_type not in _ANCHOR_SOURCES:
        raise ValueError(f"source_type must be one of {list(_ANCHOR_SOURCES)}")
    source_value = (source_value or "").strip()
    if not source_value:
        raise ValueError("source_value required")

    if active_style_anchor_count(idx) >= STYLE_ANCHOR_CAP:
        # 422-shaped: caller already has the maximum ACTIVE anchors. The cap
        # is on active (not total) so inactive seeded defaults don't block adds.
        e = ValueError(
            f"active style anchors capped at {STYLE_ANCHOR_CAP}; "
            f"deactivate one before adding another")
        e.http_status = 422  # transport reads this
        raise e

    source_url = None
    raw_text = None
    if source_type == ANCHOR_SOURCE_URL:
        source_url = source_value
        if callable(url_to_prose):
            try:
                raw_text = url_to_prose(source_value)
            except Exception as exc:
                log.warning("style anchor url -> prose extraction failed: %s",
                              exc)
                raw_text = None
    else:
        raw_text = source_value

    with idx._lock:
        cur = idx._conn.execute(
            "INSERT INTO style_anchors "
            "(name, source_type, source_url, raw_text, active, added_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (name, source_type, source_url, raw_text, _now_iso()))
    return get_style_anchor(idx, cur.lastrowid or 0) or {}


def update_style_anchor(idx, anchor_id: int, *,
                          name: str | None = None,
                          active: bool | None = None) -> dict | None:
    row = get_style_anchor(idx, anchor_id)
    if not row:
        return None
    new_name = row["name"]
    new_active = row["active"]
    if name is not None:
        clean = (name or "").strip()
        if not clean:
            raise ValueError("name cannot be empty")
        if len(clean) > 80:
            raise ValueError("name too long (max 80 chars)")
        new_name = clean
    if active is not None:
        new_active = 1 if active else 0
        # Activating counts against the cap (same rule as add_style_anchor).
        # Only check when flipping inactive -> active; re-saving an already
        # active anchor (e.g. a rename) must not trip the cap.
        if new_active and not row["active"] \
                and active_style_anchor_count(idx) >= STYLE_ANCHOR_CAP:
            err = ValueError(
                f"active style anchors capped at {STYLE_ANCHOR_CAP}; "
                "deactivate one before activating another")
            err.http_status = 422
            raise err
    with idx._lock:
        idx._conn.execute(
            "UPDATE style_anchors SET name=?, active=? WHERE id=?",
            (new_name, new_active, anchor_id))
    return get_style_anchor(idx, anchor_id)


def remove_style_anchor(idx, anchor_id: int) -> bool:
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM style_anchors WHERE id=?", (anchor_id,))
        return cur.rowcount > 0


# ---- creator credit ----------------------------------------------------
def build_credit_line(yoink_row: dict | None, *, kind: str) -> str:
    """Build the creator-credit string that gets appended to the output.
    Non-suppressible per Ryan's directive.

    Tweet/thread shape: 'via @<handle> · <short_link>'
    Blog shape: 'Source: <title> by <creator> -- <url>'

    Falls back gracefully when the yoink_row lacks fields -- we always
    end up with SOME credit (worst case 'Source: Uoink corpus' with no
    link). Callers MUST include this output verbatim in the body or
    persist it in source_credit_line for the dashboard to attach."""
    if not yoink_row:
        return ("Source: from Uoink corpus" if kind == KIND_BLOG
                else "via Uoink corpus")
    title = (yoink_row.get("title") or "").strip()
    channel = (yoink_row.get("channel") or "").strip()
    channel_url = (yoink_row.get("channel_url") or "").strip()
    yoink_url = (yoink_row.get("url") or "").strip()
    handle = _channel_handle(channel_url, channel)
    if kind == KIND_BLOG:
        bits = ["Source:"]
        if title:
            bits.append(title)
        if channel:
            bits.append(f"by {channel}")
        if yoink_url:
            bits.append(f"-- {yoink_url}")
        return " ".join(bits)
    handle_str = f"@{handle}" if handle else (channel or "the creator")
    return f"via {handle_str} · {yoink_url}" if yoink_url else f"via {handle_str}"


def _channel_handle(channel_url: str, channel_name: str) -> str | None:
    """Try to pull a clean @handle from the YouTube channel URL. Falls
    back to None when the URL doesn't carry one (the credit line then
    uses the channel display name instead)."""
    if not channel_url:
        return None
    # https://www.youtube.com/@HandleName -> HandleName
    if "/@" in channel_url:
        h = channel_url.rsplit("/@", 1)[-1].strip("/").split("/", 1)[0]
        return h or None
    return None


# ---- grounding payload (Phase 1 of two-phase generation) --------------
def assemble_grounding(idx, yoink_id: str, *,
                         style_anchor_ids: list[int] | None = None,
                         hook_type_lens: str | None = None) -> dict:
    """Pull the source yoink + active anchors + voice DNA + creator
    credit line into a structured payload the agent uses to write.

    Returns:
        {
          source_yoink: {...},
          source_credit: {tweet: '...', blog: '...'},
          style_anchors: [{id, name, raw_text}, ...],
          hook_lens: {type, directive} | None,
          voice_dna_prompt: '...',
          warning_copy: '...',
        }

    Pure local read. `hook_type_lens` is validated by the caller
    (normalize_hook_lens); here it's just shaped into the grounding."""
    yoink = idx.get_yoink(yoink_id) if yoink_id else None
    anchors_all = list_style_anchors(idx, active_only=False)
    if style_anchor_ids:
        chosen_set = {int(i) for i in style_anchor_ids}
        anchors = [a for a in anchors_all if a["id"] in chosen_set]
    else:
        anchors = [a for a in anchors_all if a.get("active")]

    return {
        "source_yoink": yoink,
        "source_credit": {
            KIND_TWEET: build_credit_line(yoink, kind=KIND_TWEET),
            KIND_THREAD: build_credit_line(yoink, kind=KIND_TWEET),
            KIND_BLOG: build_credit_line(yoink, kind=KIND_BLOG),
        },
        "style_anchors": [
            {"id": a["id"], "name": a["name"],
             "source_type": a["source_type"],
             "raw_text": a.get("raw_text") or ""}
            for a in anchors
        ],
        "hook_lens": hook_lens_grounding(hook_type_lens),
        "voice_dna_prompt": voice_dna.VOICE_DNA_PROMPT,
        "warning_copy": voice_dna.warning_copy(),
    }


# ---- persist (Phase 2) -------------------------------------------------
def _check_credit_present(body: str, credit_line: str) -> bool:
    """Locked: creator credit is non-suppressible. The agent's output
    body MUST include the credit line (or an equivalent) verbatim.
    Returns True if present; False otherwise -- transport raises 400.

    The check is forgiving: any substring match against either the
    handle-form ('via @...') or a normalised URL match counts. We do not
    require character-for-character equality because writers may
    reposition the credit, surround it with parens, etc."""
    if not credit_line:
        return True
    if not body:
        return False
    lower_body = body.lower()
    # The credit either contains a URL or a @handle. Either one being
    # present in the body counts.
    if " via @" in lower_body or "\nvia @" in lower_body:
        return True
    if credit_line.lower() in lower_body:
        return True
    if "source:" in lower_body and credit_line.lower().split("source:", 1)[-1].strip() in lower_body:
        return True
    return False


def persist_piece(idx, *, yoink_id: str | None,
                    kind: str,
                    body: str,
                    title: str | None = None,
                    dek: str | None = None,
                    tags: list | None = None,
                    source_credit_line: str,
                    style_anchor_ids: list | None = None,
                    angle: str | None = None,
                    target_length: int | None = None,
                    mode: str = COMPUTE_MODE_AGENT,
                    parent_id: int | None = None,
                    voice_dna_warnings_enabled: bool = True,
                    skip_voice_dna_this_time: bool = False,
                    suppress_credit: bool = False) -> dict:
    """Write a generated piece + run Voice DNA scan + return the full
    structured response (body + voice_warnings + warning_copy when
    relevant).

    Raises:
      ValueError on validation errors. Each has `.http_status` so the
      transport returns the right code (400 / 422).
      Specifically: suppress_credit=True → 400 (locked answer #3).

    Voice DNA scan policy (locked answer #3 -- SOFT WARN):
      - When `voice_dna_warnings_enabled=False` (settings) or
        `skip_voice_dna_this_time=True` (per-generation flag), skip
        the scan entirely and return voice_warnings=[].
      - Otherwise, run voice_dna.scan(body), persist the warnings JSON,
        return them alongside the body. NEVER auto-block.
    """
    if kind not in _KINDS:
        e = ValueError(f"kind must be one of {list(_KINDS)}")
        e.http_status = 400
        raise e
    if mode not in _MODES:
        e = ValueError(f"mode must be one of {list(_MODES)}")
        e.http_status = 400
        raise e
    if not body or not isinstance(body, str):
        e = ValueError("body required (non-empty string)")
        e.http_status = 400
        raise e
    if suppress_credit:
        e = ValueError(
            "creator credit is required and cannot be suppressed; "
            "remove suppress_credit from the request and re-issue")
        e.http_status = 400
        raise e
    if not source_credit_line:
        e = ValueError("source_credit_line required")
        e.http_status = 400
        raise e
    if not _check_credit_present(body, source_credit_line):
        e = ValueError(
            "body does not contain the creator credit. Per the locked "
            "Voice DNA spec, the credit MUST appear in the output. Add "
            f"the credit line ('{source_credit_line}') to the body and "
            "re-submit, or include it via the agent's writing.")
        e.http_status = 400
        raise e

    if voice_dna_warnings_enabled and not skip_voice_dna_this_time:
        warnings = voice_dna.scan(body)
    else:
        warnings = []

    with idx._lock:
        cur = idx._conn.execute(
            "INSERT INTO writing_pieces "
            "(yoink_id, kind, version, parent_id, title, dek, body, "
            " tags, source_credit_line, voice_warnings, "
            " style_anchor_ids, mode, generated_at, angle, target_length) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (yoink_id, kind, _next_version(idx, yoink_id, parent_id),
             parent_id, title, dek, body,
             json.dumps(tags or []), source_credit_line,
             json.dumps(warnings),
             json.dumps(style_anchor_ids or []),
             mode, _now_iso(), angle, target_length))
        piece_id = cur.lastrowid or 0

    return {
        "id": piece_id,
        "kind": kind,
        "body": body,
        "title": title,
        "dek": dek,
        "tags": tags or [],
        "source_credit_line": source_credit_line,
        "voice_warnings": warnings,
        "warning_copy": (voice_dna.warning_copy() if warnings else None),
        "mode": mode,
        "parent_id": parent_id,
        "yoink_id": yoink_id,
    }


def _next_version(idx, yoink_id: str | None,
                    parent_id: int | None) -> int:
    if parent_id:
        row = idx._conn.execute(
            "SELECT version FROM writing_pieces WHERE id=?",
            (parent_id,)).fetchone()
        return (int(row["version"]) + 1) if row else 1
    if not yoink_id:
        return 1
    row = idx._conn.execute(
        "SELECT MAX(version) AS v FROM writing_pieces WHERE yoink_id=?",
        (yoink_id,)).fetchone()
    return (int(row["v"]) + 1) if row and row["v"] else 1


# ---- read paths --------------------------------------------------------
def _shape_piece(row: dict | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    for k in ("tags", "voice_warnings", "style_anchor_ids"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    return d


def get_piece(idx, piece_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM writing_pieces WHERE id=?",
        (piece_id,)).fetchone()
    return _shape_piece(dict(row) if row else None)


def list_pieces(idx, *, kind: str | None = None,
                  yoink_id: str | None = None,
                  limit: int = 100) -> list[dict]:
    wheres = []
    params: list = []
    if kind:
        if kind not in _KINDS:
            raise ValueError(f"kind must be one of {list(_KINDS)}")
        wheres.append("kind=?")
        params.append(kind)
    if yoink_id:
        wheres.append("yoink_id=?")
        params.append(yoink_id)
    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(max(1, min(int(limit), 500)))
    rows = idx._conn.execute(
        "SELECT * FROM writing_pieces" + where_sql +
        " ORDER BY generated_at DESC LIMIT ?",
        params).fetchall()
    return [_shape_piece(dict(r)) for r in rows]


# ---- composer support (D-19 char count / thread builder, D-18 attribution) --
TWEET_LIMIT = 280

# X collapses every URL to a t.co link of fixed weight, so a long URL costs
# the same 23 characters as a short one. We don't implement X's full CJK
# weighting table (rare in this audience's drafts); plain text counts as
# Unicode code points, which is exact for Latin copy and a slight under-count
# for CJK. Good enough for an over-280 guard, and we never hard-block.
URL_WEIGHTED_LEN = 23
_URL_RE = re.compile(r"https?://\S+")

# D-18 A: native attribution. The creator credit (build_credit_line) is
# non-suppressible; this attribution fragment is REMOVABLE before publish and
# ships on by default. AG owns the final wording -- these strings are
# Voice-DNA-clean (no em dash, contraction-friendly) pending AG's pass.
NATIVE_ATTRIBUTION_DOMAIN = "uoink.app"
BLOG_ATTRIBUTION_LINE = "Captured with uoink.app. Local corpus, creator credit kept."


def tweet_length(text: str) -> int:
    """X-style weighted length for the composer's over-280 guard: every URL
    counts as 23 chars (t.co), the rest as Unicode code points."""
    if not text:
        return 0
    url_count = len(_URL_RE.findall(text))
    without_urls = _URL_RE.sub("", text)
    return len(without_urls) + url_count * URL_WEIGHTED_LEN


def assemble_footer(credit_line: str, kind: str, *,
                     attribution_enabled: bool = True) -> str:
    """Compose the publish footer: the non-suppressible creator credit plus
    the removable native attribution (D-18 A) when enabled. Tweets/threads
    append ` · uoink.app` to the credit line; blogs get the attribution on
    its own line under the Source credit."""
    credit_line = credit_line or ""
    if kind == KIND_BLOG:
        if attribution_enabled:
            return f"{credit_line}\n{BLOG_ATTRIBUTION_LINE}".strip()
        return credit_line
    suffix = f" · {NATIVE_ATTRIBUTION_DOMAIN}" if attribution_enabled else ""
    return f"{credit_line}{suffix}"


def validate_composition(idx, *, yoink_id: str | None, kind: str,
                          tweets: list[str] | None = None,
                          attribution_enabled: bool = True) -> dict:
    """Pure pre-publish computation for the Writing Studio composer (D-19).

    Returns per-tweet char counts + over-280 flags + total tweet count for
    threads, the non-suppressible credit line, and the removable native
    attribution footer (D-18 A). No persistence, no LLM call -- the composer
    UI calls this on every keystroke to render counts and the attribution
    preview. The footer appends to the LAST tweet, so that tweet also gets a
    `*_with_footer` count the UI uses to warn before publish."""
    if kind not in _KINDS:
        e = ValueError(f"kind must be one of {list(_KINDS)}")
        e.http_status = 400
        raise e

    yoink = idx.get_yoink(yoink_id) if yoink_id else None
    credit_kind = KIND_BLOG if kind == KIND_BLOG else KIND_TWEET
    credit_line = build_credit_line(yoink, kind=credit_kind)
    footer = assemble_footer(credit_line, kind,
                              attribution_enabled=attribution_enabled)

    out: dict = {
        "kind": kind,
        "limit": TWEET_LIMIT,
        "credit_line": credit_line,
        "attribution_enabled": bool(attribution_enabled),
        "footer_text": footer,
    }

    if kind == KIND_BLOG:
        out["attribution_line"] = (BLOG_ATTRIBUTION_LINE
                                    if attribution_enabled else "")
        return out

    tweets = [t if isinstance(t, str) else "" for t in (tweets or [])]
    per: list[dict] = []
    for i, text in enumerate(tweets):
        count = tweet_length(text)
        per.append({
            "index": i,
            "char_count": count,
            "over_limit": count > TWEET_LIMIT,
            "remaining": TWEET_LIMIT - count,
        })

    footer_target = len(per) - 1 if per else None
    footer_count = tweet_length(footer)
    over_with_footer = False
    if footer_target is not None:
        combined = (tweets[footer_target].rstrip() + "\n\n" + footer).strip()
        combined_count = tweet_length(combined)
        over_with_footer = combined_count > TWEET_LIMIT
        per[footer_target]["char_count_with_footer"] = combined_count
        per[footer_target]["remaining_with_footer"] = TWEET_LIMIT - combined_count
        per[footer_target]["over_limit_with_footer"] = over_with_footer

    out.update({
        "total_tweets": len(per),
        "tweets": per,
        "footer_target_index": footer_target,
        "footer_char_count": footer_count,
        "over_limit_any": any(p["over_limit"] for p in per) or over_with_footer,
    })
    return out
