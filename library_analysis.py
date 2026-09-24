"""Pure aggregation and read-only activity reporting for Living Library run AZ.

Contract: phase5-v1 (docs/library/PHASE5-CONTRACT-2026-09-08.md).
Implements get_library_activity, report_revision content binding,
history coverage, survivor baseline churn proof, whats_new_adapter,
and narration faithfulness evaluator.
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import library_resources

# ---------------------------------------------------------------------------
# Canonical budget constants and schema definitions
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
CONTRACT_VERSION = "phase5-v1"

MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 65536
TARGET_DASHBOARD_BYTES = 24576
SERVICE_DEADLINE_SEC = 2.0
MAX_ACTIVE_READS = 2
RATE_LIMIT_ADMISSIONS = 60
RATE_LIMIT_WINDOW_SEC = 60.0
MAX_JOURNAL_BYTES = 64 * 1024 * 1024  # 64 MiB
MAX_METRIC_ID_BYTES = 512
MAX_LABEL_CODEPOINTS = 120
MAX_INTERVAL_DAYS = 30
MAX_DAILY_BUCKETS = 31

CANONICAL_SOURCE_TYPES = frozenset({
    "video",
    "episode",
    "x_thread",
    "x_article",
    "page",
    "reddit_thread",
    "note",
    "image",
    "short_video",
})

REQUIRED_TABLES = frozenset({
    "yoinks",
    "shelves",
    "shelf_versions",
    "shelf_nodes",
    "library_meta",
    "library_runs",
    "item_shelves",
    "library_applies",
    "library_operation_receipts",
    "source_subscriptions",
    "source_items",
    "source_detection_cursors",
    "podcast_episodes",
})

# ---------------------------------------------------------------------------
# Concurrency & Rate Limiting state
# ---------------------------------------------------------------------------

class RateLimitExceeded(Exception):
    pass

class _RollingRateLimiter:
    def __init__(self, max_calls: int, window_sec: float):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._lock = threading.Lock()
        self._calls: List[float] = []

    def check(self) -> None:
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            self._calls = [t for t in self._calls if t > cutoff]
            if len(self._calls) >= self.max_calls:
                raise RateLimitExceeded(f"rate limit exceeded: max {self.max_calls}/minute")
            self._calls.append(now)

_rate_limiter = _RollingRateLimiter(RATE_LIMIT_ADMISSIONS, RATE_LIMIT_WINDOW_SEC)
_active_reads_sem = threading.Semaphore(MAX_ACTIVE_READS)
_READER_NONCE = str(uuid.uuid4())
_CONN_NONCES: List[Tuple[sqlite3.Connection, str]] = []
_stdio_holds_admission = threading.local()


def _get_connection_nonce(conn: sqlite3.Connection) -> str:
    global _CONN_NONCES
    for c, nonce in _CONN_NONCES:
        if c is conn:
            return nonce
    n = str(uuid.uuid4())
    _CONN_NONCES.append((conn, n))
    if len(_CONN_NONCES) > 32:
        _CONN_NONCES.pop(0)
    return n
_analysis_db_override: Any = None


def set_analysis_db(db: Any) -> None:
    """Inject a database connection, Index instance, or callable for tests."""
    global _analysis_db_override
    _analysis_db_override = db


def reset_rate_limiter() -> None:
    """Reset the rolling rate limiter (for test isolation)."""
    with _rate_limiter._lock:
        _rate_limiter._calls.clear()
    _stdio_holds_admission.depth = 0
    library_resources.reset_transport_scopes()
    guard = getattr(library_resources, "_PROCESS_GUARD", None)
    if guard is not None:
        guard.clock = time.monotonic
        with guard._lock:
            guard._admissions.clear()
            guard._active = 0


# ---------------------------------------------------------------------------
# Canonical Serializer (Phase 4 serialize_card)
# ---------------------------------------------------------------------------

def serialize_card(card: dict) -> str:
    """Canonical JSON serialization safe inside Markdown/XML boundaries."""
    result = json.dumps(card, ensure_ascii=False, sort_keys=True, allow_nan=False)
    for char in "<>&`":
        result = result.replace(char, f"\\u{ord(char):04x}")
    return result


def canonical_json_hash(obj: Any) -> str:
    # BA-01: evidence hashes use Phase 4 serialize_card, not a second JSON dialect.
    return hashlib.sha256(serialize_card(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Error Envelope
# ---------------------------------------------------------------------------

def error_envelope(
    code: str,
    message: str,
    *,
    details: Optional[dict] = None,
    retryable: Optional[bool] = None,
) -> dict:
    retryable_map = {
        "rate_limited": True,
        "deadline_exceeded": True,
        "storage_unavailable": True,
        "recovery_pending": True,
        "stale_report": False,
        "validation_error": False,
        "not_found": False,
        "feature_unavailable": False,
        "invalid_source_data": False,
        "resource_too_large": False,
    }
    is_retryable = retryable if retryable is not None else retryable_map.get(code, False)
    err: Dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": is_retryable,
    }
    if details is not None:
        err["details"] = details
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "error": err,
    }


# ---------------------------------------------------------------------------
# Date / Time parsing and normalization
# ---------------------------------------------------------------------------

_ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$")
# Whole-string grammar: `$` would still admit a trailing newline before storage.
_FRACTIONAL_ISO_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{3}))?Z\Z")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def format_canonical_utc(dt: datetime) -> str:
    dt_utc = dt.astimezone(timezone.utc)
    ms = int(dt_utc.microsecond / 1000)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}Z"


def parse_iso_utc(text: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse ISO string. Returns (dt_utc, None) or (None, unavailable_reason)."""
    if not isinstance(text, str) or not text.strip():
        return None, "missing_unindexed"
    clean = text.strip()
    if _DATE_ONLY_RE.match(clean):
        return None, "date_only"
    if not _ISO_RE.match(clean):
        return None, "invalid"
    try:
        dt = datetime.fromisoformat(clean)
    except Exception:
        return None, "invalid"
    if dt.tzinfo is None:
        return None, "timezone_unknown"
    return dt.astimezone(timezone.utc), None


