"""Read-only pytest observer for Phase 4 lifecycle snapshots.

Records context/session/owner/child identity. Does not reset globals,
release a gate, kill a writer, or change a result.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

_OUT = Path(os.environ.get("P4_SNAP_PATH") or "p4-snap.jsonl")


def _ident(obj):
    if obj is None:
        return None
    return f"{type(obj).__name__}@{id(obj):x}"


def _session_snap(session):
    if session is None:
        return None
    proc = getattr(session, "proc", None)
    poll = None
    if proc is not None:
        try:
            poll = proc.poll()
        except Exception as exc:
            poll = f"poll-error:{type(exc).__name__}"
    origin = getattr(session, "_origin_thread", None)
    owner = getattr(session, "_exclusion_owner", None)
    try:
        physical = session.physical_liveness()
    except Exception as exc:
        physical = f"error:{type(exc).__name__}:{exc}"
    try:
        alive = bool(session.alive)
    except Exception as exc:
        alive = f"error:{type(exc).__name__}"
    try:
        owned = list(session.owned_pids()) if hasattr(session, "owned_pids") else None
    except Exception as exc:
        owned = f"error:{type(exc).__name__}"
    return {
        "id": _ident(session),
        "dest": getattr(session, "dest", None),
        "pid": getattr(session, "pid", None),
        "writer_pid": getattr(session, "writer_pid", None),
        "token": getattr(session, "token", None),
        "dead": bool(getattr(session, "_dead", False)),
        "alive": alive,
        "physical_liveness": physical,
        "proc_poll": poll,
        "job": bool(getattr(session, "job", None)),
        "launching": bool(getattr(session, "_launching", False)),
        "popen_in_progress": bool(getattr(session, "_popen_in_progress", False)),
        "lease_written": bool(getattr(session, "_lease_written", False)),
        "origin_thread_id": getattr(session, "_origin_thread_id", None),
        "origin_thread_ident": id(origin) if origin is not None else None,
        "origin_is_current": origin is threading.current_thread() if origin is not None else None,
        "current_thread_ident": id(threading.current_thread()),
        "current_get_ident": threading.get_ident(),
        "owned_pids": owned,
        "owner_id": _ident(owner),
        "owner_held": bool(getattr(owner, "held", False)) if owner is not None else None,
    }


def _plan_snap(plan):
    if not isinstance(plan, dict):
        return {"present": False}
    cancelled = plan.get("cancelled")
    cancelled_set = None
    if isinstance(cancelled, threading.Event):
        cancelled_set = cancelled.is_set()
    return {
        "present": True,
        "op_id": plan.get("op_id"),
        "lock_generation": plan.get("lock_generation"),
        "io": _ident(plan.get("io")),
        "cancelled_set": cancelled_set,
        "dest": plan.get("dest"),
    }


def _owner_snap(owner):
    if owner is None:
        return None
    try:
        needed = owner.needed()
    except Exception as exc:
        needed = f"error:{type(exc).__name__}"
    with_sessions = []
    try:
        sessions = list(getattr(owner, "sessions", ()) or ())
    except Exception:
        sessions = []
    for session in sessions:
        with_sessions.append(_ident(session))
    return {
        "id": _ident(owner),
        "dest": getattr(owner, "dest", None),
        "key": getattr(owner, "key", None),
        "held": bool(getattr(owner, "held", False)),
        "abandoned": bool(getattr(owner, "abandoned", False)),
        "needed": needed,
        "exclusive_holds": getattr(owner, "_exclusive_holds", None),
        "sessions": with_sessions,
        "thread_alive": bool(getattr(getattr(owner, "_thread", None), "is_alive", lambda: None)()),
    }


def snapshot(phase: str, nodeid: str = "", extra: dict | None = None) -> dict:
    import library_mirror as mirror

    ctx_session = getattr(mirror._IO_CTX, "session", None)
    ctx_plan = getattr(mirror._IO_CTX, "plan", None)
    ctx_token = getattr(mirror._IO_CTX, "token", None)
    ctx_op = getattr(mirror._IO_CTX, "op_id", None)
    ctx_owner = getattr(mirror._EXCL_CTX, "owner", None)
    retained = []
    for session in list(getattr(mirror, "_retained_sessions", ()) or ()):
        retained.append(_session_snap(session))
    owners = []
    for owner in list(getattr(mirror, "_live_owners", ()) or ()):
        owners.append(_owner_snap(owner))
    row = {
        "ts": time.time(),
        "phase": phase,
        "nodeid": nodeid,
        "thread_ident": threading.get_ident(),
        "thread_id": id(threading.current_thread()),
        "io_ctx": {
            "session": _session_snap(ctx_session),
            "token": ctx_token,
            "op_id": ctx_op,
            "plan": _plan_snap(ctx_plan),
            "bound_must_refuse_dest": bool(mirror._bound_session_must_refuse_dest()),
        },
        "excl_ctx": _owner_snap(ctx_owner),
        "retained_count": len(retained),
        "retained": retained,
        "live_owners_count": len(owners),
        "live_owners": owners,
        "dest_holds": dict(getattr(mirror, "_dest_holds", {}) or {}),
    }
    if extra:
        row["extra"] = extra
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with _OUT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return row


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    snapshot("setup", item.nodeid)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    snapshot("teardown", item.nodeid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if call.when == "call":
        extra = {
            "outcome": report.outcome,
            "longrepr": str(report.longrepr) if report.failed else None,
        }
        snapshot("call", item.nodeid, extra=extra)
