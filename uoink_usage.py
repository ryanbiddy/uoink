"""Opt-in, bounded counts. No event bodies, credentials or network on callers.

The helper and stdio processes share a separate SQLite file. Short transactions
serialize consent and counter updates across processes, never network I/O. Callers only
put fixed labels on a bounded queue; one daemon does local I/O. Only the helper
starts the daily sender. SQLite is from the standard library on all platforms.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import atexit
import json
import logging
import math
import os
from pathlib import Path
import platform
import queue
import re
import sqlite3
import sys
import threading
import time
import uuid
import urllib.request
import urllib.error

# Bound at import so a test that patches time.monotonic cannot break flush or send deadlines.
_monotonic = time.monotonic

USAGE_ENDPOINT = "https://usage.uoink.app/v1/ping"
DAY = 24 * 60 * 60
MAX_COUNT = 100000  # The usage receiver rejects any count above this.
MAX_TOOL_KEYS = 128
SEND_DEADLINE = 4.0
# Stop before the receiver's seven-day report marker expires, including the
# time a final network attempt could take. Uncertain old counts are discarded.
REPORT_RETENTION = 7 * DAY - SEND_DEADLINE
FLUSH_DEADLINE = 1.0
SAMPLE_ID = "00000000-0000-4000-8000-000000000000"
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)"
                    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
                    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?")
SOURCES = ("youtube", "x", "reddit", "page", "podcast", "image", "note", "other")
CLIENTS = {
    "claude desktop": "claude-desktop", "claude-desktop": "claude-desktop",
    "claude": "claude-desktop", "claude-ai": "claude-desktop", "claude-code": "claude-code",
    "claude code": "claude-code", "cursor": "cursor", "cursor-vscode": "cursor", "cline": "cline",
    "continue": "continue", "codex": "codex", "openai-codex": "codex",
    "codex-mcp-client": "codex", "chatgpt": "chatgpt",
    "vscode": "vscode", "vs code": "vscode", "visual studio code": "vscode",
    "vscode-insiders": "vscode", "vscode - insiders": "vscode",
    "visual studio code - insiders": "vscode", "code - insiders": "vscode",
}
log = logging.getLogger(__name__)
_root = None
_version = "0.0.0"
_kind = "source"
_queue = queue.Queue(maxsize=1024)
_worker_lock = threading.Lock()
_worker = None
_network_lock = threading.Lock()
_capture = ContextVar("usage_capture", default=None)
_search = ContextVar("usage_search", default=False)


def configure(root, version, install_kind="source"):
    """Configure paths without opening any file or starting a sender."""
    global _root, _version, _kind
    _root = root
    _version = version if isinstance(version, str) and SEMVER.fullmatch(version) else "0.0.0"
    _kind = install_kind if install_kind in ("installer", "mcpb", "source") else "source"


def forced_off():
    return os.environ.get("UOINK_USAGE_SHARING", "").strip() == "0"


def isolated():
    import uoink_install_isolation
    return (any(k.startswith("UOINK_ISOLATED_") for k in os.environ)
            or uoink_install_isolation.current_binding() is not None
            or any(getattr(sys.modules.get(name), "_ISOLATION", None) is not None
                   for name in ("server", "__main__")))


def _path():
    return Path(_root()) / "usage-counts.sqlite3"


def _connect(path, mode):
    uri = path.as_uri() + "?mode=" + mode
    for attempt in range(4):
        try:
            return sqlite3.connect(uri, uri=True, timeout=6)
        except (PermissionError, sqlite3.OperationalError) as exc:
            # Windows sharing violations surface as SQLITE_CANTOPEN, outside
            # SQLite's busy timeout. Retry only opening, before any state change
            # or sender call can run, so a retry cannot duplicate either one.
            # _record already skips a missing file, so every retry here is a real
            # open of an existing file; a stat during a sharing violation can lie.
            if (attempt == 3 or (not isinstance(exc, PermissionError)
                    and getattr(exc, "sqlite_errorcode", 0) & 0xff != sqlite3.SQLITE_CANTOPEN)):
                raise
            time.sleep(0.05 * 2 ** attempt)


@contextmanager
def _transaction(create=False, *, path=None):
    path = _path() if path is None else path
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    # mode=rw prevents a late queued event from creating state while off.
    conn = _connect(path, "rwc" if create else "rw")
    try:
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM state WHERE id=1").fetchone()
        state = json.loads(row[0]) if row else {}
        yield state
        conn.execute("INSERT OR REPLACE INTO state VALUES (1, ?)",
                     (json.dumps(state, separators=(",", ":")),))
        conn.commit()
    finally:
        conn.close()


def _read_state(path=None):
    """Disclosure and send preflight never create a file or acquire a write lock."""
    path = _path() if path is None else path
    if not path.exists():
        return {}
    conn = _connect(path, "ro")
    try:
        row = conn.execute("SELECT value FROM state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        conn.close()


def set_enabled(enabled):
    """Consent is authoritative across processes; off erases ID and history."""
    # The environment stops this process's activity, not the shared consent.
    enabled = enabled is True
    if _root is None or (not enabled and not _path().exists()):
        return
    with _transaction(create=enabled) as state:
        if enabled and not state.get("install_id"):
            last_attempt = state.get("last_attempt", 0)
            state.clear()
            now = time.time()
            state.update(install_id=str(uuid.uuid4()), report_id=str(uuid.uuid4()), since=now, enabled_at=now,
                         last_attempt=last_attempt, counts={}, history=[])
        elif not enabled:
            last_attempt = state.get("last_attempt", 0)
            state.clear()
            state["last_attempt"] = last_attempt


def _tool_names():
    import uoink_mcp_tools
    return frozenset(uoink_mcp_tools.TOOL_REGISTRY)


def _label(group, label):
    if group == "tools":
        return label if (isinstance(label, str) and label in _tool_names()
                         and re.fullmatch(r"[a-z0-9_]{3,64}", label)) else None
    if group == "mcp_clients":
        return CLIENTS.get(label.strip().lower(), "other") if isinstance(label, str) else "other"
    if group == "transports":
        return label if label in ("stdio", "http") else None
    if group == "captures":
        return label if label in SOURCES else "other"
    return "count" if group == "searches" else None


def _record(path, group, label, outcome, occurred):
    # Path is captured at enqueue time, so reconfiguration cannot redirect work.
    if forced_off() or _root is None or path != _path() or not path.exists():
        return
    with _transaction(path=path) as state:
        if not state.get("install_id") or occurred < state.get("enabled_at", state["since"]):
            return
        counts = state.setdefault("counts", {})
        bucket = counts.setdefault(group, {})
        key = label + ":" + outcome if group == "captures" else label
        if group == "tools" and key not in bucket and len(bucket) >= MAX_TOOL_KEYS:
            return
        # Reserve room for new activity even when the outstanding report is at
        # the wire limit. Its acknowledged counts are subtracted separately.
        pending = _report_counts(state.get("pending") or {}).get(group, {}).get(key, 0)
        bucket[key] = min(MAX_COUNT + _counter(pending), bucket.get(key, 0) + 1)


def _drain():
    while True:
        event = _queue.get()
        try:
            _record(*event)
        except Exception:
            log.debug("Usage count could not be saved")
        finally:
            _queue.task_done()


def count(group, label="count", outcome="ok"):
    """Never wait for disk, network, or a busy writer. Failures stay at DEBUG."""
    global _worker
    try:
        if _root is None or forced_off():
            return
        label = _label(group, label)
        if label is None:
            return
        if _worker is None and _worker_lock.acquire(blocking=False):
            try:
                if _worker is None:
                    _worker = threading.Thread(target=_drain, name="usage-counts", daemon=True)
                    _worker.start()
            finally:
                _worker_lock.release()
        _queue.put_nowait((_path(), group, label, "ok" if outcome == "ok" else "failed", time.time()))
    except Exception:
        log.debug("Usage count skipped")


def flush(timeout=FLUSH_DEADLINE):
    """Bounded best effort at process exit. This only waits for local counts."""
    deadline = _monotonic() + timeout
    with _queue.all_tasks_done:
        while _queue.unfinished_tasks:
            remaining = deadline - _monotonic()
            if remaining <= 0:
                return False
            _queue.all_tasks_done.wait(remaining)
    return True


atexit.register(flush)


def mcp_call(name, transport):
    try:
        if name in _tool_names():
            count("tools", name)
            count("transports", transport)
    except Exception:
        log.debug("MCP usage count skipped")


def capture_result(result):
    scope = _capture.get()
    if scope is not None and isinstance(result, dict):
        # A live stream queued for later is not a completed capture. A rate
        # limited acquisition did fail, even when the helper queues a retry.
        scope["skip"] = result.get("queued") is True and result.get("reason") != "youtube_rate_limit"
        scope["ok"] = (result.get("ok", True) is not False
                       and result.get("queued") is not True
                       and result.get("status") != "saved_with_errors"
                       and ("video_id" not in result or bool(result["video_id"])))


def search(fn=None, *, query_arg=None):
    """Count the outer search once, excluding queryless browsing when requested."""
    if fn is None:
        return lambda fn: search(fn, query_arg=query_arg)
    if query_arg is not None:
        from inspect import signature
        parameters = signature(fn)
    @wraps(fn)
    def wrapped(*args, **kwargs):
        nested = _search.get()
        token = _search.set(True)
        try:
            try:
                has_query = query_arg is None or bool(parameters.bind(*args, **kwargs).arguments.get(query_arg))
                if not nested and has_query:
                    count("searches")
            except Exception:
                pass  # Usage must not change the result or the original exception.
            return fn(*args, **kwargs)
        finally:
            _search.reset(token)
    return wrapped


def capture(source, *, response=False):
    """Count a completed pipeline, including exceptions, once across nesting."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if _capture.get() is not None:
                return fn(*args, **kwargs)
            scope = {"ok": False}
            token = _capture.set(scope)
            label = "other"
            try:
                try:
                    label = source(*args, **kwargs) if callable(source) else source
                except Exception:
                    log.debug("Capture source count skipped")
                result = fn(*args, **kwargs)
                if not response or isinstance(result, dict):
                    capture_result(result)
                    if not response and not isinstance(result, dict):
                        scope["ok"] = bool(result)
                return result
            finally:
                _capture.reset(token)
                if not scope.get("skip"):
                    try:
                        count("captures", label, "ok" if scope["ok"] else "failed")
                    except Exception:
                        pass  # Preserve the capture result or its original exception.
        return wrapped
    return decorate


