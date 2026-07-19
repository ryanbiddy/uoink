"""v3 P4 Build Workspace persistence and critique compatibility.

A workspace is one act of planning a video. Corpus selection belongs to
corpus_intelligence; this module preserves workspace CRUD, assembled-ID
persistence, and the legacy workspace/critique behavior.

Locked compute policy: model-agnostic by default. Primary path is the
calling agent doing the LLM work via MCP (`assemble_workspace` returns the
slice; `critique_against_corpus` records the agent's findings). BYO-key
fallback is an optional on-server compute that this PR does not implement
(the endpoint surface accepts it but routes only to the agent path until
the BYO worker pool lands — same posture as S1 `/facets/backfill`).

This module owns:
  - Workspace CRUD against the v3 `workspaces` SQLite table
  - A compatibility wrapper around the corpus-intelligence query
  - The critique log writer

Transport (HTTP + MCP) is owned by server.py + uoink_mcp_tools.py."""

from __future__ import annotations

import json
import secrets
from datetime import datetime

import corpus_contract
import corpus_intelligence

# ---- compute mode --------------------------------------------------------
# The critique path can produce findings via the agent (calling agent
# supplies findings on POST) or via a future BYO-Anthropic worker pool.
# Stamped on every critique row so a forensic read can tell which path
# produced which finding set.
COMPUTE_MODE_AGENT = "agent"
COMPUTE_MODE_BYO_KEY = "byo_key"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _gen_workspace_id() -> str:
    return "ws_" + secrets.token_hex(4)


# ---- CRUD ---------------------------------------------------------------
def create_workspace(idx, *, format: str | None = None,
                      topic: str | None = None,
                      hook_target: str | None = None,
                      your_channel: str | None = None,
                      n_examples: int = 10,
                      notes: str | None = None) -> dict:
    """Insert + return a fresh workspace row. assembled_yoinks is empty
    until the caller invokes assemble_workspace()."""
    wid = _gen_workspace_id()
    now = _now_iso()
    with idx._lock:
        idx._conn.execute(
            "INSERT INTO workspaces (id, created_at, updated_at, format, "
            "topic, hook_target, your_channel, n_examples, "
            "assembled_yoinks, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (wid, now, now, format, topic, hook_target, your_channel,
             max(1, min(int(n_examples), 100)), "[]", notes))
    return get_workspace(idx, wid) or {}


