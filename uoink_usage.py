"""Opt-in, bounded counts. No event bodies, credentials or network on callers.

The helper and stdio processes share a separate SQLite file. BEGIN IMMEDIATE
serializes consent, counter updates and sending across processes. Callers only
put fixed labels on a bounded queue; one daemon does local I/O. Only the helper
starts the daily sender. SQLite is from the standard library on all platforms.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import logging
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

USAGE_ENDPOINT = "https://usage.uoink.app/v1/ping"
DAY = 24 * 60 * 60
MAX_COUNT = 100000  # The usage receiver rejects any count above this.
MAX_TOOL_KEYS = 64
SOURCES = ("youtube", "x", "reddit", "page", "podcast", "image", "note", "other")
CLIENTS = {
    "claude desktop": "claude-desktop", "claude-desktop": "claude-desktop",
    "claude": "claude-desktop", "claude-code": "claude-code",
    "claude code": "claude-code", "cursor": "cursor", "cline": "cline",
    "continue": "continue", "codex": "codex", "openai-codex": "codex",
    "chatgpt": "chatgpt", "vscode": "vscode", "visual studio code": "vscode",
}
log = logging.getLogger(__name__)
_root = None
_version = "0"
_kind = "source"
_queue = queue.Queue(maxsize=1024)
_worker_lock = threading.Lock()
_worker = None
_capture = ContextVar("usage_capture", default=None)
_search = ContextVar("usage_search", default=False)


def configure(root, version, install_kind="source"):
    """Configure paths without opening any file or starting a sender."""
    global _root, _version, _kind
    _root = root
    _version = version if re.fullmatch(r"\d+(?:\.\d+){0,3}", version) else "0"
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


@contextmanager
def _transaction(create=False):
    path = _path()
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    # mode=rw prevents a late queued event from creating state while off.
    uri = path.as_uri() + ("?mode=rwc" if create else "?mode=rw")
    for attempt in range(4):
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=6)
            break
        except (PermissionError, sqlite3.OperationalError) as exc:
            # Windows sharing violations surface as SQLITE_CANTOPEN, outside
            # SQLite's busy timeout. Retry only opening, before any state change
            # or sender call can run, so a retry cannot duplicate either one.
            # A missing file while sharing is off is final, not a sharing violation.
            if (attempt == 3 or (not create and not path.exists())
                    or (not isinstance(exc, PermissionError)
                        and getattr(exc, "sqlite_errorcode", 0) & 0xff != sqlite3.SQLITE_CANTOPEN)):
                raise
            time.sleep(0.05 * 2 ** attempt)
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


def set_enabled(enabled):
    """Consent is authoritative across processes; off erases ID and history."""
    enabled = enabled is True and not forced_off()
    if _root is None or (not enabled and not _path().exists()):
        return
    with _transaction(create=enabled) as state:
        if enabled and not state.get("install_id"):
            last_attempt = state.get("last_attempt", 0)
            state.clear()
            now = time.time()
            state.update(install_id=str(uuid.uuid4()), since=now, enabled_at=now,
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
        return label if isinstance(label, str) and label in _tool_names() else None
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
    with _transaction() as state:
        if not state.get("install_id") or occurred < state.get("enabled_at", state["since"]):
            return
        counts = state.setdefault("counts", {})
        bucket = counts.setdefault(group, {})
        key = label + ":" + outcome if group == "captures" else label
        if group == "tools" and key not in bucket and len(bucket) >= MAX_TOOL_KEYS:
            return
        bucket[key] = min(MAX_COUNT, bucket.get(key, 0) + 1)


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


def search(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        nested = _search.get()
        token = _search.set(True)
        try:
            if not nested:
                count("searches")
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
                    count("captures", label, "ok" if scope["ok"] else "failed")
        return wrapped
    return decorate


def _metadata():
    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    # Windows 11 still reports major version 10; build 22000 is its first release.
    release = (platform.mac_ver()[0] if os_name == "macos" else
               ("11" if sys.getwindowsversion().build >= 22000 else str(sys.getwindowsversion().major))
               if os_name == "windows" else platform.release())
    major = re.match(r"\d{1,3}", release)
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64",
            "arm64": "arm64", "i386": "x86", "i686": "x86", "x86": "x86"}.get(machine, "other")
    return dict(version=_version, os=os_name, os_major=major[0] if major else "0",
                arch=arch, install_kind=_kind)


def _payload(state, now):
    if not state.get("install_id"):
        return None
    counts = state.get("counts", {})
    def bucket(group, allowed, cap):
        return {k: min(MAX_COUNT, max(0, int(v))) for k, v in
                sorted(counts.get(group, {}).items()) if k in allowed and v > 0} if cap is None else dict(
                    list(bucket(group, allowed, None).items())[:cap])
    payload = dict(schema=1, install_id=str(uuid.UUID(state["install_id"])), **_metadata(),
                   period_hours=round(max(0, now - state["since"]) / 3600, 2),
                   mcp_clients=bucket("mcp_clients", set(CLIENTS.values()) | {"other"}, 9),
                   transports=bucket("transports", {"stdio", "http"}, 2),
                   tools=bucket("tools", _tool_names(), MAX_TOOL_KEYS), captures={},
                   searches=min(MAX_COUNT, max(0, counts.get("searches", {}).get("count", 0))))
    for source in SOURCES:
        values = counts.get("captures", {})
        if any(values.get(source + ":" + outcome, 0) for outcome in ("ok", "failed")):
            payload["captures"][source] = {outcome: min(MAX_COUNT, max(0, values.get(source + ":" + outcome, 0)))
                                          for outcome in ("ok", "failed")}
    # The limit applies to actual compact UTF-8 bytes, even if registry names grow.
    while len(_encode(payload)) >= 4096 and payload["tools"]:
        payload["tools"].pop(next(reversed(payload["tools"])))
    if len(_encode(payload)) >= 4096:
        raise ValueError("usage payload exceeds limit")
    return payload


def _encode(payload):
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


def disclosure():
    empty = {"next_payload": None, "sent": []}
    try:
        if forced_off():
            set_enabled(False)
        if _root is None or not _path().exists():
            return empty
        with _transaction() as state:
            return {"next_payload": state.get("pending") or _payload(state, time.time()),
                    "sent": state.get("history", [])[-10:]}
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
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=5) as response:
        return 200 <= response.status < 300


def send_due(now=None):
    """One attempt per day across restarts. Retry a failed snapshot only once."""
    try:
        if forced_off():
            set_enabled(False)
            return False
        endpoint = _endpoint()
        if isolated() or not endpoint or _root is None or not _path().exists():
            return False
        now = time.time() if now is None else now
        # Commit the attempt before network I/O so a crash cannot bypass the gate.
        with _transaction() as state:
            if (not state.get("install_id") or now - state.get("last_attempt", state["since"]) < DAY
                    or now - state["since"] < DAY):
                return False
            payload = state.get("pending") or _payload(state, now)
            retry = bool(state.get("pending"))
            state["last_attempt"] = now
            state["pending"] = payload
            if not retry:
                state["pending_until"] = now
        # Recheck consent under the interprocess lock. Turning off waits only for
        # an already running request; after it returns no request can start.
        with _transaction() as state:
            if state.get("install_id") != payload["install_id"] or forced_off() or isolated():
                return False
            try:
                sent = _post(endpoint, payload)
            except Exception:
                log.debug("Usage send unavailable")
                sent = False
            if not sent:
                if retry:
                    state.pop("pending", None)
                    state.pop("pending_until", None)
                return False
            counts = state.get("counts", {})
            for group in ("tools", "transports", "mcp_clients", "captures", "searches"):
                values = payload[group]
                if group == "captures":
                    values = {s + ":" + o: n for s, outcomes in values.items() for o, n in outcomes.items()}
                elif group == "searches":
                    values = {"count": values}
                for key, n in values.items():
                    if key in counts.get(group, {}):
                        remaining = max(0, counts[group][key] - n)
                        if remaining:
                            counts[group][key] = remaining
                        else:
                            counts[group].pop(key)
                if not counts.get(group):
                    counts.pop(group, None)
            state["since"] = state.pop("pending_until", now)
            state.pop("pending", None)
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