def _metadata():
    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    # Windows 11 still reports major version 10; build 22000 is its first release.
    release = (platform.mac_ver()[0] if os_name == "macos" else
               ("11" if sys.getwindowsversion().build >= 22000 else str(sys.getwindowsversion().major))
               if os_name == "windows" else platform.release())
    major = re.match(r"[0-9]{1,3}", release)
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64",
            "arm64": "arm64"}.get(machine, "other")
    return dict(version=_version, os=os_name, os_major=major[0] if major else "unknown",
                arch=arch, install_kind=_kind)


def _counter(value):
    return min(MAX_COUNT, max(0, value)) if type(value) is int else 0


def _uuid4(value):
    try:
        parsed = uuid.UUID(value)
        return str(parsed) if parsed.version == 4 else None
    except (ValueError, TypeError, AttributeError):
        return None


def _sanitize_payload(payload):
    """Rebuild persisted snapshots from today's closed labels and field rules."""
    def bucket(group, allowed, cap):
        values = payload.get(group)
        if not isinstance(values, dict):
            return {}
        return dict(sorted((k, _counter(v)) for k, v in values.items()
                           if k in allowed and _counter(v))[:cap])

    metadata = _metadata()
    for key, allowed in (("os", ("windows", "macos", "linux")),
                         ("arch", ("x86_64", "arm64", "other")),
                         ("install_kind", ("installer", "mcpb", "source"))):
        if payload.get(key) in allowed:
            metadata[key] = payload[key]
    version = payload.get("version")
    if isinstance(version, str) and SEMVER.fullmatch(version):
        metadata["version"] = version
    major = payload.get("os_major")
    metadata["os_major"] = major if isinstance(major, str) and re.fullmatch(r"[0-9]{1,3}|unknown", major) else "unknown"
    hours = payload.get("period_hours", 0)
    hours = min(MAX_COUNT, max(0, hours)) if type(hours) in (int, float) and math.isfinite(hours) else 0
    clean = dict(schema=1, install_id=_uuid4(payload.get("install_id")),
                 report_id=_uuid4(payload.get("report_id")), **metadata, period_hours=hours,
                 mcp_clients=bucket("mcp_clients", set(CLIENTS.values()) | {"other"}, 9),
                 transports={"stdio": 0, "http": 0},
                 tools=bucket("tools", {n for n in _tool_names() if re.fullmatch(r"[a-z0-9_]{3,64}", n)}, MAX_TOOL_KEYS),
                 captures={}, searches=_counter(payload.get("searches")))
    clean["transports"].update(bucket("transports", {"stdio", "http"}, 2))
    captures = payload.get("captures")
    if isinstance(captures, dict):
        for source in SOURCES:
            if isinstance(captures.get(source), dict):
                clean["captures"][source] = {o: _counter(captures[source].get(o)) for o in ("ok", "failed")}
    # Keep the actual compact UTF-8 body within the receiver's byte budget.
    while len(_encode(clean)) > 4096 and clean["tools"]:
        clean["tools"].pop(next(reversed(clean["tools"])))
    if len(_encode(clean)) > 4096 or not clean["install_id"] or not clean["report_id"]:
        raise ValueError("invalid usage payload")
    return clean


