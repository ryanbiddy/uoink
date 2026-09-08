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
import unicodedata
import uuid
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
    guard = getattr(library_resources, "_PROCESS_GUARD", None)
    if guard is not None:
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
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


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
_FRACTIONAL_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{3}))?Z$")
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
    """Parse integer epoch milliseconds."""
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


def parse_interval(interval: Any, as_of_dt: datetime) -> Tuple[Optional[datetime], Optional[datetime], Optional[dict]]:
    """Validate and parse requested interval."""
    if not isinstance(interval, dict):
        return None, None, error_envelope("validation_error", "interval must be an object with start and end")
    if "start" not in interval or "end" not in interval:
        return None, None, error_envelope("validation_error", "interval requires both start and end timestamps")
    s_raw = interval.get("start")
    e_raw = interval.get("end")
    if not isinstance(s_raw, str) or not isinstance(e_raw, str):
        return None, None, error_envelope("validation_error", "interval bounds must be strings")

    # Strict UTC ISO regex with fractional bounds
    match_s = _FRACTIONAL_ISO_RE.match(s_raw)
    match_e = _FRACTIONAL_ISO_RE.match(e_raw)
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

def _validate_delta_structure(delta: Any) -> bool:
    if not isinstance(delta, dict):
        return False
    if "items" not in delta or "policies" not in delta:
        return False
    if not isinstance(delta["items"], dict) or not isinstance(delta["policies"], dict):
        return False
    for vid, rows in delta["items"].items():
        if not isinstance(vid, str) or not isinstance(rows, list):
            return False
        for r in rows:
            if not isinstance(r, dict) or "shelf_id" not in r:
                return False
    for k in delta["policies"]:
        if not isinstance(k, str):
            return False
    return True


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
                c = sqlite3.connect(f"file:{os.path.abspath(override)}?mode=ro", uri=True)
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
                c = sqlite3.connect(f"file:{os.path.abspath(idx_path)}?mode=ro", uri=True)
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
    return {
        "metric_id": metric_id,
        "value": numerator if denominator > 0 else 0,
        "unit": "ratio",
        "scope_ref": scope_ref,
        "numerator": numerator,
        "denominator": denominator,
        "percent": percent,
        "reason": res_reason,
        "evidence": {"metric_id": metric_id, "role": "numerator"},
    }


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


def _count_metric(
    metric_id: str,
    value: Optional[int],
    unit: str,
    scope_ref: str,
    *,
    recorded_count: Optional[int] = None,
) -> CountMetric:
    m = {
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "scope_ref": scope_ref,
        "evidence": {"metric_id": metric_id, "role": "numerator"},
    }
    if value is None or recorded_count is not None:
        m["recorded_count"] = recorded_count if recorded_count is not None else 0
    return CountMetric(m)


def _truncate_label(label: str) -> str:
    if len(label) <= MAX_LABEL_CODEPOINTS:
        return label
    return label[: MAX_LABEL_CODEPOINTS - 3] + "..."