def parse_rfc2822_or_iso_utc(text: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse ISO or RFC 2822/RSS date text."""
    if not isinstance(text, str) or not text.strip():
        return None, "missing_unindexed"
    clean = text.strip()
    if _DATE_ONLY_RE.match(clean):
        return None, "date_only"
    # Try ISO
    if _ISO_RE.match(clean):
        dt, err = parse_iso_utc(clean)
        if dt is not None:
            return dt, None
        if err in ("date_only", "timezone_unknown"):
            return None, err
    # Try RFC 2822
    try:
        dt = email.utils.parsedate_to_datetime(clean)
        if dt.tzinfo is None:
            return None, "timezone_unknown"
        return dt.astimezone(timezone.utc), None
    except Exception:
        pass
    return None, "invalid"


def parse_epoch_ms(val: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse integer Unix milliseconds (source_items / cursor clocks)."""
    if val is None or val == 0 or val == "":
        return None, "missing_unindexed"
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None, "invalid"
    if isinstance(val, float) and not val.is_integer():
        return None, "invalid"
    val_int = int(val)
    if val_int < 0:
        return None, "invalid"
    try:
        dt = datetime.fromtimestamp(val_int / 1000.0, tz=timezone.utc)
        return dt, None
    except Exception:
        return None, "invalid"


def parse_native_creation_clock(val: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Admit library_applies / shelf_versions / library_runs creation clocks.

    BA-04: LibraryWorkService._stamp() stores integer milliseconds as decimal TEXT.
    Also accept integer milliseconds and timezone-aware ISO text. Do not reuse the
    source-item integer-ms parser for these TEXT columns.
    """
    if val is None or val == "":
        return None, "missing_unindexed"
    if isinstance(val, bool):
        return None, "invalid"
    if isinstance(val, (int, float)):
        return parse_epoch_ms(val)
    if isinstance(val, bytes):
        try:
            val = val.decode("utf-8")
        except Exception:
            return None, "invalid"
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return None, "missing_unindexed"
        dt, err = parse_iso_utc(text)
        if dt is not None:
            return dt, None
        if err in ("date_only", "timezone_unknown"):
            return None, err
        if re.fullmatch(r"-?\d+", text):
            try:
                return parse_epoch_ms(int(text))
            except Exception:
                return None, "invalid"
        return None, "invalid"
    return None, "invalid"


def parse_interval(interval: Any, as_of_dt: datetime) -> Tuple[Optional[datetime], Optional[datetime], Optional[dict]]:
    """Validate and parse requested interval."""
    if not isinstance(interval, dict):
        return None, None, error_envelope("validation_error", "interval must be an object with start and end")
    extra_fields = set(interval.keys()) - {"start", "end"}
    if extra_fields:
        return None, None, error_envelope("validation_error", f"Unknown field in interval: {sorted(extra_fields)}", details={"unknown": sorted(extra_fields)})
    if "start" not in interval or "end" not in interval:
        return None, None, error_envelope("validation_error", "interval requires both start and end timestamps")
    s_raw = interval.get("start")
    e_raw = interval.get("end")
    if not isinstance(s_raw, str) or not isinstance(e_raw, str):
        return None, None, error_envelope("validation_error", "interval bounds must be strings")

    # Strict UTC ISO regex with fractional bounds (whole string, including no trailing newline)
    match_s = _FRACTIONAL_ISO_RE.fullmatch(s_raw)
    match_e = _FRACTIONAL_ISO_RE.fullmatch(e_raw)
    if not match_s or not match_e:
        return None, None, error_envelope("validation_error", "interval bounds must be valid ISO 8601 UTC with optional 3-digit millisecond fraction")

    frac_s = match_s.group(1)
    frac_e = match_e.group(1)
    if frac_s is not None and len(frac_s) != 3:
        return None, None, error_envelope("validation_error", "fractional seconds must have exactly 3 digits")
    if frac_e is not None and len(frac_e) != 3:
        return None, None, error_envelope("validation_error", "fractional seconds must have exactly 3 digits")

    dt_start, s_err = parse_iso_utc(s_raw)
    dt_end, e_err = parse_iso_utc(e_raw)
    if dt_start is None or dt_end is None:
        return None, None, error_envelope("validation_error", f"Malformed interval boundary: start={s_err}, end={e_err}")
    if dt_start >= dt_end:
        return None, None, error_envelope("validation_error", "interval start must be strictly before end (half-open [start, end))")

    span_ms = (dt_end - dt_start).total_seconds() * 1000.0
    if span_ms > MAX_INTERVAL_DAYS * 86_400_000:
        return None, None, error_envelope("validation_error", f"interval duration cannot exceed {MAX_INTERVAL_DAYS} days")
    if dt_end > as_of_dt:
        return None, None, error_envelope("validation_error", "interval end cannot be in the future beyond as_of")
    return dt_start, dt_end, None


# ---------------------------------------------------------------------------
# Database connection and snapshot resolution
# ---------------------------------------------------------------------------

def _is_flag01(val: Any) -> bool:
    return type(val) is int and val in (0, 1)


def _is_unit_real(val: Any) -> bool:
    """A JSON number (not bool) inside [0, 1]: the item_shelves.confidence domain."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    try:
        return 0.0 <= float(val) <= 1.0 and float(val) == float(val)
    except (TypeError, ValueError, OverflowError):
        return False


def _is_json_text(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    try:
        json.loads(val)
    except Exception:
        return False
    return True


# Service-emitted membership rows are complete item_shelves rows (library_work
# LibraryWorkService._snapshot selects every column). The reader validates the
# full typed row rather than the shelf id alone; an abbreviated synthetic row is
# invalid source data, not a partial membership.
MEMBERSHIP_ROW_FIELDS = (
    "shelf_id", "version_id", "source_revision", "source", "locked",
    "is_primary", "confidence", "evidence_json", "assigned_at",
)
MEMBERSHIP_SOURCES = frozenset({"agent", "user"})
# Fields whose values define the replayed membership state. ``video_id`` is the
# map key and is checked separately when a row carries it.
MEMBERSHIP_STATE_FIELDS = MEMBERSHIP_ROW_FIELDS


def _validate_membership_row(vid: str, row: Any) -> bool:
    """One complete typed item_shelves row as emitted by the library service."""
    if not isinstance(row, dict):
        return False
    for field in MEMBERSHIP_ROW_FIELDS:
        if field not in row:
            return False
    for key in row:
        if not isinstance(key, str) or (key != "video_id" and key not in MEMBERSHIP_ROW_FIELDS):
            return False
    for ident in ("shelf_id", "version_id"):
        val = row[ident]
        if not isinstance(val, str) or not val:
            return False
    for text_field in ("source_revision", "assigned_at"):
        if not isinstance(row[text_field], str):
            return False
    if not isinstance(row["source"], str) or row["source"] not in MEMBERSHIP_SOURCES:
        return False
    if not _is_flag01(row["locked"]) or not _is_flag01(row["is_primary"]):
        return False
    confidence = row["confidence"]
    if confidence is not None and not _is_unit_real(confidence):
        return False
    evidence = row["evidence_json"]
    if evidence is not None and not _is_json_text(evidence):
        return False
    if "video_id" in row:
        if not isinstance(row["video_id"], str) or row["video_id"] != vid:
            return False
    # item_shelves CHECK constraints: a lock is a user assignment without
    # confidence; an agent assignment carries confidence and evidence.
    if row["locked"] == 1 and (row["source"] != "user" or confidence is not None):
        return False
    if row["source"] == "agent" and (confidence is None or evidence is None):
        return False
    return True


def _validate_policy_row(vid: str, policy: Any) -> bool:
    """One library_item_policy row (or null for a removed policy)."""
    if policy is None:
        return True
    if not isinstance(policy, dict):
        return False
    if "exclusive_move" not in policy or not _is_flag01(policy["exclusive_move"]):
        return False
    if "video_id" in policy:
        if not isinstance(policy["video_id"], str) or policy["video_id"] != vid:
            return False
    for key, val in policy.items():
        if not isinstance(key, str):
            return False
        if key not in ("video_id", "exclusive_move"):
            return False
    return True


def _validate_delta_structure(delta: Any) -> bool:
    """BA-05: typed forward/inverse maps of complete membership/policy rows."""
    if not isinstance(delta, dict):
        return False
    if "items" not in delta or "policies" not in delta:
        return False
    if not isinstance(delta["items"], dict) or not isinstance(delta["policies"], dict):
        return False
    for vid, rows in delta["items"].items():
        if not isinstance(vid, str) or not vid or not isinstance(rows, list):
            return False
        seen_shelves: Set[str] = set()
        for r in rows:
            if not _validate_membership_row(vid, r):
                return False
            if r["shelf_id"] in seen_shelves:
                return False
            seen_shelves.add(r["shelf_id"])
    for k, policy in delta["policies"].items():
        if not isinstance(k, str) or not k:
            return False
        if not _validate_policy_row(k, policy):
            return False
    if "active_version_id" in delta:
        active = delta["active_version_id"]
        if active is not None and not isinstance(active, str):
            return False
    return True


def _membership_state(rows: Any) -> Dict[str, Tuple[Any, ...]]:
    """Shelf id -> the full typed membership values used for replay comparison."""
    state: Dict[str, Tuple[Any, ...]] = {}
    for r in rows:
        state[r["shelf_id"]] = tuple(r.get(f) for f in MEMBERSHIP_STATE_FIELDS)
    return state


# Receipt statuses that prove a recorded apply. The library service publishes
# ``{"ok": true, ..., "no_change": false}`` for an applied operation and
# ``no_change: true`` for a receipt without an apply row; fixtures spell the
# same outcomes as ``status``. Anything else (failed, invented, untyped,
# ok:false) is not a successful receipt and cannot qualify an apply.
SUCCESSFUL_APPLY_RECEIPT_STATUSES = frozenset({"applied"})


def _receipt_data(receipt_json: Any) -> Optional[dict]:
    if receipt_json is None or receipt_json == "":
        return None
    try:
        data = json.loads(receipt_json) if isinstance(receipt_json, str) else receipt_json
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _receipt_status(receipt_json: Any) -> Optional[str]:
    data = _receipt_data(receipt_json)
    if data is None:
        return None
    status = data.get("status")
    if status is not None:
        if not isinstance(status, str) or not status:
            return None
        return status
    if data.get("ok") is True:
        return "no_change" if data.get("no_change") is True else "applied"
    return None


def _is_no_change_receipt(receipt_json: Any) -> bool:
    data = _receipt_data(receipt_json)
    if data is None or data.get("ok") is False:
        return False
    status = data.get("status")
    if status is not None:
        return status == "no_change"
    return data.get("no_change") is True


def _receipt_qualifies_apply(receipt_json: Any) -> bool:
    """Only a successful, non-no-change receipt binds a recorded apply."""
    data = _receipt_data(receipt_json)
    if data is None:
        return False
    if data.get("ok") is False or data.get("no_change") is True:
        return False
    return _receipt_status(receipt_json) in SUCCESSFUL_APPLY_RECEIPT_STATUSES


def _creator_hint_key(item: dict) -> Tuple[str, str, str]:
    """Frozen (platform, field, trimmed-value) grouping key. BA-02."""
    platform = item.get("platform") or "unknown"
    author = item.get("author") or ""
    channel = item.get("channel") or ""
    author_trim = author.strip() if isinstance(author, str) else ""
    channel_trim = channel.strip() if isinstance(channel, str) else ""
    if author_trim:
        return platform, "author", author_trim
    if channel_trim:
        return platform, "channel", channel_trim
    return platform, "unknown", ""


def _display_hint(value: str) -> Tuple[str, bool]:
    raw = value.strip() if value and str(value).strip() else "unknown"
    return _bound_label(raw)


def _get_connection() -> Tuple[Optional[sqlite3.Connection], Any, Optional[dict], bool]:
    """Obtain a SQLite connection and lock. Returns (conn, lock, err_envelope, should_close)."""
    global _analysis_db_override
    if _analysis_db_override is not None:
        override = _analysis_db_override
        lock = getattr(override, "_lock", None)
        if isinstance(override, sqlite3.Connection):
            return override, lock, None, False
        if hasattr(override, "_conn") and isinstance(override._conn, sqlite3.Connection):
            return override._conn, lock, None, False
        if callable(override):
            override = override()
            lock = getattr(override, "_lock", None)
        if isinstance(override, sqlite3.Connection):
            return override, lock, None, False
        if hasattr(override, "_conn") and isinstance(override._conn, sqlite3.Connection):
            return override._conn, lock, None, False
        if isinstance(override, (str, os.PathLike)):
            if not os.path.exists(override):
                return None, None, error_envelope("storage_unavailable", f"Database file does not exist: {override}"), False
            try:
                c = sqlite3.connect(
                    f"file:{os.path.abspath(override)}?mode=ro", uri=True, timeout=0)
                return c, None, None, True
            except Exception as e:
                return None, None, error_envelope("storage_unavailable", f"Failed to open database: {e}"), False
        return None, None, error_envelope("storage_unavailable", "Invalid database override"), False

    # Check backend
    backend = sys.modules.get("server")
    if backend is None:
        try:
            import uoink_mcp_tools
            backend = getattr(uoink_mcp_tools, "_backend", None)
        except Exception:
            backend = None

    if backend is not None:
        if getattr(backend, "_index_recovering", False):
            return None, None, error_envelope("recovery_pending", "Database index recovery is in progress"), False
        idx_singleton = getattr(backend, "_index_singleton", None)
        if idx_singleton is not None and hasattr(idx_singleton, "_conn"):
            return idx_singleton._conn, getattr(idx_singleton, "_lock", None), None, False
        idx_path = getattr(backend, "INDEX_PATH", None)
        if idx_path:
            if not os.path.exists(idx_path):
                return None, None, error_envelope("storage_unavailable", f"Index file not found: {idx_path}"), False
            try:
                c = sqlite3.connect(
                    f"file:{os.path.abspath(idx_path)}?mode=ro", uri=True, timeout=0)
                return c, None, None, True
            except Exception as e:
                return None, None, error_envelope("storage_unavailable", f"Cannot open index: {e}"), False

    return None, None, error_envelope("storage_unavailable", "No library database available"), False


def _verify_tables(conn: sqlite3.Connection) -> Optional[dict]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cursor.fetchall()}
    missing = REQUIRED_TABLES - existing
    if missing:
        return error_envelope(
            "feature_unavailable",
            f"Missing required database tables: {sorted(missing)}",
            details={"missing_tables": sorted(missing)},
        )
    return None


def _get_db_generation(conn: sqlite3.Connection) -> Dict[str, Any]:
    dv_row = conn.execute("PRAGMA data_version").fetchone()
    data_version = dv_row[0] if dv_row else 0
    return {
        "nonce": _get_connection_nonce(conn),
        "total_changes": conn.total_changes,
        "data_version": data_version,
    }


def _generation_changed(gen_start: Dict[str, Any], gen_end: Dict[str, Any]) -> bool:
    return (gen_end["total_changes"] != gen_start["total_changes"]
            or gen_end["data_version"] != gen_start["data_version"])


def _snapshot_owner(conn: sqlite3.Connection, *candidates: Any) -> Any:
    """The Index (or Index-like object) that owns ``conn`` and exposes read_snapshot."""
    seen: List[Any] = []
    for cand in candidates:
        if cand is None or isinstance(cand, (sqlite3.Connection, str, os.PathLike)):
            continue
        seen.append(cand)
    backend = sys.modules.get("server")
    if backend is None:
        try:
            import uoink_mcp_tools
            backend = getattr(uoink_mcp_tools, "_backend", None)
        except Exception:
            backend = None
    if backend is not None:
        seen.append(getattr(backend, "_index_singleton", None))
    for cand in seen:
        if cand is None:
            continue
        if getattr(cand, "_conn", None) is conn and callable(getattr(cand, "read_snapshot", None)):
            return cand
    return None


@contextmanager
def _local_read_snapshot(conn: sqlite3.Connection):
    """Index.read_snapshot's transaction protocol for a bare connection.

    Used only when no Index owns the connection (injected sqlite3 connections
    and read-only path connections); the Index lock is handled by the caller.
    """
    if conn.in_transaction:
        raise RuntimeError("cannot start a read snapshot while another transaction is active")
    try:
        conn.execute("BEGIN DEFERRED")
        yield conn
    finally:
        if conn.in_transaction:
            conn.rollback()


class _ReadBoundary:
    """One SQLite snapshot for the activity read (BA-08).

    ``enter`` opens the shared ``Index.read_snapshot`` boundary when the
    connection belongs to an Index, otherwise the same protocol locally.
    ``finish`` ends the snapshot (rollback) so a later generation read can see
    commits made by other connections during construction; the caller keeps
    the Index lock until it has decided what to return.
    """

    def __init__(self, conn: sqlite3.Connection, owner: Any):
        self._conn = conn
        self._owner = owner
        self._cm: Any = None
        self.active = False

    def enter(self) -> sqlite3.Connection:
        if self._owner is not None:
            cm = self._owner.read_snapshot()
        else:
            cm = _local_read_snapshot(self._conn)
        entered = cm.__enter__()
        self._cm = cm
        self.active = True
        return entered if isinstance(entered, sqlite3.Connection) else self._conn

    def finish(self) -> None:
        if not self.active:
            return
        self.active = False
        cm, self._cm = self._cm, None
        try:
            cm.__exit__(None, None, None)
        except sqlite3.Error:
            pass


def _sqlite_busy_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in text or "busy" in text)


def _remaining_activity_budget(deadline: float) -> float:
    return deadline - time.monotonic()


def _call_until_activity_deadline(deadline: float, fn):
    """Run ``fn`` without waiting past ``deadline`` on SQLITE_BUSY.

    ``PRAGMA busy_timeout`` is 0 for the snapshot, so a holder of BEGIN
    EXCLUSIVE fails immediately; this retries until the original inbound
    deadline instead of starting a fresh 2 s wait.
    """
    while True:
        rem = _remaining_activity_budget(deadline)
        if rem <= 0:
            return None, error_envelope(
                "deadline_exceeded", "Service deadline exceeded before SQLite snapshot")
        try:
            return fn(), None
        except sqlite3.OperationalError as exc:
            if not _sqlite_busy_error(exc):
                raise
            rem = _remaining_activity_budget(deadline)
            if rem <= 0:
                return None, error_envelope(
                    "deadline_exceeded", f"Database busy wait exceeded deadline: {exc}")
            time.sleep(min(0.02, rem))


# ---------------------------------------------------------------------------
# Aggregation Implementation
# ---------------------------------------------------------------------------

def _build_daily_buckets(dt_start: datetime, dt_end: datetime) -> List[Tuple[datetime, datetime]]:
    buckets: List[Tuple[datetime, datetime]] = []
    curr_day = datetime(dt_start.year, dt_start.month, dt_start.day, tzinfo=timezone.utc)
    while curr_day < dt_end:
        next_day = curr_day + timedelta(days=1)
        b_start = max(dt_start, curr_day)
        b_end = min(dt_end, next_day)
        if b_start < b_end:
            buckets.append((b_start, b_end))
        curr_day = next_day
    return buckets[:MAX_DAILY_BUCKETS]


def _ratio_metric(
    metric_id: str,
    numerator: int,
    denominator: int,
    scope_ref: str,
    *,
    reason: Optional[str] = None,
    denominator_metric_id: Optional[str] = None,
) -> dict:
    percent: Optional[float] = None
    res_reason = reason
    if denominator == 0:
        if res_reason is None:
            res_reason = "empty_population"
        percent = None
    else:
        # Exact decimal half-up rounding to 2 decimal places
        pct = (Decimal(str(numerator)) * 100 / Decimal(str(denominator))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        percent = float(pct)
    m = {
        "metric_id": metric_id,
        "value": numerator if denominator > 0 else 0,
        "unit": "ratio",
        "scope_ref": scope_ref,
        "numerator": numerator,
        "denominator": denominator,
        "percent": percent,
        "reason": res_reason,
        "evidence": _evidence_descriptor(metric_id, "numerator"),
    }
    if denominator_metric_id:
        _attach_denominator_evidence(m, denominator_metric_id)
    return m


# ---------------------------------------------------------------------------
# BA-01: compact metric-to-support relation references
# ---------------------------------------------------------------------------
# Compact evidence on each metric: role plus exact support/sample counts.
# ``provenance.relations`` is the metric-to-support registry (scope, clock,
# source tables), keyed by relation id from ``_relation_id_for``. Supporting
# observation rows live only on the paged evidence endpoint. Observation
# hashes are on those page rows, not on the summary descriptor; a first-page
# digest is not a population hash. Numerator descriptors omit metric_id: the
# enclosing metric already carries it (dashboard and Astra merge
# ``{**metric, **evidence}``). Denominator references keep ``{metric_id,role}``
# so they resolve without the enclosing metric.

EVIDENCE_PAGE_LIMIT = 20

# Relation ids are short on purpose: they appear once per metric on the wire.
_RELATION_ITEMS = "items"
_RELATION_LIVE = "live"
_RELATION_PUBLICATION = "publication"
_RELATION_TOMBSTONES = "tombstones"
_RELATION_JOURNAL = "journal"
_RELATION_SHELF_CURRENT = "shelf_current"
_RELATION_BASELINE = "baseline"
_RELATION_CAPTURES = "captures"
_RELATION_OBSERVATIONS = "observations"
_RELATION_REVISIONS = "revisions"
_RELATION_EVENTS = "events"


def _relation_id_for(metric_id: str) -> str:
    """Map a metric id to its metric-to-support relation id (BA-01 registry)."""
    if metric_id.startswith("items."):
        if metric_id in ("items.live_population", "items.capture_time_available", "items.capture_time_unavailable"):
            return _RELATION_LIVE
        if metric_id.startswith("items.publication_"):
            return _RELATION_PUBLICATION
        if metric_id.startswith("items.deleted_items_"):
            return _RELATION_TOMBSTONES
        return _RELATION_ITEMS
    if metric_id.startswith("shelf_activity."):
        if metric_id in ("shelf_activity.current_assigned_items", "shelf_activity.current_memberships"):
            return _RELATION_SHELF_CURRENT
        if metric_id.startswith("shelf_activity.churn") or metric_id == "shelf_activity.initial_filing_items":
            return _RELATION_BASELINE
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[1] == "shelves":
            kind = parts[3]
            if kind == "current_size":
                return _RELATION_SHELF_CURRENT
            if kind in ("start_size", "end_size", "churn"):
                return _RELATION_BASELINE
        return _RELATION_JOURNAL
    if metric_id.startswith("sources."):
        if metric_id in ("sources.linked_capture_union_count", "sources.multiply_linked_capture_count"):
            return _RELATION_CAPTURES
        if metric_id in ("sources.active_sources_count", "sources.unlinked_hint_groups_count"):
            return _RELATION_OBSERVATIONS
        if metric_id.endswith(".captures"):
            return _RELATION_CAPTURES
        return _RELATION_OBSERVATIONS
    if metric_id.startswith("revisions."):
        return _RELATION_REVISIONS
    if metric_id.startswith("events."):
        return _RELATION_EVENTS
    return _RELATION_ITEMS


def _build_relation_registry(date_basis: str, scope_items_ref: str) -> Dict[str, dict]:
    """``provenance.relations``: one entry per relation, resolving scope, clock and source tables once."""
    item_tables = ["yoinks"] if date_basis == "capture_time" else ["source_items", "podcast_episodes", "yoinks"]
    return {
        _RELATION_ITEMS: {"support": "selected_item_observations", "scope_ref": scope_items_ref, "clock": date_basis, "source_tables": item_tables},
        _RELATION_LIVE: {"support": "live_saved_items", "scope_ref": "scope_items_capture", "clock": "capture_time", "source_tables": ["yoinks"]},
        _RELATION_PUBLICATION: {"support": "publication_candidates", "scope_ref": "scope_items_publication", "clock": "publication_time", "source_tables": ["source_items", "podcast_episodes", "yoinks"]},
        _RELATION_TOMBSTONES: {"support": "deleted_saved_items", "scope_ref": "scope_items_tombstones", "clock": "capture_time", "source_tables": ["yoinks"]},
        _RELATION_JOURNAL: {"support": "applied_operations", "scope_ref": "scope_shelf_activity", "clock": "applied_journal_time", "source_tables": ["library_applies"]},
        _RELATION_SHELF_CURRENT: {"support": "current_memberships", "scope_ref": "scope_shelf_current", "clock": "as_of", "source_tables": ["item_shelves"]},
        _RELATION_BASELINE: {"support": "replayed_memberships", "scope_ref": "scope_shelf_baseline", "clock": "applied_journal_time", "source_tables": ["library_applies", "item_shelves"]},
        _RELATION_CAPTURES: {"support": "captured_items_by_source", "scope_ref": "scope_source_captures", "clock": "capture_time", "source_tables": ["yoinks", "source_items"]},
        _RELATION_OBSERVATIONS: {"support": "source_observations", "scope_ref": "scope_sources", "clock": "observation_time", "source_tables": ["source_items", "source_subscriptions"]},
        _RELATION_REVISIONS: {"support": "recorded_revisions", "scope_ref": "scope_revisions", "clock": "creation_time", "source_tables": ["shelf_versions", "library_runs"]},
        _RELATION_EVENTS: {"support": "combined_events", "scope_ref": "scope_events", "clock": "event_time", "source_tables": ["yoinks", "library_applies", "shelf_versions", "library_runs"]},
    }


def _evidence_descriptor(metric_id: str, role: str) -> dict:
    """Unbound compact selector; counts are bound by ``_bind_support``.

    Numerators omit metric_id (the enclosing metric already has it).
    Denominators keep metric_id because they name a different metric.
    Relation ids stay in ``provenance.relations``, not on every descriptor.
    """
    if role != "numerator":
        return {"metric_id": metric_id, "role": role}
    return {"role": role}


class _EvidenceRows(list):
    """Evidence rows for one metric: every supporting observation is counted,
    but at most ``limit`` rows are constructed (bounded work, BA-11). ``add``
    takes a zero-argument builder so unconstructed rows cost nothing."""

    def __init__(self, limit: Optional[int] = None):
        super().__init__()
        self.limit = limit
        self.total_rows = 0

    def add(self, build: Any) -> None:
        self.total_rows += 1
        if self.limit is None or len(self) < self.limit:
            self.append(build())


def _bind_support(descriptor: dict, rows: Optional[List[dict]]) -> None:
    """Bind exact support/sample counts. Do not attach a summary observation
    hash: page rows carry per-observation hashes, and a first-page digest
    would not be a population hash."""
    total = getattr(rows, "total_rows", None)
    if total is None:
        total = len(rows or [])
    descriptor["row_count"] = total
    descriptor["sample_count"] = min(EVIDENCE_PAGE_LIMIT, total)
    descriptor["has_more"] = total > EVIDENCE_PAGE_LIMIT


def _iter_metric_dicts(node: Any):
    """Yield every metric dict (has ``metric_id`` and a dict ``evidence``) in a response subtree."""
    if isinstance(node, dict):
        if isinstance(node.get("metric_id"), str) and isinstance(node.get("evidence"), dict):
            yield node
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from _iter_metric_dicts(child)
    elif isinstance(node, list):
        for child in node:
            yield from _iter_metric_dicts(child)


class CountMetric(dict):
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return self.get("value") == other
        return super().__eq__(other)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __int__(self) -> int:
        val = self.get("value")
        return int(val) if val is not None else 0

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            val = self.get("value")
            return (val if val is not None else 0) < other
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            val = self.get("value")
            return (val if val is not None else 0) <= other
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            val = self.get("value")
            return (val if val is not None else 0) > other
        return NotImplemented

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            val = self.get("value")
            return (val if val is not None else 0) >= other
        return NotImplemented

    def __sub__(self, other: Any) -> Any:
        val = self.get("value")
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return (val if val is not None else 0) - other
        return NotImplemented

    def __rsub__(self, other: Any) -> Any:
        val = self.get("value")
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return other - (val if val is not None else 0)
        return NotImplemented


def _count_metric(
    metric_id: str,
    value: Optional[int],
    unit: str,
    scope_ref: str,
    *,
    recorded_count: Optional[int] = None,
    coverage_ref: Optional[str] = None,
) -> CountMetric:
    m = {
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "scope_ref": scope_ref,
        "evidence": _evidence_descriptor(metric_id, "numerator"),
    }
    if value is None or recorded_count is not None:
        m["recorded_count"] = recorded_count if recorded_count is not None else 0
    if coverage_ref:
        m["coverage_ref"] = coverage_ref
    return CountMetric(m)


def _metric_value_or_zero(metric: Any) -> int:
    if not isinstance(metric, dict):
        return 0
    val = metric.get("value")
    return val if isinstance(val, int) else 0


def _attach_denominator_evidence(metric: dict, denom_metric_id: str) -> None:
    """BA-01: distinct addressable denominator relation (a reference to another metric id)."""
    ev = metric.setdefault("evidence", {})
    if isinstance(ev, dict):
        ev["denominator"] = {"metric_id": denom_metric_id, "role": "denominator"}


def _mark_no_history(metric: Optional[dict]) -> None:
    if not isinstance(metric, dict):
        return
    metric["value"] = None
    metric["recorded_count"] = 0


def _truncate_label(label: str) -> str:
    if len(label) <= MAX_LABEL_CODEPOINTS:
        return label
    return label[: MAX_LABEL_CODEPOINTS - 3] + "..."


def _bound_label(label: Any) -> Tuple[str, bool]:
    """Cap a display label at 120 code points and report whether it was truncated."""
    raw = label if isinstance(label, str) else ("" if label is None else str(label))
    shown = _truncate_label(raw)
    return shown, shown != raw


def _adapter_admission_depth() -> int:
    return int(getattr(_stdio_holds_admission, "depth", 0) or 0)


@contextmanager
def adapter_admission():
    """Hold the shared process guard through adapter serialization (BA-11).

    Nested entry increments the per-thread depth so an inner scope cannot
    release or clear an outer active admission. A stdio transport scope for
    this request already holds the slot; this context then only nests.
    """
    guard = library_resources.process_guard()
    depth = _adapter_admission_depth()
    _stdio_holds_admission.depth = depth + 1
    owns = depth == 0 and library_resources.current_transport_scope() is None
    try:
        if owns:
            guard.admit()
    except Exception:
        _stdio_holds_admission.depth = depth
        raise
    try:
        yield
    finally:
        _stdio_holds_admission.depth = depth
        if owns:
            try:
                guard.release()
            except Exception:
                pass


def _activity_start_time() -> float:
    """Inbound admission stamp when a transport scope already holds the slot.

    Direct/HTTP callers have no transport scope, so the clock starts here.
    """
    scope = library_resources.current_transport_scope()
    if scope is not None and scope.admitted_at is not None:
        return float(scope.admitted_at)
    return time.monotonic()


def get_library_activity(
    args: dict,
    *,
    db: Any = None,
    clock: Any = None,
) -> dict:
    """Entry point for get_library_activity read tool."""
    guard = library_resources.process_guard()
    owns_admission = (
        _adapter_admission_depth() == 0
        and library_resources.current_transport_scope() is None
    )
    if owns_admission:
        try:
            guard.admit()
        except library_resources.ResourceError as e:
            return error_envelope(e.code, e.message, details=e.details, retryable=True)
        except Exception as e:
            return error_envelope("rate_limited", str(e), retryable=True)

    start_time = _activity_start_time()
    try:
        return _execute_activity(args, db=db, clock=clock, start_time=start_time)
    finally:
        if owns_admission:
            guard.release()


def _calculate_transport_bytes(resp_dict: dict) -> int:
    try:
        import library_resources
        rendered = library_resources.render_tool_text(resp_dict)
        payload = {"content": [{"type": "text", "text": rendered}], "isError": False}
        return library_resources.wire_bytes(payload) + 256
    except Exception:
        return len(json.dumps(resp_dict, ensure_ascii=False).encode("utf-8"))


def _execute_activity(
    args: dict,
    *,
    db: Any = None,
    clock: Any = None,
    start_time: float,
) -> dict:
    def _check_deadline() -> Optional[dict]:
        if time.monotonic() - start_time > SERVICE_DEADLINE_SEC:
            return error_envelope("deadline_exceeded", "Service deadline exceeded", retryable=True)
        return None

    # Validate request size
    try:
        req_bytes = len(json.dumps(args, ensure_ascii=False).encode("utf-8"))
        if req_bytes > MAX_REQUEST_BYTES:
            return error_envelope("resource_too_large", f"Request exceeds {MAX_REQUEST_BYTES} bytes")
    except Exception:
        pass

    if not isinstance(args, dict):
        return error_envelope("validation_error", "Arguments must be an object")

    allowed_args = {"interval", "date_basis", "detail", "metric_id", "offset", "limit", "expected_revision"}
    for k in args:
        if k not in allowed_args:
            return error_envelope("validation_error", f"Unknown field: {k}", details={"unknown": [k]})

    # Freeze as_of
    if clock is not None:
        if callable(clock):
            now_dt = clock()
        elif isinstance(clock, datetime):
            now_dt = clock
        else:
            now_dt = datetime.now(timezone.utc)
    else:
        now_dt = datetime.now(timezone.utc)
    as_of_str = format_canonical_utc(now_dt)
    as_of_dt = datetime.fromisoformat(as_of_str)

    # Validate interval
    if "interval" not in args or args["interval"] is None:
        return error_envelope("validation_error", "interval is required and cannot be null")
    interval_raw = args["interval"]
    dt_start, dt_end, int_err = parse_interval(interval_raw, as_of_dt)
    if int_err is not None:
        return int_err

    canonical_start = format_canonical_utc(dt_start)
    canonical_end = format_canonical_utc(dt_end)
    canonical_interval = {"start": canonical_start, "end": canonical_end}

    date_basis = "capture_time"
    if "date_basis" in args:
        db_val = args["date_basis"]
        if not isinstance(db_val, str) or db_val not in ("capture_time", "publication_time"):
            return error_envelope("validation_error", f"Invalid date_basis: {db_val}")
        date_basis = db_val

    valid_details = {"creator_hints", "type_creator_hints", "shelves", "sources", "events", "evidence"}
    if "detail" in args:
        det_val = args["detail"]
        if not isinstance(det_val, str) or det_val not in valid_details:
            return error_envelope("validation_error", f"Invalid detail: {det_val}")
    detail = args.get("detail")

    if detail is None:
        if "offset" in args or "limit" in args:
            return error_envelope("validation_error", "Pagination offset and limit are permitted only for detail requests")
        if "expected_revision" in args:
            return error_envelope("validation_error", "expected_revision is permitted only for detail requests")
        if "metric_id" in args:
            return error_envelope("validation_error", "metric_id is permitted only for detail:evidence requests")
        offset = 0
        limit = 20
    else:
        if "expected_revision" not in args or not isinstance(args["expected_revision"], str) or not re.match(r"^[0-9a-f]{64}$", args["expected_revision"]):
            return error_envelope("validation_error", "expected_revision (64 lowercase hex) is required for detail requests")
        expected_revision = args["expected_revision"]

        if detail == "evidence":
            if "metric_id" not in args or not isinstance(args["metric_id"], str) or not args["metric_id"].strip():
                return error_envelope("validation_error", "metric_id is required for detail:evidence")
            metric_id = args["metric_id"]
            if len(metric_id.encode("utf-8")) > MAX_METRIC_ID_BYTES:
                return error_envelope("validation_error", f"metric_id cannot exceed {MAX_METRIC_ID_BYTES} bytes")
        else:
            if "metric_id" in args:
                return error_envelope("validation_error", "metric_id is permitted only for detail:evidence requests")
            metric_id = None

        if "offset" in args:
            offset = args["offset"]
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset > 1_000_000:
                return error_envelope("validation_error", "offset must be integer between 0 and 1,000,000")
        else:
            offset = 0

        if "limit" in args:
            limit = args["limit"]
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 20:
                return error_envelope("validation_error", "limit must be integer between 1 and 20")
        else:
            limit = 20

    deadline = start_time + SERVICE_DEADLINE_SEC
    rem = _remaining_activity_budget(deadline)
    if rem <= 0:
        return error_envelope("deadline_exceeded", "Service deadline exceeded before lock acquisition")

    # Connect to DB
    if db is not None:
        old_override = _analysis_db_override
        set_analysis_db(db)
        conn, lock, conn_err, should_close = _get_connection()
        set_analysis_db(old_override)
    else:
        conn, lock, conn_err, should_close = _get_connection()

    if conn_err is not None:
        return conn_err
    assert conn is not None
    snapshot_owner = _snapshot_owner(conn, db if db is not None else _analysis_db_override)

    try:
        if conn.in_transaction:
            return error_envelope("storage_unavailable", "Refusing inherited uncommitted transaction")
    except sqlite3.Error as exc:
        return error_envelope("storage_unavailable", f"Database error: {exc}")

    rem = _remaining_activity_budget(deadline)
    if rem <= 0:
        return error_envelope("deadline_exceeded", "Service deadline exceeded before lock acquisition")

    lock_acquired = False
    if lock is not None:
        if hasattr(lock, "acquire"):
            lock_acquired = lock.acquire(timeout=max(0.0, rem))
            if not lock_acquired:
                return error_envelope("deadline_exceeded", "Service deadline exceeded while acquiring lock")
        else:
            lock.__enter__()
            lock_acquired = True

    boundary = _ReadBoundary(conn, snapshot_owner)
    busy_conn = conn
    prev_busy_timeout = None
    try:
        try:
            if conn.in_transaction:
                return error_envelope("storage_unavailable", "Refusing inherited uncommitted transaction")
        except sqlite3.Error as exc:
            return error_envelope("storage_unavailable", f"Database error: {exc}")

        rem = _remaining_activity_budget(deadline)
        if rem <= 0:
            return error_envelope("deadline_exceeded", "Service deadline exceeded before SQLite snapshot")
        try:
            busy_row = conn.execute("PRAGMA busy_timeout").fetchone()
            if busy_row is not None:
                prev_busy_timeout = busy_row[0]
            # Fail-fast on SQLITE_BUSY: Windows overshoots a multi-second
            # busy_timeout, so snapshot/query waits retry until the original
            # inbound deadline instead of waiting a fresh 2 s.
            conn.execute("PRAGMA busy_timeout = 0")
            def _progress():
                if time.monotonic() >= deadline:
                    return 1
                return 0
            conn.set_progress_handler(_progress, 1000)
        except sqlite3.Error:
            pass

        # BA-08: one SQLite snapshot through the shared Index.read_snapshot
        # boundary (or its local equivalent for a bare connection), opened
        # under the Index lock acquired above.
        try:
            conn, snap_err = _call_until_activity_deadline(deadline, boundary.enter)
            if snap_err is not None:
                return snap_err
        except sqlite3.OperationalError as exc:
            if _sqlite_busy_error(exc) or time.monotonic() >= deadline:
                return error_envelope("deadline_exceeded", f"Database busy wait exceeded deadline: {exc}")
            return error_envelope("storage_unavailable", f"Failed to begin read transaction: {exc}")
        except sqlite3.Error as exc:
            return error_envelope("storage_unavailable", f"Database error: {exc}")
        except RuntimeError as exc:
            return error_envelope("storage_unavailable", f"Cannot open read snapshot: {exc}")

        try:
            tbl_err, verify_err = _call_until_activity_deadline(
                deadline, lambda: _verify_tables(conn))
            if verify_err is not None:
                return verify_err
        except sqlite3.OperationalError as exc:
            if _sqlite_busy_error(exc) or time.monotonic() >= deadline:
                return error_envelope("deadline_exceeded", f"Database busy wait exceeded deadline: {exc}")
            raise
        if tbl_err is not None:
            return tbl_err

        # Capture generation at read boundary
        gen_start = _get_db_generation(conn)

        def _finish_snapshot_and_revalidate() -> Optional[dict]:
            """BA-08: end the snapshot, then re-read the generation while the
            Index lock is still held. A commit by another connection during
            construction only becomes visible to ``PRAGMA data_version`` once
            this connection's read transaction has ended, so the check must
            follow the rollback. A changed generation is stale_report; the
            caller does not retry."""
            boundary.finish()
            gen_end = _get_db_generation(conn)
            if _generation_changed(gen_start, gen_end):
                return error_envelope("stale_report", "Database was modified during report construction", retryable=False)
            return None

        # -------------------------------------------------------------------
        # Read raw observations for report_revision and aggregation
        # -------------------------------------------------------------------

        # Q1 Yoinks
        c_yoinks = conn.execute(
            "SELECT video_id, source_type, author, channel, platform, yoinked_at, deleted_at "
            "FROM yoinks ORDER BY video_id ASC"
        )
        all_yoinks = c_yoinks.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        live_yoinks: List[dict] = []
        tombstone_yoinks: List[dict] = []
        for r in all_yoinks:
            vid, stype, author, channel, platform, y_at, d_at = r
            row_dict = {
                "video_id": vid,
                "source_type": stype or "unknown",
                "author": author or "",
                "channel": channel or "",
                "platform": (platform or "").strip() or "unknown",
                "raw_yoinked_at": y_at,
                "raw_deleted_at": d_at,
            }
            if d_at is None:
                live_yoinks.append(row_dict)
            else:
                tombstone_yoinks.append(row_dict)
        live_survivor_ids = {item["video_id"] for item in live_yoinks}
        tombstone_ids = {item["video_id"] for item in tombstone_yoinks}

        # Q2a podcast episodes
        c_episodes = conn.execute(
            "SELECT id, feed_id, guid, yoink_video_id, published_at, status "
            "FROM podcast_episodes ORDER BY id ASC"
        )
        all_episodes = c_episodes.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Q2b / Q5 source items
        c_sitems = conn.execute(
            "SELECT item_id, source_id, entry_id, video_id, published_at_ms, first_seen_ms, last_seen_ms, state "
            "FROM source_items ORDER BY source_id ASC, entry_id ASC"
        )
        all_sitems = c_sitems.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Q5 source subscriptions & cursors
        c_subs = conn.execute(
            "SELECT source_id, kind, source_key, canonical_url, display_name, revision, created_at_ms, updated_at_ms, archived, consent_state "
            "FROM source_subscriptions ORDER BY source_id ASC"
        )
        all_subs = c_subs.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        c_cursors = conn.execute(
            "SELECT source_id, revision, last_poll_attempt_ms, last_poll_success_ms, coverage, observed_count, truncated "
            "FROM source_detection_cursors ORDER BY source_id ASC"
        )
        all_cursors = c_cursors.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Measure UTF-8 journal bytes before materialization
        c_journal_bytes = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(CAST(forward_json AS BLOB)) + LENGTH(CAST(inverse_json AS BLOB))), 0) FROM library_applies"
        )
        total_journal_bytes = c_journal_bytes.fetchone()[0]
        if total_journal_bytes > MAX_JOURNAL_BYTES:
            return error_envelope(
                "resource_too_large",
                f"Combined journal deltas ({total_journal_bytes} bytes) exceed budget limit of {MAX_JOURNAL_BYTES} bytes",
            )

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        c_receipts = conn.execute(
            "SELECT operation_sequence, operation_key, authoritative_record_hash, request_hash, receipt_json "
            "FROM library_operation_receipts ORDER BY operation_sequence ASC"
        )
        all_receipts = c_receipts.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        c_meta = conn.execute(
            "SELECT singleton, projection_revision, active_version_id, last_operation_sequence, recovery_state "
            "FROM library_meta WHERE singleton=1"
        )
        meta_row = c_meta.fetchone()
        if not meta_row:
            projection_revision = 0
            active_version_id = None
            last_op_seq = 0
            recovery_state = "ready"
        else:
            _, projection_revision, active_version_id, last_op_seq, recovery_state = meta_row

        if recovery_state != "ready":
            return error_envelope("recovery_pending", f"Library recovery state is {recovery_state}")

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Current memberships
        c_item_shelves = conn.execute(
            "SELECT video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at "
            "FROM item_shelves ORDER BY video_id ASC, shelf_id ASC"
        )
        all_item_shelves = c_item_shelves.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Shelves definitions
        c_shelves = conn.execute("SELECT shelf_id, created_at FROM shelves ORDER BY shelf_id ASC")
        all_shelves = c_shelves.fetchall()

        c_shelf_versions = conn.execute("SELECT version_id, revision_hash, status, created_at FROM shelf_versions ORDER BY version_id ASC")
        all_shelf_versions = c_shelf_versions.fetchall()

        c_runs = conn.execute("SELECT run_id, version_id, manifest_hash, run_revision, state, created_at FROM library_runs ORDER BY run_id ASC")
        all_runs = c_runs.fetchall()

        c_shelf_nodes = conn.execute("SELECT version_id, shelf_id, name FROM shelf_nodes ORDER BY version_id ASC, shelf_id ASC")
        all_shelf_nodes = c_shelf_nodes.fetchall()

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # Streamed journal replay & validation
        # BA-05: bind request_hash and receipt status; no-change receipts account for apply gaps.
        receipt_by_seq: Dict[int, Tuple[Any, Any, Any, Any]] = {}
        no_change_seqs: Set[int] = set()
        for r in all_receipts:
            seq, op_key_r, auth_r, req_r, rjson = r
            receipt_by_seq[seq] = (op_key_r, auth_r, req_r, rjson)
            if _is_no_change_receipt(rjson):
                no_change_seqs.add(seq)

        expected_seqs = list(range(1, last_op_seq + 1))
        if [r[0] for r in all_receipts] != expected_seqs:
            baseline_proved = False
            baseline_reason = "missing_receipt_sequence_gap"
        else:
            baseline_proved = True
            baseline_reason = None
        expected_apply_seq = 1
        while expected_apply_seq in no_change_seqs:
            expected_apply_seq += 1

        curr_rev = 0
        total_applies_count = 0
        first_apply_dt: Optional[datetime] = None
        earliest_apply_dt: Optional[datetime] = None
        latest_apply_dt: Optional[datetime] = None
        last_apply_dt: Optional[datetime] = None
        invalid_apply_date_count = 0

        journal_binding = []
        interval_applies_compact: List[dict] = []
        applied_ops_count = 0
        shelf_additions: Dict[str, int] = {}
        shelf_removals: Dict[str, int] = {}
        interval_affected_items: Set[str] = set()
        item_change_events = 0
        primary_change_events = 0
        metadata_only_events = 0
        policy_change_events = 0
        activation_events = 0

        projected_state: Dict[str, Dict[str, dict]] = {vid: {} for vid in live_survivor_ids}
        start_state: Dict[str, Dict[str, dict]] = {}
        end_state: Dict[str, Dict[str, dict]] = {}
        captured_start = False
        captured_end = False

        c_applies = conn.execute(
            "SELECT apply_id, operation_key, kind, before_revision, after_revision, operation_sequence, "
            "authoritative_record_hash, forward_json, inverse_json, undo_of, created_at, request_hash "
            "FROM library_applies ORDER BY operation_sequence ASC"
        )

        for idx, app_row in enumerate(c_applies):
            dl_err = _check_deadline()
            if dl_err is not None:
                return dl_err

            total_applies_count += 1
            app_id, op_key, a_kind, before_rev, after_rev, op_seq, auth_hash, f_json, i_json, undo_of, c_at, req_hash = app_row

            f_hash = hashlib.sha256((f_json or "").encode("utf-8")).hexdigest()
            i_hash = hashlib.sha256((i_json or "").encode("utf-8")).hexdigest()
            journal_binding.append({
                "id": app_id,
                "k": a_kind,
                "br": before_rev,
                "ar": after_rev,
                "seq": op_seq,
                "rh": auth_hash,
                "f_hash": f_hash,
                "i_hash": i_hash,
                "undo": undo_of,
                "at": c_at,
            })

            if before_rev != curr_rev or after_rev != curr_rev + 1:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "revision_sequence_gap"
            curr_rev = after_rev

            if op_seq != expected_apply_seq:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "operation_sequence_gap"
            expected_apply_seq = op_seq + 1
            while expected_apply_seq in no_change_seqs:
                expected_apply_seq += 1

            rcpt = receipt_by_seq.get(op_seq)
            if rcpt is None or rcpt[0] != op_key or rcpt[1] != auth_hash or rcpt[2] != req_hash:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "receipt_binding_mismatch"
            elif not _receipt_qualifies_apply(rcpt[3]):
                # BA-05: an apply must be bound to a successful applied receipt;
                # no-change, failed, invented or untyped receipts do not qualify.
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "receipt_binding_mismatch"

            try:
                f_delta = json.loads(f_json)
                i_delta = json.loads(i_json)
            except Exception:
                return error_envelope("invalid_source_data", f"Malformed delta JSON in apply {app_id}")

            if not _validate_delta_structure(f_delta) or not _validate_delta_structure(i_delta):
                return error_envelope("invalid_source_data", f"Malformed delta structure in apply {app_id}")

            dt_apply, _ = parse_native_creation_clock(c_at)

            if dt_apply is None:
                invalid_apply_date_count += 1
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "invalid_apply_timestamp"
            elif dt_apply > as_of_dt:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "future_apply_timestamp"

            if earliest_apply_dt is None and dt_apply is not None:
                earliest_apply_dt = dt_apply
            if dt_apply is not None:
                latest_apply_dt = dt_apply

            if idx == 0:
                first_apply_dt = dt_apply

            if last_apply_dt is not None and dt_apply is not None and dt_apply < last_apply_dt:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "clock_regression"
            if dt_apply is not None:
                last_apply_dt = dt_apply

            # Replay if baseline still candidate
            if baseline_proved and dt_apply is not None:
                if not captured_start and dt_apply >= dt_start:
                    start_state = {vid: dict(shelves) for vid, shelves in projected_state.items()}
                    captured_start = True
                if not captured_end and dt_apply >= dt_end:
                    end_state = {vid: dict(shelves) for vid, shelves in projected_state.items()}
                    captured_end = True

                i_items = i_delta.get("items", {})
                f_items = f_delta.get("items", {})
                # BA-05: every live item touched by the forward delta needs an
                # inverse row set that equals the replayed before state in full
                # (shelf, version, revision, source, lock, primary, confidence,
                # evidence, assigned time), not only shelf ids and primary flags.
                for vid in set(f_items.keys()) | set(i_items.keys()):
                    if vid not in live_survivor_ids:
                        continue
                    if vid not in i_items or vid not in f_items:
                        baseline_proved = False
                        baseline_reason = "mismatched_inverse_projection"
                        break
                    cur_memberships = _membership_state(projected_state[vid].values())
                    inv_memberships = _membership_state(i_items[vid])
                    if cur_memberships != inv_memberships:
                        baseline_proved = False
                        baseline_reason = "mismatched_inverse_projection"
                        break

                if baseline_proved:
                    for vid, rows in f_items.items():
                        if vid in live_survivor_ids:
                            # BA-01: a replayed membership is bound to the retained
                            # apply that produced it, so historical (start/end/
                            # baseline) evidence can name library_applies rows
                            # instead of a fabricated current item_shelves key.
                            shelf_dict: Dict[str, dict] = {}
                            for r in rows:
                                r_entry = dict(r)
                                r_entry["_apply_id"] = app_id
                                r_entry["_operation_sequence"] = op_seq
                                r_entry["_created_at"] = c_at
                                r_entry["_record_hash"] = auth_hash
                                shelf_dict[r["shelf_id"]] = r_entry
                            projected_state[vid] = shelf_dict

            # Interval applies accounting
            if dt_apply is not None and dt_start <= dt_apply < dt_end:
                applied_ops_count += 1
                f_items = f_delta.get("items", {})
                i_items = i_delta.get("items", {})
                all_vids = set(f_items.keys()) | set(i_items.keys())
                ref_shelves = set()
                apply_item_change = 0
                apply_primary_change = 0
                apply_metadata_only = 0
                apply_additions = 0
                apply_removals = 0
                apply_affected: Set[str] = set()
                # BA-01: per-shelf mutation counts and thin per-item changes are
                # retained per apply (identities and shelf ids only, never the
                # decoded forward/inverse maps) so shelf-level journal evidence
                # binds only operations that touched that shelf and journal
                # evidence rows are reconcilable with the membership counts.
                apply_shelf_additions: Dict[str, int] = {}
                apply_shelf_removals: Dict[str, int] = {}
                apply_item_changes: List[dict] = []
                apply_has_deleted_item = False

                for vid in sorted(all_vids):
                    f_rows = f_items.get(vid, [])
                    i_rows = i_items.get(vid, [])
                    f_shelves = {r["shelf_id"] for r in f_rows}
                    i_shelves = {r["shelf_id"] for r in i_rows}
                    ref_shelves |= f_shelves | i_shelves
                    f_prim = next((r["shelf_id"] for r in f_rows if r.get("is_primary") == 1), None)
                    i_prim = next((r["shelf_id"] for r in i_rows if r.get("is_primary") == 1), None)

                    added = f_shelves - i_shelves
                    removed = i_shelves - f_shelves

                    for s in added:
                        shelf_additions[s] = shelf_additions.get(s, 0) + 1
                        apply_additions += 1
                        apply_shelf_additions[s] = apply_shelf_additions.get(s, 0) + 1
                    for s in removed:
                        shelf_removals[s] = shelf_removals.get(s, 0) + 1
                        apply_removals += 1
                        apply_shelf_removals[s] = apply_shelf_removals.get(s, 0) + 1

                    if vid in tombstone_ids:
                        # Deleted evidence exposes identity only (contract).
                        apply_has_deleted_item = True
                        apply_item_changes.append({"video_id": vid, "item_deleted": True})
                    else:
                        apply_item_changes.append({
                            "video_id": vid,
                            "before_shelves": sorted(i_shelves),
                            "after_shelves": sorted(f_shelves),
                            "added_shelves": sorted(added),
                            "removed_shelves": sorted(removed),
                            "before_primary": i_prim,
                            "after_primary": f_prim,
                        })

                    if f_shelves != i_shelves or f_prim != i_prim:
                        interval_affected_items.add(vid)
                        apply_affected.add(vid)
                        item_change_events += 1
                        apply_item_change += 1
                        if f_prim != i_prim and f_shelves == i_shelves:
                            primary_change_events += 1
                            apply_primary_change += 1
                    elif f_rows != i_rows:
                        metadata_only_events += 1
                        apply_metadata_only += 1

                f_pols = f_delta.get("policies", {})
                i_pols = i_delta.get("policies", {})
                apply_policy_change = 0
                for p_k in set(f_pols.keys()) | set(i_pols.keys()):
                    if f_pols.get(p_k) != i_pols.get(p_k):
                        policy_change_events += 1
                        apply_policy_change += 1

                f_act = f_delta.get("active_version_id")
                i_act = i_delta.get("active_version_id")
                apply_activation = False
                if f_act != i_act and (f_act is not None or i_act is not None):
                    activation_events += 1
                    apply_activation = True

                interval_applies_compact.append({
                    "apply_id": app_id,
                    "operation_sequence": op_seq,
                    "kind": a_kind,
                    "before_revision": before_rev,
                    "after_revision": after_rev,
                    "undo_of": undo_of,
                    "authoritative_record_hash": auth_hash,
                    "created_at_dt": dt_apply,
                    "raw_created_at": c_at,
                    "referenced_shelves": ref_shelves,
                    "item_change_count": apply_item_change,
                    "primary_change_count": apply_primary_change,
                    "metadata_only_count": apply_metadata_only,
                    "policy_change_count": apply_policy_change,
                    "activation": apply_activation,
                    "additions": apply_additions,
                    "removals": apply_removals,
                    "affected_vids": apply_affected,
                    "shelf_additions": apply_shelf_additions,
                    "shelf_removals": apply_shelf_removals,
                    "item_changes": apply_item_changes,
                    "has_deleted_item": apply_has_deleted_item,
                })

            del f_delta
            del i_delta

        if last_op_seq and expected_apply_seq <= last_op_seq:
            baseline_proved = False
            if baseline_reason is None:
                baseline_reason = "operation_sequence_gap"

        if total_applies_count == 0:
            baseline_proved = False
            baseline_reason = "no_history"
        elif curr_rev != projection_revision:
            baseline_proved = False
            if baseline_reason is None:
                baseline_reason = "projection_revision_mismatch"
        elif first_apply_dt is None:
            baseline_proved = False
            if baseline_reason is None:
                baseline_reason = "invalid_apply_timestamp"
        elif dt_start < first_apply_dt:
            baseline_proved = False
            if baseline_reason is None:
                baseline_reason = "interval_precedes_first_apply"

        if baseline_proved:
            if not captured_start:
                start_state = {vid: dict(shelves) for vid, shelves in projected_state.items()}
            if not captured_end:
                end_state = {vid: dict(shelves) for vid, shelves in projected_state.items()}

            # BA-05: the replayed projection must equal the current item_shelves
            # rows in full (every typed membership field), not shelf/primary only.
            actual_current_shelves: Dict[str, Dict[str, Tuple[Any, ...]]] = {vid: {} for vid in live_survivor_ids}
            for r in all_item_shelves:
                vid = r[0]
                if vid in live_survivor_ids:
                    row_dict = dict(zip(
                        ("video_id", "shelf_id", "version_id", "source_revision", "source", "locked",
                         "is_primary", "confidence", "evidence_json", "assigned_at"), r))
                    actual_current_shelves[vid][r[1]] = tuple(row_dict.get(f) for f in MEMBERSHIP_STATE_FIELDS)

            for vid in live_survivor_ids:
                p_memberships = _membership_state(projected_state[vid].values())
                a_memberships = actual_current_shelves[vid]
                if p_memberships != a_memberships:
                    baseline_proved = False
                    baseline_reason = "replay_does_not_reach_current_state"
                    break

        # -------------------------------------------------------------------
        # Build Content-Binding report_revision
        # -------------------------------------------------------------------
        yoinks_binding = [
            {"v": r[0], "t": r[1], "a": r[2], "c": r[3], "p": r[4], "ya": r[5], "da": r[6]}
            for r in all_yoinks
        ]
        episodes_binding = [
            {"i": r[0], "f": r[1], "g": r[2], "y": r[3], "p": r[4], "s": r[5]}
            for r in all_episodes
        ]
        sitems_binding = [
            {"i": r[0], "s": r[1], "e": r[2], "v": r[3], "p": r[4], "fs": r[5], "ls": r[6], "st": r[7]}
            for r in all_sitems
        ]
        subs_binding = [
            {"s": r[0], "k": r[1], "u": r[3], "r": r[5], "c": r[6], "a": r[8]}
            for r in all_subs
        ]
        cursors_binding = [
            {"s": r[0], "r": r[1], "lp": r[2], "ls": r[3], "c": r[4], "o": r[5]}
            for r in all_cursors
        ]
        memb_binding = [
            {"v": r[0], "s": r[1], "ver": r[2], "rev": r[3], "src": r[4], "l": r[5], "p": r[6], "c": r[7], "at": r[9]}
            for r in all_item_shelves
        ]
        receipts_binding = [{"seq": r[0], "k": r[1], "h": r[2], "rh": r[3]} for r in all_receipts]
        revisions_binding = {
            "proj": projection_revision,
            "active": active_version_id,
            "last_seq": last_op_seq,
            "versions": [{"v": r[0], "h": r[1], "s": r[2], "at": r[3]} for r in all_shelf_versions],
            "runs": [{"r": r[0], "v": r[1], "h": r[2], "rev": r[3], "s": r[4], "at": r[5]} for r in all_runs],
        }

        raw_report_binding = {
            "contract_version": CONTRACT_VERSION,
            "query_version": CONTRACT_VERSION,
            "db_generation": gen_start,
            "interval": canonical_interval,
            "date_basis": date_basis,
            "yoinks": yoinks_binding,
            "episodes": episodes_binding,
            "source_items": sitems_binding,
            "subscriptions": subs_binding,
            "cursors": cursors_binding,
            "item_shelves": memb_binding,
            "applies": journal_binding,
            "receipts": receipts_binding,
            "revisions": revisions_binding,
        }

        report_revision = hashlib.sha256(serialize_card(raw_report_binding).encode("utf-8")).hexdigest()

        # Verify expected_revision for detail requests
        if detail is not None and expected_revision != report_revision:
            return error_envelope("stale_report", "Report revision mismatch; refresh summary before paging detail", retryable=False)

        dl_err = _check_deadline()
        if dl_err is not None:
            return dl_err

        # -------------------------------------------------------------------
        # Process Items & Publications (Q1 & Q2)
        # -------------------------------------------------------------------
        live_yoinks: List[dict] = []
        tombstone_yoinks: List[dict] = []

        for r in all_yoinks:
            vid, stype, author, channel, platform, y_at, d_at = r
            row_dict = {
                "video_id": vid,
                "source_type": stype or "unknown",
                "author": author or "",
                "channel": channel or "",
                "platform": (platform or "").strip() or "unknown",
                "raw_yoinked_at": y_at,
                "raw_deleted_at": d_at,
            }
            if d_at is None:
                live_yoinks.append(row_dict)
            else:
                tombstone_yoinks.append(row_dict)

        # Build candidate publication relations for live items
        # Tier 1: source_items (state != 'deleted', exact video_id)
        sitems_by_vid: Dict[str, List[dict]] = {}
        for s in all_sitems:
            # s: item_id, source_id, entry_id, video_id, published_at_ms, first_seen_ms, last_seen_ms, state
            if s[3] and s[7] != "deleted":
                sitems_by_vid.setdefault(s[3], []).append({
                    "item_id": s[0],
                    "source_id": s[1],
                    "entry_id": s[2],
                    "published_at_ms": s[4],
                    "first_seen_ms": s[5],
                    "last_seen_ms": s[6],
                    "state": s[7],
                })

        # Tier 2: podcast_episodes (yoink_video_id)
        episodes_by_vid: Dict[str, List[dict]] = {}
        for ep in all_episodes:
            # ep: id, feed_id, guid, yoink_video_id, published_at, status
            if ep[3]:
                episodes_by_vid.setdefault(ep[3], []).append({
                    "id": ep[0],
                    "feed_id": ep[1],
                    "guid": ep[2],
                    "published_at": ep[4],
                    "status": ep[5],
                })

        pub_available_count = 0
        pub_unavailable_by_reason = {
            "conflict": 0,
            "invalid": 0,
            "timezone_unknown": 0,
            "date_only": 0,
            "missing_unindexed": 0,
        }
        capture_available_count = 0
        capture_unavailable_count = 0

        parsed_items: List[dict] = []
        for item in live_yoinks:
            # Capture time parsing
            dt_cap, cap_err = parse_iso_utc(item["raw_yoinked_at"])
            if dt_cap is not None:
                capture_available_count += 1
            else:
                capture_unavailable_count += 1
            item["capture_dt"] = dt_cap
            item["capture_err"] = cap_err

            # Publication instant selection (Tier 1 source_items, fallback to Tier 2 podcast_episodes)
            t1 = sitems_by_vid.get(item["video_id"], [])
            t2 = episodes_by_vid.get(item["video_id"], [])
            pub_dt: Optional[datetime] = None
            pub_reason: Optional[str] = None
            pub_tier: Optional[str] = None
            raw_pub_clock: Any = None
            selected_entry: Optional[dict] = None
            lower_tier_disagreement: Optional[dict] = None
            pub_conflict_candidates: List[dict] = []

            t1_candidates: List[Tuple[datetime, dict]] = []
            t1_reasons: List[str] = []
            for entry in t1:
                dt_p, r_err = parse_epoch_ms(entry["published_at_ms"])
                if dt_p is not None:
                    t1_candidates.append((dt_p, entry))
                else:
                    t1_reasons.append(r_err or "missing_unindexed")

            t2_candidates: List[Tuple[datetime, dict]] = []
            t2_reasons: List[str] = []
            for entry in t2:
                dt_p, r_err = parse_rfc2822_or_iso_utc(entry["published_at"])
                if dt_p is not None:
                    t2_candidates.append((dt_p, entry))
                else:
                    t2_reasons.append(r_err or "missing_unindexed")

            if t1_candidates:
                first_dt, first_entry = t1_candidates[0]
                if all(c[0] == first_dt for c in t1_candidates):
                    pub_dt = first_dt
                    pub_tier = "adapter_normalized"
                    raw_pub_clock = first_entry["published_at_ms"]
                    selected_entry = first_entry

                    # Check for lower tier disagreement
                    if t2_candidates:
                        for t2_dt, t2_entry in t2_candidates:
                            if t2_dt != pub_dt:
                                lower_tier_disagreement = {
                                    "conflict": True,
                                    "disagreement": "lower_tier_instant_mismatch",
                                    "tier": "direct_episode_parse",
                                    "table": "podcast_episodes",
                                    "source_key": t2_entry["id"],
                                    "original_clock_encoding": str(t2_entry["published_at"]),
                                    "normalized_instant": format_canonical_utc(t2_dt),
                                    "observation_hash": hashlib.sha256(
                                        f"ep_{t2_entry['id']}_{t2_entry['published_at']}".encode("utf-8")
                                    ).hexdigest(),
                                }
                                break
                else:
                    pub_reason = "conflict"
                    pub_conflict_candidates = [
                        {
                            "source_table": "source_items",
                            "source_key": entry["item_id"],
                            "original_clock_encoding": str(entry["published_at_ms"]),
                            "normalized_instant": format_canonical_utc(dt_p),
                            "encoding": "adapter_normalized",
                            "observation_hash": canonical_json_hash({
                                "item_id": entry["item_id"],
                                "published_at_ms": entry["published_at_ms"],
                            }),
                        }
                        for dt_p, entry in t1_candidates
                    ]
            elif t1 and any(r == "conflict" for r in t1_reasons):
                pub_reason = "conflict"
            else:
                # Higher tier has no admissible instant; fall back to Tier 2
                if t2_candidates:
                    first_dt, first_entry = t2_candidates[0]
                    if all(c[0] == first_dt for c in t2_candidates):
                        pub_dt = first_dt
                        pub_tier = "direct_episode_parse"
                        raw_pub_clock = first_entry["published_at"]
                        selected_entry = first_entry
                    else:
                        pub_reason = "conflict"
                        pub_conflict_candidates = [
                            {
                                "source_table": "podcast_episodes",
                                "source_key": str(entry["id"]),
                                "original_clock_encoding": str(entry["published_at"]),
                                "normalized_instant": format_canonical_utc(dt_p),
                                "encoding": "direct_episode_parse",
                                "observation_hash": canonical_json_hash({
                                    "id": entry["id"],
                                    "published_at": entry["published_at"],
                                }),
                            }
                            for dt_p, entry in t2_candidates
                        ]
                else:
                    combined_reasons = t1_reasons + t2_reasons
                    for r_code in ("conflict", "invalid", "timezone_unknown", "date_only", "missing_unindexed"):
                        if r_code in combined_reasons:
                            pub_reason = r_code
                            break
                    if pub_reason is None:
                        pub_reason = "missing_unindexed"

            if pub_dt is not None:
                pub_available_count += 1
            else:
                pub_unavailable_by_reason[pub_reason or "missing_unindexed"] += 1

            item["pub_dt"] = pub_dt
            item["pub_reason"] = pub_reason
            item["pub_tier"] = pub_tier
            item["raw_pub_clock"] = raw_pub_clock
            item["selected_pub_entry"] = selected_entry
            item["lower_tier_disagreement"] = lower_tier_disagreement
            item["pub_conflict_candidates"] = pub_conflict_candidates

            parsed_items.append(item)

        # Process excluded tombstones in interval (capture clock, including naive as unlocated).
        tombstones_in_interval = 0
        tombstones_unlocated = 0
        for item in tombstone_yoinks:
            dt_cap, cap_err = parse_iso_utc(item["raw_yoinked_at"])
            item["capture_dt"] = dt_cap
            item["capture_err"] = cap_err
            if dt_cap is not None:
                if dt_start <= dt_cap < dt_end:
                    tombstones_in_interval += 1
            else:
                tombstones_unlocated += 1

        # Partition selected items based on date_basis
        selected_items: List[dict] = []
        for item in parsed_items:
            if date_basis == "capture_time":
                if item["capture_dt"] and dt_start <= item["capture_dt"] < dt_end:
                    selected_items.append(item)
            else:
                if item["pub_dt"] and dt_start <= item["pub_dt"] < dt_end:
                    selected_items.append(item)

        # Warning check: capture_is_not_publication
        warnings: List[str] = []
        if date_basis == "capture_time":
            has_older_pub = any(
                item["pub_dt"] is not None and item["pub_dt"] < dt_start
                for item in selected_items
            )
            if has_older_pub:
                warnings.append("capture_is_not_publication")

        selected_total = len(selected_items)

        # Grouping helper
        type_counts: Dict[str, int] = {t: 0 for t in sorted(CANONICAL_SOURCE_TYPES)}
        type_counts["unknown"] = 0

        creator_counts: Dict[Tuple[str, str, str], int] = {}
        joint_counts: Dict[Tuple[str, str, str, str], int] = {}

        daily_buckets = _build_daily_buckets(dt_start, dt_end)
        daily_counts: Dict[Tuple[str, str], int] = {
            (format_canonical_utc(b[0]), format_canonical_utc(b[1])): 0 for b in daily_buckets
        }

        for item in selected_items:
            # Source type
            stype = item["source_type"]
            if stype not in CANONICAL_SOURCE_TYPES:
                type_counts["unknown"] += 1
            else:
                type_counts[stype] += 1

            # BA-02: frozen (platform, field, trimmed-value); whitespace-only author falls through.
            platform, c_field, c_val = _creator_hint_key(item)
            c_key = (platform, c_field, c_val)
            creator_counts[c_key] = creator_counts.get(c_key, 0) + 1

            # Joint key
            canon_type = stype if stype in CANONICAL_SOURCE_TYPES else "unknown"
            j_key = (canon_type, platform, c_field, c_val)
            joint_counts[j_key] = joint_counts.get(j_key, 0) + 1

            # Daily buckets
            target_dt = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
            assert target_dt is not None
            for b_start, b_end in daily_buckets:
                if b_start <= target_dt < b_end:
                    k = (format_canonical_utc(b_start), format_canonical_utc(b_end))
                    daily_counts[k] += 1
                    break

        # Format items metrics
        scope_items_ref = "scope_items_capture" if date_basis == "capture_time" else "scope_items_publication"

        items_total_metric = _count_metric("items.total", selected_total, "saved_items", scope_items_ref)
        # BA-01: support/sample counts and observation hashes for every metric are
        # bound from the actual evidence rows by ``_bind_returned_metrics`` below.

        by_source_type_rows: List[dict] = []
        for t_name, count in sorted(type_counts.items(), key=lambda x: (-x[1], x[0])):
            m_id = f"items.by_source_type.{t_name}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref, denominator_metric_id="items.total")
            by_source_type_rows.append({
                "source_type": t_name,
                "count": c_metric,
                "share": s_metric,
            })

        by_creator_rows: List[dict] = []
        for c_tuple, count in sorted(creator_counts.items(), key=lambda x: (-x[1], x[0])):
            p_plat, p_field, p_val = c_tuple
            key_hash = hashlib.sha256(json.dumps(list(c_tuple), ensure_ascii=False).encode("utf-8")).hexdigest()
            m_id = f"items.by_creator_hint.{key_hash}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref, denominator_metric_id="items.total")
            display_hint, hint_truncated = _display_hint(p_val)
            by_creator_rows.append({
                "platform": p_plat,
                "field": p_field,
                "hint": display_hint,
                "hint_truncated": hint_truncated,
                "key_hash": key_hash,
                "count": c_metric,
                "share": s_metric,
            })

        by_joint_rows: List[dict] = []
        for j_tuple, count in sorted(joint_counts.items(), key=lambda x: (-x[1], x[0])):
            j_stype, p_plat, p_field, p_val = j_tuple
            j_hash = hashlib.sha256(json.dumps(list(j_tuple), ensure_ascii=False).encode("utf-8")).hexdigest()
            m_id = f"items.by_type_creator_hint.{j_hash}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref, denominator_metric_id="items.total")
            display_hint, hint_truncated = _display_hint(p_val)
            by_joint_rows.append({
                "source_type": j_stype,
                "platform": p_plat,
                "field": p_field,
                "hint": display_hint,
                "hint_truncated": hint_truncated,
                "key_hash": j_hash,
                "count": c_metric,
                "share": s_metric,
            })

        daily_rows: List[dict] = []
        for (b_s, b_e), count in daily_counts.items():
            b_hash = hashlib.sha256(f"{b_s}_{b_e}".encode("utf-8")).hexdigest()[:16]
            m_id = f"items.daily_buckets.{b_hash}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref, denominator_metric_id="items.total")
            daily_rows.append({
                "bucket_start": b_s,
                "bucket_end": b_e,
                "count": c_metric,
                "share": s_metric,
            })

        items_family = {
            "total": items_total_metric,
            "by_source_type": by_source_type_rows,
            "by_creator_hint": by_creator_rows[:20],
            "by_type_creator_hint": by_joint_rows[:20],
            "daily_buckets": daily_rows,
            "live_population": _count_metric("items.live_population", len(live_yoinks), "saved_items", "scope_items_capture"),
            "capture_time_available": _count_metric("items.capture_time_available", capture_available_count, "saved_items", "scope_items_capture"),
            "capture_time_unavailable": _count_metric("items.capture_time_unavailable", capture_unavailable_count, "saved_items", "scope_items_capture"),
            "publication_time_available": _count_metric("items.publication_time_available", pub_available_count, "saved_items", "scope_items_publication"),
            "publication_time_unavailable": _count_metric("items.publication_time_unavailable", sum(pub_unavailable_by_reason.values()), "saved_items", "scope_items_publication"),
            "publication_unavailable_by_reason": {
                reason: _count_metric(
                    f"items.publication_unavailable_by_reason.{reason}",
                    count,
                    "saved_items",
                    "scope_items_publication",
                )
                for reason, count in pub_unavailable_by_reason.items()
            },
            # BA-01: tombstone metrics count deleted items, not the live population.
            "deleted_items_excluded": _count_metric("items.deleted_items_excluded", tombstones_in_interval, "saved_items", "scope_items_tombstones"),
            "deleted_items_unlocated": _count_metric("items.deleted_items_unlocated", tombstones_unlocated, "saved_items", "scope_items_tombstones"),
            "coverage_ref": "cov_capture" if date_basis == "capture_time" else "cov_publication",
        }

        # -------------------------------------------------------------------
        # Q3 / Q4 Applied Journal, Shelf Sizes and Churn Proof
        # -------------------------------------------------------------------
        interval_applies = interval_applies_compact

        total_membership_additions = sum(shelf_additions.values())
        total_membership_removals = sum(shelf_removals.values())
        total_membership_mutations = total_membership_additions + total_membership_removals

        # Current shelf sizes filtered by live survivors
        current_shelf_sizes: Dict[str, int] = {}
        distinct_current_assigned_set: Set[str] = set()
        total_current_memberships = 0
        for r in all_item_shelves:
            vid, s_id = r[0], r[1]
            if vid in live_survivor_ids:
                current_shelf_sizes[s_id] = current_shelf_sizes.get(s_id, 0) + 1
                distinct_current_assigned_set.add(vid)
                total_current_memberships += 1

        distinct_current_assigned = len(distinct_current_assigned_set)
        total_current_memberships = total_current_memberships

        # Churn metrics
        baseline_assigned_vids: Set[str] = set()
        changed_baseline_vids: Set[str] = set()
        initial_filing_vids: List[str] = []
        if baseline_proved:
            baseline_assigned_vids = {vid for vid, shelves in start_state.items() if len(shelves) > 0}
            churn_denom = len(baseline_assigned_vids)
            changed_baseline_vids = baseline_assigned_vids.intersection(interval_affected_items)
            churn_num = len(changed_baseline_vids)
            if churn_denom == 0:
                churn_metric = _ratio_metric("shelf_activity.churn", 0, 0, "scope_shelf_baseline", reason="empty_population", denominator_metric_id="shelf_activity.churn.denominator")
                churn_metric["initial_filing"] = True
            else:
                churn_metric = _ratio_metric("shelf_activity.churn", churn_num, churn_denom, "scope_shelf_baseline", denominator_metric_id="shelf_activity.churn.denominator")
                churn_metric["initial_filing"] = False

            # Initial filing items: live survivors assigned in interval that were not assigned at start
            initial_filing_vids = [
                vid for vid in interval_affected_items
                if vid in live_survivor_ids and vid not in baseline_assigned_vids
            ]
            initial_filing_count = len(initial_filing_vids)
        else:
            churn_metric = {
                "metric_id": "shelf_activity.churn",
                "value": None,
                "unit": "ratio",
                "scope_ref": "scope_shelf_baseline",
                "numerator": None,
                "denominator": None,
                "percent": None,
                "reason": "baseline_unavailable",
                "evidence": {
                    **_evidence_descriptor("shelf_activity.churn", "numerator"),
                    "denominator": {"metric_id": "shelf_activity.churn.denominator", "role": "denominator"},
                },
                "initial_filing": None,
            }
            initial_filing_count = None

        node_names: Dict[Tuple[str, str], str] = {(r[0], r[1]): r[2] for r in all_shelf_nodes}
        shelf_labels: Dict[str, str] = {r[1]: r[2] for r in all_shelf_nodes}
        active_shelf_labels: Dict[str, str] = {r[1]: r[2] for r in all_shelf_nodes if r[0] == active_version_id}
        # BA-01: resolve labels by the membership's version; expose active labels separately.
        membership_version_for_shelf: Dict[str, str] = {}
        for r in all_item_shelves:
            vid, s_id, ver_id = r[0], r[1], r[2]
            if vid in live_survivor_ids and ver_id:
                membership_version_for_shelf.setdefault(s_id, ver_id)

        journal_no_history = total_applies_count == 0 or (
            first_apply_dt is not None and dt_end <= first_apply_dt
        )

        def _journal_count(metric_id: str, value: int, unit: str) -> CountMetric:
            if journal_no_history:
                return _count_metric(metric_id, None, unit, "scope_shelf_activity", recorded_count=0)
            return _count_metric(metric_id, value, unit, "scope_shelf_activity")

        # Build shelves table rows
        known_shelves = sorted({r[0] for r in all_shelves} | set(current_shelf_sizes.keys()) | set(shelf_additions.keys()) | set(shelf_removals.keys()))
        shelves_rows: List[dict] = []
        for s_id in known_shelves:
            c_size = current_shelf_sizes.get(s_id, 0)
            added = shelf_additions.get(s_id, 0)
            removed = shelf_removals.get(s_id, 0)
            net = added - removed
            memb_ver = membership_version_for_shelf.get(s_id)
            if memb_ver and (memb_ver, s_id) in node_names:
                s_name = node_names[(memb_ver, s_id)]
            else:
                s_name = shelf_labels.get(s_id) or s_id
            active_name = active_shelf_labels.get(s_id, s_name)

            if baseline_proved:
                s_start = sum(1 for vid, shelves in start_state.items() if s_id in shelves)
                s_end = sum(1 for vid, shelves in end_state.items() if s_id in shelves)
                start_members = {vid for vid, shelves in start_state.items() if s_id in shelves}
                s_churn_num = len(start_members.intersection(interval_affected_items))
                # BA-01: the per-shelf churn denominator is exactly the shelf's
                # start-size relation, which is a returned metric with its own
                # bound descriptor; the reference names it instead of a second id.
                s_churn = _ratio_metric(f"shelf_activity.shelves.{s_id}.churn", s_churn_num, s_start, "scope_shelf_baseline", denominator_metric_id=f"shelf_activity.shelves.{s_id}.start_size")
            else:
                s_start = None
                s_end = None
                s_churn = {
                    "metric_id": f"shelf_activity.shelves.{s_id}.churn",
                    "value": None,
                    "unit": "ratio",
                    "scope_ref": "scope_shelf_baseline",
                    "numerator": None,
                    "denominator": None,
                    "percent": None,
                    "reason": "baseline_unavailable",
                    "evidence": {
                        **_evidence_descriptor(f"shelf_activity.shelves.{s_id}.churn", "numerator"),
                        "denominator": {"metric_id": f"shelf_activity.shelves.{s_id}.churn.denominator", "role": "denominator"},
                    },
                }

            shown_name, name_truncated = _bound_label(s_name)
            shown_active, _ = _bound_label(active_name)
            shelves_rows.append({
                "shelf_id": s_id,
                "name": shown_name,
                "label": shown_name,
                "label_truncated": name_truncated,
                "active_name": shown_active,
                "active_label": shown_active,
                "current_size": _count_metric(f"shelf_activity.shelves.{s_id}.current_size", c_size, "items", "scope_shelf_current"),
                "start_size": _count_metric(f"shelf_activity.shelves.{s_id}.start_size", s_start, "items", "scope_shelf_baseline") if s_start is not None else None,
                "end_size": _count_metric(f"shelf_activity.shelves.{s_id}.end_size", s_end, "items", "scope_shelf_baseline") if s_end is not None else None,
                "added": _journal_count(f"shelf_activity.shelves.{s_id}.added", added, "mutations"),
                "removed": _journal_count(f"shelf_activity.shelves.{s_id}.removed", removed, "mutations"),
                "net": _journal_count(f"shelf_activity.shelves.{s_id}.net", net, "mutations"),
                "churn": s_churn,
            })

        shelf_family = {
            "applied_operations": _journal_count("shelf_activity.applied_operations", applied_ops_count, "operations"),
            "membership_additions": _journal_count("shelf_activity.membership_additions", total_membership_additions, "mutations"),
            "membership_removals": _journal_count("shelf_activity.membership_removals", total_membership_removals, "mutations"),
            "membership_mutations": _journal_count("shelf_activity.membership_mutations", total_membership_mutations, "mutations"),
            "affected_items": _journal_count("shelf_activity.affected_items", len(interval_affected_items), "saved_items"),
            "item_change_events": _journal_count("shelf_activity.item_change_events", item_change_events, "events"),
            "primary_change_events": _journal_count("shelf_activity.primary_change_events", primary_change_events, "events"),
            "metadata_only_item_events": _journal_count("shelf_activity.metadata_only_item_events", metadata_only_events, "events"),
            "policy_change_events": _journal_count("shelf_activity.policy_change_events", policy_change_events, "events"),
            "activation_events": _journal_count("shelf_activity.activation_events", activation_events, "events"),
            "current_assigned_items": _count_metric("shelf_activity.current_assigned_items", distinct_current_assigned, "saved_items", "scope_shelf_current"),
            "current_memberships": _count_metric("shelf_activity.current_memberships", total_current_memberships, "memberships", "scope_shelf_current"),
            "shelves": shelves_rows[:20],
            "churn": churn_metric,
            "initial_filing_items": _count_metric("shelf_activity.initial_filing_items", initial_filing_count, "saved_items", "scope_shelf_baseline"),
            "coverage_ref": "cov_shelf_activity",
        }

        # -------------------------------------------------------------------
        # Q5 Sources with Activity
        # -------------------------------------------------------------------
        # Precompute links: video_id -> set of source_ids
        vid_to_sources: Dict[str, Set[str]] = {}
        source_to_vids: Dict[str, Set[str]] = {}

        for s in all_sitems:
            # item_id, source_id, entry_id, video_id, ...
            s_src, s_vid = s[1], s[3]
            if s_vid:
                vid_to_sources.setdefault(s_vid, set()).add(s_src)
                source_to_vids.setdefault(s_src, set()).add(s_vid)

        # Legacy podcast links: podcast_episodes.feed_id -> source_subscriptions.legacy_feed_id
        legacy_feed_map: Dict[int, str] = {}
        for sub in all_subs:
            # sub: source_id, kind, source_key, canonical_url, display_name, revision, created_at_ms, updated_at_ms, archived, consent_state
            # Check legacy_feed_id
            pass
        c_legacy = conn.execute("SELECT source_id, legacy_feed_id FROM source_subscriptions WHERE legacy_feed_id IS NOT NULL")
        for s_id, lf_id in c_legacy.fetchall():
            legacy_feed_map[lf_id] = s_id

        for ep in all_episodes:
            f_id, y_vid = ep[1], ep[3]
            if y_vid and f_id in legacy_feed_map:
                s_id = legacy_feed_map[f_id]
                vid_to_sources.setdefault(y_vid, set()).add(s_id)
                source_to_vids.setdefault(s_id, set()).add(y_vid)

        # Observations per source
        source_obs_in_interval: Dict[str, List[dict]] = {}
        source_first_seen_ms: Dict[str, List[int]] = {}
        source_last_seen_ms: Dict[str, List[int]] = {}
        source_invalid_obs: Dict[str, int] = {}
        source_coverage_records: Dict[str, dict] = {}
        sources_unavailable_count = 0
        for s in all_sitems:
            s_id = s[1]
            fs_ms = s[5]
            ls_ms = s[6]
            st = s[7]

            dt_fs, err_fs = parse_epoch_ms(fs_ms)
            dt_ls, err_ls = parse_epoch_ms(ls_ms)
            if fs_ms is not None and fs_ms != 0 and dt_fs is None:
                sources_unavailable_count += 1
                source_invalid_obs[s_id] = source_invalid_obs.get(s_id, 0) + 1
            if ls_ms is not None and ls_ms != 0 and dt_ls is None:
                sources_unavailable_count += 1
                source_invalid_obs[s_id] = source_invalid_obs.get(s_id, 0) + 1

            if dt_fs is not None and fs_ms is not None and fs_ms != 0:
                source_first_seen_ms.setdefault(s_id, []).append(fs_ms)
            if dt_ls is not None and ls_ms is not None and ls_ms != 0:
                source_last_seen_ms.setdefault(s_id, []).append(ls_ms)

            # Check if first_seen_ms is in interval
            if dt_fs and dt_start <= dt_fs < dt_end:
                source_obs_in_interval.setdefault(s_id, []).append(s)

        cursor_map: Dict[str, dict] = {}
        for cur in all_cursors:
            cursor_map[cur[0]] = {
                "revision": cur[1],
                "last_poll_attempt_ms": cur[2],
                "last_poll_success_ms": cur[3],
                "coverage": cur[4],
                "observed_count": cur[5],
                "truncated": cur[6],
            }

        # Captured items in interval (independent of date_basis / publication selector)
        captured_in_interval_items = [
            item for item in live_yoinks
            if item["capture_dt"] and dt_start <= item["capture_dt"] < dt_end
        ]
        captured_in_interval_vids = {item["video_id"] for item in captured_in_interval_items}

        active_source_rows: List[dict] = []
        for sub in all_subs:
            s_id = sub[0]
            kind = sub[1]
            url = sub[3]
            d_name = sub[4] or s_id
            created_ms = sub[6]
            cur_info = cursor_map.get(s_id, {})

            # Qualifying activity:
            # 1. Live captured items in interval linked to this source
            linked_vids = source_to_vids.get(s_id, set())
            captures_in_int = len(linked_vids.intersection(captured_in_interval_vids))

            # 2. Newly observed entries in interval
            obs_in_int = source_obs_in_interval.get(s_id, [])
            new_obs_count = len({o[2] for o in obs_in_int})  # distinct entry_id

            if captures_in_int > 0 or new_obs_count > 0:
                # Breakdowns by state
                state_counts: Dict[str, int] = {}
                for o in obs_in_int:
                    st = o[7]
                    state_counts[st] = state_counts.get(st, 0) + 1

                fs_list = source_first_seen_ms.get(s_id, [])
                ls_list = source_last_seen_ms.get(s_id, [])
                first_obs_dt = parse_epoch_ms(min(fs_list))[0] if fs_list else None
                last_obs_dt = parse_epoch_ms(max(ls_list))[0] if ls_list else None
                obs_no_history = new_obs_count == 0 and (first_obs_dt is None or first_obs_dt >= dt_end)
                src_cov_id = f"cov_source_{s_id}"
                src_invalid = source_invalid_obs.get(s_id, 0)
                src_span_dts: List[datetime] = []
                for ms in fs_list + ls_list:
                    dt_obs, _ = parse_epoch_ms(ms)
                    if dt_obs is not None:
                        src_span_dts.append(dt_obs)
                src_earliest = min(src_span_dts) if src_span_dts else None
                src_latest = max(src_span_dts) if src_span_dts else None
                if src_invalid > 0:
                    src_cov_status = "partial"
                elif first_obs_dt is None or dt_end <= first_obs_dt:
                    src_cov_status = "no_history"
                else:
                    src_cov_status = "retained_records"
                src_cov_rec = {
                    "clock": "observation_time",
                    "requested_interval": canonical_interval,
                    "coverage_status": src_cov_status,
                    "earliest_retained_timestamp": format_canonical_utc(src_earliest) if src_earliest else None,
                    "latest_retained_timestamp": format_canonical_utc(src_latest) if src_latest else None,
                }
                if src_invalid:
                    src_cov_rec["exclusions"] = {"invalid_observation_timestamp": src_invalid}
                source_coverage_records[src_cov_id] = src_cov_rec

                shown_source, source_name_truncated = _bound_label(d_name)
                active_source_rows.append({
                    "source_id": s_id,
                    "identity_kind": "subscription",
                    "kind": kind,
                    "canonical_url": url,
                    "display_name": shown_source,
                    "display_name_truncated": source_name_truncated,
                    "captures_in_interval": _count_metric(f"sources.{s_id}.captures", captures_in_int, "saved_items", "scope_source_captures"),
                    "new_observations": (
                        _count_metric(
                            f"sources.{s_id}.new_observations",
                            None,
                            "entries",
                            "scope_sources",
                            recorded_count=0,
                            coverage_ref=src_cov_id,
                        )
                        if obs_no_history
                        else _count_metric(
                            f"sources.{s_id}.new_observations",
                            new_obs_count,
                            "entries",
                            "scope_sources",
                            coverage_ref=src_cov_id,
                        )
                    ),
                    "new_observations_by_state": {
                        st: _count_metric(
                            f"sources.{s_id}.new_observations_by_state.{st}",
                            c,
                            "entries",
                            "scope_sources",
                            coverage_ref=src_cov_id,
                        )
                        for st, c in state_counts.items()
                    },
                    "observation_window": {
                        "first_observed_at": format_canonical_utc(first_obs_dt) if first_obs_dt else None,
                        "last_item_seen_at": format_canonical_utc(last_obs_dt) if last_obs_dt else None,
                        "enrollment_at": format_canonical_utc(parse_epoch_ms(created_ms)[0]) if parse_epoch_ms(created_ms)[0] else None,
                        "last_poll_attempt": format_canonical_utc(parse_epoch_ms(cur_info.get("last_poll_attempt_ms"))[0]) if parse_epoch_ms(cur_info.get("last_poll_attempt_ms"))[0] else None,
                        "last_poll_success": format_canonical_utc(parse_epoch_ms(cur_info.get("last_poll_success_ms"))[0]) if parse_epoch_ms(cur_info.get("last_poll_success_ms"))[0] else None,
                        "cursor_coverage": f"latest enumeration at as_of: {cur_info.get('coverage', 'unknown')}",
                        "cursor_observed_count": cur_info.get("observed_count", 0),
                        "cursor_truncated": bool(cur_info.get("truncated", 0)),
                        "source_revision": sub[5],
                        "cursor_revision": cur_info.get("revision", 0),
                    },
                })

        # Overlap analysis across captured items in interval
        linked_captured_vids: Set[str] = set()
        multi_linked_captured_vids: Set[str] = set()
        unlinked_captured_items: List[dict] = []

        for item in captured_in_interval_items:
            vid = item["video_id"]
            srcs = vid_to_sources.get(vid, set())
            if srcs:
                linked_captured_vids.add(vid)
                if len(srcs) > 1:
                    multi_linked_captured_vids.add(vid)
            else:
                unlinked_captured_items.append(item)

        unlinked_hint_groups: Dict[Tuple[str, str, str], List[dict]] = {}
        for item in unlinked_captured_items:
            unlinked_hint_groups.setdefault(_creator_hint_key(item), []).append(item)

        unlinked_hint_rows: List[dict] = []
        for (p, f, v), group_items in sorted(unlinked_hint_groups.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            h_hash = hashlib.sha256(f"{p}_{f}_{v}".encode("utf-8")).hexdigest()[:16]
            display_hint, hint_truncated = _display_hint(v)
            cap_dts = [it["capture_dt"] for it in group_items if it.get("capture_dt")]
            min_cap = min(cap_dts) if cap_dts else None
            max_cap = max(cap_dts) if cap_dts else None
            unlinked_hint_rows.append({
                "source_id": None,
                "identity_kind": "creator_hint",
                "platform": p,
                "field": f,
                "hint": display_hint,
                "hint_truncated": hint_truncated,
                "display_name": display_hint,
                "captures_in_interval": _count_metric(f"sources.hint.{h_hash}.captures", len(group_items), "saved_items", "scope_source_captures"),
                "retained_capture_span": {
                    "earliest_captured_at": format_canonical_utc(min_cap) if min_cap else None,
                    "latest_captured_at": format_canonical_utc(max_cap) if max_cap else None,
                },
                "capture_span": {
                    "earliest_captured_at": format_canonical_utc(min_cap) if min_cap else None,
                    "latest_captured_at": format_canonical_utc(max_cap) if max_cap else None,
                },
            })

        all_source_details = active_source_rows + unlinked_hint_rows

        # Support level derived from selected_items (A1/A2 selected population)
        selected_vids = {it["video_id"] for it in selected_items}
        selected_sources = {s for vid in selected_vids for s in vid_to_sources.get(vid, set())}
        unlinked_selected = [it for it in selected_items if not vid_to_sources.get(it["video_id"])]

        if len(selected_items) == 0:
            support_level = "none"
        elif len(unlinked_selected) == 0 and len(selected_sources) == 1:
            support_level = "single_source"
        else:
            support_level = "unresolved"

        sources_family = {
            "active_sources_count": _count_metric("sources.active_sources_count", len(active_source_rows), "sources", "scope_sources"),
            "unlinked_hint_groups_count": _count_metric("sources.unlinked_hint_groups_count", len(unlinked_hint_groups), "creator_hints", "scope_sources"),
            "linked_capture_union_count": _count_metric("sources.linked_capture_union_count", len(linked_captured_vids), "saved_items", "scope_source_captures"),
            "multiply_linked_capture_count": _count_metric("sources.multiply_linked_capture_count", len(multi_linked_captured_vids), "saved_items", "scope_source_captures"),
            "details": all_source_details[:20],
            "coverage_ref": "cov_sources",
        }

        # -------------------------------------------------------------------
        # Q8 Revisions
        # -------------------------------------------------------------------
        tax_versions_created = 0
        revision_dts: List[datetime] = []
        invalid_revision_count = 0
        for sv in all_shelf_versions:
            dt_sv, _ = parse_native_creation_clock(sv[3])
            if dt_sv is not None:
                revision_dts.append(dt_sv)
                if dt_start <= dt_sv < dt_end:
                    tax_versions_created += 1
            else:
                invalid_revision_count += 1

        runs_created = 0
        for r in all_runs:
            dt_r, _ = parse_native_creation_clock(r[5])
            if dt_r is not None:
                revision_dts.append(dt_r)
                if dt_start <= dt_r < dt_end:
                    runs_created += 1
            else:
                invalid_revision_count += 1

        revisions_family = {
            "taxonomy_versions_created": _count_metric("revisions.taxonomy_versions_created", tax_versions_created, "revisions", "scope_revisions"),
            "runs_created": _count_metric("revisions.runs_created", runs_created, "runs", "scope_revisions"),
            "coverage_ref": "cov_revisions",
        }

        # -------------------------------------------------------------------
        # Combined Events (at most 20 rows in summary)
        # -------------------------------------------------------------------
        combined_events: List[dict] = []

        # 1. Item captures or publications
        for item in selected_items:
            dt_ev = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
            assert dt_ev is not None
            combined_events.append({
                "event_id": f"item_{item['video_id']}",
                "kind": "capture" if date_basis == "capture_time" else "publication",
                "time": format_canonical_utc(dt_ev),
                "time_dt": dt_ev,
                "operation_sequence": -1,
                "stable_id": item["video_id"],
                "details": {
                    "video_id": item["video_id"],
                    "source_type": item["source_type"],
                    "platform": item["platform"],
                    "hint": item["author"] or item["channel"] or "unknown",
                },
            })

        # 2. Applied journal operations
        for app in interval_applies:
            dt_ev = app["created_at_dt"]
            assert dt_ev is not None
            combined_events.append({
                "event_id": f"apply_{app['apply_id']}",
                "kind": app["kind"],
                "time": format_canonical_utc(dt_ev),
                "time_dt": dt_ev,
                "operation_sequence": app["operation_sequence"],
                "stable_id": app["apply_id"],
                "details": {
                    "apply_id": app["apply_id"],
                    "operation_sequence": app["operation_sequence"],
                    "authoritative_record_hash": app["authoritative_record_hash"],
                    "before_revision": app["before_revision"],
                    "after_revision": app["after_revision"],
                    "undo_of": app["undo_of"],
                },
            })

        # 3. Taxonomy version creations
        for sv in all_shelf_versions:
            dt_sv, _ = parse_native_creation_clock(sv[3])
            if dt_sv and dt_start <= dt_sv < dt_end:
                combined_events.append({
                    "event_id": f"tax_{sv[0]}",
                    "kind": "taxonomy_version",
                    "time": format_canonical_utc(dt_sv),
                    "time_dt": dt_sv,
                    "operation_sequence": -1,
                    "stable_id": sv[0],
                    "details": {
                        "version_id": sv[0],
                        "revision_hash": sv[1],
                        "status": sv[2],
                    },
                })

        # 4. Run creations
        for r in all_runs:
            dt_r, _ = parse_native_creation_clock(r[5])
            if dt_r and dt_start <= dt_r < dt_end:
                combined_events.append({
                    "event_id": f"run_{r[0]}",
                    "kind": "run",
                    "time": format_canonical_utc(dt_r),
                    "time_dt": dt_r,
                    "operation_sequence": -1,
                    "stable_id": r[0],
                    "details": {
                        "run_id": r[0],
                        "version_id": r[1],
                        "manifest_hash": r[2],
                        "run_revision": r[3],
                        "state": r[4],
                    },
                })

        # Sort combined events: normalized_time DESC, kind ASC, stable_id ASC (ties in applied time use descending operation_sequence)
        def _event_sort_key(ev: dict):
            # For reverse sort:
            return (ev["time_dt"], ev["operation_sequence"], ev["kind"], ev["stable_id"])

        combined_events.sort(key=_event_sort_key, reverse=True)

        # Strip internal time_dt and operation_sequence from output
        cleaned_events = []
        for ev in combined_events:
            c_ev = dict(ev)
            c_ev.pop("time_dt", None)
            c_ev.pop("operation_sequence", None)
            c_ev.pop("stable_id", None)
            cleaned_events.append(c_ev)

        total_events_count = len(cleaned_events)
        events_summary_rows = cleaned_events[:20]

        events_family = {
            # BA-01: combined events are their own population on their own clocks
            # (item clock, applied journal time, revision creation time).
            "total": _count_metric("events.total", total_events_count, "events", "scope_events"),
            "rows": events_summary_rows,
            "returned_rows": len(events_summary_rows),
            "omitted_rows": max(0, total_events_count - len(events_summary_rows)),
            "next": None if total_events_count <= 20 else {
                "interval": canonical_interval,
                "date_basis": date_basis,
                "detail": "events",
                "expected_revision": report_revision,
                "offset": 20,
                "limit": 20,
            },
        }

        # -------------------------------------------------------------------
        # Provenance and Scopes
        # -------------------------------------------------------------------
        scopes = {
            "scope_items_capture": {
                "population": "current_live_saved_items",
                "clock": "capture_time",
                "interval": canonical_interval,
                "query_id": "Q1",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_capture",
            },
            "scope_items_publication": {
                "population": "current_live_saved_items",
                "clock": "publication_time",
                "interval": canonical_interval,
                "query_id": "Q2",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_publication",
            },
            "scope_shelf_activity": {
                "population": "recorded_journal_operations",
                "clock": "applied_journal_time",
                "interval": canonical_interval,
                "query_id": "Q3",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_shelf_activity",
            },
            "scope_shelf_baseline": {
                "population": "current_live_survivors",
                "clock": "applied_journal_time",
                "interval": canonical_interval,
                "query_id": "Q3",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_shelf_activity",
            },
            "scope_shelf_current": {
                "population": "current_assigned_items",
                "clock": "as_of",
                "interval": None,
                "query_id": "Q4",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_shelf_current",
            },
            "scope_sources": {
                "population": "source_observations",
                "clock": "observation_time",
                "interval": canonical_interval,
                "query_id": "Q5",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_sources",
            },
            "scope_source_captures": {
                "population": "current_live_saved_items",
                "clock": "capture_time",
                "interval": canonical_interval,
                "query_id": "Q5",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_capture",
            },
            "scope_revisions": {
                "population": "recorded_revisions",
                "clock": "creation_time",
                "interval": canonical_interval,
                "query_id": "Q8",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_revisions",
            },
            # BA-01: tombstone metrics are scoped to deleted items, not the live population.
            "scope_items_tombstones": {
                "population": "deleted_saved_items",
                "clock": "capture_time",
                "interval": canonical_interval,
                "query_id": "Q1",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_capture",
            },
            # BA-01: combined events are a union population across clocks; the
            # journal clock is named so event totals are not read as item counts.
            "scope_events": {
                "population": "combined_events",
                "clock": "event_time",
                "clocks": {
                    ("capture" if date_basis == "capture_time" else "publication"): date_basis,
                    "apply": "applied_journal_time",
                    "taxonomy_version": "creation_time",
                    "run": "creation_time",
                },
                "interval": canonical_interval,
                "query_id": "Q1" if date_basis == "capture_time" else "Q2",
                "query_ids": ["Q1" if date_basis == "capture_time" else "Q2", "Q3", "Q8"],
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_shelf_activity",
            },
        }

        # Active taxonomy hash
        active_tax_hash = None
        for sv in all_shelf_versions:
            if sv[0] == active_version_id:
                active_tax_hash = sv[1]
                break

        input_schema_version = None
        try:
            sv_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            if sv_row is not None:
                input_schema_version = sv_row[0]
        except Exception:
            input_schema_version = None

        provenance = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "input_schema_version": input_schema_version,
            "database_schema_version": input_schema_version,
            "taxonomy_run_digest": canonical_json_hash(revisions_binding),
            "source_observation_digest": canonical_json_hash({
                "source_items": sitems_binding,
                "cursors": cursors_binding,
            }),
            "queries_used": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q8"],
            "projection_revision": projection_revision,
            "last_operation_sequence": last_op_seq,
            "active_taxonomy_version_id": active_version_id,
            "active_taxonomy_hash": active_tax_hash,
            "scopes": scopes,
            # BA-01: metric-to-support relation registry; each metric's compact
            # evidence descriptor names one of these by ``relation``.
            "relations": _build_relation_registry(date_basis, scope_items_ref),
            "evidence_request": {
                "interval": canonical_interval,
                "date_basis": date_basis,
                "detail": "evidence",
                "expected_revision": report_revision,
                "offset": 0,
                "limit": 20,
            },
        }

        # Coverage map
        # Find earliest and latest timestamps across stored records
        all_cap_dts = [item["capture_dt"] for item in live_yoinks if item["capture_dt"]]
        earliest_cap = min(all_cap_dts) if all_cap_dts else None
        latest_cap = max(all_cap_dts) if all_cap_dts else None

        all_pub_dts = [item["pub_dt"] for item in live_yoinks if item["pub_dt"]]
        earliest_pub = min(all_pub_dts) if all_pub_dts else None
        latest_pub = max(all_pub_dts) if all_pub_dts else None

        if not earliest_cap or dt_end <= earliest_cap:
            cap_cov_status = "no_history"
        elif capture_unavailable_count > 0:
            cap_cov_status = "partial"
        elif capture_available_count > 0:
            cap_cov_status = "retained_records"
        else:
            cap_cov_status = "no_history"

        pub_unavailable_count = sum(pub_unavailable_by_reason.values())
        if not earliest_pub or dt_end <= earliest_pub:
            pub_cov_status = "no_history"
        elif pub_unavailable_count > 0:
            pub_cov_status = "partial"
        elif pub_available_count > 0:
            pub_cov_status = "retained_records"
        else:
            pub_cov_status = "no_history"

        item_clock_no_history = (
            (date_basis == "capture_time" and cap_cov_status == "no_history")
            or (date_basis == "publication_time" and pub_cov_status == "no_history")
        )
        if item_clock_no_history:
            _mark_no_history(items_total_metric)
            for daily in daily_rows:
                _mark_no_history(daily.get("count"))
            for row in by_source_type_rows:
                _mark_no_history(row.get("count"))
            for row in by_creator_rows:
                _mark_no_history(row.get("count"))
            for row in by_joint_rows:
                _mark_no_history(row.get("count"))

        obs_span_dts: List[datetime] = []
        for ms_list in list(source_first_seen_ms.values()) + list(source_last_seen_ms.values()):
            for ms in ms_list:
                dt_obs, _ = parse_epoch_ms(ms)
                if dt_obs is not None:
                    obs_span_dts.append(dt_obs)
        earliest_obs = min(obs_span_dts) if obs_span_dts else None
        latest_obs = max(obs_span_dts) if obs_span_dts else None
        if sources_unavailable_count > 0:
            sources_cov_status = "partial"
        elif not earliest_obs or dt_end <= earliest_obs:
            sources_cov_status = "no_history"
        elif all_sitems:
            sources_cov_status = "retained_records"
        else:
            sources_cov_status = "no_history"

        earliest_rev = min(revision_dts) if revision_dts else None
        latest_rev = max(revision_dts) if revision_dts else None
        if invalid_revision_count > 0:
            rev_cov_status = "partial"
        elif not earliest_rev or dt_end <= earliest_rev:
            rev_cov_status = "no_history"
        else:
            rev_cov_status = "retained_records"

        if cap_cov_status == "no_history":
            _mark_no_history(sources_family.get("linked_capture_union_count"))
            _mark_no_history(sources_family.get("multiply_linked_capture_count"))
        if rev_cov_status == "no_history":
            _mark_no_history(revisions_family.get("taxonomy_versions_created"))
            _mark_no_history(revisions_family.get("runs_created"))
        if item_clock_no_history and journal_no_history and rev_cov_status == "no_history":
            _mark_no_history(events_family.get("total"))

        coverage_map = {
            "cov_capture": {
                "clock": "capture_time",
                "requested_interval": canonical_interval,
                "coverage_status": cap_cov_status,
                "earliest_retained_timestamp": format_canonical_utc(earliest_cap) if earliest_cap else None,
                "latest_retained_timestamp": format_canonical_utc(latest_cap) if latest_cap else None,
                "exclusions": {"capture_time_unavailable": capture_unavailable_count},
            },
            "cov_publication": {
                "clock": "publication_time",
                "requested_interval": canonical_interval,
                "coverage_status": pub_cov_status,
                "earliest_retained_timestamp": format_canonical_utc(earliest_pub) if earliest_pub else None,
                "latest_retained_timestamp": format_canonical_utc(latest_pub) if latest_pub else None,
                "exclusions": pub_unavailable_by_reason,
            },
            "cov_shelf_activity": {
                "clock": "applied_journal_time",
                "requested_interval": canonical_interval,
                "coverage_status": "journal_complete" if baseline_proved else ("no_history" if total_applies_count == 0 or (first_apply_dt is not None and dt_end <= first_apply_dt) else "partial"),
                "earliest_retained_timestamp": format_canonical_utc(earliest_apply_dt) if earliest_apply_dt else None,
                "latest_retained_timestamp": format_canonical_utc(latest_apply_dt) if latest_apply_dt else None,
                "reasons": [baseline_reason] if baseline_reason else [],
                "exclusions": {"invalid_apply_timestamp": invalid_apply_date_count} if invalid_apply_date_count > 0 else {},
            },
            "cov_shelf_current": {
                "clock": "as_of",
                "requested_interval": None,
                "coverage_status": "retained_records",
                "earliest_retained_timestamp": None,
                "latest_retained_timestamp": as_of_str,
            },
            "cov_sources": {
                "clock": "observation_time",
                "requested_interval": canonical_interval,
                "coverage_status": sources_cov_status,
                "earliest_retained_timestamp": format_canonical_utc(earliest_obs) if earliest_obs else None,
                "latest_retained_timestamp": format_canonical_utc(latest_obs) if latest_obs else None,
                "exclusions": {"invalid_observation_timestamp": sources_unavailable_count} if sources_unavailable_count else {},
            },
            "cov_revisions": {
                "clock": "creation_time",
                "requested_interval": canonical_interval,
                "coverage_status": rev_cov_status,
                "earliest_retained_timestamp": format_canonical_utc(earliest_rev) if earliest_rev else None,
                "latest_retained_timestamp": format_canonical_utc(latest_rev) if latest_rev else None,
            },
        }
        if invalid_revision_count:
            coverage_map["cov_revisions"]["exclusions"] = {
                "invalid_revision_timestamp": invalid_revision_count
            }
        coverage_map.update(source_coverage_records)

        # Pagination metadata for summary
        other_types_count = sum(_metric_value_or_zero(r["count"]) for r in by_source_type_rows[20:])
        other_creator_count = sum(_metric_value_or_zero(r["count"]) for r in by_creator_rows[20:])
        other_joint_count = sum(_metric_value_or_zero(r["count"]) for r in by_joint_rows[20:])

        pagination_map = {
            "creator_hints": {
                "total_rows": len(by_creator_rows),
                "returned_rows": min(20, len(by_creator_rows)),
                "omitted_rows": max(0, len(by_creator_rows) - 20),
                "other_count": other_creator_count,
                "next": None if len(by_creator_rows) <= 20 else {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": "creator_hints",
                    "expected_revision": report_revision,
                    "offset": 20,
                    "limit": 20,
                },
            },
            "type_creator_hints": {
                "total_rows": len(by_joint_rows),
                "returned_rows": min(20, len(by_joint_rows)),
                "omitted_rows": max(0, len(by_joint_rows) - 20),
                "other_count": other_joint_count,
                "next": None if len(by_joint_rows) <= 20 else {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": "type_creator_hints",
                    "expected_revision": report_revision,
                    "offset": 20,
                    "limit": 20,
                },
            },
            "shelves": {
                "total_rows": len(shelves_rows),
                "returned_rows": min(20, len(shelves_rows)),
                "omitted_rows": max(0, len(shelves_rows) - 20),
                "next": None if len(shelves_rows) <= 20 else {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": "shelves",
                    "expected_revision": report_revision,
                    "offset": 20,
                    "limit": 20,
                },
            },
            "sources": {
                "total_rows": len(all_source_details),
                "returned_rows": min(20, len(all_source_details)),
                "omitted_rows": max(0, len(all_source_details) - 20),
                "next": None if len(all_source_details) <= 20 else {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": "sources",
                    "expected_revision": report_revision,
                    "offset": 20,
                    "limit": 20,
                },
            },
            "events": {
                "total_rows": total_events_count,
                "returned_rows": min(20, total_events_count),
                "omitted_rows": max(0, total_events_count - 20),
                "next": None if total_events_count <= 20 else {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": "events",
                    "expected_revision": report_revision,
                    "offset": 20,
                    "limit": 20,
                },
            },
        }

        # -------------------------------------------------------------------
        # BA-01: metric-to-support relation registry. Every returned metric id
        # is an evidence selector; the same lookup binds the compact descriptor
        # counts/hashes and serves the paged evidence endpoint, so a descriptor
        # always reconciles with its page.
        # -------------------------------------------------------------------
        valid_metric_ids: Set[str] = {
            "items.total",
            "items.live_population",
            "items.capture_time_available",
            "items.capture_time_unavailable",
            "items.publication_time_available",
            "items.publication_time_unavailable",
            "items.deleted_items_excluded",
            "items.deleted_items_unlocated",
            "shelf_activity.churn.denominator",
        }
        for r in by_source_type_rows + by_creator_rows + by_joint_rows + daily_rows:
            valid_metric_ids.add(r["count"]["metric_id"])
            valid_metric_ids.add(r["share"]["metric_id"])
        for sh_r in shelves_rows:
            for k in ("current_size", "start_size", "end_size", "churn", "added", "removed", "net"):
                if sh_r.get(k) and isinstance(sh_r[k], dict) and "metric_id" in sh_r[k]:
                    valid_metric_ids.add(sh_r[k]["metric_id"])
        for s_r in all_source_details:
            for k in ("captures_in_interval", "new_observations"):
                if isinstance(s_r.get(k), dict) and "metric_id" in s_r[k]:
                    valid_metric_ids.add(s_r[k]["metric_id"])
            state_map = s_r.get("new_observations_by_state")
            if isinstance(state_map, dict):
                for st_m in state_map.values():
                    if isinstance(st_m, dict) and "metric_id" in st_m:
                        valid_metric_ids.add(st_m["metric_id"])

        def _register_metric_tree(obj: Any) -> None:
            if isinstance(obj, dict):
                mid = obj.get("metric_id")
                if isinstance(mid, str):
                    valid_metric_ids.add(mid)
                for child in obj.values():
                    _register_metric_tree(child)
            elif isinstance(obj, list):
                for child in obj:
                    _register_metric_tree(child)

        _register_metric_tree(items_family)
        _register_metric_tree(shelf_family)
        _register_metric_tree(sources_family)
        _register_metric_tree(revisions_family)
        _register_metric_tree(events_family)

        daily_buckets_map = {
            hashlib.sha256(f"{format_canonical_utc(b[0])}_{format_canonical_utc(b[1])}".encode("utf-8")).hexdigest()[:16]: (b[0], b[1])
            for b in daily_buckets
        }

        # Group index: one pass over the selected items so per-bucket, per-type
        # and per-hint lookups are O(group) rather than O(items) per metric.
        group_index = _build_item_group_index(selected_items, daily_buckets, date_basis)

        def _rows_for(m_id: str, row_limit: Optional[int] = None) -> Optional[_EvidenceRows]:
            return _lookup_evidence(
                m_id,
                valid_metric_ids=valid_metric_ids,
                selected_items=selected_items,
                captured_in_interval_items=captured_in_interval_items,
                unlinked_hint_groups=unlinked_hint_groups,
                live_yoinks=live_yoinks,
                tombstone_yoinks=tombstone_yoinks,
                interval_applies=interval_applies,
                all_item_shelves=all_item_shelves,
                daily_buckets_map=daily_buckets_map,
                vid_to_sources=vid_to_sources,
                source_to_vids=source_to_vids,
                source_obs_in_interval=source_obs_in_interval,
                active_source_rows=active_source_rows,
                all_shelf_versions=all_shelf_versions,
                all_runs=all_runs,
                date_basis=date_basis,
                dt_start=dt_start,
                dt_end=dt_end,
                as_of_dt=as_of_dt,
                as_of_str=as_of_str,
                start_state=start_state,
                end_state=end_state,
                baseline_assigned_vids=baseline_assigned_vids,
                changed_baseline_vids=changed_baseline_vids,
                initial_filing_vids=initial_filing_vids,
                cleaned_events=cleaned_events,
                group_index=group_index,
                row_limit=row_limit,
            )

        def _bind_returned_metrics(*subtrees: Any) -> Optional[dict]:
            """Bind compact descriptors (exact counts only) for every metric
            about to be returned. Counts walk the support relation without
            constructing observation rows. Denominator references that are
            themselves returned metrics stay as ``{metric_id,role}`` selectors;
            the churn denominator has no metric of its own and is bound in place."""
            bound = 0
            for metric in _iter_metric_dicts(list(subtrees)):
                ev = metric["evidence"]
                if "row_count" not in ev:
                    _bind_support(ev, _rows_for(metric["metric_id"], row_limit=0))
                den = ev.get("denominator")
                if isinstance(den, dict) and "row_count" not in den:
                    den_id = den.get("metric_id")
                    if den_id == "shelf_activity.churn.denominator":
                        den["relation"] = _relation_id_for(den_id)
                        _bind_support(den, _rows_for(den_id, row_limit=0))
                bound += 1
                if bound % 25 == 0:
                    dl = _check_deadline()
                    if dl is not None:
                        return dl
            return None

        # -------------------------------------------------------------------
        # Build Detail Response if requested
        # -------------------------------------------------------------------
        if detail is not None:
            detail_rows: List[dict] = []
            detail_total = 0

            if detail == "creator_hints":
                detail_total = len(by_creator_rows)
                detail_rows = by_creator_rows[offset : offset + limit]
            elif detail == "type_creator_hints":
                detail_total = len(by_joint_rows)
                detail_rows = by_joint_rows[offset : offset + limit]
            elif detail == "shelves":
                detail_total = len(shelves_rows)
                detail_rows = shelves_rows[offset : offset + limit]
            elif detail == "sources":
                detail_total = len(all_source_details)
                detail_rows = all_source_details[offset : offset + limit]
            elif detail == "events":
                detail_total = len(cleaned_events)
                detail_rows = cleaned_events[offset : offset + limit]
            elif detail == "evidence":
                # Metric evidence lookup
                assert metric_id is not None
                # Bounded: rows beyond the requested page are counted, not built.
                ev_rows = _rows_for(metric_id, row_limit=offset + limit)
                if ev_rows is None:
                    return error_envelope("not_found", f"Metric ID not found: {metric_id}")
                detail_total = ev_rows.total_rows
                detail_rows = list(ev_rows[offset : offset + limit])

            if detail != "evidence":
                dl_err = _bind_returned_metrics(detail_rows)
                if dl_err is not None:
                    return dl_err

            next_page = None
            if offset + len(detail_rows) < detail_total:
                next_page = {
                    "interval": canonical_interval,
                    "date_basis": date_basis,
                    "detail": detail,
                    "expected_revision": report_revision,
                    "offset": offset + len(detail_rows),
                    "limit": limit,
                }
                if detail == "evidence":
                    next_page["metric_id"] = metric_id

            detail_response = {
                "ok": True,
                "schema_version": SCHEMA_VERSION,
                "contract_version": CONTRACT_VERSION,
                "as_of": as_of_str,
                "interval": canonical_interval,
                "date_basis": date_basis,
                "report_revision": report_revision,
                "provenance": provenance,
                "coverage": coverage_map,
                "detail": detail,
                "rows": detail_rows,
                "total_rows": detail_total,
                "returned_rows": len(detail_rows),
                "omitted_rows": max(0, detail_total - (offset + len(detail_rows))),
                "next": next_page,
                "warnings": warnings,
                "analysis_scope": "descriptive",
                "trend_eligible": False,
                "independent_creator_count": None,
                "independent_creators_minimum_met": False,
                "support_level": support_level,
                "pagination": {
                    detail: {
                        "total_rows": detail_total,
                        "returned_rows": len(detail_rows),
                        "omitted_rows": max(0, detail_total - (offset + len(detail_rows))),
                        "next": next_page,
                    }
                },
            }
            if detail == "evidence":
                detail_response["metric_id"] = metric_id

            def _refresh_detail_page() -> None:
                page_next = None
                if offset + len(detail_rows) < detail_total:
                    page_next = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": detail,
                        "expected_revision": report_revision,
                        "offset": offset + len(detail_rows),
                        "limit": limit,
                    }
                    if detail == "evidence":
                        page_next["metric_id"] = metric_id
                omitted = max(0, detail_total - (offset + len(detail_rows)))
                detail_response["rows"] = detail_rows
                detail_response["returned_rows"] = len(detail_rows)
                detail_response["omitted_rows"] = omitted
                detail_response["next"] = page_next
                detail_response["pagination"][detail] = {
                    "total_rows": detail_total,
                    "returned_rows": len(detail_rows),
                    "omitted_rows": omitted,
                    "next": page_next,
                }

            # Whole-row shedding: drop complete detail rows until the packet
            # fits. A single identity that still cannot fit mandatory output
            # is resource_too_large; metric IDs remain the only 512-byte limit.
            while _calculate_transport_bytes(detail_response) > MAX_RESPONSE_BYTES:
                if len(detail_rows) <= 1:
                    return error_envelope("resource_too_large", "Requested document exceeds bounded response limits")
                detail_rows.pop()
                _refresh_detail_page()

            # Finish the snapshot, then verify generation before returning
            stale_err = _finish_snapshot_and_revalidate()
            if stale_err is not None:
                return stale_err

            # Check service deadline
            if time.monotonic() - start_time > SERVICE_DEADLINE_SEC:
                return error_envelope("deadline_exceeded", "Service deadline exceeded", retryable=True)

            return detail_response

        # -------------------------------------------------------------------
        # Build Summary Response
        # -------------------------------------------------------------------
        # BA-01: bind compact descriptors for the returned families only (top-20
        # rows); detail pages bind their own rows when requested.
        dl_err = _bind_returned_metrics(items_family, shelf_family, sources_family, revisions_family, events_family)
        if dl_err is not None:
            return dl_err

        summary_response = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "as_of": as_of_str,
            "interval": canonical_interval,
            "date_basis": date_basis,
            "report_revision": report_revision,
            "provenance": provenance,
            "coverage": coverage_map,
            "items": items_family,
            "shelf_activity": shelf_family,
            "sources": sources_family,
            "revisions": revisions_family,
            "events": events_family,
            "warnings": warnings,
            "analysis_scope": "descriptive",
            "trend_eligible": False,
            "independent_creator_count": None,
            "independent_creators_minimum_met": False,
            "support_level": support_level,
            "pagination": pagination_map,
        }

        # Wire budget enforcement & row reduction
        resp_bytes = _calculate_transport_bytes(summary_response)

        while resp_bytes > MAX_RESPONSE_BYTES:
            # Fixed drop order: event rows, joint creator rows, creator rows, source rows, shelf rows
            if events_family["rows"]:
                events_family["rows"].pop()
                ret_len = len(events_family["rows"])
                events_family["returned_rows"] = ret_len
                events_family["omitted_rows"] = total_events_count - ret_len
                if ret_len < total_events_count:
                    events_family["next"] = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": "events",
                        "expected_revision": report_revision,
                        "offset": ret_len,
                        "limit": 20,
                    }
                else:
                    events_family["next"] = None
                pagination_map["events"]["returned_rows"] = ret_len
                pagination_map["events"]["omitted_rows"] = pagination_map["events"]["total_rows"] - ret_len
                pagination_map["events"]["next"] = events_family["next"]
            elif items_family["by_type_creator_hint"]:
                items_family["by_type_creator_hint"].pop()
                ret_len = len(items_family["by_type_creator_hint"])
                pagination_map["type_creator_hints"]["returned_rows"] = ret_len
                pagination_map["type_creator_hints"]["omitted_rows"] = pagination_map["type_creator_hints"]["total_rows"] - ret_len
                pagination_map["type_creator_hints"]["other_count"] = sum(_metric_value_or_zero(r["count"]) for r in by_joint_rows[ret_len:])
                if ret_len < pagination_map["type_creator_hints"]["total_rows"]:
                    pagination_map["type_creator_hints"]["next"] = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": "type_creator_hints",
                        "expected_revision": report_revision,
                        "offset": ret_len,
                        "limit": 20,
                    }
                else:
                    pagination_map["type_creator_hints"]["next"] = None
            elif items_family["by_creator_hint"]:
                items_family["by_creator_hint"].pop()
                ret_len = len(items_family["by_creator_hint"])
                pagination_map["creator_hints"]["returned_rows"] = ret_len
                pagination_map["creator_hints"]["omitted_rows"] = pagination_map["creator_hints"]["total_rows"] - ret_len
                pagination_map["creator_hints"]["other_count"] = sum(_metric_value_or_zero(r["count"]) for r in by_creator_rows[ret_len:])
                if ret_len < pagination_map["creator_hints"]["total_rows"]:
                    pagination_map["creator_hints"]["next"] = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": "creator_hints",
                        "expected_revision": report_revision,
                        "offset": ret_len,
                        "limit": 20,
                    }
                else:
                    pagination_map["creator_hints"]["next"] = None
            elif sources_family["details"]:
                sources_family["details"].pop()
                ret_len = len(sources_family["details"])
                pagination_map["sources"]["returned_rows"] = ret_len
                pagination_map["sources"]["omitted_rows"] = pagination_map["sources"]["total_rows"] - ret_len
                if ret_len < pagination_map["sources"]["total_rows"]:
                    pagination_map["sources"]["next"] = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": "sources",
                        "expected_revision": report_revision,
                        "offset": ret_len,
                        "limit": 20,
                    }
                else:
                    pagination_map["sources"]["next"] = None
            elif shelf_family["shelves"]:
                shelf_family["shelves"].pop()
                ret_len = len(shelf_family["shelves"])
                pagination_map["shelves"]["returned_rows"] = ret_len
                pagination_map["shelves"]["omitted_rows"] = pagination_map["shelves"]["total_rows"] - ret_len
                if ret_len < pagination_map["shelves"]["total_rows"]:
                    pagination_map["shelves"]["next"] = {
                        "interval": canonical_interval,
                        "date_basis": date_basis,
                        "detail": "shelves",
                        "expected_revision": report_revision,
                        "offset": ret_len,
                        "limit": 20,
                    }
                else:
                    pagination_map["shelves"]["next"] = None
            else:
                return error_envelope("resource_too_large", "Mandatory response fields exceed 65536-byte wire limit")

            resp_bytes = _calculate_transport_bytes(summary_response)

        # Finish the snapshot, then verify generation before returning
        stale_err = _finish_snapshot_and_revalidate()
        if stale_err is not None:
            return stale_err

        # Check service deadline
        if time.monotonic() - start_time > SERVICE_DEADLINE_SEC:
            return error_envelope("deadline_exceeded", "Service deadline exceeded", retryable=True)

        return summary_response

    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower() or "locked" in str(exc).lower() or "busy" in str(exc).lower() or time.monotonic() >= deadline:
            return error_envelope("deadline_exceeded", f"Database query exceeded deadline: {exc}")
        return error_envelope("storage_unavailable", f"Database operational error: {exc}")
    except sqlite3.Error as exc:
        return error_envelope("storage_unavailable", f"Database error: {exc}")
    finally:
        if prev_busy_timeout is not None:
            try:
                busy_conn.execute(f"PRAGMA busy_timeout = {int(prev_busy_timeout)}")
            except Exception:
                pass
        try:
            conn.set_progress_handler(None, 0)
        except Exception:
            pass
        # Error paths leave the snapshot open until here; it ends before the
        # Index lock is released, so the boundary is retained through the return.
        try:
            boundary.finish()
        except Exception:
            pass
        if lock is not None and lock_acquired:
            try:
                if hasattr(lock, "release"):
                    lock.release()
                else:
                    lock.__exit__(*sys.exc_info())
            except Exception:
                pass
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Evidence Lookup
# ---------------------------------------------------------------------------