def _payload(state, now):
    if not state.get("install_id"):
        return None
    counts = state.get("counts", {})
    payload = dict(schema=1, install_id=state["install_id"], report_id=state.get("report_id", SAMPLE_ID), **_metadata(),
                   period_hours=round(max(0, now - state["since"]) / 3600, 2),
                   mcp_clients=counts.get("mcp_clients", {}), transports=counts.get("transports", {}),
                   tools=counts.get("tools", {}), captures={}, searches=counts.get("searches", {}).get("count", 0))
    for source in SOURCES:
        values = counts.get("captures", {})
        if any(values.get(source + ":" + outcome, 0) for outcome in ("ok", "failed")):
            payload["captures"][source] = {outcome: values.get(source + ":" + outcome, 0)
                                          for outcome in ("ok", "failed")}
    return _sanitize_payload(payload)


def _encode(payload):
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


def disclosure():
    sample = _payload({"install_id": SAMPLE_ID, "report_id": SAMPLE_ID, "since": 0}, 0)
    empty = {"next_payload": sample, "sample": True, "sent": []}
    try:
        if forced_off() or _root is None:
            return empty
        state = _read_state()
        if not state.get("install_id"):
            return empty
        payload = _sanitize_payload(state["pending"]) if state.get("pending") else _payload(state, time.time())
        return {"next_payload": payload, "sample": False, "sent": state.get("history", [])[-10:]}
    except Exception:
        log.debug("Usage disclosure unavailable")
        return {**empty, "error": "Usage counts could not be read."}


