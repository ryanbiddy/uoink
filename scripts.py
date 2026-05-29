"""v3 P5 Script Studio backend.

Generate structured video scripts grounded in corpus + taste anchors.
Sits on top of P4 (Build Workspace) -- a script is always tied to a
workspace_id so the helper can resolve the workspace's assembled
corpus slice, the user's taste anchors (when S4 is available), and
the optional self-channel performance snapshot.

Compute policy (locked, model-agnostic by default): mirror of P4's
two-phase critique tool.

Phase 1 (no `script` payload): helper returns the GROUNDING CONTEXT
the agent needs to write a script -- the assembled yoinks, audience
questions from comments, optional taste anchors from S4, optional
self-channel snapshot from P3. The agent writes the script using its
own model.

Phase 2 (`script` payload present): helper persists the structured
script the agent produced -- hook, beats, body, CTA, shot_list,
source_yoinks citations.

Shot list is derived per ROADMAP P5's bonus output -- a separate tool
+ endpoint that processes an existing script row into a per-scene
B-roll checklist based on the script's `beats` + the workspace's
`format` facet.

This module owns NO transport. server.py drives HTTP, uoink_mcp_tools.py
drives MCP."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

log = logging.getLogger("uoink.scripts")

# ---- compute modes -------------------------------------------------------
COMPUTE_MODE_AGENT = "agent"
COMPUTE_MODE_BYO_KEY = "byo_key"
_MODES = (COMPUTE_MODE_AGENT, COMPUTE_MODE_BYO_KEY)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ---- helpers -------------------------------------------------------------
def _next_version(idx, workspace_id: str) -> int:
    row = idx._conn.execute(
        "SELECT MAX(version) AS v FROM scripts WHERE workspace_id=?",
        (workspace_id,)).fetchone()
    current = (row["v"] if row else 0) or 0
    return int(current) + 1


def _validate_json_list(value: Any, *, field: str) -> str:
    """Accept either a list (JSON-serialise it) or a string (assume the
    caller already serialised). Returns a JSON string."""
    if isinstance(value, str):
        return value or "[]"
    if value is None:
        return "[]"
    if isinstance(value, list):
        return json.dumps(value)
    raise ValueError(f"{field} must be a list or JSON string")


# ---- grounding context ---------------------------------------------------
def assemble_grounding(idx, workspace_id: str, *,
                        style_anchors: bool = True) -> dict:
    """Pull everything the agent needs to write a script:
      - Workspace metadata (format, topic, hook_target, etc.)
      - Assembled corpus slice (re-run if empty; reuse if populated)
      - Audience questions from comments_json
      - Self-channel snapshot when your_channel is set
      - S4 taste anchors when memory_layer is available (graceful)

    Pure local read. No LLM, no outbound. Returned dict is the phase-1
    response of generate_script."""
    # Late import -- workspaces.py owns the assembler + workspace CRUD;
    # depending on it from scripts.py is acceptable because the P5
    # substrate is layered on top of P4 by design.
    import workspaces as _ws_mod

    ws = _ws_mod.get_workspace(idx, workspace_id)
    if ws is None:
        return {"ok": False, "error": f"workspace not found: {workspace_id}"}

    # Re-run the assembler -- inexpensive on a personal corpus, ensures
    # the grounding reflects the latest engagement scores even if the
    # workspace's stored assembled_yoinks is stale.
    assembled = _ws_mod.assemble_workspace(
        idx,
        format=ws.get("format"),
        topic=ws.get("topic"),
        hook_target=ws.get("hook_target"),
        your_channel=ws.get("your_channel"),
        n_examples=int(ws.get("n_examples") or 10),
        workspace_id=workspace_id,
    )

    # Taste anchors (S4) -- gracefully degrade if memory_layer isn't in
    # the install yet (its branch hasn't landed in main as of the P5 ship
    # date; the substrate gap is well-documented in the PR body).
    taste = None
    if style_anchors:
        try:
            import memory_layer as _ml
            try:
                import server as _srv
                data_root = _srv.DATA_ROOT
            except Exception:
                from pathlib import Path
                data_root = Path.cwd()
            payload = _ml.read_taste(idx, data_root)
            if payload.get("ok"):
                taste = payload.get("content")
        except ImportError:
            taste = None
        except Exception as e:
            log.warning("taste anchors pull skipped: %s", e)
            taste = None

    return {
        "ok": True,
        "workspace": ws,
        "assembled": assembled,
        "taste_anchors": taste,
    }


# ---- generation (phase 2 persistence) -----------------------------------
def persist_script(idx, workspace_id: str, *, script: dict,
                    mode: str = COMPUTE_MODE_AGENT,
                    parent_script_id: int | None = None) -> dict:
    """Persist a structured script that an agent produced. Returns the
    inserted row id + the assigned version number.

    `script` shape (per ROADMAP P5):
        {
          "format": str?,                  # if absent, copied from workspace
          "target_length_sec": int?,
          "hook": str,                     # the opening
          "beats": list[dict],             # [{label, content, timecode}, ...]
          "body": str?,                    # optional prose body
          "cta": str?,
          "shot_list": list[dict]?,        # populated by /script/shot-list or agent
          "source_yoinks": list[dict],     # [{video_id, slug, why}, ...]
        }"""
    import workspaces as _ws_mod

    if mode not in _MODES:
        raise ValueError(f"mode must be one of {_MODES}")
    if _ws_mod.get_workspace(idx, workspace_id) is None:
        raise ValueError(f"workspace not found: {workspace_id}")
    if not isinstance(script, dict):
        raise ValueError("script must be a JSON object")

    hook = (script.get("hook") or "").strip()
    if not hook:
        raise ValueError("script.hook required")

    version = _next_version(idx, workspace_id)
    beats_blob = _validate_json_list(script.get("beats"), field="beats")
    shot_blob = _validate_json_list(script.get("shot_list"), field="shot_list")
    src_blob = _validate_json_list(script.get("source_yoinks"),
                                     field="source_yoinks")

    # Fill format from workspace when omitted.
    fmt = script.get("format")
    if fmt is None:
        ws_row = _ws_mod.get_workspace(idx, workspace_id)
        fmt = (ws_row or {}).get("format")

    try:
        target_len = (int(script["target_length_sec"])
                       if script.get("target_length_sec") is not None else None)
    except (TypeError, ValueError):
        raise ValueError("target_length_sec must be an integer")

    with idx._lock:
        cur = idx._conn.execute(
            "INSERT INTO scripts (workspace_id, version, generated_at, format, "
            "target_length_sec, hook, beats, body, cta, shot_list, "
            "source_yoinks, mode, parent_script_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, version, _now_iso(), fmt, target_len, hook,
             beats_blob, script.get("body"), script.get("cta"),
             shot_blob, src_blob, mode, parent_script_id))
        return {"ok": True, "id": cur.lastrowid or 0,
                "workspace_id": workspace_id, "version": version,
                "mode": mode}


def generate_script(idx, workspace_id: str, *,
                     script: dict | None = None,
                     mode: str = COMPUTE_MODE_AGENT,
                     parent_script_id: int | None = None) -> dict:
    """Two-phase entry point.

    Phase 1 (`script` is None): return the grounding context the agent
    needs to write a script. NEVER persists.

    Phase 2 (`script` is a dict): persist the agent-produced script.
    Returns the new script row id + version."""
    if script is None:
        ctx = assemble_grounding(idx, workspace_id)
        if not ctx.get("ok"):
            return ctx
        return {"ok": True, "mode": "grounding_only", "context": ctx,
                "next": ("Produce the structured script JSON (hook, "
                          "beats, body, cta, source_yoinks) and POST "
                          "again with `script` to persist it.")}
    try:
        return persist_script(idx, workspace_id, script=script, mode=mode,
                                parent_script_id=parent_script_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}


# ---- revision (a versioned regeneration grounded in critique findings) --
def revise_script(idx, script_id: int, *,
                   critique_findings: dict | None = None,
                   revision_target: str | None = None,
                   revised_script: dict | None = None,
                   mode: str = COMPUTE_MODE_AGENT) -> dict:
    """Revise an existing script grounded in critique findings.

    Phase 1 (`revised_script` is None): return the previous script + the
    parent workspace's grounding so the agent can produce a revised
    version.

    Phase 2 (`revised_script` is a dict): persist as a new version with
    parent_script_id pointing to script_id."""
    prev = get_script(idx, script_id)
    if prev is None:
        return {"ok": False, "error": f"script not found: {script_id}"}
    workspace_id = prev.get("workspace_id")

    if revised_script is None:
        ctx = assemble_grounding(idx, workspace_id)
        return {
            "ok": True,
            "mode": "revision_context",
            "previous_script": prev,
            "context": ctx,
            "critique_findings": critique_findings or {},
            "revision_target": revision_target,
            "next": ("Produce a revised script JSON (same shape as "
                      "generate_script phase 2) and POST again with "
                      "`revised_script` to persist."),
        }
    return generate_script(idx, workspace_id, script=revised_script, mode=mode,
                             parent_script_id=script_id)


# ---- shot list (derive from beats + format facet) ------------------------
# Heuristic: format -> default scene cues. The agent can override by
# passing `shot_list` directly in the generate_script script payload;
# this endpoint exists for the case where the agent wants the helper to
# offer a starter checklist based on the format conventions.
_FORMAT_DEFAULTS: dict[str, list[str]] = {
    "talking_head": ["close-up host", "b-roll cutaway", "lower-third tag"],
    "tutorial": ["screen recording", "annotated overlay", "close-up hands"],
    "listicle": ["title card per item", "b-roll demo", "host beat"],
    "narrative": ["wide establishing", "close-up subject", "interview cut"],
    "vlog": ["selfie cam", "POV walking", "b-roll location"],
    "interview": ["two-shot wide", "single-shot interviewee",
                   "single-shot interviewer"],
    "screen_recording": ["full screen", "highlight zoom", "voiceover"],
    "broll_heavy": ["wide", "medium", "macro", "host bookend"],
    "one_shot": ["single locked frame"],
}


def derive_shot_list(idx, script_id: int) -> dict:
    """Generate a default shot list for a script based on its beats +
    the parent workspace's format. Persists the derived list on the
    script row (overwriting any prior shot_list)."""
    s = get_script(idx, script_id)
    if s is None:
        return {"ok": False, "error": f"script not found: {script_id}"}
    fmt = (s.get("format") or "").strip()
    defaults = _FORMAT_DEFAULTS.get(fmt, ["wide", "close-up", "b-roll"])
    beats = s.get("beats") or []
    rows: list[dict] = []
    # One shot row per beat, with the format defaults as the suggested
    # cue list. Keeps the heuristic simple + useful for an agent to
    # iterate on.
    for i, b in enumerate(beats):
        label = b.get("label") if isinstance(b, dict) else None
        rows.append({
            "scene": i + 1,
            "label": label or f"beat {i + 1}",
            "cues": list(defaults),
            "notes": None,
        })
    blob = json.dumps(rows)
    with idx._lock:
        idx._conn.execute(
            "UPDATE scripts SET shot_list=? WHERE id=?",
            (blob, script_id))
    return {"ok": True, "script_id": script_id, "shot_list": rows,
            "format": fmt or None}


# ---- read paths ---------------------------------------------------------
def _row_to_dict(row: dict | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("beats", "shot_list", "source_yoinks"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    return d


def get_script(idx, script_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM scripts WHERE id=?", (script_id,)).fetchone()
    return _row_to_dict(row)


def list_scripts(idx, *, workspace_id: str | None = None,
                  limit: int = 50) -> list[dict]:
    if workspace_id:
        rows = idx._conn.execute(
            "SELECT * FROM scripts WHERE workspace_id=? "
            "ORDER BY generated_at DESC LIMIT ?",
            (workspace_id, max(1, min(int(limit), 500)))).fetchall()
    else:
        rows = idx._conn.execute(
            "SELECT * FROM scripts ORDER BY generated_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_shot_list(idx, script_id: int) -> dict:
    """Read-only accessor for a script's persisted shot list."""
    s = get_script(idx, script_id)
    if s is None:
        return {"ok": False, "error": f"script not found: {script_id}"}
    return {"ok": True, "script_id": script_id,
            "shot_list": s.get("shot_list") or [],
            "format": s.get("format")}
