"""Real model-usage meter (D-17: model calls are "named, default-off, metered").

Every Anthropic Messages response carries a ``usage`` block::

    {"input_tokens": 5123, "output_tokens": 412,
     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

Until 2026-09-04 nobody read it. This module accumulates it into the
existing ``memory_layer`` KV table (migration 0006) -- one row per feature,
per model, per UTC month -- so the dashboard can show what calls *did* cost
instead of only what they were estimated to cost. No migration, no new
table: the KV table exists for "persistent metadata" and the Phase 2
substrate owns 0027.

Contract:

- **Model-specific.** The key carries the model id, so a mid-month model
  swap produces two rows rather than one row that lies about its price.
- **Atomic.** One ``BEGIN IMMEDIATE`` write transaction per call (under the
  Index re-entrant lock), read-modify-write inside it. Two concurrent
  background threads sum; they never overwrite each other.
- **Best-effort, never silent.** ``record_usage`` never raises: metering
  must not fail a call that already succeeded. But nothing disappears
  either (run F acceptance, case 3): a response without a usable ``usage``
  block is counted in ``unavailable_calls`` for its feature/model/month,
  and a meter write that fails is counted in the process-wide
  :func:`meter_status` that the public payload carries. Successful
  inference and meter failure stay separate: the call's result is
  untouched, only the accounting reports the gap.
- **Estimates, with provenance.** ``est_usd`` prices all four counters
  (input, output, cache read, cache creation) with a ``rates`` mapping
  that carries its own source URL and verified date; the rates used are
  stored next to the number. The result is labelled an estimate: it is
  list price applied to reported counters, not an invoice.
- **No network, no model.** This is a counter.

Key:   ``usage.anthropic.<feature>.<model>.<YYYY-MM>``
Value: ``{"feature", "model", "month", "calls", "unavailable_calls",
"input_tokens", "output_tokens", "cache_read", "cache_create", "est_usd",
"est_rates", "last_call_at", "last_unavailable_at", "last_usage"}``
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger("uoink.usage_meter")

KEY_PREFIX = "usage.anthropic."

# Anthropic usage field -> our short bucket name.
_USAGE_FIELDS = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read",
    "cache_creation_input_tokens": "cache_create",
}
_COUNTERS = ("input_tokens", "output_tokens", "cache_read", "cache_create")
_CALL_COUNTS = ("calls", "unavailable_calls")

# A ``rates`` mapping: per-million USD for each counter plus its provenance.
# Missing rate fields price as 0.0 (and the record shows the 0.0), missing
# provenance is stored as None -- neither is silently invented.
_RATE_FIELDS = {
    "input_per_million": "input_tokens",
    "output_per_million": "output_tokens",
    "cache_read_per_million": "cache_read",
    "cache_create_per_million": "cache_create",
}
_RATE_PROVENANCE = ("source", "source_checked")

# Legacy two-argument pricer (input_tokens, output_tokens) -> USD. Still
# accepted so older callers keep working; it cannot price cache counters,
# and a summary priced this way reports ``rates: None`` to say so.
PriceFn = Callable[[int, int], float]


def _now_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_of(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m")


def _safe_int(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _safe_float(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if f > 0 else 0.0


def _safe_label(value, fallback: str) -> str:
    """Key components must not contain the '.' separator or whitespace."""
    text = str(value or "").strip()
    if not text:
        text = fallback
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in text)


# ---- meter status (process-wide, visible accounting) -----------------------

_status_lock = threading.Lock()
_status: dict = {
    "write_failures": 0,
    "last_error": None,
    "last_failure_at": None,
    "last_failed_feature": None,
}


def note_write_failure(feature, exc: BaseException | str,
                       now: datetime | None = None) -> None:
    """Record that one meter write did not happen. Counted since helper
    start; the index is exactly what failed, so this lives in memory."""
    error = exc if isinstance(exc, str) else type(exc).__name__
    with _status_lock:
        _status["write_failures"] += 1
        _status["last_error"] = str(error)
        _status["last_failure_at"] = _now_iso(now)
        _status["last_failed_feature"] = _safe_label(feature, "unknown")


def meter_status() -> dict:
    """Snapshot of the write-failure status. ``ok`` is False as soon as one
    write since helper start was lost, so a dashboard cannot read an empty
    meter as "nothing was spent"."""
    with _status_lock:
        snapshot = dict(_status)
    snapshot["ok"] = snapshot["write_failures"] == 0
    return snapshot


def reset_status() -> None:
    """Forget recorded write failures (tests, or a deliberate reset)."""
    with _status_lock:
        _status.update(write_failures=0, last_error=None,
                       last_failure_at=None, last_failed_feature=None)


# ---- parsing ---------------------------------------------------------------

def parse_usage(resp: dict, *, default_model: str = "") -> dict | None:
    """Pull the four token counters and the model id out of a Messages
    response. Returns None when there is nothing to meter (no ``usage``
    block, or a block with no positive counters)."""
    if not isinstance(resp, dict):
        return None
    usage = resp.get("usage")
    if not isinstance(usage, dict):
        return None
    counters = {short: _safe_int(usage.get(long))
                for long, short in _USAGE_FIELDS.items()}
    if not any(counters.values()):
        return None
    return {"model": _model_of(resp, default_model), **counters}


def _model_of(resp: dict, default_model: str = "") -> str:
    model = str(resp.get("model") or default_model or "unknown").strip()
    return model or "unknown"


def usage_key(feature: str, model: str, month: str) -> str:
    return (f"{KEY_PREFIX}{_safe_label(feature, 'unknown')}."
            f"{_safe_label(model, 'unknown')}.{month}")


def _empty_bucket(feature: str, model: str, month: str) -> dict:
    return {
        "feature": feature,
        "model": model,
        "month": month,
        "calls": 0,
        "unavailable_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_create": 0,
        "est_usd": 0.0,
        "est_rates": None,
        "last_call_at": None,
        "last_unavailable_at": None,
        "last_usage": None,
    }


# ---- pricing ---------------------------------------------------------------

def rates_record(rates) -> dict | None:
    """Normalise a rates mapping into the shape stored next to every
    estimate: four per-million floats plus ``source`` and
    ``source_checked``. None when no rates were supplied."""
    if not isinstance(rates, dict):
        return None
    record = {field: _safe_float(rates.get(field)) for field in _RATE_FIELDS}
    for field in _RATE_PROVENANCE:
        value = rates.get(field)
        record[field] = str(value) if value else None
    return record


def estimate_usd(counters: dict, *, rates=None,
                 price: PriceFn | None = None) -> float:
    """List-price estimate for a set of counters. ``rates`` prices all four
    counters; the legacy ``price`` callable prices input/output only.
    Pricing is decoration -- it never raises, it returns 0.0 instead."""
    try:
        if isinstance(rates, dict):
            total = 0.0
            for rate_field, counter in _RATE_FIELDS.items():
                total += (_safe_int(counters.get(counter)) / 1_000_000
                          * _safe_float(rates.get(rate_field)))
            return round(total, 6)
        if price is not None:
            return round(float(price(_safe_int(counters.get("input_tokens")),
                                     _safe_int(counters.get("output_tokens")))), 6)
    except Exception:
        return 0.0
    return 0.0


# ---- recording -------------------------------------------------------------

def _load_bucket(conn, key: str, feature: str, model: str, month: str) -> dict:
    row = conn.execute(
        "SELECT value FROM memory_layer WHERE key=?", (key,)
    ).fetchone()
    bucket = _empty_bucket(feature, model, month)
    if row is not None and row[0]:
        try:
            stored = json.loads(row[0])
        except (TypeError, ValueError):
            stored = None
        if isinstance(stored, dict):
            for k in (*_CALL_COUNTS, *_COUNTERS):
                bucket[k] = _safe_int(stored.get(k))
            for k in ("last_call_at", "last_unavailable_at", "last_usage"):
                bucket[k] = stored.get(k)
    return bucket


def record_usage(idx, feature: str, resp: dict, *,
                 default_model: str = "",
                 price: PriceFn | None = None,
                 rates: dict | None = None,
                 now: datetime | None = None) -> dict | None:
    """Accumulate one response into its feature/model/month bucket.

    A response with a usable ``usage`` block adds to ``calls`` and the four
    counters. A response *without* one (a dict with no ``usage``, a
    malformed block, all-zero counters) adds to ``unavailable_calls`` so
    the gap is visible in the meter instead of vanishing. Returns the
    updated bucket, or None when nothing could be recorded -- and then the
    reason is in :func:`meter_status`. Never raises."""
    feature = _safe_label(feature, "unknown")
    if not isinstance(resp, dict):
        return None  # not a response at all: nothing happened to meter
    try:
        if idx is None:
            raise RuntimeError("no index")
        parsed = parse_usage(resp, default_model=default_model)
        model = parsed["model"] if parsed else _model_of(resp, default_model)
        month = month_of(now)
        key = usage_key(feature, model, month)
        stamp = _now_iso(now)
        with idx.write_transaction() as conn:
            bucket = _load_bucket(conn, key, feature, model, month)
            if parsed is None:
                bucket["unavailable_calls"] += 1
                bucket["last_unavailable_at"] = stamp
            else:
                bucket["calls"] += 1
                for k in _COUNTERS:
                    bucket[k] += parsed[k]
                bucket["last_call_at"] = stamp
                bucket["last_usage"] = {k: parsed[k] for k in _COUNTERS}
            bucket["est_usd"] = estimate_usd(bucket, rates=rates, price=price)
            bucket["est_rates"] = rates_record(rates)
            conn.execute(
                "INSERT INTO memory_layer (key, value, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(bucket, ensure_ascii=False), stamp),
            )
        return bucket
    except Exception as exc:  # best-effort by contract, but never silent
        note_write_failure(feature, exc, now)
        log.warning("usage meter: could not record %s usage: %s",
                    feature, type(exc).__name__)
        return None


# ---- reading ---------------------------------------------------------------

def read_buckets(idx, *, month: str | None = None) -> list[dict]:
    """Every stored bucket (optionally one month), newest month first."""
    if idx is None:
        return []
    like = f"{KEY_PREFIX}%"
    with idx._lock:
        rows = idx._conn.execute(
            "SELECT key, value FROM memory_layer WHERE key LIKE ? "
            "ORDER BY key", (like,)
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            data = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if month and data.get("month") != month:
            continue
        data.setdefault("unavailable_calls", 0)  # rows written before case 3
        out.append(data)
    out.sort(key=lambda b: (str(b.get("month")), str(b.get("feature")),
                            str(b.get("model"))), reverse=True)
    return out


def month_summary(idx, *, month: str | None = None,
                  price: PriceFn | None = None,
                  rates: dict | None = None) -> dict:
    """The ``actual`` block for the pricing payload: per-feature totals for
    one month (default: the current UTC month), priced with ``rates`` (all
    four counters) or the legacy ``price`` callable (input/output only).

    ``unavailable_calls`` counts responses whose usage could not be read,
    per feature and in total; ``status`` carries meter write failures since
    helper start; ``estimate`` says what ``usd`` is."""
    month = month or month_of()
    by_feature: dict[str, dict] = {}
    total_usd = 0.0
    unavailable_total = 0
    for bucket in read_buckets(idx, month=month):
        feature = str(bucket.get("feature") or "unknown")
        agg = by_feature.setdefault(feature, {
            "calls": 0, "unavailable_calls": 0,
            "input_tokens": 0, "output_tokens": 0,
            "cache_read": 0, "cache_create": 0, "usd": 0.0, "models": [],
        })
        for k in (*_CALL_COUNTS, *_COUNTERS):
            agg[k] += _safe_int(bucket.get(k))
        model = str(bucket.get("model") or "unknown")
        if model not in agg["models"]:
            agg["models"].append(model)
    for agg in by_feature.values():
        agg["usd"] = estimate_usd(agg, rates=rates, price=price)
        total_usd += agg["usd"]
        unavailable_total += agg["unavailable_calls"]
    return {
        "month": month,
        "by_feature": by_feature,
        "total_usd": round(total_usd, 6),
        "unavailable_calls": unavailable_total,
        "estimate": True,
        "rates": rates_record(rates),
        "status": meter_status(),
    }