def _endpoint():
    endpoint = os.environ.get("UOINK_USAGE_ENDPOINT", USAGE_ENDPOINT).strip()
    testing = ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
               or "IG_FORBIDDEN_LIVE" in os.environ)
    # Tests must explicitly select a non-production endpoint; no implicit ping.
    if testing and ("UOINK_USAGE_ENDPOINT" not in os.environ or endpoint == USAGE_ENDPOINT):
        return ""
    from urllib.parse import urlsplit
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return endpoint


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(endpoint, payload):
    request = urllib.request.Request(endpoint, data=_encode(payload), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=SEND_DEADLINE) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _send_snapshot(endpoint, payload, path, generation):
    """Bound the sender's wait, including DNS. At most one network worker lives."""
    if not _network_lock.acquire(blocking=False):
        return None
    result = []
    expired = threading.Event()

    def run():
        try:
            state = _read_state(path)
            if (not expired.is_set() and not forced_off() and not isolated() and _root is not None and path == _path()
                    and state.get("send_generation") == generation
                    and state.get("install_id") == payload["install_id"]):
                result.append(_post(endpoint, payload))
        except Exception:
            log.debug("Usage send unavailable")
        finally:
            _network_lock.release()

    worker = threading.Thread(target=run, name="usage-post", daemon=True)
    deadline = _monotonic() + SEND_DEADLINE
    try:
        worker.start()
    except Exception:
        _network_lock.release()
        raise
    worker.join(max(0, deadline - _monotonic()))
    expired.set()
    return result[0] if not worker.is_alive() and result else None