def get_library_activity(
    args: dict,
    *,
    db: Any = None,
    clock: Any = None,
) -> dict:
    """Entry point for get_library_activity read tool."""
    guard = library_resources.process_guard()
    try:
        guard.admit()
    except library_resources.ResourceError as e:
        return error_envelope(e.code, e.message, details=e.details, retryable=True)
    except Exception as e:
        return error_envelope("rate_limited", str(e), retryable=True)

    start_time = time.monotonic()
    try:
        return _execute_activity(args, db=db, clock=clock, start_time=start_time)
    finally:
        guard.release()


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

    if conn.in_transaction:
        return error_envelope("invalid_state", "Refusing inherited uncommitted transaction", retryable=False)

    from contextlib import nullcontext
    lock_ctx = lock if lock is not None else nullcontext()
    lock_ctx.__enter__()
    try:
        if conn.in_transaction:
            return error_envelope("invalid_state", "Refusing inherited uncommitted transaction", retryable=False)

        tbl_err = _verify_tables(conn)
        if tbl_err is not None:
            return tbl_err

        # Capture generation at read boundary
        gen_start = _get_db_generation(conn)

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
            "SELECT operation_sequence, operation_key, authoritative_record_hash "
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
        receipt_by_seq = {}
        for r in all_receipts:
            receipt_by_seq[r[0]] = (r[1], r[2])

        expected_seqs = list(range(1, last_op_seq + 1))
        if [r[0] for r in all_receipts] != expected_seqs:
            baseline_proved = False
            baseline_reason = "missing_receipt_sequence_gap"
        else:
            baseline_proved = True
            baseline_reason = None

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
            "authoritative_record_hash, forward_json, inverse_json, undo_of, created_at "
            "FROM library_applies ORDER BY operation_sequence ASC"
        )

        for idx, app_row in enumerate(c_applies):
            dl_err = _check_deadline()
            if dl_err is not None:
                return dl_err

            total_applies_count += 1
            app_id, op_key, a_kind, before_rev, after_rev, op_seq, auth_hash, f_json, i_json, undo_of, c_at = app_row

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

            if op_seq != idx + 1:
                baseline_proved = False
                if baseline_reason is None:
                    baseline_reason = "operation_sequence_gap"

            rcpt = receipt_by_seq.get(op_seq)
            if rcpt is None or rcpt[0] != op_key or rcpt[1] != auth_hash:
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

            dt_apply, _ = parse_iso_utc(c_at)
            if dt_apply is None and isinstance(c_at, (int, float)):
                dt_apply, _ = parse_epoch_ms(c_at)

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
                for vid, rows in i_items.items():
                    if vid in live_survivor_ids:
                        cur_memberships = {s_id: r.get("is_primary", 0) for s_id, r in projected_state[vid].items()}
                        inv_memberships = {r["shelf_id"]: r.get("is_primary", 0) for r in rows}
                        if cur_memberships != inv_memberships:
                            baseline_proved = False
                            baseline_reason = "mismatched_inverse_projection"
                            break

                if baseline_proved:
                    f_items = f_delta.get("items", {})
                    for vid, rows in f_items.items():
                        if vid in live_survivor_ids:
                            projected_state[vid] = {r["shelf_id"]: r for r in rows}

            # Interval applies accounting
            if dt_apply is not None and dt_start <= dt_apply < dt_end:
                applied_ops_count += 1
                f_items = f_delta.get("items", {})
                i_items = i_delta.get("items", {})
                all_vids = set(f_items.keys()) | set(i_items.keys())
                ref_shelves = set()

                for vid in all_vids:
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
                    for s in removed:
                        shelf_removals[s] = shelf_removals.get(s, 0) + 1

                    if f_shelves != i_shelves or f_prim != i_prim:
                        interval_affected_items.add(vid)
                        item_change_events += 1
                        if f_prim != i_prim and f_shelves == i_shelves:
                            primary_change_events += 1
                    elif f_rows != i_rows:
                        metadata_only_events += 1

                f_pols = f_delta.get("policies", {})
                i_pols = i_delta.get("policies", {})
                for p_k in set(f_pols.keys()) | set(i_pols.keys()):
                    if f_pols.get(p_k) != i_pols.get(p_k):
                        policy_change_events += 1

                f_act = f_delta.get("active_version_id")
                i_act = i_delta.get("active_version_id")
                if f_act != i_act and (f_act is not None or i_act is not None):
                    activation_events += 1

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
                })

            del f_delta
            del i_delta

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

            actual_current_shelves: Dict[str, Dict[str, int]] = {vid: {} for vid in live_survivor_ids}
            for r in all_item_shelves:
                vid = r[0]
                if vid in live_survivor_ids:
                    actual_current_shelves[vid][r[1]] = r[6]

            for vid in live_survivor_ids:
                p_memberships = {s_id: r.get("is_primary", 0) for s_id, r in projected_state[vid].items()}
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
        receipts_binding = [{"seq": r[0], "k": r[1], "h": r[2]} for r in all_receipts]
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

            parsed_items.append(item)

        # Process excluded tombstones in interval
        tombstones_in_interval = 0
        tombstones_unlocated = 0
        for item in tombstone_yoinks:
            dt_cap, cap_err = parse_iso_utc(item["raw_yoinked_at"])
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

            # Creator hint: (platform, field, trimmed-value)
            platform = item["platform"]
            if item["author"]:
                c_field = "author"
                c_val = item["author"]
            elif item["channel"]:
                c_field = "channel"
                c_val = item["channel"]
            else:
                c_field = "unknown"
                c_val = ""

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

        by_source_type_rows: List[dict] = []
        for t_name, count in sorted(type_counts.items(), key=lambda x: (-x[1], x[0])):
            m_id = f"items.by_source_type.{t_name}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref)
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
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref)
            display_hint = _truncate_label(p_val.strip()) if p_val and p_val.strip() else "unknown"
            by_creator_rows.append({
                "platform": p_plat,
                "field": p_field,
                "hint": display_hint,
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
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref)
            display_hint = _truncate_label(p_val.strip()) if p_val and p_val.strip() else "unknown"
            by_joint_rows.append({
                "source_type": j_stype,
                "platform": p_plat,
                "field": p_field,
                "hint": display_hint,
                "key_hash": j_hash,
                "count": c_metric,
                "share": s_metric,
            })

        daily_rows: List[dict] = []
        for (b_s, b_e), count in daily_counts.items():
            b_hash = hashlib.sha256(f"{b_s}_{b_e}".encode("utf-8")).hexdigest()[:16]
            m_id = f"items.daily_buckets.{b_hash}"
            c_metric = _count_metric(f"{m_id}.count", count, "saved_items", scope_items_ref)
            s_metric = _ratio_metric(f"{m_id}.share", count, selected_total, scope_items_ref)
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
            "publication_unavailable_by_reason": pub_unavailable_by_reason,
            "deleted_items_excluded": _count_metric("items.deleted_items_excluded", tombstones_in_interval, "saved_items", "scope_items_capture"),
            "deleted_items_unlocated": _count_metric("items.deleted_items_unlocated", tombstones_unlocated, "saved_items", "scope_items_capture"),
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
        if baseline_proved:
            baseline_assigned_vids = {vid for vid, shelves in start_state.items() if len(shelves) > 0}
            churn_denom = len(baseline_assigned_vids)
            changed_baseline_vids = baseline_assigned_vids.intersection(interval_affected_items)
            churn_num = len(changed_baseline_vids)
            if churn_denom == 0:
                churn_metric = _ratio_metric("shelf_activity.churn", 0, 0, "scope_shelf_activity", reason="empty_population")
                churn_metric["initial_filing"] = True
            else:
                churn_metric = _ratio_metric("shelf_activity.churn", churn_num, churn_denom, "scope_shelf_activity")
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
                "scope_ref": "scope_shelf_activity",
                "numerator": None,
                "denominator": None,
                "percent": None,
                "reason": "baseline_unavailable",
                "evidence": {"metric_id": "shelf_activity.churn", "role": "numerator"},
                "initial_filing": None,
            }
            initial_filing_count = 0

        shelf_labels: Dict[str, str] = {r[1]: r[2] for r in all_shelf_nodes}
        active_shelf_labels: Dict[str, str] = {r[1]: r[2] for r in all_shelf_nodes if r[0] == active_version_id}

        # Build shelves table rows
        known_shelves = sorted({r[0] for r in all_shelves} | set(current_shelf_sizes.keys()) | set(shelf_additions.keys()) | set(shelf_removals.keys()))
        shelves_rows: List[dict] = []
        for s_id in known_shelves:
            c_size = current_shelf_sizes.get(s_id, 0)
            added = shelf_additions.get(s_id, 0)
            removed = shelf_removals.get(s_id, 0)
            net = added - removed
            s_name = active_shelf_labels.get(s_id) or shelf_labels.get(s_id) or s_id

            if baseline_proved:
                s_start = sum(1 for vid, shelves in start_state.items() if s_id in shelves)
                s_end = sum(1 for vid, shelves in end_state.items() if s_id in shelves)
                # Shelf churn numerator: members at start that changed
                start_members = {vid for vid, shelves in start_state.items() if s_id in shelves}
                s_churn_num = len(start_members.intersection(interval_affected_items))
                s_churn = _ratio_metric(f"shelf_activity.shelves.{s_id}.churn", s_churn_num, s_start, "scope_shelf_activity")
            else:
                s_start = None
                s_end = None
                s_churn = {
                    "metric_id": f"shelf_activity.shelves.{s_id}.churn",
                    "value": None,
                    "unit": "ratio",
                    "scope_ref": "scope_shelf_activity",
                    "numerator": None,
                    "denominator": None,
                    "percent": None,
                    "reason": "baseline_unavailable",
                    "evidence": {"metric_id": f"shelf_activity.shelves.{s_id}.churn", "role": "numerator"},
                }

            shelves_rows.append({
                "shelf_id": s_id,
                "name": s_name,
                "label": s_name,
                "active_name": active_shelf_labels.get(s_id, s_name),
                "active_label": active_shelf_labels.get(s_id, s_name),
                "current_size": _count_metric(f"shelf_activity.shelves.{s_id}.current_size", c_size, "items", "scope_shelf_current"),
                "start_size": _count_metric(f"shelf_activity.shelves.{s_id}.start_size", s_start, "items", "scope_shelf_activity") if s_start is not None else None,
                "end_size": _count_metric(f"shelf_activity.shelves.{s_id}.end_size", s_end, "items", "scope_shelf_activity") if s_end is not None else None,
                "added": added,
                "removed": removed,
                "net": net,
                "churn": s_churn,
            })

        shelf_family = {
            "applied_operations": _count_metric("shelf_activity.applied_operations", applied_ops_count, "operations", "scope_shelf_activity"),
            "membership_additions": _count_metric("shelf_activity.membership_additions", total_membership_additions, "mutations", "scope_shelf_activity"),
            "membership_removals": _count_metric("shelf_activity.membership_removals", total_membership_removals, "mutations", "scope_shelf_activity"),
            "membership_mutations": _count_metric("shelf_activity.membership_mutations", total_membership_mutations, "mutations", "scope_shelf_activity"),
            "affected_items": _count_metric("shelf_activity.affected_items", len(interval_affected_items), "saved_items", "scope_shelf_activity"),
            "item_change_events": _count_metric("shelf_activity.item_change_events", item_change_events, "events", "scope_shelf_activity"),
            "primary_change_events": _count_metric("shelf_activity.primary_change_events", primary_change_events, "events", "scope_shelf_activity"),
            "metadata_only_item_events": _count_metric("shelf_activity.metadata_only_item_events", metadata_only_events, "events", "scope_shelf_activity"),
            "policy_change_events": _count_metric("shelf_activity.policy_change_events", policy_change_events, "events", "scope_shelf_activity"),
            "activation_events": _count_metric("shelf_activity.activation_events", activation_events, "events", "scope_shelf_activity"),
            "current_assigned_items": _count_metric("shelf_activity.current_assigned_items", distinct_current_assigned, "saved_items", "scope_shelf_current"),
            "current_memberships": _count_metric("shelf_activity.current_memberships", total_current_memberships, "memberships", "scope_shelf_current"),
            "shelves": shelves_rows[:20],
            "churn": churn_metric,
            "initial_filing_items": _count_metric("shelf_activity.initial_filing_items", initial_filing_count, "saved_items", "scope_shelf_activity"),
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
            if ls_ms is not None and ls_ms != 0 and dt_ls is None:
                sources_unavailable_count += 1

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

                active_source_rows.append({
                    "source_id": s_id,
                    "identity_kind": "subscription",
                    "kind": kind,
                    "canonical_url": url,
                    "display_name": _truncate_label(d_name),
                    "captures_in_interval": _count_metric(f"sources.{s_id}.captures", captures_in_int, "saved_items", "scope_sources"),
                    "new_observations": _count_metric(f"sources.{s_id}.new_observations", new_obs_count, "entries", "scope_sources"),
                    "new_observations_by_state": state_counts,
                    "observation_window": {
                        "first_observed_at": format_canonical_utc(first_obs_dt) if first_obs_dt else None,
                        "last_item_seen_at": format_canonical_utc(last_obs_dt) if last_obs_dt else None,
                        "enrollment_at": format_canonical_utc(parse_epoch_ms(created_ms)[0]) if parse_epoch_ms(created_ms)[0] else None,
                        "last_poll_attempt": format_canonical_utc(parse_epoch_ms(cur_info.get("last_poll_attempt_ms"))[0]) if parse_epoch_ms(cur_info.get("last_poll_attempt_ms"))[0] else None,
                        "last_poll_success": format_canonical_utc(parse_epoch_ms(cur_info.get("last_poll_success_ms"))[0]) if parse_epoch_ms(cur_info.get("last_poll_success_ms"))[0] else None,
                        "cursor_coverage": cur_info.get("coverage", "unknown"),
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
            p = item["platform"]
            f = "author" if item["author"] else ("channel" if item["channel"] else "unknown")
            v = item["author"] or item["channel"] or ""
            unlinked_hint_groups.setdefault((p, f, v), []).append(item)

        unlinked_hint_rows: List[dict] = []
        for (p, f, v), group_items in sorted(unlinked_hint_groups.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            h_hash = hashlib.sha256(f"{p}_{f}_{v}".encode("utf-8")).hexdigest()[:16]
            display_hint = _truncate_label(v.strip()) if v and v.strip() else "unknown"
            cap_dts = [it["capture_dt"] for it in group_items if it.get("capture_dt")]
            min_cap = min(cap_dts) if cap_dts else None
            max_cap = max(cap_dts) if cap_dts else None
            unlinked_hint_rows.append({
                "source_id": None,
                "identity_kind": "creator_hint",
                "platform": p,
                "field": f,
                "hint": display_hint,
                "display_name": display_hint,
                "captures_in_interval": _count_metric(f"sources.hint.{h_hash}.captures", len(group_items), "saved_items", "scope_sources"),
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

        # Support level
        if len(captured_in_interval_items) == 0:
            support_level = "none"
        elif len(unlinked_captured_items) == 0 and len({s for vid in captured_in_interval_vids for s in vid_to_sources.get(vid, set())}) == 1:
            support_level = "single_source"
        else:
            support_level = "unresolved"

        sources_family = {
            "active_sources_count": _count_metric("sources.active_sources_count", len(active_source_rows), "sources", "scope_sources"),
            "unlinked_hint_groups_count": _count_metric("sources.unlinked_hint_groups_count", len(unlinked_hint_groups), "creator_hints", "scope_sources"),
            "linked_capture_union_count": _count_metric("sources.linked_capture_union_count", len(linked_captured_vids), "saved_items", "scope_sources"),
            "multiply_linked_capture_count": _count_metric("sources.multiply_linked_capture_count", len(multi_linked_captured_vids), "saved_items", "scope_sources"),
            "details": all_source_details[:20],
            "coverage_ref": "cov_sources",
        }

        # -------------------------------------------------------------------
        # Q8 Revisions
        # -------------------------------------------------------------------
        tax_versions_created = 0
        for sv in all_shelf_versions:
            dt_sv, _ = parse_epoch_ms(sv[3])
            if dt_sv and dt_start <= dt_sv < dt_end:
                tax_versions_created += 1

        runs_created = 0
        for r in all_runs:
            dt_r, _ = parse_epoch_ms(r[5])
            if dt_r and dt_start <= dt_r < dt_end:
                runs_created += 1

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
            dt_sv, _ = parse_epoch_ms(sv[3])
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
            dt_r, _ = parse_epoch_ms(r[5])
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
            "total": total_events_count,
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
            "scope_revisions": {
                "population": "recorded_revisions",
                "clock": "creation_time",
                "interval": canonical_interval,
                "query_id": "Q8",
                "query_version": CONTRACT_VERSION,
                "revision_ref": report_revision,
                "coverage_ref": "cov_revisions",
            },
        }

        # Active taxonomy hash
        active_tax_hash = None
        for sv in all_shelf_versions:
            if sv[0] == active_version_id:
                active_tax_hash = sv[1]
                break

        provenance = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "queries_used": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q8"],
            "projection_revision": projection_revision,
            "last_operation_sequence": last_op_seq,
            "active_taxonomy_version_id": active_version_id,
            "active_taxonomy_hash": active_tax_hash,
            "scopes": scopes,
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

        if (date_basis == "capture_time" and cap_cov_status == "no_history") or (date_basis == "publication_time" and pub_cov_status == "no_history"):
            items_total_metric["value"] = None
            items_total_metric["recorded_count"] = 0

        sources_cov_status = "partial" if sources_unavailable_count > 0 else ("retained_records" if all_sitems else "no_history")

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
                "earliest_retained_timestamp": None,
                "latest_retained_timestamp": None,
            },
            "cov_revisions": {
                "clock": "creation_time",
                "requested_interval": canonical_interval,
                "coverage_status": "retained_records",
                "earliest_retained_timestamp": None,
                "latest_retained_timestamp": None,
            },
        }

        # Pagination metadata for summary
        other_types_count = sum(r["count"]["value"] for r in by_source_type_rows[20:])
        other_creator_count = sum(r["count"]["value"] for r in by_creator_rows[20:])
        other_joint_count = sum(r["count"]["value"] for r in by_joint_rows[20:])

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
                valid_metric_ids: Set[str] = {
                    "items.total",
                    "items.live_population",
                    "items.capture_time_available",
                    "items.capture_time_unavailable",
                    "items.publication_time_available",
                    "items.publication_time_unavailable",
                    "items.deleted_items_excluded",
                    "items.deleted_items_unlocated",
                }
                for r in by_source_type_rows:
                    valid_metric_ids.add(r["count"]["metric_id"])
                    valid_metric_ids.add(r["share"]["metric_id"])
                for r in by_creator_rows:
                    valid_metric_ids.add(r["count"]["metric_id"])
                    valid_metric_ids.add(r["share"]["metric_id"])
                for r in by_joint_rows:
                    valid_metric_ids.add(r["count"]["metric_id"])
                    valid_metric_ids.add(r["share"]["metric_id"])
                for r in daily_rows:
                    valid_metric_ids.add(r["count"]["metric_id"])
                    valid_metric_ids.add(r["share"]["metric_id"])
                for k in (
                    "applied_operations", "membership_additions", "membership_removals",
                    "membership_mutations", "affected_items", "item_change_events",
                    "primary_change_events", "metadata_only_item_events", "policy_change_events",
                    "activation_events", "current_assigned_items", "current_memberships",
                    "initial_filing_items", "churn"
                ):
                    if k in shelf_family and isinstance(shelf_family[k], dict) and "metric_id" in shelf_family[k]:
                        valid_metric_ids.add(shelf_family[k]["metric_id"])
                for sh_r in shelves_rows:
                    for k in ("current_size", "start_size", "end_size", "churn"):
                        if sh_r.get(k) and isinstance(sh_r[k], dict) and "metric_id" in sh_r[k]:
                            valid_metric_ids.add(sh_r[k]["metric_id"])
                for k in ("active_sources_count", "unlinked_hint_groups_count", "linked_capture_union_count", "multiply_linked_capture_count"):
                    if k in sources_family and isinstance(sources_family[k], dict) and "metric_id" in sources_family[k]:
                        valid_metric_ids.add(sources_family[k]["metric_id"])
                for s_r in all_source_details:
                    if "captures_in_interval" in s_r and isinstance(s_r["captures_in_interval"], dict):
                        valid_metric_ids.add(s_r["captures_in_interval"]["metric_id"])
                    if "new_observations" in s_r and isinstance(s_r["new_observations"], dict):
                        valid_metric_ids.add(s_r["new_observations"]["metric_id"])
                for k in ("taxonomy_versions_created", "runs_created"):
                    if k in revisions_family and isinstance(revisions_family[k], dict) and "metric_id" in revisions_family[k]:
                        valid_metric_ids.add(revisions_family[k]["metric_id"])

                daily_buckets_map = {
                    hashlib.sha256(f"{format_canonical_utc(b[0])}_{format_canonical_utc(b[1])}".encode("utf-8")).hexdigest()[:16]: (b[0], b[1])
                    for b in daily_buckets
                }

                ev_rows = _lookup_evidence(
                    metric_id,
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
                )
                if ev_rows is None:
                    return error_envelope("not_found", f"Metric ID not found: {metric_id}")
                detail_total = len(ev_rows)
                detail_rows = ev_rows[offset : offset + limit]

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

            # Refuse unfit identity (> 512 bytes or control characters) without truncation
            for r in detail_rows:
                ids_to_check = [r.get("row_id"), r.get("source_key")]
                if isinstance(r.get("details"), dict):
                    ids_to_check.extend(r["details"].values())
                for id_val in ids_to_check:
                    if isinstance(id_val, str):
                        raw_id = id_val.encode("utf-8")
                        if len(raw_id) > 512 or any(unicodedata.category(ch) == "Cc" for ch in id_val):
                            return error_envelope("resource_too_large", "Requested document exceeds bounded response limits", retryable=False)

            # Bound serialized response
            resp_bytes = len(json.dumps(detail_response, ensure_ascii=False).encode("utf-8"))
            if resp_bytes > MAX_RESPONSE_BYTES:
                return error_envelope("resource_too_large", "Requested document exceeds bounded response limits", retryable=False)

            # Verify generation before returning
            gen_end = _get_db_generation(conn)
            if gen_end["total_changes"] != gen_start["total_changes"] or gen_end["data_version"] != gen_start["data_version"]:
                return error_envelope("stale_report", "Database was modified during report construction", retryable=False)

            # Check service deadline
            if time.monotonic() - start_time > SERVICE_DEADLINE_SEC:
                return error_envelope("deadline_exceeded", "Service deadline exceeded", retryable=True)

            return detail_response

        # -------------------------------------------------------------------
        # Build Summary Response
        # -------------------------------------------------------------------
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
        resp_json = json.dumps(summary_response, ensure_ascii=False)
        resp_bytes = len(resp_json.encode("utf-8"))

        while resp_bytes > MAX_RESPONSE_BYTES:
            # Fixed drop order: event rows, joint creator rows, creator rows, source rows, shelf rows
            if events_family["rows"]:
                events_family["rows"].pop()
                ret_len = len(events_family["rows"])
                events_family["returned_rows"] = ret_len
                events_family["omitted_rows"] = events_family["total"] - ret_len
                if ret_len < events_family["total"]:
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
                pagination_map["type_creator_hints"]["other_count"] = sum(r["count"]["value"] for r in by_joint_rows[ret_len:])
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
                pagination_map["creator_hints"]["other_count"] = sum(r["count"]["value"] for r in by_creator_rows[ret_len:])
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

            resp_bytes = len(json.dumps(summary_response, ensure_ascii=False).encode("utf-8"))

        # Verify generation before returning
        gen_end = _get_db_generation(conn)
        if gen_end["total_changes"] != gen_start["total_changes"] or gen_end["data_version"] != gen_start["data_version"]:
            return error_envelope("stale_report", "Database was modified during report construction", retryable=False)

        # Check service deadline
        if time.monotonic() - start_time > SERVICE_DEADLINE_SEC:
            return error_envelope("deadline_exceeded", "Service deadline exceeded", retryable=True)

        return summary_response

    finally:
        try:
            lock_ctx.__exit__(*sys.exc_info())
        except Exception:
            pass
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Evidence Lookup
# ---------------------------------------------------------------------------

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
) -> Optional[List[dict]]:
    """Return supporting evidence rows for a given metric ID."""
    if metric_id not in valid_metric_ids:
        return None

    if captured_in_interval_items is None:
        captured_in_interval_items = selected_items
    if unlinked_hint_groups is None:
        unlinked_hint_groups = {}

    rows: List[dict] = []

    # 1. items.total
    if metric_id == "items.total":
        if date_basis == "capture_time":
            for item in selected_items:
                dt_ev = item["capture_dt"]
                assert dt_ev is not None
                raw_clock = item["raw_yoinked_at"]
                obs_dict = {"v": item["video_id"], "t": item["source_type"], "p": item["platform"], "c": raw_clock}
                rows.append({
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": format_canonical_utc(dt_ev),
                    "original_clock_encoding": str(raw_clock),
                    "observation_hash": canonical_json_hash(obs_dict),
                    "details": {
                        "video_id": item["video_id"],
                        "source_type": item["source_type"],
                        "platform": item["platform"],
                        "author": item["author"],
                        "channel": item["channel"],
                        "hint": item["author"] or item["channel"] or "unknown",
                        "follow_up": f"get_library_item('{item['video_id']}')",
                    },
                })
        else:
            for item in selected_items:
                dt_ev = item["pub_dt"]
                assert dt_ev is not None
                pub_tier = item.get("pub_tier")
                if pub_tier == "adapter_normalized" and item.get("selected_pub_entry"):
                    entry = item["selected_pub_entry"]
                    raw_clock = entry["published_at_ms"]
                    obs_dict = {"item_id": entry["item_id"], "published_at_ms": raw_clock}
                    row_details = {
                        "video_id": item["video_id"],
                        "item_id": entry["item_id"],
                        "source_id": entry["source_id"],
                        "entry_id": entry["entry_id"],
                        "source_items": True,
                        "adapter_normalized": True,
                        "follow_up": f"get_library_item('{item['video_id']}')",
                    }
                    if item.get("lower_tier_disagreement"):
                        row_details["lower_tier_disagreement"] = item["lower_tier_disagreement"]
                        row_details["disagreement"] = item["lower_tier_disagreement"]
                        row_details["conflict"] = True
                    rows.append({
                        "row_id": entry["item_id"],
                        "source_table": "source_items",
                        "source_key": entry["item_id"],
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash(obs_dict),
                        "details": row_details,
                    })
                elif pub_tier == "direct_episode_parse" and item.get("selected_pub_entry"):
                    ep = item["selected_pub_entry"]
                    raw_clock = ep["published_at"]
                    obs_dict = {"id": ep["id"], "published_at": raw_clock}
                    rows.append({
                        "row_id": str(ep["id"]),
                        "source_table": "podcast_episodes",
                        "source_key": str(ep["id"]),
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash(obs_dict),
                        "details": {
                            "video_id": item["video_id"],
                            "episode_id": ep["id"],
                            "direct_episode_parse": True,
                            "follow_up": f"get_library_item('{item['video_id']}')",
                        },
                    })
                else:
                    raw_clock = item.get("raw_pub_clock") or item["raw_yoinked_at"]
                    rows.append({
                        "row_id": item["video_id"],
                        "source_table": "yoinks",
                        "source_key": item["video_id"],
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"v": item["video_id"], "c": raw_clock}),
                        "details": {
                            "video_id": item["video_id"],
                            "follow_up": f"get_library_item('{item['video_id']}')",
                        },
                    })
        return rows

    # 2. Availability and exclusion metrics
    if metric_id == "items.live_population":
        for item in live_yoinks:
            dt_ev = item["capture_dt"]
            raw_clock = item["raw_yoinked_at"]
            rows.append({
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
                rows.append({
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
                rows.append({
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
        for item in live_yoinks:
            if item["pub_dt"] is not None:
                dt_ev = item["pub_dt"]
                rows.append({
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": format_canonical_utc(dt_ev),
                    "original_clock_encoding": str(item["raw_pub_clock"]),
                    "observation_hash": canonical_json_hash({"v": item["video_id"], "pub": True}),
                    "details": {"video_id": item["video_id"], "tier": item["pub_tier"]},
                })
        return rows

    if metric_id == "items.publication_time_unavailable":
        for item in live_yoinks:
            if item["pub_dt"] is None:
                rows.append({
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": None,
                    "original_clock_encoding": str(item["raw_pub_clock"]),
                    "observation_hash": canonical_json_hash({"v": item["video_id"], "reason": item["pub_reason"]}),
                    "details": {"video_id": item["video_id"], "reason": item["pub_reason"]},
                })
        return rows

    if metric_id == "items.deleted_items_excluded":
        for item in tombstone_yoinks:
            dt_ev, _ = parse_iso_utc(item["raw_deleted_at"]) if item["raw_deleted_at"] else (None, None)
            rows.append({
                "row_id": item["video_id"],
                "source_table": "yoinks",
                "source_key": item["video_id"],
                "event_time": format_canonical_utc(dt_ev) if dt_ev else None,
                "original_clock_encoding": str(item["raw_deleted_at"]),
                "observation_hash": canonical_json_hash({"v": item["video_id"], "deleted": True}),
                "details": {"video_id": item["video_id"], "deleted_at": item["raw_deleted_at"]},
            })
        return rows

    if metric_id == "items.deleted_items_unlocated":
        for item in tombstone_yoinks:
            if item["raw_yoinked_at"] is None:
                rows.append({
                    "row_id": item["video_id"],
                    "source_table": "yoinks",
                    "source_key": item["video_id"],
                    "event_time": None,
                    "original_clock_encoding": None,
                    "observation_hash": canonical_json_hash({"v": item["video_id"], "unlocated": True}),
                    "details": {"video_id": item["video_id"]},
                })
        return rows

    # 3. Source types
    if metric_id.startswith("items.by_source_type."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            stype = parts[2]
            for item in selected_items:
                match = (item["source_type"] == stype) if stype in CANONICAL_SOURCE_TYPES else (item["source_type"] not in CANONICAL_SOURCE_TYPES)
                if match:
                    dt_ev = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
                    assert dt_ev is not None
                    raw_clock = item["raw_yoinked_at"] if date_basis == "capture_time" else item["raw_pub_clock"]
                    rows.append({
                        "row_id": item["video_id"],
                        "source_table": "yoinks",
                        "source_key": item["video_id"],
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"v": item["video_id"], "t": item["source_type"]}),
                        "details": {
                            "video_id": item["video_id"],
                            "source_type": item["source_type"],
                            "follow_up": f"get_library_item('{item['video_id']}')",
                        },
                    })
            return rows

    # 4. Creator hints
    if metric_id.startswith("items.by_creator_hint."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            k_hash = parts[2]
            for item in selected_items:
                platform = item["platform"]
                if item["author"]:
                    c_field = "author"
                    c_val = item["author"]
                elif item["channel"]:
                    c_field = "channel"
                    c_val = item["channel"]
                else:
                    c_field = "unknown"
                    c_val = ""
                item_khash = hashlib.sha256(json.dumps([platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
                if item_khash == k_hash:
                    dt_ev = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
                    assert dt_ev is not None
                    raw_clock = item["raw_yoinked_at"] if date_basis == "capture_time" else item["raw_pub_clock"]
                    rows.append({
                        "row_id": item["video_id"],
                        "source_table": "yoinks",
                        "source_key": item["video_id"],
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"v": item["video_id"], "c": item_khash}),
                        "details": {
                            "video_id": item["video_id"],
                            "author": item["author"],
                            "channel": item["channel"],
                            "original_author": item["author"],
                            "original_channel": item["channel"],
                            "hint": _truncate_label(c_val.strip()) if c_val and c_val.strip() else "unknown",
                            "original_hint": c_val,
                            "platform": platform,
                            "follow_up": f"get_library_item('{item['video_id']}')",
                        },
                    })
            return rows

    # 5. Joint type + creator hints
    if metric_id.startswith("items.by_type_creator_hint."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            j_hash = parts[2]
            for item in selected_items:
                platform = item["platform"]
                if item["author"]:
                    c_field = "author"
                    c_val = item["author"]
                elif item["channel"]:
                    c_field = "channel"
                    c_val = item["channel"]
                else:
                    c_field = "unknown"
                    c_val = ""
                stype = item["source_type"] if item["source_type"] in CANONICAL_SOURCE_TYPES else "unknown"
                item_jhash = hashlib.sha256(json.dumps([stype, platform, c_field, c_val], ensure_ascii=False).encode("utf-8")).hexdigest()
                if item_jhash == j_hash:
                    dt_ev = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
                    assert dt_ev is not None
                    raw_clock = item["raw_yoinked_at"] if date_basis == "capture_time" else item["raw_pub_clock"]
                    rows.append({
                        "row_id": item["video_id"],
                        "source_table": "yoinks",
                        "source_key": item["video_id"],
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"v": item["video_id"], "j": item_jhash}),
                        "details": {
                            "video_id": item["video_id"],
                            "source_type": stype,
                            "author": item["author"],
                            "channel": item["channel"],
                            "original_author": item["author"],
                            "original_channel": item["channel"],
                            "platform": platform,
                            "hint": _truncate_label(c_val.strip()) if c_val and c_val.strip() else "unknown",
                            "original_hint": c_val,
                            "follow_up": f"get_library_item('{item['video_id']}')",
                        },
                    })
            return rows

    # 6. Daily buckets
    if metric_id.startswith("items.daily_buckets."):
        parts = metric_id.split(".")
        if len(parts) >= 4 and parts[3] in ("count", "share"):
            b_hash = parts[2]
            if b_hash in daily_buckets_map:
                b_start, b_end = daily_buckets_map[b_hash]
                for item in selected_items:
                    target_dt = item["capture_dt"] if date_basis == "capture_time" else item["pub_dt"]
                    assert target_dt is not None
                    if b_start <= target_dt < b_end:
                        raw_clock = item["raw_yoinked_at"] if date_basis == "capture_time" else item["raw_pub_clock"]
                        rows.append({
                            "row_id": item["video_id"],
                            "source_table": "yoinks",
                            "source_key": item["video_id"],
                            "event_time": format_canonical_utc(target_dt),
                            "original_clock_encoding": str(raw_clock),
                            "observation_hash": canonical_json_hash({"v": item["video_id"], "t": format_canonical_utc(target_dt)}),
                            "details": {
                                "video_id": item["video_id"],
                                "follow_up": f"get_library_item('{item['video_id']}')",
                            },
                        })
                return rows

    # 7. Shelf activity
    live_vid_set = {it["video_id"] for it in live_yoinks}

    if metric_id == "shelf_activity.current_assigned_items":
        assigned_vids = sorted({r[0] for r in all_item_shelves if r[0] in live_vid_set})
        for vid in assigned_vids:
            sh_rows = [r for r in all_item_shelves if r[0] == vid]
            assigned_at = sh_rows[0][9] if sh_rows else None
            dt_a = parse_iso_utc(assigned_at)[0] if assigned_at else as_of_dt
            rows.append({
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
            })
        return rows

    if metric_id == "shelf_activity.current_memberships":
        for r in all_item_shelves:
            if r[0] in live_vid_set:
                vid, s_id = r[0], r[1]
                assigned_at = r[9]
                dt_a = parse_iso_utc(assigned_at)[0] if assigned_at else as_of_dt
                rows.append({
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
                        rows.append({
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
            elif metric_kind in ("start_size", "end_size", "churn"):
                for app in interval_applies:
                    if s_id in app.get("referenced_shelves", set()):
                        dt_ev = app["created_at_dt"]
                        assert dt_ev is not None
                        rows.append({
                            "row_id": app["apply_id"],
                            "source_table": "library_applies",
                            "source_key": app["operation_sequence"],
                            "event_time": format_canonical_utc(dt_ev),
                            "original_clock_encoding": str(app["raw_created_at"]),
                            "observation_hash": app["authoritative_record_hash"],
                            "details": {
                                "apply_id": app["apply_id"],
                                "shelf_id": s_id,
                                "operation_sequence": app["operation_sequence"],
                            },
                        })
                return rows

    if metric_id.startswith("shelf_activity."):
        # Applied operations and journal mutation metrics
        for app in interval_applies:
            dt_ev = app["created_at_dt"]
            assert dt_ev is not None
            rows.append({
                "row_id": app["apply_id"],
                "source_table": "library_applies",
                "source_key": app["operation_sequence"],
                "event_time": format_canonical_utc(dt_ev),
                "original_clock_encoding": str(app["raw_created_at"]),
                "observation_hash": app["authoritative_record_hash"],
                "details": {
                    "apply_id": app["apply_id"],
                    "operation_sequence": app["operation_sequence"],
                    "kind": app["kind"],
                    "before_revision": app["before_revision"],
                    "after_revision": app["after_revision"],
                    "undo_of": app["undo_of"],
                },
            })
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
                    rows.append({
                        "row_id": vid,
                        "source_table": "source_items",
                        "source_key": vid,
                        "event_time": format_canonical_utc(dt_ev),
                        "original_clock_encoding": str(raw_clock),
                        "observation_hash": canonical_json_hash({"s": s_id, "v": vid}),
                        "details": {
                            "video_id": vid,
                            "source_id": s_id,
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
                        rows.append({
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
                    rows.append({
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

        # Aggregate source counts
        s_name = parts[1] if len(parts) >= 2 else None
        if s_name in ("active_sources_count", "unlinked_hint_groups_count", "linked_capture_union_count", "multiply_linked_capture_count"):
            if s_name == "active_sources_count":
                for s_row in active_source_rows:
                    rows.append({
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
                        rows.append({
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
                        rows.append({
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
                        rows.append({
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
                            rows.append({
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
            dt_r, _ = parse_epoch_ms(r[5])
            if dt_r and dt_start <= dt_r < dt_end:
                rows.append({
                    "row_id": r[0],
                    "source_table": "library_runs",
                    "source_key": r[0],
                    "event_time": format_canonical_utc(dt_r),
                    "original_clock_encoding": str(r[5]),
                    "observation_hash": r[2],
                    "details": {"run_id": r[0], "version_id": r[1], "state": r[4]},
                })
        return rows

    if metric_id == "revisions.taxonomy_versions_created":
        for sv in all_shelf_versions:
            dt_sv, _ = parse_epoch_ms(sv[3])
            if dt_sv and dt_start <= dt_sv < dt_end:
                rows.append({
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
# Narration Faithfulness Evaluator
# ---------------------------------------------------------------------------

_FORBIDDEN_CONSENSUS_TERMS = frozenset({
    "broad consensus",
    "creators agree",
    "industry-wide",
    "across creators",
    "multiple perspectives",
    "widespread trend",
    "surge across channels",
    "widespread community agreement",
    "broadly aligned",
})


def evaluate_narration_faithfulness(narration_text: str, activity_packet: dict) -> dict:
    """Evaluate candidate narration against activity packet facts (Section 4 metric)."""
    if not isinstance(narration_text, str) or not narration_text.strip():
        return {
            "passed": False,
            "score": 0.0,
            "supported_assertions": 0,
            "unsupported_assertions": 0,
            "failures": ["empty_narration"],
        }

    failures: List[str] = []
    supported_assertions = 0
    unsupported_assertions = 0

    text_lower = narration_text.lower()

    # 1. Unsupported consensus claims
    support_level = activity_packet.get("support_level")
    trend_eligible = activity_packet.get("trend_eligible", False)

    if support_level in ("single_source", "none", "unresolved") or not trend_eligible:
        for term in _FORBIDDEN_CONSENSUS_TERMS:
            if term in text_lower:
                failures.append(f"unsupported_consensus_claim: '{term}'")
                unsupported_assertions += 1

    # 2. Missing denominator check (claiming churn or ratio when baseline denominator is unavailable)
    sa = activity_packet.get("shelf_activity", {})
    churn_metric = sa.get("churn", {})
    if "churn" in text_lower or "%" in narration_text:
        if churn_metric.get("denominator") is None or churn_metric.get("reason") == "baseline_unavailable":
            failures.append("missing_denominator: claimed churn when baseline denominator is unavailable")
            unsupported_assertions += 1

    # 3. Directional claims
    shelves_list = sa.get("shelves", [])
    net_map = {s["shelf_id"]: s.get("net", 0) for s in shelves_list if isinstance(s, dict)}

    if "grew" in text_lower or "increased" in text_lower or "expanded" in text_lower:
        has_positive = False
        for s_id, net_val in net_map.items():
            s_name = s_id.replace("sh_", "").lower()
            if s_name in text_lower:
                if net_val > 0:
                    has_positive = True
                else:
                    failures.append(f"directional_inconsistency: asserted growth for shelf {s_id} with net {net_val}")
                    unsupported_assertions += 1
        if not net_map and not has_positive:
            failures.append("directional_inconsistency: asserted growth when net was not positive")
            unsupported_assertions += 1

    if "remained unchanged" in text_lower or "net zero" in text_lower:
        all_zero = all(s.get("net", 0) == 0 for s in shelves_list) if shelves_list else True
        if all_zero:
            supported_assertions += 1
        else:
            failures.append("directional_inconsistency: asserted unchanged when net was non-zero")
            unsupported_assertions += 1

    # 4. Temporal basis slippage
    date_basis = activity_packet.get("date_basis", "capture_time")
    if date_basis == "capture_time":
        if "published" in text_lower or "released" in text_lower:
            evidence_archive_dates = activity_packet.get("evidence_archive_dates", [])
            mentions_archive_date = any(ad in narration_text for ad in evidence_archive_dates)
            if not mentions_archive_date:
                failures.append("temporal_basis_slippage: claimed publication on capture date")
                unsupported_assertions += 1

    # 5. Invented topics
    known_topics = set(activity_packet.get("known_topics", []))
    for inv_term in ("quantum thermodynamics", "quantum mechanics", "astrophysics", "cryptography"):
        if inv_term in text_lower:
            if not any(inv_term in kt.lower() for kt in known_topics):
                failures.append(f"invented_topic: '{inv_term}'")
                unsupported_assertions += 1

    # 6. Unrelated entities / facts
    unrelated_entities = ("rabbits", "cats", "dogs", "kittens", "horses")
    for unk_ent in unrelated_entities:
        if unk_ent in text_lower:
            failures.append(f"unrelated_entity_claim: '{unk_ent}'")
            unsupported_assertions += 1

    # 7. Numbers and metrics checking
    # Mask out time strings (00:00, 18:00), dates, years, and archive dates
    masked_text = narration_text
    masked_text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " [TIME] ", masked_text)
    masked_text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " [DATE] ", masked_text)
    masked_text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b", " [DATE] ", masked_text)
    masked_text = re.sub(r"\b20\d\d\b", " [YEAR] ", masked_text)

    # Word numbers mapping
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }
    extracted_counts: List[int] = []
    for w, val in word_to_num.items():
        if re.search(rf"\b{w}\b", masked_text, re.IGNORECASE):
            extracted_counts.append(val)
    for n_str in re.findall(r"\b\d+\b", masked_text):
        extracted_counts.append(int(n_str))

    valid_metric_counts: Set[int] = set()
    def _gather_counts(obj: Any):
        if isinstance(obj, dict):
            if "value" in obj and isinstance(obj["value"], int) and not isinstance(obj["value"], bool):
                valid_metric_counts.add(obj["value"])
            for v in obj.values():
                _gather_counts(v)
        elif isinstance(obj, list):
            for it in obj:
                _gather_counts(it)

    _gather_counts(activity_packet)

    for c in extracted_counts:
        if c in valid_metric_counts:
            supported_assertions += 1
        else:
            failures.append(f"hallucinated_number: {c}")
            unsupported_assertions += 1

    total_assertions = supported_assertions + unsupported_assertions
    score = (supported_assertions / total_assertions) if total_assertions > 0 else (1.0 if not failures else 0.0)
    passed = (len(failures) == 0 and total_assertions > 0)

    return {
        "passed": passed,
        "score": round(score, 4),
        "supported_assertions": supported_assertions,
        "unsupported_assertions": unsupported_assertions,
        "failures": failures,
    }
