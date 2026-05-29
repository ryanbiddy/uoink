"""v3 A2 claim extraction + verification backend.

LOCKED FRAMING (ROADMAP A2): claim extraction + verification ASSISTANCE.
Never auto-assert "this creator lied." Surface checkable claims with
evidence + sources -- the user judges. Tool descriptions + dashboard
copy enforce this; the module mirrors the constraint with an
`alignment_signal` enum that has no "true" / "false" / "lie" value.

Loki inspiration (vendor/loki/): the 5-step OpenFactVerification pipeline
underpins the design: decompose -> assess check-worthiness -> generate
queries -> retrieve evidence -> surface evidence. This module owns the
PERSISTENCE for those steps; the LLM compute happens in the calling
agent via MCP per locked compute policy.

Module surface:
  - extract_claims (persist a list of claims for a video; mode='agent')
  - verify_claim (record evidence + alignment signal for one claim)
  - list_claims, get_claim, get_claims_for_video

This module is transport-agnostic. server.py drives the HTTP layer +
uoink_mcp_tools.py drives the MCP layer."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

log = logging.getLogger("uoink.claims")

# ---- enums + constraints ------------------------------------------------
# Status flow: extracted -> verified | not-attempted.
STATUS_EXTRACTED = "extracted"
STATUS_VERIFIED = "verified"
STATUS_NOT_ATTEMPTED = "not-attempted"
_STATUSES = (STATUS_EXTRACTED, STATUS_VERIFIED, STATUS_NOT_ATTEMPTED)

# Locked vocabulary: NEVER 'true' / 'false' / 'lie' / 'verified-as-X'.
# These signals describe the relationship between the evidence and the
# claim, not a verdict on the claim itself. The user judges the verdict.
ALIGNMENT_SUPPORTS = "supports"
ALIGNMENT_CONTRADICTS = "contradicts"
ALIGNMENT_MIXED = "mixed"
ALIGNMENT_INCONCLUSIVE = "inconclusive"
_ALIGNMENTS = (
    ALIGNMENT_SUPPORTS, ALIGNMENT_CONTRADICTS,
    ALIGNMENT_MIXED, ALIGNMENT_INCONCLUSIVE,
)

# Source of compute. Agent path is the locked default per ROADMAP A2;
# byo_key is a future on-server worker pool, scaffolded but not active.
COMPUTE_MODE_AGENT = "agent"
COMPUTE_MODE_BYO_KEY = "byo_key"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _validate_claim_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("claim_text required")
    if len(text) > 1024:
        raise ValueError("claim_text too long (max 1024 chars)")
    return text


def _validate_check_worthiness(score: Any) -> float | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        raise ValueError("check_worthiness must be a number in [0.0, 1.0]")
    if not (0.0 <= s <= 1.0):
        raise ValueError("check_worthiness must be in [0.0, 1.0]")
    return s


# ---- extraction ---------------------------------------------------------
def extract_claims(idx, video_id: str, *, claims: list[dict],
                    mode: str = COMPUTE_MODE_AGENT) -> dict:
    """Persist a batch of agent-extracted claims. Each claim dict:
        {claim_text, check_worthiness?, context?: {timestamp, speaker, ...}}

    `mode` indicates which path produced the claims (agent | byo_key).
    Returns the inserted row ids."""
    if not video_id or not isinstance(video_id, str):
        return {"ok": False, "error": "video_id required"}
    if mode not in (COMPUTE_MODE_AGENT, COMPUTE_MODE_BYO_KEY):
        return {"ok": False, "error":
                f"mode must be one of {COMPUTE_MODE_AGENT}, {COMPUTE_MODE_BYO_KEY}"}
    if not isinstance(claims, list):
        return {"ok": False, "error": "claims must be a list"}

    now = _now_iso()
    inserted: list[int] = []
    errors: list[str] = []
    with idx._lock:
        for c in claims:
            if not isinstance(c, dict):
                errors.append("non-dict claim skipped")
                continue
            try:
                text = _validate_claim_text(c.get("claim_text"))
                worth = _validate_check_worthiness(c.get("check_worthiness"))
            except ValueError as e:
                errors.append(str(e))
                continue
            ctx = c.get("context")
            ctx_blob = json.dumps(ctx) if isinstance(ctx, dict) else None
            cur = idx._conn.execute(
                "INSERT INTO claims "
                "(video_id, claim_text, check_worthiness, status, "
                "evidence, extracted_at, context_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (video_id, text, worth, STATUS_EXTRACTED, "[]", now, ctx_blob))
            if cur.lastrowid:
                inserted.append(cur.lastrowid)
    return {"ok": True, "video_id": video_id, "inserted_ids": inserted,
            "errors": errors, "mode": mode}


# ---- verification -------------------------------------------------------
def verify_claim(idx, claim_id: int, *, evidence: list[dict],
                  mode: str = COMPUTE_MODE_AGENT) -> dict:
    """Record evidence for one claim. Each evidence dict:
        {source_url, quote, alignment_signal}

    alignment_signal MUST be one of supports | contradicts | mixed |
    inconclusive. NEVER 'true' / 'false' / 'lie' / 'verified-as-X'. This
    enforces the ROADMAP A2 assistance posture: we surface signals, the
    user judges the verdict."""
    if mode not in (COMPUTE_MODE_AGENT, COMPUTE_MODE_BYO_KEY):
        return {"ok": False, "error":
                f"mode must be one of {COMPUTE_MODE_AGENT}, {COMPUTE_MODE_BYO_KEY}"}
    if not isinstance(evidence, list):
        return {"ok": False, "error": "evidence must be a list"}

    row = idx._conn.execute(
        "SELECT id, video_id FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not row:
        return {"ok": False, "error": f"claim not found: {claim_id}"}

    clean: list[dict] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            return {"ok": False, "error":
                    "each evidence entry must be a JSON object"}
        align = (ev.get("alignment_signal") or "").strip()
        if align not in _ALIGNMENTS:
            return {"ok": False, "error":
                    (f"alignment_signal must be one of {list(_ALIGNMENTS)} -- "
                     "NEVER 'true'/'false'/'lie' (assistance posture)")}
        src = (ev.get("source_url") or "").strip()
        quote = (ev.get("quote") or "").strip()
        if not src or not quote:
            return {"ok": False, "error":
                    "each evidence entry needs source_url + quote"}
        clean.append({
            "source_url": src, "quote": quote[:1024],
            "alignment_signal": align,
        })
    with idx._lock:
        idx._conn.execute(
            "UPDATE claims SET evidence=?, status=?, verified_at=? WHERE id=?",
            (json.dumps(clean), STATUS_VERIFIED, _now_iso(), claim_id))
    return {"ok": True, "claim_id": claim_id, "evidence_count": len(clean),
            "mode": mode}


# ---- read paths ---------------------------------------------------------
def _row_to_dict(row: dict | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    try:
        d["evidence"] = json.loads(d.get("evidence") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["evidence"] = []
    if d.get("context_json"):
        try:
            d["context"] = json.loads(d["context_json"])
        except (json.JSONDecodeError, TypeError):
            d["context"] = None
    else:
        d["context"] = None
    d.pop("context_json", None)
    return d


def get_claim(idx, claim_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return _row_to_dict(row)


def get_claims_for_video(idx, video_id: str, *,
                          limit: int = 200) -> list[dict]:
    rows = idx._conn.execute(
        "SELECT * FROM claims WHERE video_id=? "
        "ORDER BY check_worthiness DESC NULLS LAST, id ASC LIMIT ?",
        (video_id, max(1, min(int(limit), 1000)))).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_claims(idx, *, video_id: str | None = None,
                  status: str | None = None,
                  limit: int = 200) -> list[dict]:
    wheres: list[str] = []
    params: list = []
    if video_id:
        wheres.append("video_id=?")
        params.append(video_id)
    if status:
        if status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}")
        wheres.append("status=?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(max(1, min(int(limit), 1000)))
    rows = idx._conn.execute(
        f"SELECT * FROM claims{where_sql} "
        f"ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_not_attempted(idx, claim_id: int) -> bool:
    """User-initiated 'skip verification' (per ROADMAP A2 status enum)."""
    with idx._lock:
        cur = idx._conn.execute(
            "UPDATE claims SET status=?, verified_at=? WHERE id=?",
            (STATUS_NOT_ATTEMPTED, _now_iso(), claim_id))
        return cur.rowcount > 0