def _report_counts(payload):
    def bucket(group):
        value = payload.get(group)
        return value if isinstance(value, dict) else {}

    values = {g: {k: _counter(n) for k, n in bucket(g).items()}
              for g in ("tools", "transports", "mcp_clients")}
    values["captures"] = {s + ":" + o: _counter(n) for s, outcomes in bucket("captures").items()
                          if isinstance(outcomes, dict) for o, n in outcomes.items()}
    values["searches"] = {"count": _counter(payload.get("searches", 0))}
    return values


def _subtract_counts(state, payload):
    counts = state.get("counts", {})
    for group, values in _report_counts(payload).items():
        for key, n in values.items():
            if key in counts.get(group, {}):
                remaining = max(0, counts[group][key] - n)
                if remaining:
                    counts[group][key] = remaining
                else:
                    counts[group].pop(key)
        if not counts.get(group):
            counts.pop(group, None)


def _finish_report(state, now, payload):
    _subtract_counts(state, payload)
    state["since"] = state.pop("pending_until", now)
    state.pop("pending", None)
    state.pop("pending_created", None)
    state.pop("send_generation", None)
    state["report_id"] = str(uuid.uuid4())


def send_due(now=None):
    """One attempt per day. Keep the report ID within the receiver's retry window."""
    try:
        if forced_off():
            return False
        endpoint = _endpoint()
        if isolated() or not endpoint or _root is None or not _path().exists():
            return False
        now = time.time() if now is None else now
        path = _path()
        # Commit the attempt before network I/O so a crash cannot bypass the gate.
        with _transaction(path=path) as state:
            if (not state.get("install_id") or now - state.get("last_attempt", state["since"]) < DAY
                    or now - state["since"] < DAY):
                return False
            pending = state.get("pending")
            if pending and (not _uuid4(pending.get("report_id"))
                            or now - state.get("pending_created", 0) >= REPORT_RETENTION):
                # Legacy reports cannot safely gain an ID on retry, and expired
                # report markers cannot prevent double counting. Retire only
                # that snapshot, without claiming it was sent successfully.
                # Retire every old count, even keys a new wire payload would
                # omit to fit its byte limit. None of this legacy JSON is sent.
                _finish_report(state, now, pending)
            state["report_id"] = (_uuid4((state.get("pending") or {}).get("report_id"))
                                  or _uuid4(state.get("report_id")) or str(uuid.uuid4()))
            if state.get("pending"):
                payload = _sanitize_payload({**state["pending"], "install_id": state["install_id"],
                                             "report_id": state["report_id"]})
            else:
                payload = _payload(state, now)
                state["pending_until"] = now
                state["pending_created"] = now
            generation = str(uuid.uuid4())
            state["send_generation"] = generation
            state["last_attempt"] = now
            state["pending"] = payload
        status = _send_snapshot(endpoint, payload, path, generation)
        # A timed-out worker never touches storage. Off/on and a later send both
        # invalidate this generation, so late responses cannot affect new counts.
        if _root is None or path != _path():
            return False
        with _transaction(path=path) as state:
            if (state.get("install_id") != payload["install_id"]
                    or state.get("send_generation") != generation or forced_off() or isolated()):
                return False
            if status not in (204, 208):
                return False
            _finish_report(state, now, payload)
            state["history"] = (state.get("history", []) + [{
                "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "payload": payload}])[-10:]
            return True
    except Exception:
        log.debug("Usage send skipped")
        return False


def start_sender(sync_consent):
    def run():
        while True:
            try:
                sync_consent()
                send_due()
            except Exception:
                log.debug("Usage sender unavailable")
            time.sleep(60)
    try:
        threading.Thread(target=run, name="usage-sender", daemon=True).start()
    except Exception:
        log.debug("Usage sender could not start")