def get_workspace(idx, workspace_id: str) -> dict | None:
    row = idx._conn.execute(
        "SELECT id, created_at, updated_at, format, topic, hook_target, "
        "your_channel, n_examples, assembled_yoinks, notes "
        "FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["assembled_yoinks"] = json.loads(d.get("assembled_yoinks") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["assembled_yoinks"] = []
    return d


def list_workspaces(idx, *, limit: int = 50) -> list[dict]:
    rows = idx._conn.execute(
        "SELECT id, created_at, updated_at, format, topic, hook_target, "
        "your_channel, n_examples FROM workspaces "
        "ORDER BY updated_at DESC LIMIT ?",
        (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(r) for r in rows]


def delete_workspace(idx, workspace_id: str) -> bool:
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM workspaces WHERE id=?", (workspace_id,))
        return cur.rowcount > 0


def _save_assembled(idx, workspace_id: str, video_ids: list[str]) -> None:
    with idx._lock:
        idx._conn.execute(
            "UPDATE workspaces SET assembled_yoinks=?, updated_at=? "
            "WHERE id=?",
            (json.dumps(video_ids), _now_iso(), workspace_id))


# ---- legacy assembly compatibility -------------------------------------
def assemble_workspace(idx, *, format: str | None = None,
                        topic: str | None = None,
                        hook_target: str | None = None,
                        your_channel: str | None = None,
                        n_examples: int = 10,
                        workspace_id: str | None = None) -> dict:
    """Preserve the legacy workspace response around the core query."""
    n_examples = max(1, min(int(n_examples), 100))
    request = corpus_contract.AssemblyRequest(
        format=format,
        topic=topic,
        hook_target=hook_target,
        your_channel=your_channel,
        n_examples=n_examples,
    )
    data = corpus_intelligence.assemble(
        idx, request, data_root=_data_root_for_taste())
    if workspace_id:
        _save_assembled(
            idx,
            workspace_id,
            [row["video_id"] for row in data["assembled"]],
        )

    return {
        "ok": True,
        "workspace_id": workspace_id,
        **data,
    }


def _data_root_for_taste():
    """memory_layer.read_taste needs DATA_ROOT. Import lazily to avoid a
    hard server.py dependency from this module."""
    try:
        import server as _server
        return _server.DATA_ROOT
    except Exception:
        from pathlib import Path
        return Path.cwd()


# ---- critique log -------------------------------------------------------
def log_critique(idx, workspace_id: str, *, draft_text: str,
                  mode: str = COMPUTE_MODE_AGENT,
                  findings: dict | None = None) -> int:
    """Record one critique call against a workspace. Returns row id.

    The findings dict structure (per ROADMAP P4):
        {
          "hook_strength": "...",
          "structural_deviation": [...],
          "pacing_issues": [...],
          "missing_audience_hooks": [...],
        }
    Schema is free-form -- the helper doesn't validate, just persists,
    because the agent's analysis surface evolves faster than this SQL."""
    if mode not in (COMPUTE_MODE_AGENT, COMPUTE_MODE_BYO_KEY):
        raise ValueError(
            f"mode must be one of {COMPUTE_MODE_AGENT}, {COMPUTE_MODE_BYO_KEY}")
    if not get_workspace(idx, workspace_id):
        raise ValueError(f"workspace not found: {workspace_id}")
    findings_blob = json.dumps(findings or {})
    with idx._lock:
        cur = idx._conn.execute(
            "INSERT INTO workspace_critique_log "
            "(workspace_id, ts_utc, mode, draft_text, findings) "
            "VALUES (?, ?, ?, ?, ?)",
            (workspace_id, _now_iso(), mode, draft_text, findings_blob))
        # Bump updated_at on the parent
        idx._conn.execute(
            "UPDATE workspaces SET updated_at=? WHERE id=?",
            (_now_iso(), workspace_id))
        return cur.lastrowid or 0


def critique_log_for(idx, workspace_id: str, *, limit: int = 50) -> list[dict]:
    rows = idx._conn.execute(
        "SELECT id, workspace_id, ts_utc, mode, draft_text, findings "
        "FROM workspace_critique_log WHERE workspace_id=? "
        "ORDER BY ts_utc DESC LIMIT ?",
        (workspace_id, max(1, min(int(limit), 500)))).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["findings"] = json.loads(d.get("findings") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["findings"] = {}
        out.append(d)
    return out


def critique_against_corpus(idx, workspace_id: str, *, draft_text: str,
                             findings: dict | None = None,
                             mode: str = COMPUTE_MODE_AGENT) -> dict:
    """Persist a critique call. The actual LLM analysis happens in the
    calling agent (model-agnostic primary path); this is the writer the
    agent calls after producing findings.

    The endpoint variant routes through here too -- when an agent calls
    POST /workspace/critique with `findings`, we store them; when it
    calls without `findings`, we return the assembled context so the
    agent can produce findings + call back."""
    ws = get_workspace(idx, workspace_id)
    if ws is None:
        return {"ok": False, "error": f"workspace not found: {workspace_id}"}
    if findings is None:
        # Bootstrap mode -- return the assembled corpus + draft so the
        # caller can drive the critique. No row written.
        ass = assemble_workspace(
            idx,
            format=ws.get("format"),
            topic=ws.get("topic"),
            hook_target=ws.get("hook_target"),
            your_channel=ws.get("your_channel"),
            n_examples=int(ws.get("n_examples") or 10),
        )
        return {
            "ok": True,
            "mode": "context_only",
            "workspace": ws,
            "context": ass,
            "draft_text": draft_text,
            "next": ("Produce findings JSON and POST again with "
                      "`findings` to persist them."),
        }
    row_id = log_critique(idx, workspace_id,
                           draft_text=draft_text, mode=mode,
                           findings=findings)
    return {"ok": True, "mode": "persisted", "id": row_id,
            "workspace_id": workspace_id}