def _build_item_group_index(selected_items: List[dict], daily_buckets: List[Tuple[datetime, datetime]], date_basis: str) -> dict:
    """One pass over the selected items: members per source type, creator hint,
    joint key and daily bucket, in selected-item order (BA-01 registry support;
    keeps per-metric descriptor binding bounded)."""
    by_type: Dict[str, List[dict]] = {}
    by_creator: Dict[str, List[dict]] = {}
    by_joint: Dict[str, List[dict]] = {}
    by_bucket: Dict[str, List[dict]] = {}
    bucket_keys = [
        (b_start, b_end, hashlib.sha256(f"{format_canonical_utc(b_start)}_{format_canonical_utc(b_end)}".encode("utf-8")).hexdigest()[:16])
        for b_start, b_end in daily_buckets
    ]
    for item in selected_items:
        stype = item["source_type"] if item["source_type"] in CANONICAL_SOURCE_TYPES else "unknown"
        by_type.setdefault(stype, []).append(item)
        platform, c_field, c_val = _creator_hint_key(item)
        k_hash = hashlib.sha256(json.dumps([platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
        by_creator.setdefault(k_hash, []).append(item)
        j_hash = hashlib.sha256(json.dumps([stype, platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
        by_joint.setdefault(j_hash, []).append(item)
        target_dt = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
        if target_dt is not None:
            for b_start, b_end, b_hash in bucket_keys:
                if b_start <= target_dt < b_end:
                    by_bucket.setdefault(b_hash, []).append(item)
                    break
    return {"by_type": by_type, "by_creator": by_creator, "by_joint": by_joint, "by_bucket": by_bucket}


def _selected_observation_row(item: dict, date_basis: str) -> dict:
    """Memoised per item and clock; callers get a shallow copy they may re-detail."""
    cache = item.get("_obs_rows")
    if cache is None:
        cache = {}
        item["_obs_rows"] = cache
    row = cache.get(date_basis)
    if row is None:
        row = _build_selected_observation_row(item, date_basis)
        cache[date_basis] = row
    return dict(row)


def _build_selected_observation_row(item: dict, date_basis: str) -> dict:
    """Evidence row for a selected item, attributing publication instants to their source relation. BA-03.

    The observation hash covers every selected observation field, including the
    channel: a channel-only correction changes the selected observation (BA-01)."""
    if date_basis == "publication_time" and item.get("pub_dt") is not None:
        dt_ev = item["pub_dt"]
        pub_tier = item.get("pub_tier")
        if pub_tier == "adapter_normalized" and item.get("selected_pub_entry"):
            entry = item["selected_pub_entry"]
            raw_clock = entry["published_at_ms"]
            obs_dict = {
                "item_id": entry["item_id"],
                "published_at_ms": raw_clock,
                "author": item.get("author"),
                "channel": item.get("channel"),
            }
            row_details = {
                "video_id": item["video_id"],
                "item_id": entry["item_id"],
                "source_id": entry["source_id"],
                "entry_id": entry["entry_id"],
                "author": item.get("author"),
                "channel": item.get("channel"),
                "source_items": True,
                "adapter_normalized": True,
                "follow_up": f"get_library_item('{item['video_id']}')",
            }
            if item.get("lower_tier_disagreement"):
                row_details["lower_tier_disagreement"] = item["lower_tier_disagreement"]
                row_details["disagreement"] = item["lower_tier_disagreement"]
                row_details["conflict"] = True
            return {
                "row_id": entry["item_id"],
                "source_table": "source_items",
                "source_key": entry["item_id"],
                "event_time": format_canonical_utc(dt_ev),
                "original_clock_encoding": str(raw_clock),
                "observation_hash": canonical_json_hash(obs_dict),
                "details": row_details,
            }
        if pub_tier == "direct_episode_parse" and item.get("selected_pub_entry"):
            ep = item["selected_pub_entry"]
            raw_clock = ep["published_at"]
            obs_dict = {"id": ep["id"], "published_at": raw_clock, "author": item.get("author"), "channel": item.get("channel")}
            return {
                "row_id": str(ep["id"]),
                "source_table": "podcast_episodes",
                "source_key": str(ep["id"]),
                "event_time": format_canonical_utc(dt_ev),
                "original_clock_encoding": str(raw_clock),
                "observation_hash": canonical_json_hash(obs_dict),
                "details": {
                    "video_id": item["video_id"],
                    "episode_id": ep["id"],
                    "author": item.get("author"),
                    "channel": item.get("channel"),
                    "direct_episode_parse": True,
                    "follow_up": f"get_library_item('{item['video_id']}')",
                },
            }
        raw_clock = item.get("raw_pub_clock") or item["raw_yoinked_at"]
        return {
            "row_id": item["video_id"],
            "source_table": "yoinks",
            "source_key": item["video_id"],
            "event_time": format_canonical_utc(dt_ev),
            "original_clock_encoding": str(raw_clock),
            "observation_hash": canonical_json_hash({
                "v": item["video_id"],
                "a": item.get("author"),
                "ch": item.get("channel"),
                "c": raw_clock,
            }),
            "details": {
                "video_id": item["video_id"],
                "author": item.get("author"),
                "channel": item.get("channel"),
                "follow_up": f"get_library_item('{item['video_id']}')",
            },
        }
    dt_ev = item.get("capture_dt")
    raw_clock = item.get("raw_yoinked_at")
    obs_dict = {
        "v": item["video_id"],
        "t": item.get("source_type"),
        "p": item.get("platform"),
        "a": item.get("author"),
        "ch": item.get("channel"),
        "c": raw_clock,
    }
    return {
        "row_id": item["video_id"],
        "source_table": "yoinks",
        "source_key": item["video_id"],
        "event_time": format_canonical_utc(dt_ev) if dt_ev else None,
        "original_clock_encoding": str(raw_clock),
        "observation_hash": canonical_json_hash(obs_dict),
        "details": {
            "video_id": item["video_id"],
            "source_type": item.get("source_type"),
            "platform": item.get("platform"),
            "author": item.get("author"),
            "channel": item.get("channel"),
            "hint": item.get("author") or item.get("channel") or "unknown",
            "follow_up": f"get_library_item('{item['video_id']}')",
        },
    }


def _lookup_evidence(
    metric_id: str,
    *,
    valid_metric_ids: Set[str],
    selected_items: List[dict],
    live_yoinks: List[dict],
    tombstone_yoinks: List[dict],
    interval_applies: List[dict],
    all_item_shelves: List[tuple],
    daily_buckets_map: Dict[str, Tuple[datetime, datetime]],
    vid_to_sources: Dict[str, Set[str]],
    source_to_vids: Dict[str, Set[str]],
    source_obs_in_interval: Dict[str, List[dict]],
    active_source_rows: List[dict],
    all_shelf_versions: List[tuple],
    all_runs: List[tuple],
    date_basis: str,
    dt_start: datetime,
    dt_end: datetime,
    as_of_dt: datetime,
    as_of_str: str,
    captured_in_interval_items: Optional[List[dict]] = None,
    unlinked_hint_groups: Optional[dict] = None,
    start_state: Optional[dict] = None,
    end_state: Optional[dict] = None,
    baseline_assigned_vids: Optional[Set[str]] = None,
    changed_baseline_vids: Optional[Set[str]] = None,
    initial_filing_vids: Optional[List[str]] = None,
    cleaned_events: Optional[List[dict]] = None,
    group_index: Optional[dict] = None,
    row_limit: Optional[int] = None,
) -> Optional["_EvidenceRows"]:
    """Return supporting evidence rows for a given metric ID.

    This is the single metric-to-support relation lookup (BA-01): the compact
    descriptors on returned metrics are bound from these rows, and the paged
    evidence endpoint serves the same rows. Every supporting observation is
    counted (``total_rows``); at most ``row_limit`` rows are constructed."""
    if metric_id not in valid_metric_ids:
        return None

    if captured_in_interval_items is None:
        captured_in_interval_items = selected_items
    if unlinked_hint_groups is None:
        unlinked_hint_groups = {}
    if start_state is None:
        start_state = {}
    if end_state is None:
        end_state = {}
    if baseline_assigned_vids is None:
        baseline_assigned_vids = set()
    if changed_baseline_vids is None:
        changed_baseline_vids = set()
    if initial_filing_vids is None:
        initial_filing_vids = []
    if cleaned_events is None:
        cleaned_events = []

    rows = _EvidenceRows(row_limit)

    # 1. items.total
    if metric_id == "items.total":
        for item in selected_items:
            rows.add(lambda:_selected_observation_row(item, date_basis))
        return rows

    # 2. Availability and exclusion metrics
    if metric_id == "items.live_population":
        for item in live_yoinks:
            dt_ev = item["capture_dt"]
            raw_clock = item["raw_yoinked_at"]
            rows.add(lambda:{
                "row_id": item["video_id"],
                "source_table": "yoinks",
                "source_key": item["video_id"],
                "event_time": format_canonical_utc(dt_ev) if dt_ev else None,
                "original_clock_encoding": str(raw_clock),
                "observation_hash": canonical_json_hash({"v": item["video_id"], "live": True}),
                "details": {"video_id": item["video_id"], "source_type": item["source_type"], "follow_up": f"get_library_item('{item['video_id']}')"},
            })
        return rows

    if metric_id == "items.capture_time_available":
        for item in live_yoinks:
            if item["capture_dt"] is not None:
                dt_ev = item["capture_dt"]
                raw_clock = item["raw_yoinked_at"]
                rows.add(lambda:{
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": format_canonical_utc(dt_ev),
                    "original_clock_encoding": str(raw_clock),
                    "observation_hash": canonical_json_hash({"v": item["video_id"], "cap": True}),
                    "details": {"video_id": item["video_id"], "follow_up": f"get_library_item('{item['video_id']}')"},
                })
        return rows

    if metric_id == "items.capture_time_unavailable":
        for item in live_yoinks:
            if item["capture_dt"] is None:
                rows.add(lambda:{
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": None,
                    "original_clock_encoding": str(item["raw_yoinked_at"]),
                    "observation_hash": canonical_json_hash({"v": item["video_id"], "err": item["capture_err"]}),
                    "details": {"video_id": item["video_id"], "reason": item["capture_err"]},
                })
        return rows

    if metric_id == "items.publication_time_available":
        # BA-03: availability reuses the admitted candidate relation (source key,
        # encoding, normalized instant, provenance, observation hash) that the
        # selected total/group/bucket evidence uses.
        def _availability_row(item: dict) -> dict:
            row = _selected_observation_row(item, "publication_time")
            row["details"] = {**row.get("details", {}), "tier": item.get("pub_tier")}
            return row

        for item in live_yoinks:
            if item.get("pub_dt") is not None:
                rows.add(lambda: _availability_row(item))
        return rows

    if metric_id == "items.publication_time_unavailable" or metric_id.startswith("items.publication_unavailable_by_reason."):
        reason_filter = None
        if metric_id.startswith("items.publication_unavailable_by_reason."):
            reason_filter = metric_id.rsplit(".", 1)[-1]
        for item in live_yoinks:
            if item.get("pub_dt") is not None:
                continue
            reason = item.get("pub_reason") or "missing_unindexed"
            if reason_filter is not None and reason != reason_filter:
                continue
            candidates = item.get("pub_conflict_candidates") or []
            details = {
                "video_id": item["video_id"],
                "reason": reason,
                "candidates": candidates,
            }
            source_table = "yoinks"
            source_key = item["video_id"]
            if candidates:
                source_table = candidates[0].get("source_table", source_table)
                source_key = candidates[0].get("source_key", source_key)
                details["conflicting_source_keys"] = [c.get("source_key") for c in candidates]
            rows.add(lambda:{
                "row_id": item["video_id"],
                "source_table": source_table,
                "source_key": source_key,
                "event_time": None,
                "original_clock_encoding": str(item.get("raw_pub_clock")),
                "observation_hash": canonical_json_hash({
                    "v": item["video_id"],
                    "reason": reason,
                    "candidates": candidates,
                    "author": item.get("author"),
                }),
                "details": details,
            })
        return rows

    if metric_id == "items.deleted_items_excluded":
        for item in tombstone_yoinks:
            dt_cap = item.get("capture_dt")
            if dt_cap is None:
                dt_cap, _ = parse_iso_utc(item["raw_yoinked_at"])
            if dt_cap is None or not (dt_start <= dt_cap < dt_end):
                continue
            rows.add(lambda:{
                "row_id": item["video_id"],
                "source_table": "yoinks",
                "source_key": item["video_id"],
                "event_time": format_canonical_utc(dt_cap),
                "original_clock_encoding": str(item["raw_yoinked_at"]),
                "observation_hash": canonical_json_hash({
                    "v": item["video_id"],
                    "deleted": True,
                    "author": item.get("author"),
                    "c": item["raw_yoinked_at"],
                }),
                "details": {"video_id": item["video_id"], "deleted_at": item["raw_deleted_at"]},
            })
        return rows

    if metric_id == "items.deleted_items_unlocated":
        for item in tombstone_yoinks:
            dt_cap = item.get("capture_dt")
            if dt_cap is None:
                dt_cap, _ = parse_iso_utc(item["raw_yoinked_at"])
            if dt_cap is not None:
                continue
            rows.add(lambda:{
                "row_id": item["video_id"],
                "source_table": "yoinks",
                "source_key": item["video_id"],
                "event_time": None,
                "original_clock_encoding": str(item.get("raw_yoinked_at")),
                "observation_hash": canonical_json_hash({
                    "v": item["video_id"],
                    "unlocated": True,
                    "author": item.get("author"),
                }),
                "details": {"video_id": item["video_id"]},
            })
        return rows

    # 3. Source types
    if metric_id.startswith("items.by_source_type."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            stype = parts[2]
            if group_index is not None:
                members = group_index["by_type"].get(stype, [])
            else:
                members = [
                    item for item in selected_items
                    if ((item["source_type"] == stype) if stype in CANONICAL_SOURCE_TYPES else (item["source_type"] not in CANONICAL_SOURCE_TYPES))
                ]
            for item in members:
                rows.add(lambda:_selected_observation_row(item, date_basis))
            return rows

    # 4. Creator hints
    if metric_id.startswith("items.by_creator_hint."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            k_hash = parts[2]
            if group_index is not None:
                members = group_index["by_creator"].get(k_hash, [])
            else:
                members = []
                for item in selected_items:
                    platform, c_field, c_val = _creator_hint_key(item)
                    item_khash = hashlib.sha256(json.dumps([platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
                    if item_khash == k_hash:
                        members.append(item)
            def _creator_row(item: dict) -> dict:
                platform, c_field, c_val = _creator_hint_key(item)
                row = _selected_observation_row(item, date_basis)
                row["details"] = {
                    **row.get("details", {}),
                    "author": item["author"],
                    "channel": item["channel"],
                    "original_author": item["author"],
                    "original_channel": item["channel"],
                    "hint": _display_hint(c_val)[0],
                    "original_hint": item.get("author") or item.get("channel") or "",
                    "platform": platform,
                }
                return row

            for item in members:
                rows.add(lambda: _creator_row(item))
            return rows

    # 5. Joint type + creator hints
    if metric_id.startswith("items.by_type_creator_hint."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            j_hash = parts[2]
            if group_index is not None:
                members = group_index["by_joint"].get(j_hash, [])
            else:
                members = []
                for item in selected_items:
                    platform, c_field, c_val = _creator_hint_key(item)
                    stype = item["source_type"] if item["source_type"] in CANONICAL_SOURCE_TYPES else "unknown"
                    item_jhash = hashlib.sha256(json.dumps([stype, platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
                    if item_jhash == j_hash:
                        members.append(item)
            def _joint_row(item: dict) -> dict:
                platform, c_field, c_val = _creator_hint_key(item)
                stype = item["source_type"] if item["source_type"] in CANONICAL_SOURCE_TYPES else "unknown"
                row = _selected_observation_row(item, date_basis)
                row["details"] = {
                    **row.get("details", {}),
                    "source_type": stype,
                    "author": item["author"],
                    "channel": item["channel"],
                    "original_author": item["author"],
                    "original_channel": item["channel"],
                    "platform": platform,
                    "hint": _display_hint(c_val)[0],
                    "original_hint": item.get("author") or item.get("channel") or "",
                }
                return row

            for item in members:
                rows.add(lambda: _joint_row(item))
            return rows

    # 6. Daily buckets
    if metric_id.startswith("items.daily_buckets."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            b_hash = parts[2]
            if b_hash in daily_buckets_map:
                b_start, b_end = daily_buckets_map[b_hash]
                if group_index is not None:
                    members = group_index["by_bucket"].get(b_hash, [])
                else:
                    members = []
                    for item in selected_items:
                        target_dt = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
                        assert target_dt is not None
                        if b_start <= target_dt < b_end:
                            members.append(item)
                for item in members:
                    rows.add(lambda:_selected_observation_row(item, date_basis))
                return rows

    # 7. Shelf activity
    live_vid_set = {it["video_id"] for it in live_yoinks}

    def _apply_row(app: dict, s_id: Optional[str] = None) -> dict:
        """Applied-journal evidence: operation identity, revisions, undo binding,
        and thin per-item before/after shelf identities (never the decoded
        forward/inverse maps). Deleted items are marked and exposed by identity only."""
        dt_ev = app["created_at_dt"]
        assert dt_ev is not None
        details: Dict[str, Any] = {
            "apply_id": app["apply_id"],
            "operation_sequence": app["operation_sequence"],
            "kind": app["kind"],
            "before_revision": app["before_revision"],
            "after_revision": app["after_revision"],
            "undo_of": app["undo_of"],
        }
        item_changes = app.get("item_changes") or []
        if s_id is not None:
            details["shelf_id"] = s_id
            item_changes = [
                ch for ch in item_changes
                if ch.get("item_deleted") or s_id in ch.get("before_shelves", []) or s_id in ch.get("after_shelves", [])
            ]
        # Bounded: one evidence row never carries more than one page of item
        # changes; omission is explicit pagination metadata (BA-10).
        details["item_changes"] = item_changes[:EVIDENCE_PAGE_LIMIT]
        details["item_changes_omitted"] = max(0, len(item_changes) - EVIDENCE_PAGE_LIMIT)
        if app.get("has_deleted_item"):
            details["item_deleted"] = True
        return {
            "row_id": app["apply_id"],
            "source_table": "library_applies",
            "source_key": app["operation_sequence"],
            "event_time": format_canonical_utc(dt_ev),
            "original_clock_encoding": str(app["raw_created_at"]),
            "observation_hash": app["authoritative_record_hash"],
            "details": details,
        }

    def _replayed_member_row(vid: str, s_id: str, info: Any, role: str, dt_role: datetime) -> dict:
        """A replayed (historical) membership names the retained apply that
        produced it; a current item_shelves key is never fabricated for it."""
        app_id = info.get("_apply_id") if isinstance(info, dict) else None
        det: Dict[str, Any] = {"video_id": vid, "shelf_id": s_id, "role": role}
        if app_id:
            det["apply_id"] = app_id
            det["operation_sequence"] = info.get("_operation_sequence")
        record_hash = info.get("_record_hash") if isinstance(info, dict) else None
        return {
            "row_id": vid,
            "source_table": "library_applies" if app_id else "item_shelves",
            "source_key": app_id if app_id else f"{vid}_{s_id}",
            "event_time": format_canonical_utc(dt_role),
            "original_clock_encoding": str(info.get("_created_at")) if (isinstance(info, dict) and info.get("_created_at")) else None,
            "observation_hash": canonical_json_hash({"v": vid, "s": s_id, "role": role, "apply": app_id, "rh": record_hash}),
            "details": det,
        }

    if metric_id == "shelf_activity.current_assigned_items":
        # One pass to group memberships by item (bounded work, BA-11).
        shelves_by_vid: Dict[str, List[tuple]] = {}
        for r in all_item_shelves:
            if r[0] in live_vid_set:
                shelves_by_vid.setdefault(r[0], []).append(r)

        def _assigned_row(vid: str) -> dict:
            sh_rows = shelves_by_vid.get(vid, [])
            assigned_at = sh_rows[0][9] if sh_rows else None
            dt_a = parse_iso_utc(assigned_at)[0] if assigned_at else as_of_dt
            return {
                "row_id": vid,
                "source_table": "item_shelves",
                "source_key": vid,
                "event_time": format_canonical_utc(dt_a) if dt_a else as_of_str,
                "original_clock_encoding": str(assigned_at),
                "observation_hash": hashlib.sha256(f"assigned_{vid}_{assigned_at}".encode("utf-8")).hexdigest(),
                "details": {
                    "video_id": vid,
                    "shelves": [r[1] for r in sh_rows],
                    "follow_up": f"get_library_item('{vid}')",
                },
            }

        for vid in sorted(shelves_by_vid.keys()):
            rows.add(lambda: _assigned_row(vid))
        return rows

    if metric_id == "shelf_activity.current_memberships":
        for r in all_item_shelves:
            if r[0] in live_vid_set:
                vid, s_id = r[0], r[1]
                assigned_at = r[9]
                dt_a = parse_iso_utc(assigned_at)[0] if assigned_at else as_of_dt
                rows.add(lambda:{
                    "row_id": f"{vid}_{s_id}",
                    "source_table": "item_shelves",
                    "source_key": f"{vid}_{s_id}",
                    "event_time": format_canonical_utc(dt_a) if dt_a else as_of_str,
                    "original_clock_encoding": str(assigned_at),
                    "observation_hash": hashlib.sha256(f"membership_{vid}_{s_id}_{assigned_at}".encode("utf-8")).hexdigest(),
                    "details": {
                        "video_id": vid,
                        "shelf_id": s_id,
                        "is_primary": r[6],
                    },
                })
        return rows

    if metric_id.startswith("shelf_activity.shelves."):
        parts = metric_id.split(".")
        if len(parts) >= 4:
            s_id = parts[2]
            metric_kind = parts[3]
            if metric_kind == "current_size":
                for r in all_item_shelves:
                    if r[1] == s_id and r[0] in live_vid_set:
                        vid = r[0]
                        assigned_at = r[9]
                        dt_a = parse_iso_utc(assigned_at)[0] if assigned_at else as_of_dt
                        rows.add(lambda:{
                            "row_id": vid,
                            "source_table": "item_shelves",
                            "source_key": f"{vid}_{s_id}",
                            "event_time": format_canonical_utc(dt_a) if dt_a else as_of_str,
                            "original_clock_encoding": str(assigned_at),
                            "observation_hash": hashlib.sha256(f"shelf_{s_id}_{vid}_{assigned_at}".encode("utf-8")).hexdigest(),
                            "details": {
                                "video_id": vid,
                                "shelf_id": s_id,
                            },
                        })
                return rows
            elif metric_kind in ("start_size", "end_size"):
                state = start_state if metric_kind == "start_size" else end_state
                dt_role = dt_start if metric_kind == "start_size" else dt_end
                for vid, shelves in sorted(state.items()):
                    if s_id in shelves:
                        rows.add(lambda:_replayed_member_row(vid, s_id, shelves[s_id], metric_kind, dt_role))
                return rows
            elif metric_kind in ("churn", "added", "removed", "net"):
                if metric_kind == "churn":
                    if metric_id.endswith(".denominator"):
                        for vid, shelves in sorted(start_state.items()):
                            if s_id in shelves:
                                rows.add(lambda:_replayed_member_row(vid, s_id, shelves[s_id], "denominator", dt_start))
                        return rows
                    # BA-01: the per-shelf churn numerator is the shelf's start
                    # members whose membership changed in the interval; an
                    # operation that only touched metadata is not support.
                    for vid, shelves in sorted(start_state.items()):
                        if s_id in shelves and vid in changed_baseline_vids:
                            rows.add(lambda:_replayed_member_row(vid, s_id, shelves[s_id], "churn", dt_start))
                    return rows
                # BA-01: shelf-level journal counts bind only operations that
                # added to / removed from this shelf, never operation-wide
                # additions or a merely referenced shelf.
                for app in interval_applies:
                    sh_adds = app.get("shelf_additions") or {}
                    sh_rems = app.get("shelf_removals") or {}
                    if metric_kind == "added" and not sh_adds.get(s_id):
                        continue
                    if metric_kind == "removed" and not sh_rems.get(s_id):
                        continue
                    if metric_kind == "net" and not (sh_adds.get(s_id) or sh_rems.get(s_id)):
                        continue
                    rows.add(lambda:_apply_row(app, s_id=s_id))
                return rows

    if metric_id == "shelf_activity.churn.denominator" or metric_id.endswith(".denominator") and metric_id.startswith("shelf_activity.churn"):
        for vid in sorted(baseline_assigned_vids):
            shelves = start_state.get(vid) or {}
            first_shelf = sorted(shelves.keys())[0] if shelves else None
            info = shelves.get(first_shelf) if first_shelf else None
            app_id = info.get("_apply_id") if isinstance(info, dict) else None
            det: Dict[str, Any] = {"video_id": vid, "role": "denominator", "shelves": sorted(shelves.keys())}
            if app_id:
                det["apply_id"] = app_id
                det["operation_sequence"] = info.get("_operation_sequence")
            rows.add(lambda:{
                "row_id": vid,
                "source_table": "library_applies" if app_id else "item_shelves",
                "source_key": app_id if app_id else vid,
                "event_time": format_canonical_utc(dt_start),
                "original_clock_encoding": str(info.get("_created_at")) if (isinstance(info, dict) and info.get("_created_at")) else None,
                "observation_hash": canonical_json_hash({"v": vid, "role": "denominator", "shelves": sorted(shelves.keys()), "apply": app_id}),
                "details": det,
            })
        return rows

    if metric_id == "shelf_activity.churn":
        for vid in sorted(changed_baseline_vids):
            shelves = start_state.get(vid) or {}
            first_shelf = sorted(shelves.keys())[0] if shelves else None
            info = shelves.get(first_shelf) if first_shelf else None
            app_id = info.get("_apply_id") if isinstance(info, dict) else None
            det: Dict[str, Any] = {"video_id": vid, "role": "churn", "start_shelves": sorted(shelves.keys())}
            if app_id:
                det["apply_id"] = app_id
                det["operation_sequence"] = info.get("_operation_sequence")
            rows.add(lambda:{
                "row_id": vid,
                "source_table": "library_applies" if app_id else "item_shelves",
                "source_key": app_id if app_id else vid,
                "event_time": format_canonical_utc(dt_start),
                "original_clock_encoding": str(info.get("_created_at")) if (isinstance(info, dict) and info.get("_created_at")) else None,
                "observation_hash": canonical_json_hash({"v": vid, "role": "churn", "shelves": sorted(shelves.keys()), "apply": app_id}),
                "details": det,
            })
        return rows

    if metric_id == "shelf_activity.initial_filing_items":
        for vid in initial_filing_vids:
            rows.add(lambda:{
                "row_id": vid,
                "source_table": "yoinks",
                "source_key": vid,
                "event_time": format_canonical_utc(dt_start),
                "original_clock_encoding": None,
                "observation_hash": canonical_json_hash({"v": vid, "role": "initial_filing"}),
                "details": {"video_id": vid},
            })
        return rows

    if metric_id.startswith("shelf_activity."):
        filtered = interval_applies
        if metric_id == "shelf_activity.metadata_only_item_events":
            filtered = [a for a in interval_applies if a.get("metadata_only_count")]
        elif metric_id == "shelf_activity.primary_change_events":
            filtered = [a for a in interval_applies if a.get("primary_change_count")]
        elif metric_id == "shelf_activity.item_change_events":
            filtered = [a for a in interval_applies if a.get("item_change_count")]
        elif metric_id == "shelf_activity.policy_change_events":
            filtered = [a for a in interval_applies if a.get("policy_change_count")]
        elif metric_id == "shelf_activity.activation_events":
            filtered = [a for a in interval_applies if a.get("activation")]
        elif metric_id == "shelf_activity.membership_additions":
            filtered = [a for a in interval_applies if a.get("additions")]
        elif metric_id == "shelf_activity.membership_removals":
            filtered = [a for a in interval_applies if a.get("removals")]
        elif metric_id == "shelf_activity.membership_mutations":
            filtered = [a for a in interval_applies if a.get("additions") or a.get("removals")]
        elif metric_id == "shelf_activity.affected_items":
            filtered = [a for a in interval_applies if a.get("affected_vids")]
        for app in filtered:
            rows.add(lambda:_apply_row(app))
        return rows

    # 8. Sources
    if metric_id.startswith("sources."):
        parts = metric_id.split(".")
        if len(parts) >= 3 and parts[2] == "captures":
            s_id = parts[1]
            for item in captured_in_interval_items:
                vid = item["video_id"]
                if s_id in vid_to_sources.get(vid, set()):
                    dt_ev = item["capture_dt"]
                    assert dt_ev is not None
                    raw_clock = item["raw_yoinked_at"]
                    rows.add(lambda:{
                        "row_id": vid,
                        "source_table": "yoinks",
                        "source_key": vid,
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"s": s_id, "v": vid, "a": item.get("author")}),
                        "details": {
                            "video_id": vid,
                            "source_id": s_id,
                            "author": item.get("author"),
                            "follow_up": f"get_library_item('{vid}')",
                        },
                    })
            return rows

        if len(parts) >= 4 and parts[1] == "hint" and parts[3] == "captures":
            target_hash = parts[2]
            for (p, f, v), group_items in unlinked_hint_groups.items():
                h_hash = hashlib.sha256(f"{p}_{f}_{v}".encode("utf-8")).hexdigest()[:16]
                if h_hash == target_hash:
                    for item in group_items:
                        vid = item["video_id"]
                        dt_ev = item["capture_dt"]
                        raw_clock = item["raw_yoinked_at"]
                        rows.add(lambda:{
                            "row_id": vid,
                            "source_table": "yoinks",
                            "source_key": vid,
                            "event_time": format_canonical_utc(dt_ev) if dt_ev else None,
                            "original_clock_encoding": str(raw_clock),
                            "observation_hash": canonical_json_hash({"h": target_hash, "v": vid}),
                            "details": {
                                "video_id": vid,
                                "hint": v,
                                "follow_up": f"get_library_item('{vid}')",
                            },
                        })
            return rows

        if len(parts) >= 3 and parts[2] == "new_observations":
            s_id = parts[1]
            obs_list = source_obs_in_interval.get(s_id, [])
            seen_entries = set()
            for o in obs_list:
                e_id = o[2]
                if e_id not in seen_entries:
                    seen_entries.add(e_id)
                    dt_fs, _ = parse_epoch_ms(o[5])
                    rows.add(lambda:{
                        "row_id": e_id,
                        "source_table": "source_items",
                        "source_key": o[0],
                        "event_time": format_canonical_utc(dt_fs) if dt_fs else None,
                        "original_clock_encoding": str(o[5]),
                        "observation_hash": hashlib.sha256(f"{o[0]}_{o[5]}".encode("utf-8")).hexdigest(),
                        "details": {
                            "entry_id": e_id,
                            "source_id": s_id,
                            "item_id": o[0],
                        },
                    })
            return rows

        if len(parts) >= 4 and parts[2] == "new_observations_by_state":
            # BA-01: per-state source observation metrics have exact evidence:
            # the interval's first-seen entries in that state.
            s_id = parts[1]
            target_state = parts[3]
            obs_list = source_obs_in_interval.get(s_id, [])
            seen_entries = set()
            for o in obs_list:
                if o[7] != target_state:
                    continue
                e_id = o[2]
                if e_id in seen_entries:
                    continue
                seen_entries.add(e_id)
                dt_fs, _ = parse_epoch_ms(o[5])
                rows.add(lambda:{
                    "row_id": e_id,
                    "source_table": "source_items",
                    "source_key": o[0],
                    "event_time": format_canonical_utc(dt_fs) if dt_fs else None,
                    "original_clock_encoding": str(o[5]),
                    "observation_hash": canonical_json_hash({"item_id": o[0], "first_seen_ms": o[5], "state": target_state}),
                    "details": {
                        "entry_id": e_id,
                        "source_id": s_id,
                        "item_id": o[0],
                        "state": target_state,
                    },
                })
            return rows

        # Aggregate source counts
        s_name = parts[1] if len(parts) >= 2 else None
        if s_name in ("active_sources_count", "unlinked_hint_groups_count", "linked_capture_union_count", "multiply_linked_capture_count"):
            if s_name == "active_sources_count":
                for s_row in active_source_rows:
                    rows.add(lambda:{
                        "row_id": s_row["source_id"],
                        "source_table": "source_subscriptions",
                        "source_key": s_row["source_id"],
                        "event_time": s_row["observation_window"].get("last_item_seen_at") or format_canonical_utc(dt_start),
                        "original_clock_encoding": str(s_row["observation_window"].get("last_item_seen_at")),
                        "observation_hash": hashlib.sha256(s_row["source_id"].encode("utf-8")).hexdigest(),
                        "details": {"source_id": s_row["source_id"], "display_name": s_row["display_name"]},
                    })
                return rows
            elif s_name == "linked_capture_union_count":
                for item in captured_in_interval_items:
                    vid = item["video_id"]
                    if vid_to_sources.get(vid):
                        rows.add(lambda:{
                            "row_id": vid,
                            "source_table": "yoinks",
                            "source_key": vid,
                            "event_time": format_canonical_utc(item["capture_dt"]) if item["capture_dt"] else None,
                            "original_clock_encoding": str(item["raw_yoinked_at"]),
                            "observation_hash": hashlib.sha256(f"union_{vid}".encode("utf-8")).hexdigest(),
                            "details": {"video_id": vid},
                        })
                return rows
            elif s_name == "multiply_linked_capture_count":
                for item in captured_in_interval_items:
                    vid = item["video_id"]
                    if len(vid_to_sources.get(vid, set())) > 1:
                        rows.add(lambda:{
                            "row_id": vid,
                            "source_table": "yoinks",
                            "source_key": vid,
                            "event_time": format_canonical_utc(item["capture_dt"]) if item["capture_dt"] else None,
                            "original_clock_encoding": str(item["raw_yoinked_at"]),
                            "observation_hash": hashlib.sha256(f"multi_{vid}".encode("utf-8")).hexdigest(),
                            "details": {"video_id": vid},
                        })
                return rows
            elif s_name == "unlinked_hint_groups_count":
                if unlinked_hint_groups:
                    for (p, f, v), group_items in sorted(unlinked_hint_groups.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
                        h_hash = hashlib.sha256(f"{p}_{f}_{v}".encode("utf-8")).hexdigest()[:16]
                        rows.add(lambda:{
                            "row_id": h_hash,
                            "source_table": "yoinks",
                            "source_key": h_hash,
                            "event_time": format_canonical_utc(dt_start),
                            "original_clock_encoding": str(dt_start),
                            "observation_hash": hashlib.sha256(f"{p}_{f}_{v}".encode("utf-8")).hexdigest(),
                            "details": {"platform": p, "field": f, "hint": v},
                        })
                else:
                    for item in captured_in_interval_items:
                        vid = item["video_id"]
                        if not vid_to_sources.get(vid):
                            rows.add(lambda:{
                                "row_id": vid,
                                "source_table": "yoinks",
                                "source_key": vid,
                                "event_time": format_canonical_utc(item["capture_dt"]) if item["capture_dt"] else None,
                                "original_clock_encoding": str(item["raw_yoinked_at"]),
                                "observation_hash": hashlib.sha256(f"unlinked_{vid}".encode("utf-8")).hexdigest(),
                                "details": {"video_id": vid},
                            })
                return rows

    # 9. Revisions
    if metric_id == "revisions.runs_created":
        for r in all_runs:
            dt_r, _ = parse_native_creation_clock(r[5])
            if dt_r and dt_start <= dt_r < dt_end:
                rows.add(lambda:{
                    "row_id": r[0],
                    "source_table": "library_runs",
                    "source_key": r[0],
                    "event_time": format_canonical_utc(dt_r),
                    "original_clock_encoding": str(r[5]),
                    "observation_hash": r[2],
                    "details": {"run_id": r[0], "version_id": r[1], "state": r[4]},
                })
        return rows

    if metric_id == "events.total":
        for ev in cleaned_events:
            rows.add(lambda:{
                "row_id": ev.get("event_id"),
                "source_table": "events",
                "source_key": ev.get("event_id"),
                "event_time": ev.get("time"),
                "original_clock_encoding": ev.get("time"),
                "observation_hash": canonical_json_hash({"id": ev.get("event_id"), "kind": ev.get("kind")}),
                "details": ev.get("details") or {},
            })
        return rows

    if metric_id == "revisions.taxonomy_versions_created":
        for sv in all_shelf_versions:
            dt_sv, _ = parse_native_creation_clock(sv[3])
            if dt_sv and dt_start <= dt_sv < dt_end:
                rows.add(lambda:{
                    "row_id": sv[0],
                    "source_table": "shelf_versions",
                    "source_key": sv[0],
                    "event_time": format_canonical_utc(dt_sv),
                    "original_clock_encoding": str(sv[3]),
                    "observation_hash": sv[1],
                    "details": {"version_id": sv[0], "status": sv[2]},
                })
        return rows

    return None


# ---------------------------------------------------------------------------
# Tool Handler & MCP Seam
# ---------------------------------------------------------------------------

def handle_get_library_activity(args: dict) -> dict:
    return get_library_activity(args)


# ---------------------------------------------------------------------------
# whats_new_adapter
# ---------------------------------------------------------------------------

def whats_new_adapter(
    db_conn_or_path: Any,
    *,
    days: int = 7,
    as_of: Optional[Union[datetime, str]] = None,
) -> dict:
    """Prompt integration seam for Phase 4 whats-new."""
    if not isinstance(days, int) or isinstance(days, bool) or days < 1 or days > 30:
        raise ValueError("days must be integer between 1 and 30")

    if as_of is None:
        as_of_dt = datetime.now(timezone.utc)
    elif isinstance(as_of, datetime):
        as_of_dt = as_of.astimezone(timezone.utc)
    elif isinstance(as_of, str):
        parsed, err = parse_iso_utc(as_of)
        if parsed is None:
            raise ValueError(f"Invalid as_of timestamp: {err}")
        as_of_dt = parsed
    else:
        raise ValueError("as_of must be datetime, string, or None")

    dt_end = as_of_dt
    dt_start = dt_end - timedelta(days=days)

    req = {
        "interval": {
            "start": format_canonical_utc(dt_start),
            "end": format_canonical_utc(dt_end),
        },
        "date_basis": "capture_time",
    }
    return get_library_activity(req, db=db_conn_or_path, clock=as_of_dt)


# ---------------------------------------------------------------------------
# Narration Faithfulness Evaluation Harness (Section 4 static evaluation harness)
# ---------------------------------------------------------------------------

from library_faithfulness import (
    AssertionFixture,
    evaluate_narration_faithfulness,
)
