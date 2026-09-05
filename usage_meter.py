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
- **Best-effort.** ``record_usage`` never raises. Metering must not fail a
  call that already succeeded, and a response without ``usage`` is a no-op.
- **No network, no model.** This is a counter.

Key:   ``usage.anthropic.<feature>.<model>.<YYYY-MM>``
Value: ``{"feature", "model", "month", "calls", "input_tokens",
"output_tokens", "cache_read", "cache_create", "est_usd", "last_call_at",
"last_usage"}``
"""
from __future__ import annotations

import json
import logging
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


def _safe_label(value, fallback: str) -> str:
    """Key components must not contain the '.' separator or whitespace."""
    text = str(value or "").strip()
    if not text:
        text = fallback
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in text)


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
    model = str(resp.get("model") or default_model or "unknown").strip()
    return {"model": model or "unknown", **counters}


def usage_key(feature: str, model: str, month: str) -> str:
    return (f"{KEY_PREFIX}{_safe_label(feature, 'unknown')}."
            f"{_safe_label(model, 'unknown')}.{month}")


def _empty_bucket(feature: str, model: str, month: str) -> dict:
    return {
        "feature": feature,
        "model": model,
        "month": month,
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_create": 0,
        "est_usd": 0.0,
        "last_call_at": None,
        "last_usage": None,
    }


def _price(price: PriceFn | None, input_tokens: int, output_tokens: int) -> float:
    if price is None:
        return 0.0
    try:
        return round(float(price(input_tokens, output_tokens)), 6)
    except Exception:  # pricing is decoration; never block the meter
        return 0.0


def record_usage(idx, feature: str, resp: dict, *,
                 default_model: str = "",
                 price: PriceFn | None = None,
                 now: datetime | None = None) -> dict | None:
    """Accumulate one response's ``usage`` into its feature/model/month
    bucket. Returns the updated bucket, or None when nothing was recorded.
    Never raises."""
    try:
        parsed = parse_usage(resp, default_model=default_model)
        if parsed is None or idx is None:
            return None
        feature = _safe_label(feature, "unknown")
        model = parsed["model"]
        month = month_of(now)
        key = usage_key(feature, model, month)
        stamp = _now_iso(now)
        with idx.write_transaction() as conn:
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
                    for k in ("calls", "input_tokens", "output_tokens",
                              "cache_read", "cache_create"):
                        bucket[k] = _safe_int(stored.get(k))
            bucket["calls"] += 1
            for k in ("input_tokens", "output_tokens", "cache_read",
                      "cache_create"):
                bucket[k] += parsed[k]
            bucket["est_usd"] = _price(
                price, bucket["input_tokens"], bucket["output_tokens"])
            bucket["last_call_at"] = stamp
            bucket["last_usage"] = {
                k: parsed[k] for k in ("input_tokens", "output_tokens",
                                       "cache_read", "cache_create")
            }
            conn.execute(
                "INSERT INTO memory_layer (key, value, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(bucket, ensure_ascii=False), stamp),
            )
        return bucket
    except Exception as exc:  # best-effort by contract
        log.warning("usage meter: could not record %s usage: %s",
                    feature, type(exc).__name__)
        return None


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
        out.append(data)
    out.sort(key=lambda b: (str(b.get("month")), str(b.get("feature")),
                            str(b.get("model"))), reverse=True)
    return out


def month_summary(idx, *, month: str | None = None,
                  price: PriceFn | None = None) -> dict:
    """The ``actual`` block for the pricing payload: per-feature totals for
    one month (default: the current UTC month), priced with ``price``."""
    month = month or month_of()
    by_feature: dict[str, dict] = {}
    total_usd = 0.0
    for bucket in read_buckets(idx, month=month):
        feature = str(bucket.get("feature") or "unknown")
        agg = by_feature.setdefault(feature, {
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read": 0, "cache_create": 0, "usd": 0.0, "models": [],
        })
        for k in ("calls", "input_tokens", "output_tokens", "cache_read",
                  "cache_create"):
            agg[k] += _safe_int(bucket.get(k))
        model = str(bucket.get("model") or "unknown")
        if model not in agg["models"]:
            agg["models"].append(model)
    for agg in by_feature.values():
        agg["usd"] = _price(price, agg["input_tokens"], agg["output_tokens"])
        total_usd += agg["usd"]
    return {
        "month": month,
        "by_feature": by_feature,
        "total_usd": round(total_usd, 6),
    }
