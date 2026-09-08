"""Phase 3 standing capture: source subscriptions, consent, detection, ledger.

Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md (``phase3-v1-2026-09-07``).
Brief: docs/library/PHASE3-IMPLEMENTATION-BRIEF-2026-09-07.md (run AM).
Adapter limits: docs/library/PHASE3-ADAPTER-LIMITS-2026-09-07.md (Grok).

This module owns every durable decision about standing capture:

* source identity and registration (contract, "Source identity and detection");
* consent receipts and user-intent capabilities (contract, "Consent and
  enrollment");
* the detection cursor, poll ownership and enrollment boundaries;
* the atomic start ledger (contract, "Atomic starts, failure, and restart");
* restart reconciliation and legacy registry import (contract, "Migration
  0028 schema");
* the post-commit classification outbox (contract, "Post-commit
  classification handoff").

It performs no model reasoning, never spawns a client, and never captures from
detection. Adapters return validated observations only. Capture is delegated
to an injected ``CaptureBackend`` that runs after, and only after, the ledger
has committed a ``started`` row. Transports (server.py, uoink_mcp_tools.py)
call ``SourceSubscriptionService`` with a trusted ``RequestContext``; no
client-supplied actor string, cap, adapter command, path or clock value is
ever trusted.

Every state transition and ledger operation cites its contract section in a
comment; keep that discipline when editing.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import json
import logging
import math
import re
import secrets
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

log = logging.getLogger("uoink.sources")

CONTRACT_VERSION = "phase3-v1-2026-09-07"
SCHEMA_VERSION = 1
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# ---- Product policy (contract, opening scope; decisions 4 and 5) ----------
BACK_CATALOG_CAP = 25            # lifetime initial cohort ceiling per source
DAILY_START_CAP = 10             # actual starts per source per UTC day
MAX_ACTUAL_STARTS = 3            # automatic attempts per source item
RESERVATION_TTL_MS = 120_000     # reserved -> released if not dispatched
POLL_LEASE_MS = 120_000          # poll ownership lease; adapter budgets fit it
INTENT_TTL_MS = 5 * 60 * 1000    # dashboard capability lifetime
DEFAULT_POLL_INTERVAL_MIN = 60
MIN_POLL_INTERVAL_MIN = 15
MAX_POLL_INTERVAL_MIN = 1440
MAX_BACKOFF_MIN = 1440
# Transient failure waits (contract, "Atomic starts"): after attempt one and
# after attempt two. The third failure blocks automatic retries.
RETRY_WAIT_MS = (15 * 60 * 1000, 60 * 60 * 1000)
PREFLIGHT_BLOCK_AFTER = 3
# Clock regression tolerance before a source reports clock_regressed.
CLOCK_REGRESSION_TOLERANCE_MS = 5_000
MAX_REQUEST_BYTES = 16 * 1024
MAX_JSON_DEPTH = 16
ERROR_MESSAGE_MAX = 512

# ---- Adapter budgets (Grok's note section 3.3; recorded in fixtures) ------
FEED_FETCH_TIMEOUT_SEC = 8.0
FEED_MAX_BYTES = 8 * 1024 * 1024         # bounded response bytes; over -> feed_too_large
FEED_USER_AGENT = "Uoink/3.1 (+https://uoink.video)"
FEED_MAX_REDIRECTS = 3
PODCAST_ENTRIES_PER_POLL = 50            # parser window; reported as truncation
PODCAST_ENTRY_ID_MAX = 2048
YOUTUBE_ATOM_HOST = "www.youtube.com"
YOUTUBE_ATOM_PATH = "/feeds/videos.xml"

KINDS = ("podcast_rss", "youtube_channel", "youtube_playlist")
ADAPTERS = {
    "podcast_rss": "podcast_rss_v1",
    "youtube_channel": "youtube_channel_rss_v1",
    # Frozen DDL label. Fable's reconciliation ruling 1 makes the playlist
    # detector the Atom ``?playlist_id=`` pull, not a yt-dlp flat listing; the
    # adapter name stays as the migration's CHECK constraint spells it.
    "youtube_playlist": "youtube_playlist_flat_v1",
}
ERROR_CODES = (
    "validation_error", "not_found", "unsupported_source", "source_archived",
    "user_intent_required", "invalid_user_intent", "stale_revision",
    "stale_cursor", "idempotency_conflict", "invalid_cursor", "storage_busy",
    "service_unavailable", "internal_error",
)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,200}$")
_SOURCE_ID_RE = re.compile(r"^src_[a-f0-9]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_YT_NS = "http://www.youtube.com/xml/schemas/2015"
_ATOM_NS = "http://www.w3.org/2005/Atom"


# ===========================================================================
# Errors and envelope
# ===========================================================================
class ServiceError(Exception):
    """Raised inside the service; the endpoint decorator converts it."""

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details

    def response(self) -> dict:
        return error_envelope(self.code, self.message,
                              retryable=self.retryable, details=self.details)


def fail(code: str, message: str, *, retryable: bool = False, **details: Any):
    raise ServiceError(code, message, retryable=retryable, **details)


def success(**values: Any) -> dict:
    return {"ok": True, "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION, **values}


def error_envelope(code: str, message: str, *, retryable: bool = False,
                   details: dict | None = None) -> dict:
    return {
        "ok": False, "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "error": {
            "code": code, "message": sanitize_message(message),
            "retryable": bool(retryable),
            "details": dict(details or {}),
        },
    }


def sanitize_message(text: Any) -> str:
    """Public error text: bounded, printable, no raw SQL/paths/stderr."""
    value = str(text or "")
    value = _CONTROL_RE.sub(" ", value)
    return value[:ERROR_MESSAGE_MAX]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# Strict JSON decoding and schema validation (contract, "Registry and
# dashboard contract": duplicate keys, malformed Unicode, non-finite numbers,
# boolean-as-integer, unknown fields, 16 KiB, nesting 16)
# ===========================================================================
def _reject_pairs(pairs):
    out: dict = {}
    for key, value in pairs:
        if key in out:
            fail("validation_error", "Duplicate JSON key", field=key)
        out[key] = value
    return out


def decode_json(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_REQUEST_BYTES:
            fail("validation_error", "Request body exceeds 16 KiB")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            fail("validation_error", "Malformed Unicode")
    elif len(raw.encode("utf-8", errors="surrogatepass")) > MAX_REQUEST_BYTES:
        fail("validation_error", "Request body exceeds 16 KiB")
    try:
        return json.loads(
            raw, object_pairs_hook=_reject_pairs,
            parse_constant=lambda _n: fail("validation_error", "Non-finite number"))
    except ServiceError:
        raise
    except (ValueError, TypeError, RecursionError):
        fail("validation_error", "Invalid JSON")


def check_json_value(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        fail("validation_error", "JSON nesting exceeds 16 levels")
    if value is None or type(value) in (str, bool, int):
        if type(value) is int and not -(2 ** 63) <= value < 2 ** 63:
            fail("validation_error", "Integer outside supported range")
        if type(value) is str:
            try:
                value.encode("utf-8")
            except UnicodeError:
                fail("validation_error", "Malformed Unicode")
        return
    if type(value) is float:
        if not math.isfinite(value):
            fail("validation_error", "Non-finite number")
        return
    if type(value) is list:
        for child in value:
            check_json_value(child, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for key, child in value.items():
            check_json_value(key, depth + 1)
            check_json_value(child, depth + 1)
        return
    fail("validation_error", "Expected JSON values")


def _schema_check(value: Any, schema: dict, path: str) -> None:
    if "oneOf" in schema:
        matched = 0
        for branch in schema["oneOf"]:
            try:
                _schema_check(value, branch, path)
                matched += 1
            except ServiceError:
                pass
        if matched != 1:
            fail("validation_error", "Value must match exactly one allowed shape", field=path)
    if "not" in schema:
        rejected = False
        try:
            _schema_check(value, schema["not"], path)
            rejected = True
        except ServiceError:
            pass
        if rejected:
            fail("validation_error", "Value matches a forbidden shape", field=path)
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if kind in types and type(value) is not types[kind]:
        fail("validation_error", f"Expected {kind}", field=path)
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        fail("validation_error", "Unexpected constant", field=path)
    if "enum" in schema:
        if not any(type(value) is type(option) and value == option for option in schema["enum"]):
            fail("validation_error", "Unexpected choice", field=path)
    if type(value) is dict:
        # Object keywords apply whether or not the branch spells "type" (the
        # consent schema's oneOf/not branches do not).
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            fail("validation_error", "Missing required fields", field=path,
                 missing=sorted(missing))
        if schema.get("additionalProperties") is False and value.keys() - props.keys():
            fail("validation_error", "Unknown fields", field=path,
                 unknown=sorted(value.keys() - props.keys()))
        for key, child in value.items():
            if key in props:
                _schema_check(child, props[key], f"{path}.{key}" if path else key)
    if kind == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2 ** 31):
            fail("validation_error", "Invalid length", field=path)
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            fail("validation_error", "Invalid format", field=path)
    if kind == "integer":
        if not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            fail("validation_error", "Number out of range", field=path)


def validate_arguments(tool: str, args: Any) -> dict:
    """Strict validation of ``args`` against the frozen tool schema."""
    if type(args) is not dict:
        fail("validation_error", "Arguments must be an object")
    check_json_value(args)
    if len(canonical_json(args).encode("utf-8")) > MAX_REQUEST_BYTES:
        fail("validation_error", "Request exceeds 16 KiB")
    _schema_check(args, TOOL_SCHEMAS[tool], "")
    return copy.deepcopy(args)


# ===========================================================================
# Frozen registry schemas (contract, "Registry and dashboard contract")
# ===========================================================================
def _tool_schema(body: dict) -> dict:
    return {"$schema": JSON_SCHEMA_DIALECT, **body}


TOOL_SCHEMAS: dict[str, dict] = {
    "list_sources": _tool_schema({
        "type": "object",
        "properties": {
            "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
            "consent_state": {"enum": ["off", "on"]},
            "include_archived": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            "cursor": {"type": "string", "minLength": 1, "maxLength": 512},
        },
        "additionalProperties": False,
    }),
    "register_source": _tool_schema({
        "type": "object",
        "properties": {
            "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
            "url": {"type": "string", "minLength": 1, "maxLength": 2048},
            "display_name": {"type": "string", "minLength": 1, "maxLength": 200},
            "poll_interval_min": {"type": "integer", "minimum": 15, "maximum": 1440, "default": 60},
        },
        "required": ["kind", "url"],
        "additionalProperties": False,
    }),
    "source_status": _tool_schema({
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
            "item_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            "item_cursor": {"type": "string", "minLength": 1, "maxLength": 512},
        },
        "required": ["source_id"],
        "additionalProperties": False,
    }),
    "set_source_consent": _tool_schema({
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
            "consent_state": {"enum": ["off", "on"]},
            "expected_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "expected_cursor_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "operation_key": {"type": "string", "minLength": 1, "maxLength": 200, "pattern": "^[A-Za-z0-9_-]+$"},
            "user_intent_token": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43,128}$"},
        },
        "required": ["source_id", "consent_state", "expected_revision", "operation_key", "user_intent_token"],
        "oneOf": [
            {"properties": {"consent_state": {"const": "on"}}, "required": ["expected_cursor_revision"]},
            {"properties": {"consent_state": {"const": "off"}}, "not": {"required": ["expected_cursor_revision"]}},
        ],
        "additionalProperties": False,
    }),
}
TOOL_NAMES = tuple(TOOL_SCHEMAS)


def consent_intent_operation_schema() -> dict:
    """set_source_consent minus the token the dashboard route is about to mint."""
    source = TOOL_SCHEMAS["set_source_consent"]
    return _tool_schema({
        "type": "object",
        "properties": {k: v for k, v in source["properties"].items() if k != "user_intent_token"},
        "required": [k for k in source["required"] if k != "user_intent_token"],
        "oneOf": source["oneOf"],
        "additionalProperties": False,
    })


def tool_manifest() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "json_schema_dialect": JSON_SCHEMA_DIALECT,
        "tools": [{"name": name, "inputSchema": copy.deepcopy(schema)}
                  for name, schema in TOOL_SCHEMAS.items()],
    }


# ===========================================================================
# Identity (contract, "Source identity and detection")
# ===========================================================================
def source_identity(kind: str, source_key: str) -> str:
    return "src_" + sha256_text(f"{kind}\n{source_key}")


def item_identity(source_id: str, entry_id: str) -> str:
    return "si_" + sha256_text(f"{source_id}\n{entry_id}")


def capture_key_for(kind: str, source_key: str, entry_id: str) -> str:
    if kind in ("youtube_channel", "youtube_playlist"):
        return f"youtube:{entry_id}"
    return "podcast:" + sha256_text(f"{source_key}\n{entry_id}")


def podcast_corpus_id(feed_url: str, entry_id: str) -> str:
    """Preserve the existing ``episode_<suffix>`` corpus identity."""
    identity = f"{feed_url}\n{entry_id}"
    return "episode_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:11]


def classification_run_id(capture_key: str) -> str:
    return "ss_" + sha256_text(capture_key)


def utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def next_utc_midnight_ms(ms: int) -> int:
    day = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int((day + timedelta(days=1)).timestamp() * 1000)


def parse_published_ms(raw: Any) -> int | None:
    """RFC 2822 or ISO 8601 -> UTC ms; None when missing or invalid."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    parsed = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError, IndexError):
            parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return int(parsed.timestamp() * 1000)
    except (OverflowError, OSError, ValueError):
        return None


def _new_token() -> str:
    # 43 URL-safe characters: satisfies the ledger's length(owner_token)>=43.
    return secrets.token_urlsafe(32)


# ===========================================================================
# URL validation (contract, "Scheduler and adapter boundaries")
# ===========================================================================
def _reject_private_ip(host: str) -> None:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if (address.is_loopback or address.is_link_local or address.is_private
            or address.is_multicast or address.is_reserved or address.is_unspecified):
        fail("unsupported_source", "Loopback, link-local and private targets are refused")


def _split_query(query: str) -> list[tuple[str, str]]:
    return urllib.parse.parse_qsl(query, keep_blank_values=True)


def _single_param(pairs: list[tuple[str, str]], name: str) -> str | None:
    values = [v for k, v in pairs if k == name]
    if len(values) > 1:
        fail("validation_error", f"Repeated {name} parameter", field="url")
    return values[0] if values else None


def _parse_http_url(raw: str) -> urllib.parse.ParseResult:
    if type(raw) is not str or not raw.strip():
        fail("validation_error", "url is required", field="url")
    if _CONTROL_RE.search(raw):
        fail("validation_error", "url contains control characters", field="url")
    text = raw.strip()
    if "://" not in text:
        fail("unsupported_source", "Only absolute http(s) URLs are accepted")
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        fail("unsupported_source", "Malformed URL")
    if parsed.scheme.lower() not in ("http", "https"):
        fail("unsupported_source", "Only http(s) sources are supported")
    if parsed.username is not None or parsed.password is not None:
        fail("unsupported_source", "Credentials in URLs are refused")
    if parsed.fragment:
        fail("unsupported_source", "URL fragments are refused")
    host = parsed.hostname or ""
    if not host or len(host) > 253:
        fail("unsupported_source", "URL host is required")
    try:
        parsed.port
    except ValueError:
        fail("unsupported_source", "Malformed URL port")
    _reject_private_ip(host)
    if host.lower() in ("localhost",) or host.lower().endswith(".localhost"):
        fail("unsupported_source", "Loopback targets are refused")
    return parsed


def normalize_podcast_feed_url(raw: str) -> str:
    parsed = _parse_http_url(raw)
    host = parsed.hostname.lower()
    netloc = f"[{host}]" if ":" in host else host
    port = parsed.port
    if port is not None and not ((parsed.scheme == "http" and port == 80)
                                 or (parsed.scheme == "https" and port == 443)):
        netloc += f":{port}"
    path = parsed.path or "/"
    return f"{parsed.scheme.lower()}://{netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")


def parse_source_url(kind: str, raw: str) -> tuple[str, str]:
    """Return ``(source_key, canonical_url)`` or raise a ServiceError.

    podcast_rss: normalized feed URL. youtube_channel: canonical ``/channel/UC…``
    URL or the Atom feed URL carrying ``channel_id``; handles, ``/user/`` and
    ``/c/`` are rejected (adapter limits section 3.1). youtube_playlist: a
    ``list=`` playlist or the Atom feed URL carrying ``playlist_id``;
    Watch Later, Liked and mix ids are rejected (adapter limits section 4.2).
    """
    if kind == "podcast_rss":
        key = normalize_podcast_feed_url(raw)
        return key, key
    parsed = _parse_http_url(raw)
    host = parsed.hostname.lower()
    if host not in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        fail("unsupported_source", "Only youtube.com sources are supported for this kind")
    pairs = _split_query(parsed.query)
    path = parsed.path.rstrip("/")
    if kind == "youtube_channel":
        channel_id = None
        if path == YOUTUBE_ATOM_PATH:
            channel_id = _single_param(pairs, "channel_id")
            if _single_param(pairs, "playlist_id") is not None:
                fail("unsupported_source", "Ambiguous feed URL")
        elif path.startswith("/channel/"):
            channel_id = path.split("/", 3)[2] if path.count("/") >= 2 else None
        elif path.startswith("/@") or path.startswith("/user/") or path.startswith("/c/"):
            fail("unsupported_source",
                 "Channel handles are not accepted; use the UC… channel id URL")
        if not channel_id or not _CHANNEL_ID_RE.match(channel_id):
            fail("unsupported_source", "A UC… channel id is required")
        return channel_id, f"https://www.youtube.com/channel/{channel_id}"
    if kind == "youtube_playlist":
        playlist_id = None
        if path == YOUTUBE_ATOM_PATH:
            playlist_id = _single_param(pairs, "playlist_id")
            if _single_param(pairs, "channel_id") is not None:
                fail("unsupported_source", "Ambiguous feed URL")
        elif path in ("/playlist", "/watch"):
            playlist_id = _single_param(pairs, "list")
        if not playlist_id or not _PLAYLIST_ID_RE.match(playlist_id):
            fail("unsupported_source", "A playlist id is required")
        if playlist_id in ("WL", "LL") or playlist_id.startswith("RD"):
            fail("unsupported_source", "Watch Later, Liked and mix playlists are not public sources")
        return playlist_id, f"https://www.youtube.com/playlist?list={playlist_id}"
    fail("validation_error", "Unsupported kind", field="kind")


def youtube_feed_url(kind: str, source_key: str) -> str:
    param = "channel_id" if kind == "youtube_channel" else "playlist_id"
    return f"https://{YOUTUBE_ATOM_HOST}{YOUTUBE_ATOM_PATH}?{param}={urllib.parse.quote(source_key, safe='')}"


def video_watch_url(video_id: str) -> str:
    if not _VIDEO_ID_RE.match(video_id or ""):
        raise ValueError("invalid video id")
    return f"https://www.youtube.com/watch?v={video_id}"


def validate_entry_id(entry_id: Any) -> str | None:
    """Podcast entry ids are opaque 1-2048 char strings without control chars."""
    if not isinstance(entry_id, str):
        return None
    text = entry_id.strip()
    if not text or len(text) > PODCAST_ENTRY_ID_MAX or _CONTROL_RE.search(text):
        return None
    try:
        text.encode("utf-8")
    except UnicodeError:
        return None
    return text


# ===========================================================================
# Adapters (contract, "Scheduler and adapter boundaries")
# ===========================================================================
@dataclass
class Observation:
    entry_id: str
    title: str | None = None
    canonical_url: str | None = None
    published_at_ms: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AdapterResult:
    """What an adapter returns. ``status`` is ``snapshot``, ``not_modified`` or
    ``error``. ``coverage`` describes the returned enumeration only."""
    status: str
    observations: list[Observation] = field(default_factory=list)
    coverage: str = "unknown"
    truncated: bool = False
    etag: str | None = None
    last_modified: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_after_ms: int | None = None
    rejected: int = 0
    conflicts: int = 0


@dataclass
class FetchResponse:
    status: int
    headers: dict
    body: bytes


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect target: http(s) only, no private addresses."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _parse_http_url(newurl)
        _check_resolved_host(urllib.parse.urlparse(newurl).hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _check_resolved_host(host: str) -> None:
    """Resolve and reject loopback/link-local/private addresses (production)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ServiceError("feed_unreachable", f"DNS resolution failed: {exc.errno}")
    for info in infos:
        address = info[4][0]
        _reject_private_ip(address)


def default_http_fetch(url: str, headers: dict, *, timeout: float = FEED_FETCH_TIMEOUT_SEC,
                       max_bytes: int = FEED_MAX_BYTES) -> FetchResponse:
    """Bounded conditional GET. Never called by tests; inject a fake fetcher."""
    parsed = _parse_http_url(url)
    _check_resolved_host(parsed.hostname or "")
    opener = urllib.request.build_opener(_BoundedRedirectHandler())
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ServiceError("feed_too_large", "Feed body exceeds the bounded byte budget")
            return FetchResponse(resp.status, dict(resp.headers.items()), body)
    except urllib.error.HTTPError as exc:
        return FetchResponse(exc.code, dict(exc.headers.items()) if exc.headers else {}, b"")


def _retry_after_ms(headers: dict) -> int | None:
    value = None
    for key, item in headers.items():
        if key.lower() == "retry-after":
            value = item
    if not value:
        return None
    try:
        seconds = int(value.strip())
        return max(0, seconds) * 1000 if seconds <= 7 * 24 * 3600 else None
    except ValueError:
        stamp = parse_published_ms(value)
        return None if stamp is None else max(0, stamp - int(time.time() * 1000))


def _conditional_headers(cursor: dict | None, conditional: bool) -> dict:
    headers = {"User-Agent": FEED_USER_AGENT,
               "Accept": "application/atom+xml,application/rss+xml,"
                         "application/xml,text/xml;q=0.9,*/*;q=0.5"}
    if conditional and cursor:
        if cursor.get("etag"):
            headers["If-None-Match"] = cursor["etag"]
        if cursor.get("last_modified"):
            headers["If-Modified-Since"] = cursor["last_modified"]
    return headers


def _header(headers: dict, name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _child_text(parent, *names) -> str | None:
    for child in parent:
        if _localname(child.tag) in names:
            text = (child.text or "").strip()
            return text or None
    return None


def _child_attr(parent, name: str, attr: str) -> str | None:
    for child in parent:
        if _localname(child.tag) == name:
            value = child.attrib.get(attr)
            if value:
                return value.strip()
    return None


def _http_link(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urllib.parse.urlparse(value.strip())
    except ValueError:
        return None
    if parsed.scheme in ("http", "https") and parsed.netloc and not _CONTROL_RE.search(value):
        return value.strip()[:2048]
    return None


class HttpFeedAdapter:
    """Shared fetch/parse skeleton for the three Atom/RSS detectors."""

    def __init__(self, fetch: Callable[..., FetchResponse] | None = None):
        self.fetch = fetch or default_http_fetch

    def feed_url(self, source: dict) -> str:
        raise NotImplementedError

    def parse(self, body: bytes, source: dict) -> AdapterResult:
        raise NotImplementedError

    def poll(self, source: dict, cursor: dict | None, *, conditional: bool) -> AdapterResult:
        headers = _conditional_headers(cursor, conditional)
        try:
            response = self.fetch(self.feed_url(source), headers)
        except ServiceError as exc:
            return AdapterResult("error", error_code=exc.code, error_message=exc.message)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            code = "poll_timeout" if isinstance(exc, (socket.timeout, TimeoutError)) else "feed_unreachable"
            return AdapterResult("error", error_code=code, error_message=type(exc).__name__)
        except Exception as exc:  # adapter bug or unexpected transport failure
            return AdapterResult("error", error_code="feed_unreachable", error_message=type(exc).__name__)
        retry_after = _retry_after_ms(response.headers or {})
        if response.status == 304:
            return AdapterResult("not_modified", etag=_header(response.headers, "ETag"),
                                 last_modified=_header(response.headers, "Last-Modified"))
        if response.status != 200:
            code = "rate_limited" if response.status == 429 else f"http_{int(response.status)}"
            return AdapterResult("error", error_code=code, error_message=f"HTTP {int(response.status)}",
                                 retry_after_ms=retry_after)
        if len(response.body or b"") > FEED_MAX_BYTES:
            return AdapterResult("error", error_code="feed_too_large",
                                 error_message="Feed body exceeds the bounded byte budget")
        try:
            result = self.parse(response.body, source)
        except (ET.ParseError, ValueError) as exc:
            return AdapterResult("error", error_code="malformed_feed", error_message=type(exc).__name__)
        result.etag = _header(response.headers, "ETag")
        result.last_modified = _header(response.headers, "Last-Modified")
        return result


class YouTubeAtomAdapter(HttpFeedAdapter):
    """Atom ``feeds/videos.xml`` pull; identity is the bare video id."""

    def feed_url(self, source: dict) -> str:
        return youtube_feed_url(source["kind"], source["source_key"])

    def parse(self, body: bytes, source: dict) -> AdapterResult:
        root = ET.fromstring(body)
        if _localname(root.tag) != "feed":
            raise ValueError("not an Atom feed")
        result = AdapterResult("snapshot", coverage="window", truncated=False)
        seen: dict[str, Observation] = {}
        for entry in root:
            if _localname(entry.tag) != "entry":
                continue
            video_id = entry.findtext(f"{{{_YT_NS}}}videoId")
            if not video_id:
                raw_id = _child_text(entry, "id") or ""
                video_id = raw_id[len("yt:video:"):] if raw_id.startswith("yt:video:") else None
            video_id = (video_id or "").strip()
            if not _VIDEO_ID_RE.match(video_id):
                result.rejected += 1
                continue
            observation = Observation(
                entry_id=video_id,
                title=(_child_text(entry, "title") or None),
                canonical_url=video_watch_url(video_id),
                published_at_ms=parse_published_ms(_child_text(entry, "published", "updated")),
                metadata={"identity_method": "yt:videoId",
                          "channel_id": entry.findtext(f"{{{_YT_NS}}}channelId")},
            )
            if video_id in seen:
                if seen[video_id].title != observation.title:
                    result.conflicts += 1
                continue
            seen[video_id] = observation
            result.observations.append(observation)
        return result


class PodcastRssAdapter(HttpFeedAdapter):
    """RSS 2.0 / Atom 1.0 podcast feed; identity is guid, item link, or Atom id."""

    def feed_url(self, source: dict) -> str:
        return source["source_key"]

    def parse(self, body: bytes, source: dict) -> AdapterResult:
        root = ET.fromstring(body)
        root_name = _localname(root.tag)
        entries: list[tuple[str | None, str, dict]] = []
        if root_name == "rss":
            channels = [c for c in root if _localname(c.tag) == "channel"]
            channel = channels[0] if channels else None
            for item in (channel if channel is not None else []):
                if _localname(item.tag) != "item":
                    continue
                link = _child_text(item, "link")
                guid = _child_text(item, "guid")
                method = "guid" if guid else ("link" if link else None)
                entries.append((guid or link, method or "missing", {
                    "title": _child_text(item, "title"),
                    "page": link, "audio": _child_attr(item, "enclosure", "url"),
                    "published": _child_text(item, "pubDate", "published"),
                    "duration": _child_text(item, "duration"),
                }))
        elif root_name == "feed":
            for entry in root:
                if _localname(entry.tag) != "entry":
                    continue
                page = None
                audio = None
                for child in entry:
                    if _localname(child.tag) == "link":
                        rel = child.attrib.get("rel") or "alternate"
                        if rel == "enclosure":
                            audio = child.attrib.get("href")
                        elif rel == "alternate" and not page:
                            page = child.attrib.get("href")
                entry_id = _child_text(entry, "id")
                entries.append((entry_id, "atom_id" if entry_id else "missing", {
                    "title": _child_text(entry, "title"), "page": page, "audio": audio,
                    "published": _child_text(entry, "published", "updated"),
                    "duration": None,
                }))
        else:
            raise ValueError(f"unrecognised feed root element: {root_name!r}")
        truncated = len(entries) > PODCAST_ENTRIES_PER_POLL
        result = AdapterResult("snapshot", coverage="window" if truncated else "complete",
                               truncated=truncated)
        seen: dict[str, Observation] = {}
        for raw_id, method, meta in entries[:PODCAST_ENTRIES_PER_POLL]:
            entry_id = validate_entry_id(raw_id)
            if entry_id is None:
                result.rejected += 1
                continue
            observation = Observation(
                entry_id=entry_id, title=meta["title"],
                canonical_url=_http_link(meta["page"]) or _http_link(entry_id),
                published_at_ms=parse_published_ms(meta["published"]),
                metadata={"identity_method": method, "audio_url": _http_link(meta["audio"]),
                          "published_raw": meta["published"], "duration_raw": meta["duration"]},
            )
            if entry_id in seen:
                if seen[entry_id].title != observation.title or \
                        seen[entry_id].metadata.get("audio_url") != observation.metadata.get("audio_url"):
                    result.conflicts += 1
                continue
            seen[entry_id] = observation
            result.observations.append(observation)
        return result


def default_adapters(fetch: Callable[..., FetchResponse] | None = None) -> dict:
    return {
        "podcast_rss_v1": PodcastRssAdapter(fetch),
        "youtube_channel_rss_v1": YouTubeAtomAdapter(fetch),
        "youtube_playlist_flat_v1": YouTubeAtomAdapter(fetch),
    }


# ===========================================================================
# Capture backend protocol (contract, "Atomic starts": the reservation is the
# durable dispatch intent; backend identity binds atomically with the start)
# ===========================================================================
@dataclass
class CaptureOutcome:
    """``status``: succeeded | failed | uncertain | in_flight | preflight_failed."""
    status: str
    video_id: str | None = None
    code: str | None = None
    message: str | None = None
    terminal: bool = False


class CaptureBackend:
    """Base class for the injected capture executor.

    ``bind`` runs inside the ``started`` write transaction and must persist any
    queue row on the same connection; it returns the backend identity. ``run``
    executes outside the transaction and returns the outcome (``in_flight`` for
    asynchronous pipelines that will call ``complete_capture``/``fail_capture``
    with the owner token). ``probe`` answers restart reconciliation: ``running``,
    ``stopped`` or ``unknown``. ``published_video_id`` reports an already
    committed corpus identity for an item (linking without a charge).
    """
    kind = "inline"

    def preflight(self, item: dict, source: dict) -> CaptureOutcome | None:
        return None

    def bind(self, conn, start: dict, item: dict, source: dict) -> str:
        return start["start_id"]

    def run(self, start: dict, item: dict, source: dict) -> CaptureOutcome:
        return CaptureOutcome("failed", code="no_backend", terminal=True)

    def probe(self, start: dict) -> str:
        return "unknown"

    def published_video_id(self, conn, item: dict, source: dict) -> str | None:
        return None


@dataclass(frozen=True)
class RequestContext:
    authenticated: bool = False
    session_id: str | None = None
    operator: bool = False
    local_user_confirmed: bool = False
    transport: str = "registry"


def endpoint(fn):
    def call(self, context, args=None):
        try:
            if context is None or getattr(context, "authenticated", False) is not True:
                fail("validation_error", "Authenticated request context required")
            if args is None:
                args = {}
            if isinstance(args, (str, bytes)):
                args = decode_json(args)
            check_json_value(args)
            if type(args) is not dict:
                fail("validation_error", "Arguments must be an object")
            return fn(self, context, copy.deepcopy(args))
        except ServiceError as exc:
            return exc.response()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                return error_envelope("storage_busy", "Storage is busy; retry", retryable=True)
            log.exception("source service storage failure in %s", fn.__name__)
            return error_envelope("internal_error", "Storage error", retryable=True)
        except (sqlite3.Error, OSError):
            log.exception("source service failure in %s", fn.__name__)
            return error_envelope("internal_error", "Storage error", retryable=True)
    call.__name__ = fn.__name__
    call.__doc__ = fn.__doc__
    return call


# ===========================================================================
# Storage boundary
# ===========================================================================
class _Store:
    """One connection, one lock, BEGIN IMMEDIATE write units.

    Bound to an ``index.Index`` it reuses that connection and re-entrant lock
    and delegates writes to ``Index.write_transaction`` so helper threads keep
    a single write boundary. Opened standalone (two-connection tests, a second
    scheduler process) it owns a connection with a bounded busy timeout.
    """

    def __init__(self, conn: sqlite3.Connection, lock, index=None):
        self.conn = conn
        self.lock = lock
        self.index = index

    @classmethod
    def open(cls, path, *, busy_timeout_ms: int = 5000) -> "_Store":
        conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None,
                               timeout=busy_timeout_ms / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        return cls(conn, threading.RLock())

    @contextmanager
    def write(self):
        if self.index is not None:
            with self.index.write_transaction() as conn:
                yield conn
            return
        with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                raise ServiceError("storage_busy", "Storage is busy; retry", retryable=True) from exc
            try:
                yield self.conn
                self.conn.execute("COMMIT")
            except BaseException:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise

    @contextmanager
    def read(self):
        """A consistent read snapshot (deferred transaction)."""
        with self.lock:
            if self.conn.in_transaction:
                yield self.conn
                return
            self.conn.execute("BEGIN")
            try:
                yield self.conn
            finally:
                if self.conn.in_transaction:
                    self.conn.execute("COMMIT")

    def close(self) -> None:
        if self.index is None:
            self.conn.close()


ITEM_STATES = ("observed", "eligible", "reserved", "started", "uncertain",
               "committed", "failed", "deleted")
ACTIVE_START_STATES = ("reserved", "started", "uncertain")


def _row(row) -> dict | None:
    return dict(row) if row is not None else None


def _encode_cursor(payload: dict) -> str:
    raw = canonical_json(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(text: str, binding: dict) -> dict:
    """Keyset cursors are bound to their filters and source; foreign or
    malformed cursors are ``invalid_cursor`` (contract, registry section)."""
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError, TypeError):
        fail("invalid_cursor", "Malformed pagination cursor")
    if type(payload) is not dict or payload.get("v") != 1 or payload.get("bind") != binding \
            or "key" not in payload:
        fail("invalid_cursor", "Cursor does not belong to this query")
    return payload


def _safe_text(value: Any, limit: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _CONTROL_RE.sub(" ", value).strip()
    return cleaned[:limit] or None


def _published_sort_key(row: dict) -> tuple:
    published = row.get("published_at_ms")
    # Valid dates first (descending), then first-seen descending, then entry id.
    return (0 if published is not None else 1, -(published or 0),
            -(row.get("first_seen_ms") or 0), row.get("entry_id") or "")


# ===========================================================================
# The service
# ===========================================================================
class SourceSubscriptionService:
    """One service behind HTTP, MCP, the dashboard and the scheduler.

    ``index``: an ``index.Index`` (shares its connection/lock). ``path``: open a
    standalone connection instead (two-connection tests, a second scheduler).
    ``clock`` returns UTC Unix milliseconds. ``adapters`` maps adapter names to
    objects with ``poll(source, cursor, conditional=)``. ``backend`` is the
    ``CaptureBackend`` that executes a started capture. ``jitter`` returns a
    nonnegative delay in ms added to due times (never negative).
    """

    def __init__(self, index=None, *, path=None, clock: Callable[[], int] | None = None,
                 adapters: dict | None = None, backend: CaptureBackend | None = None,
                 instance_id: str | None = None, jitter: Callable[[], int] | None = None,
                 busy_timeout_ms: int = 5000):
        if index is not None:
            self.store = _Store(index._conn, index._lock, index=index)
        elif path is not None:
            self.store = _Store.open(path, busy_timeout_ms=busy_timeout_ms)
        else:
            raise ValueError("index or path is required")
        self.index = index
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.adapters = adapters if adapters is not None else default_adapters()
        self.backend = backend or CaptureBackend()
        self.instance_id = instance_id or f"{socket.gethostname()}:{secrets.token_hex(4)}"
        self.jitter = jitter or (lambda: 0)

    # ---- small helpers ---------------------------------------------------
    def _now(self) -> int:
        return int(self.clock())

    def _jitter(self) -> int:
        try:
            return max(0, int(self.jitter()))
        except Exception:
            return 0

    def close(self) -> None:
        self.store.close()

    @staticmethod
    def _source(conn, source_id: str) -> dict:
        row = conn.execute("SELECT * FROM source_subscriptions WHERE source_id=?",
                           (source_id,)).fetchone()
        if row is None:
            fail("not_found", "Unknown source", source_id=source_id)
        return dict(row)

    @staticmethod
    def _cursor(conn, source_id: str) -> dict:
        row = conn.execute("SELECT * FROM source_detection_cursors WHERE source_id=?",
                           (source_id,)).fetchone()
        if row is None:
            fail("internal_error", "Source has no detection cursor", source_id=source_id)
        return dict(row)

    @staticmethod
    def _item(conn, item_id: str) -> dict | None:
        return _row(conn.execute("SELECT * FROM source_items WHERE item_id=?", (item_id,)).fetchone())

    @staticmethod
    def _start(conn, start_id: str) -> dict | None:
        return _row(conn.execute("SELECT * FROM source_capture_starts WHERE start_id=?",
                                 (start_id,)).fetchone())

    @staticmethod
    def _clock_regressed(source: dict, now: int) -> bool:
        # Contract "Atomic starts": clock rollback must not move due times
        # backwards or reuse a newer observed day.
        return now + CLOCK_REGRESSION_TOLERANCE_MS < int(source.get("last_observed_ms") or 0)

    @staticmethod
    def _touch_observed(conn, source: dict, now: int) -> None:
        if now > int(source.get("last_observed_ms") or 0):
            conn.execute("UPDATE source_subscriptions SET last_observed_ms=? WHERE source_id=?",
                         (now, source["source_id"]))
            source["last_observed_ms"] = now

    @staticmethod
    def _in_flight(conn, source_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT start_id, item_id, state, utc_day, slot, started_at_ms, reserved_at_ms, "
            "reservation_expires_ms, video_id FROM source_capture_starts "
            "WHERE source_id=? AND state IN ('reserved','started','uncertain') "
            "ORDER BY reserved_at_ms", (source_id,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _session_hash(context) -> str | None:
        session = getattr(context, "session_id", None)
        return digest(session) if isinstance(session, str) and session else None

    def _corpus_video_id(self, source: dict, entry_id: str) -> str:
        if source["kind"] == "podcast_rss":
            return podcast_corpus_id(source["source_key"], entry_id)
        return entry_id

    @staticmethod
    def _corpus_row(conn, video_id: str) -> dict | None:
        try:
            row = conn.execute("SELECT video_id, deleted_at FROM yoinks WHERE video_id=?",
                               (video_id,)).fetchone()
        except sqlite3.OperationalError:
            return None  # bare fixture without the corpus table
        return _row(row)

    # ======================================================================
    # Registration (contract, "Source identity and detection"; registry)
    # ======================================================================
    @endpoint
    def register_source(self, context, args):
        args = validate_arguments("register_source", args)
        source_key, canonical_url = parse_source_url(args["kind"], args["url"])
        display_name = _safe_text(args.get("display_name"), 200)
        interval = int(args.get("poll_interval_min", DEFAULT_POLL_INTERVAL_MIN))
        source_id = source_identity(args["kind"], source_key)
        now = self._now()
        with self.store.write() as conn:
            existing = _row(conn.execute(
                "SELECT * FROM source_subscriptions WHERE kind=? AND source_key=?",
                (args["kind"], source_key)).fetchone())
            if existing is not None:
                receipt = None
                if existing["archived"]:
                    # Contract: re-registration unarchives with capture off and a receipt;
                    # it preserves history and caps and cannot replenish anything.
                    receipt = self._unarchive(conn, existing, now)
                    existing = self._source(conn, existing["source_id"])
                summary = self._summary(conn, existing, now)
                return success(created=False, source=summary, receipt=receipt)
            legacy_feed_id = None
            if args["kind"] == "podcast_rss":
                # Compatibility projection: the existing download/transcribe/publish
                # pipeline keys on podcast_feeds/podcast_episodes rows. The row is
                # created with auto_ingest=0; consent lives only in this service.
                legacy_feed_id = self._legacy_feed_projection(conn, source_key, interval)
            self._insert_source(conn, source_id=source_id, kind=args["kind"], source_key=source_key,
                                canonical_url=canonical_url, display_name=display_name,
                                interval=interval, now=now, detection_enabled=True,
                                legacy_feed_id=legacy_feed_id)
            source = self._source(conn, source_id)
            return success(created=True, source=self._summary(conn, source, now))

    @staticmethod
    def _legacy_feed_projection(conn, feed_url: str, interval: int) -> int | None:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO podcast_feeds (feed_url, poll_interval_min, auto_ingest, "
                "enabled, added_at) VALUES (?, ?, 0, 1, ?)",
                (feed_url, max(MIN_POLL_INTERVAL_MIN, min(int(interval), MAX_POLL_INTERVAL_MIN)),
                 datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")))
            row = conn.execute("SELECT id FROM podcast_feeds WHERE feed_url=?", (feed_url,)).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        taken = conn.execute("SELECT 1 FROM source_subscriptions WHERE legacy_feed_id=?",
                             (int(row[0]),)).fetchone()
        return None if taken else int(row[0])

    @staticmethod
    def _insert_source(conn, *, source_id, kind, source_key, canonical_url, display_name,
                       interval, now, detection_enabled=True, legacy_feed_id=None,
                       legacy_playlist_id=None, etag=None, last_modified=None,
                       hold_until_ms=0) -> None:
        # Contract, registry: creates only the off row and its due cursor.
        conn.execute(
            "INSERT INTO source_subscriptions (source_id, kind, source_key, canonical_url, "
            "display_name, adapter, legacy_feed_id, legacy_playlist_id, detection_enabled, "
            "archived, consent_state, revision, consent_epoch, boundary, poll_interval_min, "
            "capture_not_before_ms, accounting_hold_until_ms, last_observed_ms, created_at_ms, "
            "updated_at_ms) VALUES (?,?,?,?,?,?,?,?,?,0,'off',0,0,'none',?,0,?,?,?,?)",
            (source_id, kind, source_key, canonical_url, display_name, ADAPTERS[kind],
             legacy_feed_id, legacy_playlist_id, 1 if detection_enabled else 0,
             max(MIN_POLL_INTERVAL_MIN, min(int(interval), MAX_POLL_INTERVAL_MIN)),
             int(hold_until_ms), now, now, now))
        conn.execute(
            "INSERT INTO source_detection_cursors (source_id, revision, next_poll_at_ms, etag, "
            "last_modified) VALUES (?, 0, ?, ?, ?)",
            (source_id, now, etag, last_modified))

    def _unarchive(self, conn, source: dict, now: int) -> dict:
        conn.execute(
            "UPDATE source_subscriptions SET archived=0, detection_enabled=1, consent_state='off', "
            "boundary='none', revision=revision+1, updated_at_ms=? WHERE source_id=?",
            (now, source["source_id"]))
        fresh = self._source(conn, source["source_id"])
        return self._write_receipt(
            conn, fresh, old_state="off", new_state="off", before=source["revision"],
            after=fresh["revision"], authority="archive",
            operation_key=f"unarchive-{source['source_id'][-16:]}-{fresh['revision']}",
            request_hash=digest({"unarchive": source["source_id"], "revision": fresh["revision"]}),
            session_hash="server", changed=True, released=0, now=now)

    @endpoint
    def archive_source(self, context, args):
        """Dashboard/UI archive route. Archiving disables detection, sets capture
        off and releases unstarted reservations; rows are preserved."""
        if getattr(context, "operator", False) is not True and \
                getattr(context, "local_user_confirmed", False) is not True:
            fail("user_intent_required", "Archiving requires the local dashboard or operator")
        if set(args) - {"source_id"} or type(args.get("source_id")) is not str \
                or not _SOURCE_ID_RE.match(args["source_id"]):
            fail("validation_error", "source_id is required")
        now = self._now()
        with self.store.write() as conn:
            source = self._source(conn, args["source_id"])
            if source["archived"]:
                return success(source_id=source["source_id"], changed=False,
                               revision=source["revision"])
            old_state = source["consent_state"]
            # Contract "Consent and enrollment": archiving disables detection and sets
            # capture off; unstarted reservations release in the same transaction.
            released = self._release_unstarted(conn, source["source_id"], now, "archived")
            conn.execute(
                "UPDATE source_subscriptions SET archived=1, detection_enabled=0, consent_state='off', "
                "boundary='none', revision=revision+1, updated_at_ms=? WHERE source_id=?",
                (now, source["source_id"]))
            conn.execute(
                "UPDATE source_detection_cursors SET poll_owner_token=NULL, poll_consent_epoch=NULL, "
                "poll_lease_expires_ms=NULL WHERE source_id=?", (source["source_id"],))
            fresh = self._source(conn, source["source_id"])
            receipt = self._write_receipt(
                conn, fresh, old_state=old_state, new_state="off", before=source["revision"],
                after=fresh["revision"], authority="archive",
                operation_key=f"archive-{source['source_id'][-16:]}-{fresh['revision']}",
                request_hash=digest({"archive": source["source_id"], "revision": fresh["revision"]}),
                session_hash=self._session_hash(context) or "server", changed=True,
                released=released, now=now)
            return success(source_id=source["source_id"], changed=True,
                           revision=fresh["revision"], receipt=receipt)

    # ======================================================================
    # Consent (contract, "Consent and enrollment")
    # ======================================================================
    @endpoint
    def mint_consent_intent(self, context, args):
        """Dashboard-only seam behind ``POST /sources/consent-intent``. Never a
        registry tool: only the authenticated local confirmation route may
        grant user authority (contract, consent section)."""
        if getattr(context, "local_user_confirmed", False) is not True or not getattr(context, "session_id", None):
            fail("user_intent_required", "Authenticated local dashboard confirmation required")
        if set(args) != {"operation"} or type(args["operation"]) is not dict:
            fail("validation_error", "Expected {operation}")
        operation = args["operation"]
        if "user_intent_token" in operation:
            fail("validation_error", "Operation must exclude its capability token")
        check_json_value(operation)
        _schema_check(operation, consent_intent_operation_schema(), "operation")
        now = self._now()
        token = _new_token()
        with self.store.write() as conn:
            source = self._source(conn, operation["source_id"])
            if source["archived"]:
                fail("source_archived", "Archived sources cannot change consent")
            cursor = self._cursor(conn, source["source_id"])
            self._check_revisions(source, cursor, operation)
            expires = now + INTENT_TTL_MS
            conn.execute(
                "INSERT INTO source_user_intents (token_hash, source_id, request_hash, session_hash, "
                "expires_ms, consumed_by) VALUES (?,?,?,?,?,NULL)",
                (digest(token), source["source_id"], digest(operation),
                 self._session_hash(context), expires))
            summary = self._summary(conn, source, now)
        return success(user_intent_token=token, expires_ms=expires, source=summary,
                       confirmation=self._confirmation_copy(summary, operation["consent_state"]))

    @staticmethod
    def _confirmation_copy(summary: dict, new_state: str) -> dict:
        """What the UI must name: the source, bounded enrollment, the 10-start UTC
        allowance, and what turning off does to current work."""
        enrollment = summary["enrollment"]
        if new_state == "on":
            bound = (f"up to {enrollment['remaining_initial_slots']} back-catalog items"
                     if not enrollment["initial_completed"] else
                     "no new back-catalog items (initial enrollment already completed)")
            effect = ("Standing capture will start automatically for this source: "
                      f"{bound}, then newly published items, at most "
                      f"{DAILY_START_CAP} starts per UTC day.")
        else:
            effect = ("Standing capture stops. Unstarted reservations are released; "
                      f"{len(summary.get('in_flight', []))} already-started capture(s) may "
                      "finish and stay visible. No new start is authorized while off.")
        return {"source": summary["display_name"] or summary["canonical_url"],
                "consent_state": new_state, "effect": effect,
                "back_catalog_cap": BACK_CATALOG_CAP, "daily_cap": DAILY_START_CAP}

    @staticmethod
    def _check_revisions(source: dict, cursor: dict, args: dict) -> None:
        if args["expected_revision"] != source["revision"]:
            # Contract: stale errors return current revisions; a stale request writes nothing.
            fail("stale_revision", "Source revision changed; reload and confirm again",
                 current_revision=source["revision"], current_cursor_revision=cursor["revision"])
        if args["consent_state"] == "on" and args.get("expected_cursor_revision") != cursor["revision"]:
            fail("stale_cursor", "Detection cursor changed; reload and confirm again",
                 current_revision=source["revision"], current_cursor_revision=cursor["revision"])

    @endpoint
    def set_source_consent(self, context, args):
        args = validate_arguments("set_source_consent", args)
        request = {k: v for k, v in args.items() if k != "user_intent_token"}
        request_hash = digest(request)
        session_hash = self._session_hash(context)
        now = self._now()
        with self.store.write() as conn:
            source = self._source(conn, args["source_id"])
            receipt = _row(conn.execute(
                "SELECT * FROM source_consent_receipts WHERE operation_key=?",
                (args["operation_key"],)).fetchone())
            if receipt is not None:
                # Contract: identical retries from the same session return the original
                # receipt, including after token expiry; a changed request conflicts.
                if receipt["request_hash"] == request_hash and receipt["session_hash"] == session_hash \
                        and receipt["source_id"] == source["source_id"]:
                    return json.loads(receipt["response_json"])
                fail("idempotency_conflict", "operation_key was used for a different request",
                     operation_key=args["operation_key"])
            if session_hash is None:
                fail("user_intent_required", "User session required")
            if source["archived"]:
                fail("source_archived", "Archived sources cannot change consent")
            cursor = self._cursor(conn, source["source_id"])
            self._check_revisions(source, cursor, args)
            intent = _row(conn.execute(
                "SELECT * FROM source_user_intents WHERE token_hash=?",
                (digest(args["user_intent_token"]),)).fetchone())
            if intent is None or intent["source_id"] != source["source_id"] \
                    or intent["request_hash"] != request_hash or intent["session_hash"] != session_hash:
                fail("invalid_user_intent", "Capability does not bind this operation and session")
            if intent["consumed_by"] is not None or now >= intent["expires_ms"]:
                fail("invalid_user_intent", "Capability is expired or consumed")
            response = self._transition_consent(
                conn, source, args["consent_state"], now, authority="local_user",
                operation_key=args["operation_key"], request_hash=request_hash,
                session_hash=session_hash)
            # Token consumption, revision, releases and receipt commit atomically.
            conn.execute("UPDATE source_user_intents SET consumed_by=? WHERE token_hash=?",
                         (args["operation_key"], intent["token_hash"]))
            return response

    def _transition_consent(self, conn, source: dict, new_state: str, now: int, *,
                            authority: str, operation_key: str, request_hash: str,
                            session_hash: str) -> dict:
        old_state = source["consent_state"]
        before = int(source["revision"])
        epoch = int(source["consent_epoch"])
        released = 0
        changed = old_state != new_state
        if not changed:
            # Contract table, "Same-state request": no-change receipt; no revision,
            # epoch, enrollment or allowance change.
            after = before
            boundary = source["boundary"]
        elif new_state == "on":
            # Contract table, "Confirm off -> on": increment revision and epoch; the
            # boundary is initial when never enrolled, otherwise resume.
            after = before + 1
            epoch += 1
            boundary = "initial" if source["initial_enrollment_completed_ms"] is None else "resume"
            conn.execute(
                "UPDATE source_subscriptions SET consent_state='on', revision=?, consent_epoch=?, "
                "boundary=?, updated_at_ms=? WHERE source_id=?",
                (after, epoch, boundary, now, source["source_id"]))
        else:
            # Contract table, "Confirm on -> off": increment revision; clear the
            # pending boundary; release every unstarted reservation in this
            # transaction. Started work keeps its charged row and stays visible.
            after = before + 1
            boundary = "none"
            conn.execute(
                "UPDATE source_subscriptions SET consent_state='off', revision=?, boundary='none', "
                "updated_at_ms=? WHERE source_id=?", (after, now, source["source_id"]))
            released = self._release_unstarted(conn, source["source_id"], now, "consent_off")
        fresh = self._source(conn, source["source_id"])
        return self._write_receipt(
            conn, fresh, old_state=old_state, new_state=new_state, before=before, after=after,
            authority=authority, operation_key=operation_key, request_hash=request_hash,
            session_hash=session_hash, changed=changed, released=released, now=now)

    def _write_receipt(self, conn, source: dict, *, old_state, new_state, before, after,
                       authority, operation_key, request_hash, session_hash, changed,
                       released, now) -> dict:
        response = success(
            operation_key=operation_key, changed=bool(changed), source_id=source["source_id"],
            before_revision=int(before), after_revision=int(after),
            consent_state=source["consent_state"], consent_epoch=int(source["consent_epoch"]),
            boundary=source["boundary"], released_reservations=int(released),
            in_flight=[{"start_id": r["start_id"], "item_id": r["item_id"], "state": r["state"]}
                       for r in self._in_flight(conn, source["source_id"])],
            recorded_at_ms=int(now), authority=authority)
        conn.execute(
            "INSERT INTO source_consent_receipts (operation_key, source_id, request_hash, session_hash, "
            "authority, old_state, new_state, before_revision, after_revision, consent_epoch, "
            "response_json, created_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (operation_key, source["source_id"], request_hash, session_hash, authority, old_state,
             new_state, int(before), int(after), int(source["consent_epoch"]),
             canonical_json(response), int(now)))
        return response

    def _release_unstarted(self, conn, source_id: str, now: int, code: str) -> int:
        rows = conn.execute(
            "SELECT * FROM source_capture_starts WHERE source_id=? AND state='reserved'",
            (source_id,)).fetchall()
        for row in rows:
            self._release(conn, dict(row), now, code)
        return len(rows)

    @staticmethod
    def _release(conn, start: dict, now: int, code: str) -> None:
        # Contract ledger table, "reserved -> released": only before started_at_ms
        # exists; keep the row and reason; free the active ownership and slot.
        conn.execute(
            "UPDATE source_capture_starts SET state='released', finished_at_ms=?, "
            "release_or_failure_code=? WHERE start_id=? AND state='reserved'",
            (now, code, start["start_id"]))
        conn.execute(
            "UPDATE source_items SET state='eligible' WHERE item_id=? AND state='reserved'",
            (start["item_id"],))

    # ======================================================================
    # Reads (contract, "Registry and dashboard contract")
    # ======================================================================
    @endpoint
    def list_sources(self, context, args):
        args = validate_arguments("list_sources", args)
        limit = int(args.get("limit", 50))
        binding = {"kind": args.get("kind"), "consent_state": args.get("consent_state"),
                   "include_archived": bool(args.get("include_archived", False))}
        after = _decode_cursor(args["cursor"], binding)["key"] if "cursor" in args else None
        if after is not None and (type(after) is not str or not _SOURCE_ID_RE.match(after)):
            fail("invalid_cursor", "Malformed pagination cursor")
        wheres = ["1=1"]
        params: list[Any] = []
        if binding["kind"]:
            wheres.append("kind=?")
            params.append(binding["kind"])
        if binding["consent_state"]:
            wheres.append("consent_state=?")
            params.append(binding["consent_state"])
        if not binding["include_archived"]:
            wheres.append("archived=0")
        if after:
            wheres.append("source_id>?")
            params.append(after)
        params.append(limit + 1)
        now = self._now()
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM source_subscriptions WHERE " + " AND ".join(wheres) +
                " ORDER BY source_id LIMIT ?", params).fetchall()
            page = [self._summary(conn, dict(r), now) for r in rows[:limit]]
        next_cursor = (_encode_cursor({"v": 1, "bind": binding, "key": page[-1]["source_id"]})
                       if len(rows) > limit else None)
        return success(sources=page, next_cursor=next_cursor, as_of_ms=now)

    @endpoint
    def source_status(self, context, args):
        args = validate_arguments("source_status", args)
        limit = int(args.get("item_limit", 25))
        binding = {"source_id": args["source_id"]}
        key = _decode_cursor(args["item_cursor"], binding)["key"] if "item_cursor" in args else None
        if key is not None and not (type(key) is list and len(key) == 2 and type(key[0]) is int
                                    and type(key[1]) is str):
            fail("invalid_cursor", "Malformed pagination cursor")
        now = self._now()
        with self.store.read() as conn:
            source = self._source(conn, args["source_id"])
            summary = self._summary(conn, source, now)
            params: list[Any] = [source["source_id"]]
            keyset = ""
            if key is not None:
                keyset = " AND (first_seen_ms>? OR (first_seen_ms=? AND item_id>?))"
                params.extend([key[0], key[0], key[1]])
            params.append(limit + 1)
            rows = conn.execute(
                "SELECT * FROM source_items WHERE source_id=?" + keyset +
                " ORDER BY first_seen_ms, item_id LIMIT ?", params).fetchall()
            items = [self._item_record(conn, dict(r)) for r in rows[:limit]]
            in_flight = [self._item_record(conn, self._item(conn, r["item_id"]), start=r)
                         for r in self._in_flight(conn, source["source_id"])]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = _encode_cursor({"v": 1, "bind": binding,
                                          "key": [last["first_seen_ms"], last["item_id"]]})
        return success(source=summary, items=items, next_item_cursor=next_cursor,
                       in_flight=in_flight, as_of_ms=now)

    def _summary(self, conn, source: dict, now: int) -> dict:
        cursor = self._cursor(conn, source["source_id"])
        counts = {state: 0 for state in ITEM_STATES}
        for state, count in conn.execute(
                "SELECT state, COUNT(*) FROM source_items WHERE source_id=? GROUP BY state",
                (source["source_id"],)).fetchall():
            counts[state] = int(count)
        in_flight = self._in_flight(conn, source["source_id"])
        allowance = self._allowance(conn, source, now)
        return {
            "source_id": source["source_id"], "kind": source["kind"],
            "canonical_url": source["canonical_url"],
            "display_name": _safe_text(source.get("display_name"), 200),
            "adapter": source["adapter"],
            "consent_state": source["consent_state"], "revision": int(source["revision"]),
            "consent_epoch": int(source["consent_epoch"]),
            "detection_enabled": bool(source["detection_enabled"]),
            "archived": bool(source["archived"]),
            "poll_interval_min": int(source["poll_interval_min"]),
            "boundary": source["boundary"],
            "enrollment": self._enrollment(source, cursor, counts),
            "allowance": allowance,
            "detection": self._detection(cursor, source, now),
            "item_counts": counts,
            "in_flight": [{"start_id": r["start_id"], "item_id": r["item_id"], "state": r["state"]}
                          for r in in_flight],
            "capture_status": self._capture_status(source, allowance, in_flight, now),
            "legacy": {"feed_id": source.get("legacy_feed_id"),
                       "playlist_id": source.get("legacy_playlist_id")},
            "created_at_ms": int(source["created_at_ms"]),
            "updated_at_ms": int(source["updated_at_ms"]),
        }

    @staticmethod
    def _enrollment(source: dict, cursor: dict, counts: dict) -> dict:
        completed = source["initial_enrollment_completed_ms"] is not None
        enrolled = int(source["back_catalog_enrolled"])
        return {
            "cap": BACK_CATALOG_CAP, "enrolled": enrolled, "initial_completed": completed,
            "known_candidates": int(counts.get("observed", 0)) + int(counts.get("eligible", 0)),
            "pending": source["consent_state"] == "on" and source["boundary"] != "none",
            "remaining_initial_slots": 0 if completed else max(0, BACK_CATALOG_CAP - enrolled),
            "coverage": cursor["coverage"],
            "initial_completed_ms": source["initial_enrollment_completed_ms"],
        }

    def _allowance(self, conn, source: dict, now: int) -> dict:
        day = utc_day(now)
        reserved = int(conn.execute(
            "SELECT COUNT(*) FROM source_capture_starts WHERE source_id=? AND utc_day=? "
            "AND state='reserved'", (source["source_id"], day)).fetchone()[0])
        charged = int(conn.execute(
            "SELECT COUNT(*) FROM source_capture_starts WHERE source_id=? AND utc_day=? "
            "AND started_at_ms IS NOT NULL", (source["source_id"], day)).fetchone()[0])
        hold_reason = None
        hold_until = None
        if int(source["accounting_hold_until_ms"] or 0) > now:
            hold_reason, hold_until = "legacy_accounting_hold", int(source["accounting_hold_until_ms"])
        elif self._clock_regressed(source, now):
            hold_reason, hold_until = "clock_regressed", int(source["last_observed_ms"])
        return {
            "utc_day": day, "cap": DAILY_START_CAP, "reserved": reserved, "charged": charged,
            "remaining": max(0, DAILY_START_CAP - reserved - charged),
            "resets_at_ms": next_utc_midnight_ms(now),
            "capture_not_before_ms": int(source["capture_not_before_ms"] or 0),
            "hold_reason": hold_reason, "hold_until_ms": hold_until,
        }

    @staticmethod
    def _detection(cursor: dict, source: dict, now: int) -> dict:
        error = None
        if cursor.get("last_error_code"):
            error = {"code": cursor["last_error_code"],
                     "message": sanitize_message(cursor.get("last_error_message") or "")}
        lease = cursor.get("poll_lease_expires_ms")
        return {
            "cursor_revision": int(cursor["revision"]),
            "enabled": bool(source["detection_enabled"]),
            "last_poll_attempt_ms": cursor.get("last_poll_attempt_ms"),
            "last_poll_success_ms": cursor.get("last_poll_success_ms"),
            "next_poll_at_ms": int(cursor["next_poll_at_ms"]),
            "observed_count": int(cursor["observed_count"]),
            "coverage": cursor["coverage"], "truncated": bool(cursor["truncated"]),
            "consecutive_failures": int(cursor["error_count"]),
            "poll_in_progress": bool(cursor.get("poll_owner_token")) and (lease or 0) > now,
            "error": error,
        }

    @staticmethod
    def _capture_status(source: dict, allowance: dict, in_flight: list, now: int) -> str:
        if source["archived"]:
            return "archived"
        if source["consent_state"] != "on":
            return "off"
        if allowance["hold_reason"]:
            return allowance["hold_reason"]
        if source["boundary"] != "none":
            return "enrollment_pending"
        if in_flight:
            return "in_flight"
        if allowance["remaining"] <= 0:
            return "allowance_exhausted"
        if int(source["capture_not_before_ms"] or 0) > now:
            return "not_due"
        return "ready"

    def _item_record(self, conn, item: dict | None, start: dict | None = None) -> dict:
        if item is None:
            return {}
        if start is None:
            start = _row(conn.execute(
                "SELECT * FROM source_capture_starts WHERE item_id=? "
                "ORDER BY reserved_at_ms DESC LIMIT 1", (item["item_id"],)).fetchone())
        charged_day = start["utc_day"] if start and start.get("started_at_ms") else None
        # Never return owner tokens, queue internals, paths or transcript bodies.
        return {
            "item_id": item["item_id"], "entry_id": item["entry_id"],
            "title": _safe_text(item.get("title")),
            "canonical_url": _http_link(item.get("canonical_url")),
            "published_at_ms": item.get("published_at_ms"),
            "first_seen_ms": int(item["first_seen_ms"]), "last_seen_ms": int(item["last_seen_ms"]),
            "eligibility": item["eligibility"], "capture_state": item["state"],
            "blocked_reason": item.get("blocked_reason"),
            "actual_attempts": int(item["actual_starts"]),
            "preflight_failures": int(item["preflight_failures"]),
            "retry_at_ms": item.get("retry_at_ms"),
            "start_id": start["start_id"] if start else None,
            "start_state": start["state"] if start else None,
            "charged_utc_day": charged_day,
            "video_id": item.get("video_id"), "committed_at_ms": item.get("committed_at_ms"),
            "classification": self._classification_display(conn, item),
        }

    @staticmethod
    def _classification_display(conn, item: dict) -> dict:
        if item["state"] != "committed":
            return {"state": "not_captured", "work_id": None}
        outbox = _row(conn.execute(
            "SELECT * FROM source_classification_outbox WHERE capture_key=?",
            (item["capture_key"],)).fetchone())
        if outbox is None:
            owned = conn.execute(
                "SELECT 1 FROM source_capture_starts WHERE capture_key=? AND state='succeeded'",
                (item["capture_key"],)).fetchone()
            # A standing success without its outbox row is repaired on restart;
            # a linked pre-existing capture has no work of its own.
            return {"state": "pending" if owned else "not_requested", "work_id": None}
        if outbox["state"] in ("pending", "waiting_configuration", "blocked"):
            return {"state": outbox["state"], "work_id": outbox.get("work_id"),
                    "error_code": outbox.get("last_error_code")}
        try:
            work = _row(conn.execute("SELECT state FROM library_work WHERE work_id=?",
                                     (outbox["work_id"],)).fetchone())
        except sqlite3.OperationalError:
            work = None
        state = (work or {}).get("state")
        display = {"ready": "waiting_for_client", "leased": "leased", "accepted": "accepted",
                   "unmapped": "unmapped", "unsupported": "unsupported", "blocked": "blocked",
                   "cancelled": "cancelled"}.get(state, "pending")
        return {"state": display, "work_id": outbox.get("work_id"), "run_id": outbox.get("run_id")}

    # ======================================================================
    # Detection (contract, "Source identity and detection"; "Scheduler and
    # adapter boundaries")
    # ======================================================================
    def detection_pass(self, now: int | None = None, *, limit: int | None = None) -> list[dict]:
        """Claim every due poll, fetch outside the database, commit each result.
        A pass with nothing due returns [] (a heartbeat, not a poll)."""
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            self._expire_poll_leases(conn, now)
        results = []
        for claim in self.claim_due_polls(now, limit=limit):
            try:
                results.append(self.run_claimed_poll(claim))
            except (ServiceError, sqlite3.OperationalError) as exc:
                log.warning("poll commit for %s deferred: %s", claim["source_id"], type(exc).__name__)
                results.append({"ok": False, "outcome": "storage_busy",
                                "source_id": claim["source_id"], "retryable": True})
        return results

    def due_poll_ids(self, now: int | None = None, *, limit: int | None = None) -> list[str]:
        now = self._now() if now is None else int(now)
        sql = ("SELECT s.source_id FROM source_subscriptions s "
               "JOIN source_detection_cursors c ON c.source_id=s.source_id "
               "WHERE s.archived=0 AND s.detection_enabled=1 AND c.poll_owner_token IS NULL "
               "AND c.next_poll_at_ms<=? ORDER BY c.next_poll_at_ms, s.source_id")
        params: list[Any] = [now]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.store.read() as conn:
            return [r[0] for r in conn.execute(sql, params).fetchall()]

    def claim_due_polls(self, now: int | None = None, *, limit: int | None = None) -> list[dict]:
        now = self._now() if now is None else int(now)
        claims = []
        for source_id in self.due_poll_ids(now, limit=limit):
            claim = self.claim_poll(source_id, now)
            if claim is not None:
                claims.append(claim)
        return claims

    def claim_poll(self, source_id: str, now: int | None = None) -> dict | None:
        """Claim poll ownership and its 120-second lease atomically, before any
        network I/O (contract, scheduler section). Returns None when not due,
        owned elsewhere, disabled, or when the clock regressed."""
        now = self._now() if now is None else int(now)
        token = _new_token()
        with self.store.write() as conn:
            source = self._source(conn, source_id)
            cursor = self._cursor(conn, source_id)
            if source["archived"] or not source["detection_enabled"]:
                return None
            if cursor["poll_owner_token"] is not None and int(cursor["poll_lease_expires_ms"]) > now:
                return None
            if int(cursor["next_poll_at_ms"]) > now:
                return None
            if self._clock_regressed(source, now):
                conn.execute(
                    "UPDATE source_detection_cursors SET last_error_code='clock_regressed', "
                    "last_error_message='server clock is behind the last observed time' "
                    "WHERE source_id=?", (source_id,))
                return None
            self._touch_observed(conn, source, now)
            conn.execute(
                "UPDATE source_detection_cursors SET poll_owner_token=?, poll_consent_epoch=?, "
                "poll_lease_expires_ms=?, last_poll_attempt_ms=? WHERE source_id=?",
                (token, int(source["consent_epoch"]), now + POLL_LEASE_MS, now, source_id))
            boundary_pending = source["consent_state"] == "on" and source["boundary"] != "none"
            return {"source_id": source_id, "owner_token": token,
                    "consent_epoch": int(source["consent_epoch"]), "source": source,
                    "cursor": cursor, "boundary_pending": boundary_pending}

    def run_claimed_poll(self, claim: dict) -> dict:
        """Fetch outside any transaction, then commit under the owner token."""
        adapter = self.adapters.get(claim["source"]["adapter"])
        if adapter is None:
            result = AdapterResult("error", error_code="adapter_unavailable",
                                   error_message="no adapter registered")
        else:
            try:
                # Contract: omit conditional headers while a boundary is pending.
                result = adapter.poll(claim["source"], claim["cursor"],
                                      conditional=not claim["boundary_pending"])
            except Exception as exc:
                log.exception("adapter %s raised", claim["source"]["adapter"])
                result = AdapterResult("error", error_code="adapter_error",
                                       error_message=type(exc).__name__)
        return self.commit_poll(claim["source_id"], claim["owner_token"], result)

    def commit_poll(self, source_id: str, owner_token: str, result: AdapterResult,
                    now: int | None = None) -> dict:
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            cursor = self._cursor(conn, source_id)
            source = self._source(conn, source_id)
            base = {"source_id": source_id, "kind": source["kind"]}
            if cursor["poll_owner_token"] != owner_token:
                # Contract: reject late results from an expired/replaced owner.
                return {"ok": False, "outcome": "stale_owner", **base}
            if int(cursor["poll_lease_expires_ms"]) <= now:
                self._record_poll_failure(conn, source, cursor, AdapterResult(
                    "error", error_code="poll_timeout", error_message="lease expired"), now)
                return {"ok": False, "outcome": "stale_owner", "code": "poll_timeout", **base}
            stale_epoch = int(source["consent_epoch"]) != int(cursor["poll_consent_epoch"])
            if result.status == "error":
                self._record_poll_failure(conn, source, cursor, result, now)
                return {"ok": False, "outcome": "error", "code": result.error_code,
                        "message": sanitize_message(result.error_message), **base}
            if result.status == "not_modified":
                # Contract: a valid 304 advances success time and sequence, inserts
                # nothing, and completes no boundary.
                conn.execute(
                    "UPDATE source_detection_cursors SET revision=revision+1, last_poll_success_ms=?, "
                    "next_poll_at_ms=?, error_count=0, last_error_code=NULL, last_error_message=NULL, "
                    "etag=COALESCE(?, etag), last_modified=COALESCE(?, last_modified), "
                    "poll_owner_token=NULL, poll_consent_epoch=NULL, poll_lease_expires_ms=NULL "
                    "WHERE source_id=?",
                    (now, self._next_due(source, now), result.etag, result.last_modified, source_id))
                return {"ok": True, "outcome": "not_modified", "inserted": 0, **base}
            scan_revision = int(cursor["revision"]) + 1
            on_current = source["consent_state"] == "on" and not stale_epoch
            epoch_for_items = int(source["consent_epoch"]) if on_current else None
            stats = self._persist_observations(conn, source, result.observations, now,
                                               scan_revision, epoch_for_items)
            if result.coverage == "partial":
                # Contract: incomplete batches persist metadata but advance no success
                # cursor or enrollment and create no eligibility.
                self._record_poll_failure(conn, source, cursor, AdapterResult(
                    "error", error_code="partial_listing", error_message="incomplete enumeration",
                    coverage="partial", truncated=result.truncated), now,
                    observed_count=len(result.observations))
                return {"ok": False, "outcome": "partial", "code": "partial_listing",
                        "stale_epoch": stale_epoch, **stats, **base}
            enrollment = None
            if on_current:
                enrollment = self._apply_enrollment(conn, source, scan_revision, now)
            if stale_epoch and source["consent_state"] == "on" and source["boundary"] != "none":
                next_due = now  # the next due poll must use the current epoch
            else:
                next_due = self._next_due(source, now)
            conn.execute(
                "UPDATE source_detection_cursors SET revision=?, last_poll_success_ms=?, "
                "next_poll_at_ms=?, etag=?, last_modified=?, coverage=?, observed_count=?, "
                "truncated=?, error_count=0, last_error_code=NULL, last_error_message=NULL, "
                "poll_owner_token=NULL, poll_consent_epoch=NULL, poll_lease_expires_ms=NULL "
                "WHERE source_id=?",
                (scan_revision, now, next_due, result.etag, result.last_modified,
                 result.coverage if result.coverage in ("window", "complete") else "unknown",
                 len(result.observations), 1 if result.truncated else 0, source_id))
            return {"ok": True, "outcome": "snapshot", "scan_revision": scan_revision,
                    "coverage": result.coverage, "truncated": bool(result.truncated),
                    "rejected": result.rejected, "conflicts": result.conflicts,
                    "stale_epoch": stale_epoch, "enrollment": enrollment, **stats, **base}

    def _next_due(self, source: dict, now: int) -> int:
        # Contract: success schedules completion plus interval; jitter only delays.
        return now + int(source["poll_interval_min"]) * 60_000 + self._jitter()

    def _record_poll_failure(self, conn, source: dict, cursor: dict, result: AdapterResult,
                             now: int, *, observed_count: int | None = None) -> None:
        # Contract: failure number n backs off min(1440 min, interval * 2^min(n-1, 7));
        # Retry-After may extend, never shorten; success time and validators stay.
        n = int(cursor["error_count"]) + 1
        backoff_min = min(MAX_BACKOFF_MIN, int(source["poll_interval_min"]) * (2 ** min(n - 1, 7)))
        delay = backoff_min * 60_000
        if result.retry_after_ms:
            delay = max(delay, int(result.retry_after_ms))
        conn.execute(
            "UPDATE source_detection_cursors SET error_count=?, last_error_code=?, "
            "last_error_message=?, next_poll_at_ms=?, coverage=?, truncated=?, "
            "observed_count=COALESCE(?, observed_count), poll_owner_token=NULL, "
            "poll_consent_epoch=NULL, poll_lease_expires_ms=NULL WHERE source_id=?",
            (n, result.error_code or "poll_failed", sanitize_message(result.error_message or ""),
             now + delay + self._jitter(),
             result.coverage if result.coverage in ("partial",) else cursor["coverage"],
             1 if result.truncated else cursor["truncated"], observed_count, source["source_id"]))

    def _expire_poll_leases(self, conn, now: int) -> int:
        rows = conn.execute(
            "SELECT c.*, s.poll_interval_min, s.source_id AS sid FROM source_detection_cursors c "
            "JOIN source_subscriptions s ON s.source_id=c.source_id "
            "WHERE c.poll_owner_token IS NOT NULL AND c.poll_lease_expires_ms<=?", (now,)).fetchall()
        for row in rows:
            cursor = dict(row)
            # Contract: a poll timeout records failure and schedules another due time.
            self._record_poll_failure(conn, {"source_id": cursor["sid"],
                                             "poll_interval_min": cursor["poll_interval_min"]},
                                      cursor, AdapterResult("error", error_code="poll_timeout",
                                                            error_message="lease expired"), now)
        return len(rows)

    def _persist_observations(self, conn, source: dict, observations: list[Observation],
                              now: int, scan_revision: int, epoch: int | None) -> dict:
        inserted = updated = linked = 0
        seen_in_batch: set[str] = set()
        for obs in observations:
            entry_id = obs.entry_id
            if entry_id in seen_in_batch:
                continue  # duplicate ids in one response collapse to one row
            seen_in_batch.add(entry_id)
            item_id = item_identity(source["source_id"], entry_id)
            capture_key = capture_key_for(source["kind"], source["source_key"], entry_id)
            metadata_json = canonical_json(obs.metadata or {})
            title = _safe_text(obs.title)
            url = _http_link(obs.canonical_url)
            existing = _row(conn.execute(
                "SELECT * FROM source_items WHERE source_id=? AND entry_id=?",
                (source["source_id"], entry_id)).fetchone())
            if existing is None:
                state, video_id, committed_at = self._preexisting_capture(conn, source, capture_key, entry_id, now)
                conn.execute(
                    "INSERT INTO source_items (item_id, source_id, entry_id, capture_key, canonical_url, "
                    "title, published_at_ms, first_seen_ms, last_seen_ms, first_scan_revision, "
                    "first_seen_consent_epoch, metadata_json, eligibility, enrolled_epoch, state, "
                    "video_id, committed_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'none',NULL,?,?,?)",
                    (item_id, source["source_id"], entry_id, capture_key, url, title,
                     obs.published_at_ms, now, now, scan_revision, epoch, metadata_json, state,
                     video_id, committed_at))
                inserted += 1
                if state == "committed":
                    linked += 1
                self._project_legacy(conn, source, item_id, obs, now)
                continue
            changed = (existing.get("title") != title or existing.get("canonical_url") != url
                       or existing.get("metadata_json") != metadata_json)
            # Contract: preflight blocks lift when item metadata changes.
            reset_preflight = changed and int(existing["preflight_failures"]) >= PREFLIGHT_BLOCK_AFTER
            conn.execute(
                "UPDATE source_items SET last_seen_ms=?, title=?, canonical_url=?, "
                "published_at_ms=COALESCE(?, published_at_ms), metadata_json=?, "
                "preflight_failures=CASE WHEN ? THEN 0 ELSE preflight_failures END "
                "WHERE item_id=?",
                (now, title, url, obs.published_at_ms, metadata_json, 1 if reset_preflight else 0,
                 item_id))
            updated += 1
        return {"inserted": inserted, "updated": updated, "linked": linked}

    @staticmethod
    def _project_legacy(conn, source: dict, item_id: str, obs: Observation, now: int) -> None:
        """Compatibility projection into podcast_episodes for legacy-linked feeds
        (the old table is a projection, never a scheduler authority)."""
        if source["kind"] != "podcast_rss" or source.get("legacy_feed_id") is None:
            return
        meta = obs.metadata or {}
        stamp = datetime.fromtimestamp(now / 1000, tz=timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        project_podcast_episode(conn, source, item_id, obs.entry_id, _safe_text(obs.title),
                                _http_link(meta.get("audio_url")), _http_link(obs.canonical_url),
                                meta.get("published_raw"), meta.get("duration_raw"), stamp)

    def _preexisting_capture(self, conn, source: dict, capture_key: str, entry_id: str,
                             now: int) -> tuple[str, str | None, int | None]:
        """Link an observation to an already committed or deleted capture of the
        same canonical item (contract: no charge, no resurrection)."""
        succeeded = _row(conn.execute(
            "SELECT video_id, finished_at_ms FROM source_capture_starts WHERE capture_key=? "
            "AND state='succeeded'", (capture_key,)).fetchone())
        if succeeded is not None:
            deleted = _row(conn.execute(
                "SELECT 1 FROM source_items WHERE capture_key=? AND state='deleted' LIMIT 1",
                (capture_key,)).fetchone())
            if deleted:
                return "deleted", succeeded["video_id"], None
            return "committed", succeeded["video_id"], succeeded["finished_at_ms"] or now
        sibling = _row(conn.execute(
            "SELECT state, video_id, committed_at_ms FROM source_items WHERE capture_key=? "
            "AND state IN ('committed','deleted') ORDER BY CASE state WHEN 'deleted' THEN 0 ELSE 1 END "
            "LIMIT 1", (capture_key,)).fetchone())
        if sibling is not None:
            return sibling["state"], sibling["video_id"], sibling["committed_at_ms"]
        corpus = self._corpus_row(conn, self._corpus_video_id(source, entry_id))
        if corpus is not None:
            if corpus.get("deleted_at"):
                return "deleted", corpus["video_id"], None
            return "committed", corpus["video_id"], now
        return "observed", None, None

    def _apply_enrollment(self, conn, source: dict, scan_revision: int, now: int) -> dict:
        epoch = int(source["consent_epoch"])
        source_id = source["source_id"]
        if source["boundary"] == "initial":
            # Contract table, "First valid initial snapshot while on": at most 25
            # eligible, uncommitted observations; persist the exact cohort; complete
            # initial enrollment once per stable identity, never refilled.
            remaining = max(0, BACK_CATALOG_CAP - int(source["back_catalog_enrolled"]))
            candidates = [dict(r) for r in conn.execute(
                "SELECT item_id, entry_id, published_at_ms, first_seen_ms FROM source_items "
                "WHERE source_id=? AND state='observed' AND eligibility='none' "
                "AND blocked_reason IS NULL", (source_id,)).fetchall()]
            candidates.sort(key=_published_sort_key)
            cohort = candidates[:remaining]
            for item in cohort:
                conn.execute(
                    "UPDATE source_items SET eligibility='back_catalog', enrolled_epoch=?, "
                    "state='eligible' WHERE item_id=?", (epoch, item["item_id"]))
            conn.execute(
                "UPDATE source_subscriptions SET initial_enrollment_completed_ms=?, "
                "back_catalog_enrolled=back_catalog_enrolled+?, boundary='none', updated_at_ms=? "
                "WHERE source_id=?", (now, len(cohort), now, source_id))
            return {"boundary": "initial", "enrolled": len(cohort),
                    "cohort": [item["item_id"] for item in cohort]}
        if source["boundary"] == "resume":
            # Contract table, "Confirm off -> on after initial enrollment": one resume
            # snapshot; previously eligible items resume; items unseen before this
            # snapshot are metadata-only; later observations may become future.
            conn.execute(
                "UPDATE source_subscriptions SET boundary='none', updated_at_ms=? WHERE source_id=?",
                (now, source_id))
            return {"boundary": "resume", "enrolled": 0}
        # Contract table, "Later normal snapshot while on": newly observed valid
        # entries get future eligibility; staged partial observations qualify only
        # when their first-seen epoch is current and their prospective revision was
        # not yet committed.
        rows = conn.execute(
            "SELECT item_id FROM source_items WHERE source_id=? AND state='observed' "
            "AND eligibility='none' AND first_seen_consent_epoch=? AND first_scan_revision>=?",
            (source_id, epoch, scan_revision)).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE source_items SET eligibility='future', enrolled_epoch=?, state='eligible' "
                "WHERE item_id=?", (epoch, row[0]))
        return {"boundary": "none", "enrolled": len(rows)}

    @endpoint
    def refresh_source(self, context, args):
        """Manual refresh through the same due-time/lease gate. Not due returns
        ``not_due`` with the persisted due time (contract, scheduler section)."""
        if set(args) - {"source_id"} or type(args.get("source_id")) is not str \
                or not _SOURCE_ID_RE.match(args["source_id"]):
            fail("validation_error", "source_id is required")
        now = self._now()
        with self.store.read() as conn:
            source = self._source(conn, args["source_id"])
            cursor = self._cursor(conn, source["source_id"])
        if source["archived"] or not source["detection_enabled"]:
            return success(source_id=source["source_id"], outcome="detection_disabled",
                           next_poll_at_ms=int(cursor["next_poll_at_ms"]))
        if int(cursor["next_poll_at_ms"]) > now or (
                cursor["poll_owner_token"] and int(cursor["poll_lease_expires_ms"]) > now):
            return success(source_id=source["source_id"], outcome="not_due",
                           next_poll_at_ms=int(cursor["next_poll_at_ms"]),
                           poll_in_progress=bool(cursor["poll_owner_token"]))
        claim = self.claim_poll(source["source_id"], now)
        if claim is None:
            with self.store.read() as conn:
                fresh = self._cursor(conn, source["source_id"])
            return success(source_id=source["source_id"], outcome="not_due",
                           next_poll_at_ms=int(fresh["next_poll_at_ms"]))
        result = self.run_claimed_poll(claim)
        return success(source_id=source["source_id"], outcome=result.get("outcome"),
                       poll=result)

    # ======================================================================
    # Capture ledger (contract, "Atomic starts, failure, and restart")
    # ======================================================================
    def capture_pass(self, now: int | None = None, *, limit: int = 1) -> list[dict]:
        """Bounded reconciliation, then advance at most ``limit`` starts across
        sources. Independent of detection: an exhausted allowance never stops
        polling, and a poll failure never erases eligible work."""
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            self._reconcile_reservations(conn, now)
        with self.store.read() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT source_id FROM source_subscriptions WHERE archived=0 AND consent_state='on' "
                "AND boundary='none' AND capture_not_before_ms<=? AND accounting_hold_until_ms<=? "
                "ORDER BY capture_not_before_ms, source_id", (now, now)).fetchall()]
        outcomes = []
        for source_id in ids:
            if len(outcomes) >= limit:
                break
            outcome = self.advance_source(source_id)
            if outcome.get("outcome") not in ("idle", "not_due", "in_flight", "allowance_exhausted",
                                              "consent_off", "enrollment_pending",
                                              "legacy_accounting_hold", "clock_regressed"):
                outcomes.append(outcome)
        return outcomes

    def advance_source(self, source_id: str, item_id: str | None = None) -> dict:
        """Claim, preflight, start and execute at most one capture for a source."""
        try:
            return self._advance_source(source_id, item_id)
        except (ServiceError, sqlite3.OperationalError) as exc:
            log.warning("capture advance for %s deferred: %s", source_id, type(exc).__name__)
            return {"outcome": "storage_busy", "retryable": True, "source_id": source_id}

    def _advance_source(self, source_id: str, item_id: str | None) -> dict:
        claim = self.claim_start(source_id, item_id=item_id)
        if claim.get("outcome") != "reserved":
            return claim
        preflight = self._preflight(claim)
        if preflight is not None:
            return preflight
        started = self.mark_started(claim["start_id"], claim["owner_token"])
        if started.get("outcome") == "day_rollover":
            # Contract: release the old-day row and claim a new row for today.
            claim = self.claim_start(source_id, item_id=claim["item_id"])
            if claim.get("outcome") != "reserved":
                return claim
            started = self.mark_started(claim["start_id"], claim["owner_token"])
        if started.get("outcome") != "started":
            return started
        return self.execute_started(started)

    def _pick_item(self, conn, source: dict, item_id: str | None, now: int) -> dict | None:
        sql = ("SELECT * FROM source_items WHERE source_id=? AND state='eligible' "
               "AND eligibility!='none' AND actual_starts<? AND preflight_failures<? "
               "AND (retry_at_ms IS NULL OR retry_at_ms<=?)")
        params: list[Any] = [source["source_id"], MAX_ACTUAL_STARTS, PREFLIGHT_BLOCK_AFTER, now]
        if item_id is not None:
            sql += " AND item_id=?"
            params.append(item_id)
        sql += (" ORDER BY (published_at_ms IS NULL), published_at_ms DESC, first_seen_ms DESC, "
                "entry_id ASC LIMIT 1")
        return _row(conn.execute(sql, params).fetchone())

    def claim_start(self, source_id: str, *, item_id: str | None = None,
                    now: int | None = None) -> dict:
        """No row -> ``reserved``: hold one current-day slot with a fresh read of
        consent, epoch, boundary, due time, item eligibility, attempt limit,
        existing corpus identity and active reservations, under BEGIN IMMEDIATE."""
        now = self._now() if now is None else int(now)
        token = _new_token()
        try:
            with self.store.write() as conn:
                source = self._source(conn, source_id)
                base = {"source_id": source_id}
                if self._clock_regressed(source, now):
                    return {"outcome": "clock_regressed", **base}
                self._touch_observed(conn, source, now)
                if source["archived"] or source["consent_state"] != "on":
                    return {"outcome": "consent_off", **base}
                if int(source["accounting_hold_until_ms"]) > now:
                    # Contract, import: hold new starts until the next UTC day after
                    # cutover; reported separately from the ledger's counts.
                    return {"outcome": "legacy_accounting_hold",
                            "hold_until_ms": int(source["accounting_hold_until_ms"]), **base}
                if source["boundary"] != "none":
                    return {"outcome": "enrollment_pending", "boundary": source["boundary"], **base}
                if int(source["capture_not_before_ms"]) > now:
                    return {"outcome": "not_due",
                            "capture_not_before_ms": int(source["capture_not_before_ms"]), **base}
                active = self._in_flight(conn, source_id)
                if active:
                    return {"outcome": "in_flight", "start_id": active[0]["start_id"],
                            "state": active[0]["state"], **base}
                item = self._pick_item(conn, source, item_id, now)
                if item is None:
                    return {"outcome": "idle", **base}
                linked = self._link_if_captured(conn, source, item, now)
                if linked is not None:
                    return {"outcome": "linked", "item_id": item["item_id"], "video_id": linked, **base}
                elsewhere = conn.execute(
                    "SELECT source_id, start_id FROM source_capture_starts WHERE capture_key=? "
                    "AND state IN ('reserved','started','uncertain')", (item["capture_key"],)).fetchone()
                if elsewhere is not None:
                    # Contract: keep the observation eligible; charge only the winner.
                    conn.execute(
                        "UPDATE source_items SET blocked_reason='capture_in_progress_elsewhere' "
                        "WHERE item_id=?", (item["item_id"],))
                    return {"outcome": "capture_in_progress_elsewhere", "item_id": item["item_id"],
                            "owner_source_id": elsewhere[0], **base}
                day = utc_day(now)
                occupied = {int(r[0]) for r in conn.execute(
                    "SELECT slot FROM source_capture_starts WHERE source_id=? AND utc_day=? "
                    "AND state!='released'", (source_id, day)).fetchall()}
                slot = next((s for s in range(1, DAILY_START_CAP + 1) if s not in occupied), None)
                if slot is None:
                    return {"outcome": "allowance_exhausted", "utc_day": day, **base}
                start_id = "st_" + secrets.token_hex(16)
                conn.execute(
                    "INSERT INTO source_capture_starts (start_id, source_id, item_id, capture_key, "
                    "consent_epoch, utc_day, slot, state, reserved_at_ms, reservation_expires_ms, "
                    "owner_token, owner_instance) VALUES (?,?,?,?,?,?,?,'reserved',?,?,?,?)",
                    (start_id, source_id, item["item_id"], item["capture_key"],
                     int(source["consent_epoch"]), day, slot, now, now + RESERVATION_TTL_MS,
                     token, self.instance_id))
                conn.execute(
                    "UPDATE source_items SET state='reserved', blocked_reason=NULL WHERE item_id=?",
                    (item["item_id"],))
                return {"outcome": "reserved", "start_id": start_id, "owner_token": token,
                        "item_id": item["item_id"], "capture_key": item["capture_key"],
                        "slot": slot, "utc_day": day, "consent_epoch": int(source["consent_epoch"]),
                        "reserved_at_ms": now, "reservation_expires_ms": now + RESERVATION_TTL_MS,
                        **base}
        except sqlite3.IntegrityError as exc:
            # The partial unique indexes are the backstop: another writer took the
            # slot or the capture key between our read and insert.
            return {"outcome": "storage_busy", "retryable": True, "source_id": source_id,
                    "detail": type(exc).__name__}
        except ServiceError as exc:
            return {"outcome": exc.code, "retryable": exc.retryable, "source_id": source_id,
                    "message": exc.message}

    def _link_if_captured(self, conn, source: dict, item: dict, now: int) -> str | None:
        """An already committed corpus item is linked before reservation, with no
        charge; a deleted committed item is never resurrected."""
        state, video_id, committed_at = self._preexisting_capture(
            conn, source, item["capture_key"], item["entry_id"], now)
        if state == "committed":
            conn.execute(
                "UPDATE source_items SET state='committed', video_id=?, committed_at_ms=?, "
                "blocked_reason=NULL, retry_at_ms=NULL WHERE item_id=?",
                (video_id, committed_at or now, item["item_id"]))
            return video_id
        if state == "deleted":
            conn.execute(
                "UPDATE source_items SET state='deleted', video_id=?, blocked_reason='deleted' "
                "WHERE item_id=?", (video_id, item["item_id"]))
            return video_id or ""
        backend_video = self.backend.published_video_id(conn, item, source)
        if backend_video:
            conn.execute(
                "UPDATE source_items SET state='committed', video_id=?, committed_at_ms=?, "
                "blocked_reason=NULL, retry_at_ms=NULL WHERE item_id=?",
                (backend_video, now, item["item_id"]))
            return backend_video
        return None

    def _preflight(self, claim: dict) -> dict | None:
        """Local checks before any start; failures release the slot and never
        count as actual attempts (contract, retry paragraph)."""
        with self.store.read() as conn:
            item = self._item(conn, claim["item_id"])
            source = self._source(conn, claim["source_id"])
        try:
            outcome = self.backend.preflight(item, source)
        except Exception as exc:
            log.exception("preflight raised for %s", claim["item_id"])
            outcome = CaptureOutcome("preflight_failed", code="preflight_error",
                                     message=type(exc).__name__)
        if outcome is None or outcome.status != "preflight_failed":
            return None
        return self.release_reservation(claim["start_id"], claim["owner_token"],
                                        f"preflight:{outcome.code or 'failed'}",
                                        terminal=outcome.terminal, preflight=True)

    def release_reservation(self, start_id: str, owner_token: str, code: str, *,
                            terminal: bool = False, preflight: bool = False,
                            now: int | None = None) -> dict:
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            start = self._start(conn, start_id)
            if start is None or start["owner_token"] != owner_token:
                return {"outcome": "not_owner", "start_id": start_id}
            if start["state"] != "reserved":
                return {"outcome": "not_reserved", "state": start["state"], "start_id": start_id}
            self._release(conn, start, now, code)
            if preflight:
                item = self._item(conn, start["item_id"])
                failures = int(item["preflight_failures"]) + 1
                if terminal:
                    # Contract: terminal errors remain visible and blocked.
                    conn.execute(
                        "UPDATE source_items SET state='failed', blocked_reason=?, "
                        "preflight_failures=? WHERE item_id=?", (code, failures, item["item_id"]))
                else:
                    conn.execute(
                        "UPDATE source_items SET preflight_failures=?, blocked_reason=? "
                        "WHERE item_id=?",
                        (failures, code if failures >= PREFLIGHT_BLOCK_AFTER else None,
                         item["item_id"]))
            return {"outcome": "released", "code": code, "start_id": start_id,
                    "item_id": start["item_id"], "source_id": start["source_id"]}

    def mark_started(self, start_id: str, owner_token: str, now: int | None = None) -> dict:
        """``reserved`` -> ``started``: recheck consent, epoch, UTC day, item and
        owner in one write transaction; bind the backend identity; set
        ``started_at_ms`` exactly once and commit before dispatch."""
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            start = self._start(conn, start_id)
            if start is None or start["owner_token"] != owner_token:
                return {"outcome": "not_owner", "start_id": start_id}
            if start["state"] != "reserved":
                return {"outcome": "not_reserved", "state": start["state"], "start_id": start_id}
            source = self._source(conn, start["source_id"])
            item = self._item(conn, start["item_id"])
            base = {"start_id": start_id, "source_id": start["source_id"], "item_id": start["item_id"]}
            if source["archived"] or source["consent_state"] != "on" \
                    or int(source["consent_epoch"]) != int(start["consent_epoch"]):
                self._release(conn, start, now, "consent_off")
                return {"outcome": "released", "code": "consent_off", **base}
            if now >= int(start["reservation_expires_ms"]):
                self._release(conn, start, now, "expired")
                return {"outcome": "released", "code": "expired", **base}
            if now < int(start["reserved_at_ms"]) or self._clock_regressed(source, now):
                # A start can never precede its reservation; wait for the clock.
                return {"outcome": "clock_regressed", **base}
            if utc_day(now) != start["utc_day"]:
                self._release(conn, start, now, "day_rollover")
                return {"outcome": "day_rollover", **base}
            if item is None or item["state"] != "reserved" or item["capture_key"] != start["capture_key"]:
                self._release(conn, start, now, "item_mismatch")
                return {"outcome": "released", "code": "item_mismatch", **base}
            if int(item["actual_starts"]) >= MAX_ACTUAL_STARTS:
                self._release(conn, start, now, "attempts_exhausted")
                return {"outcome": "released", "code": "attempts_exhausted", **base}
            backend_id = self.backend.bind(conn, dict(start), dict(item), dict(source))
            if type(backend_id) is not str or not backend_id:
                self._release(conn, start, now, "backend_bind_failed")
                return {"outcome": "released", "code": "backend_bind_failed", **base}
            conn.execute(
                "UPDATE source_capture_starts SET state='started', started_at_ms=?, backend_kind=?, "
                "backend_id=? WHERE start_id=?",
                (now, self.backend.kind, backend_id, start_id))
            conn.execute(
                "UPDATE source_items SET state='started', actual_starts=actual_starts+1, "
                "retry_at_ms=NULL, blocked_reason=NULL WHERE item_id=?", (item["item_id"],))
            # Contract: at most one new start per source per configured interval,
            # measured from its last started transition.
            conn.execute(
                "UPDATE source_subscriptions SET capture_not_before_ms=?, updated_at_ms=? "
                "WHERE source_id=?",
                (now + int(source["poll_interval_min"]) * 60_000, now, source["source_id"]))
            start = self._start(conn, start_id)
            item = self._item(conn, item["item_id"])
            return {"outcome": "started", "owner_token": owner_token, "start": start,
                    "item": item, "source": source, **base}

    def execute_started(self, started: dict) -> dict:
        start, item, source = started["start"], started["item"], started["source"]
        token = started["owner_token"]
        try:
            outcome = self.backend.run(dict(start), dict(item), dict(source))
        except Exception as exc:
            log.exception("capture backend raised for %s", start["start_id"])
            outcome = CaptureOutcome("failed", code="backend_error", message=type(exc).__name__)
        return self.apply_outcome(start["start_id"], token, outcome)

    def apply_outcome(self, start_id: str, owner_token: str, outcome: CaptureOutcome) -> dict:
        if outcome.status == "succeeded":
            return self.complete_capture(start_id, owner_token, outcome.video_id or "")
        if outcome.status == "failed":
            return self.fail_capture(start_id, owner_token, outcome.code or "download_failed",
                                     terminal=outcome.terminal)
        if outcome.status == "uncertain":
            return self.mark_uncertain(start_id, owner_token)
        if outcome.status == "in_flight":
            return {"outcome": "in_flight", "start_id": start_id}
        return self.fail_capture(start_id, owner_token, outcome.code or "unknown_outcome")

    def complete_capture(self, start_id: str, owner_token: str, video_id: str,
                         now: int | None = None) -> dict:
        """``started``/``uncertain`` -> ``succeeded`` after publication committed:
        one write transaction marks the item committed, the ledger succeeded,
        links every matching observation and inserts the outbox row."""
        now = self._now() if now is None else int(now)
        if type(video_id) is not str or not video_id.strip():
            return self.fail_capture(start_id, owner_token, "publication_without_identity", now=now)
        with self.store.write() as conn:
            start = self._start(conn, start_id)
            if start is None or start["owner_token"] != owner_token:
                return {"outcome": "not_owner", "start_id": start_id}
            if start["state"] == "succeeded" and start["video_id"] == video_id:
                return {"outcome": "succeeded", "start_id": start_id, "video_id": video_id,
                        "idempotent": True}
            if start["state"] not in ("started", "uncertain"):
                return {"outcome": "not_started", "state": start["state"], "start_id": start_id}
            conn.execute(
                "UPDATE source_capture_starts SET state='succeeded', finished_at_ms=?, video_id=? "
                "WHERE start_id=?", (now, video_id, start_id))
            conn.execute(
                "UPDATE source_items SET state='committed', video_id=?, committed_at_ms=?, "
                "blocked_reason=NULL, retry_at_ms=NULL WHERE item_id=?",
                (video_id, now, start["item_id"]))
            # Contract: link all matching observations without starting or charging.
            conn.execute(
                "UPDATE source_items SET state='committed', video_id=?, committed_at_ms=?, "
                "blocked_reason=NULL, retry_at_ms=NULL WHERE capture_key=? "
                "AND state IN ('observed','eligible')", (video_id, now, start["capture_key"]))
            # Contract, "Post-commit classification handoff": INSERT OR IGNORE.
            conn.execute(
                "INSERT OR IGNORE INTO source_classification_outbox (capture_key, video_id, "
                "committed_at_ms, state, updated_at_ms) VALUES (?,?,?,'pending',?)",
                (start["capture_key"], video_id, now, now))
            return {"outcome": "succeeded", "start_id": start_id, "item_id": start["item_id"],
                    "source_id": start["source_id"], "video_id": video_id}

    def fail_capture(self, start_id: str, owner_token: str, code: str, *,
                     terminal: bool = False, now: int | None = None) -> dict:
        """``started``/``uncertain`` -> ``failed``: release active ownership, retain
        the day's charge, record retry eligibility (contract ledger table)."""
        now = self._now() if now is None else int(now)
        with self.store.write() as conn:
            start = self._start(conn, start_id)
            if start is None or start["owner_token"] != owner_token:
                return {"outcome": "not_owner", "start_id": start_id}
            if start["state"] not in ("started", "uncertain"):
                return {"outcome": "not_started", "state": start["state"], "start_id": start_id}
            conn.execute(
                "UPDATE source_capture_starts SET state='failed', finished_at_ms=?, "
                "release_or_failure_code=? WHERE start_id=?", (now, sanitize_message(code)[:80], start_id))
            item = self._item(conn, start["item_id"])
            attempts = int(item["actual_starts"])
            retry_at = None
            if terminal:
                conn.execute(
                    "UPDATE source_items SET state='failed', blocked_reason=?, retry_at_ms=NULL "
                    "WHERE item_id=?", (code, item["item_id"]))
            elif attempts >= MAX_ACTUAL_STARTS:
                conn.execute(
                    "UPDATE source_items SET state='failed', blocked_reason='attempts_exhausted', "
                    "retry_at_ms=NULL WHERE item_id=?", (item["item_id"],))
            else:
                # Contract: wait 15 minutes after attempt one, 60 after attempt two.
                retry_at = now + RETRY_WAIT_MS[min(attempts - 1, len(RETRY_WAIT_MS) - 1)]
                conn.execute(
                    "UPDATE source_items SET state='eligible', blocked_reason=?, retry_at_ms=? "
                    "WHERE item_id=?", (code, retry_at, item["item_id"]))
            return {"outcome": "failed", "start_id": start_id, "item_id": item["item_id"],
                    "source_id": start["source_id"], "code": code, "terminal": terminal,
                    "attempts": attempts, "retry_at_ms": retry_at}

    def mark_uncertain(self, start_id: str, owner_token: str, now: int | None = None) -> dict:
        """``started`` -> ``uncertain``: retain ownership and the charge until
        reconciled (contract ledger table)."""
        with self.store.write() as conn:
            start = self._start(conn, start_id)
            if start is None or start["owner_token"] != owner_token:
                return {"outcome": "not_owner", "start_id": start_id}
            if start["state"] == "uncertain":
                return {"outcome": "uncertain", "start_id": start_id}
            if start["state"] != "started":
                return {"outcome": "not_started", "state": start["state"], "start_id": start_id}
            conn.execute("UPDATE source_capture_starts SET state='uncertain' WHERE start_id=?",
                         (start_id,))
            conn.execute("UPDATE source_items SET state='uncertain' WHERE item_id=?",
                         (start["item_id"],))
            return {"outcome": "uncertain", "start_id": start_id, "item_id": start["item_id"]}

    def _reconcile_reservations(self, conn, now: int) -> int:
        rows = conn.execute(
            "SELECT st.*, s.consent_state, s.archived, s.consent_epoch AS source_epoch "
            "FROM source_capture_starts st JOIN source_subscriptions s ON s.source_id=st.source_id "
            "WHERE st.state='reserved'").fetchall()
        released = 0
        for raw in rows:
            row = dict(raw)
            if now >= int(row["reservation_expires_ms"]):
                code = "expired"
            elif utc_day(now) != row["utc_day"]:
                code = "day_rollover"
            elif row["archived"] or row["consent_state"] != "on":
                code = "consent_off"
            elif int(row["consent_epoch"]) != int(row["source_epoch"]):
                code = "consent_epoch_changed"
            else:
                continue
            self._release(conn, row, now, code)
            released += 1
        return released

    # ======================================================================
    # Restart reconciliation (contract, "Atomic starts", restart list)
    # ======================================================================
    def reconcile_on_startup(self, now: int | None = None) -> dict:
        now = self._now() if now is None else int(now)
        report = {"released": 0, "leases_expired": 0, "succeeded": 0, "failed": 0,
                  "uncertain": 0, "outbox_repaired": 0}
        with self.store.write() as conn:
            # 1-2. Committed rows are durable; release expired/old-day/old-epoch rows.
            report["released"] = self._reconcile_reservations(conn, now)
            report["leases_expired"] = self._expire_poll_leases(conn, now)
        with self.store.read() as conn:
            started = [dict(r) for r in conn.execute(
                "SELECT st.*, s.kind, s.source_key FROM source_capture_starts st "
                "JOIN source_subscriptions s ON s.source_id=st.source_id "
                "WHERE st.state IN ('started','uncertain') ORDER BY st.started_at_ms").fetchall()]
        for start in started:
            report[self._reconcile_started_row(start, now)] += 1
        with self.store.write() as conn:
            # 5. Reconcile committed captures whose classification handoff is missing.
            rows = conn.execute(
                "SELECT st.capture_key, st.video_id, st.finished_at_ms FROM source_capture_starts st "
                "LEFT JOIN source_classification_outbox o ON o.capture_key=st.capture_key "
                "WHERE st.state='succeeded' AND st.video_id IS NOT NULL AND o.capture_key IS NULL").fetchall()
            for row in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO source_classification_outbox (capture_key, video_id, "
                    "committed_at_ms, state, updated_at_ms) VALUES (?,?,?,'pending',?)",
                    (row[0], row[1], row[2] or now, now))
                report["outbox_repaired"] += int(cur.rowcount or 0)
        return report

    def _reconcile_started_row(self, start: dict, now: int) -> str:
        """Steps 3-4 of restart reconciliation for one started/uncertain row.
        Returns ``succeeded``, ``failed`` or ``uncertain``. A fenced recovery
        action: it verifies committed artifacts or a provably stopped owner and
        never starts a replacement because a lease expired."""
        with self.store.read() as conn:
            item = self._item(conn, start["item_id"])
            source = self._source(conn, start["source_id"])
            expected = start.get("video_id") or self._corpus_video_id(source, item["entry_id"])
            corpus = self._corpus_row(conn, expected)
        if corpus is not None and not corpus.get("deleted_at"):
            self.complete_capture(start["start_id"], start["owner_token"], corpus["video_id"], now=now)
            return "succeeded"
        try:
            probe = self.backend.probe(start)
        except Exception:
            log.exception("backend probe raised for %s", start["start_id"])
            probe = "unknown"
        if probe == "stopped":
            self.fail_capture(start["start_id"], start["owner_token"], "worker_lost", now=now)
            return "failed"
        self.mark_uncertain(start["start_id"], start["owner_token"], now=now)
        return "uncertain"

    def reconcile_start(self, start_id: str, now: int | None = None) -> dict:
        """Trusted recovery for one ledger row (a resumed job that lost its
        in-memory owner token). Reads the row's own token; never a client input."""
        now = self._now() if now is None else int(now)
        with self.store.read() as conn:
            start = self._start(conn, start_id)
        if start is None:
            return {"outcome": "not_found", "start_id": start_id}
        if start["state"] not in ("started", "uncertain"):
            return {"outcome": start["state"], "start_id": start_id}
        return {"outcome": self._reconcile_started_row(start, now), "start_id": start_id}

    def note_corpus_deleted(self, video_ids, now: int | None = None) -> int:
        """Corpus deletion marks every matching observation deleted; the
        successful capture-key record stays as a tombstone (contract)."""
        now = self._now() if now is None else int(now)
        ids = [v for v in video_ids if isinstance(v, str) and v]
        if not ids:
            return 0
        with self.store.write() as conn:
            total = 0
            for video_id in ids:
                cur = conn.execute(
                    "UPDATE source_items SET state='deleted', blocked_reason='deleted' "
                    "WHERE video_id=? AND state='committed'", (video_id,))
                total += int(cur.rowcount or 0)
            return total

    # ======================================================================
    # Legacy import (contract, "Migration 0028 schema", import paragraphs)
    # ======================================================================
    def import_legacy_registries(self, now: int | None = None) -> dict:
        """Idempotent application-level conversion of podcast_feeds and
        monitored_playlists. Explicit podcast opt-in transfers as ``on`` with a
        ``legacy_explicit_opt_in`` receipt and an initial boundary; playlists are
        always off; every imported source holds new starts until the next UTC
        day. Reruns never touch an already imported source."""
        now = self._now() if now is None else int(now)
        report = {"feeds_imported": 0, "playlists_imported": 0, "items_imported": 0,
                  "conflicts": [], "skipped": 0}
        hold_until = next_utc_midnight_ms(now)
        with self.store.write() as conn:
            for feed in self._legacy_rows(conn, "podcast_feeds"):
                self._import_feed(conn, feed, now, hold_until, report)
            for playlist in self._legacy_rows(conn, "monitored_playlists"):
                self._import_playlist(conn, playlist, now, hold_until, report)
        return report

    @staticmethod
    def _legacy_rows(conn, table: str) -> list[dict]:
        try:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]
        except sqlite3.OperationalError:
            return []

    def _import_feed(self, conn, feed: dict, now: int, hold_until: int, report: dict) -> None:
        if conn.execute("SELECT 1 FROM source_subscriptions WHERE legacy_feed_id=?",
                        (feed["id"],)).fetchone():
            report["skipped"] += 1
            return
        try:
            source_key, canonical_url = parse_source_url("podcast_rss", feed["feed_url"])
        except ServiceError as exc:
            report["conflicts"].append({"table": "podcast_feeds", "id": feed["id"], "reason": exc.code})
            return
        source_id = source_identity("podcast_rss", source_key)
        if conn.execute("SELECT 1 FROM source_subscriptions WHERE source_id=?", (source_id,)).fetchone():
            report["conflicts"].append({"table": "podcast_feeds", "id": feed["id"],
                                        "reason": "duplicate_identity"})
            return
        self._insert_source(
            conn, source_id=source_id, kind="podcast_rss", source_key=source_key,
            canonical_url=canonical_url, display_name=_safe_text(feed.get("title"), 200),
            interval=feed.get("poll_interval_min") or DEFAULT_POLL_INTERVAL_MIN, now=now,
            detection_enabled=bool(feed.get("enabled", 1)), legacy_feed_id=feed["id"],
            etag=feed.get("last_etag"), last_modified=feed.get("last_modified"),
            hold_until_ms=hold_until)
        if feed.get("auto_ingest"):
            # Contract: an existing auto_ingest=1 is an explicit opt-in; preserve it
            # as on with a legacy receipt and the initial boundary pending.
            source = self._source(conn, source_id)
            self._transition_consent(
                conn, source, "on", now, authority="legacy_explicit_opt_in",
                operation_key=f"legacy-feed-{feed['id']}",
                request_hash=digest({"legacy_feed_id": feed["id"], "auto_ingest": 1}),
                session_hash="legacy_import")
        try:
            episodes = [dict(r) for r in conn.execute(
                "SELECT * FROM podcast_episodes WHERE feed_id=? ORDER BY id", (feed["id"],)).fetchall()]
        except sqlite3.OperationalError:
            episodes = []
        for episode in episodes:
            entry_id = validate_entry_id(episode.get("guid"))
            if entry_id is None:
                report["conflicts"].append({"table": "podcast_episodes", "id": episode["id"],
                                            "reason": "invalid_identity"})
                continue
            capture_key = capture_key_for("podcast_rss", source_key, entry_id)
            state = "observed"
            video_id = episode.get("yoink_video_id")
            committed_at = None
            if video_id:
                state = "committed"
                committed_at = now
            elif episode.get("status") == "ignored":
                state = "failed"
            seen = parse_published_ms(episode.get("discovered_at")) or now
            conn.execute(
                "INSERT OR IGNORE INTO source_items (item_id, source_id, entry_id, capture_key, "
                "canonical_url, title, published_at_ms, first_seen_ms, last_seen_ms, "
                "first_scan_revision, first_seen_consent_epoch, metadata_json, legacy_episode_id, "
                "eligibility, enrolled_epoch, state, video_id, committed_at_ms, blocked_reason) "
                "VALUES (?,?,?,?,?,?,?,?,?,0,NULL,?,?,'none',NULL,?,?,?,?)",
                (item_identity(source_id, entry_id), source_id, entry_id, capture_key,
                 _http_link(episode.get("episode_page_url")), _safe_text(episode.get("title")),
                 parse_published_ms(episode.get("published_at")), seen, seen,
                 canonical_json({"identity_method": "guid", "legacy": True,
                                 "audio_url": _http_link(episode.get("audio_url"))}),
                 episode["id"], state, video_id, committed_at,
                 "ignored" if state == "failed" else None))
            report["items_imported"] += 1
        report["feeds_imported"] += 1

    def _import_playlist(self, conn, playlist: dict, now: int, hold_until: int, report: dict) -> None:
        if conn.execute("SELECT 1 FROM source_subscriptions WHERE legacy_playlist_id=?",
                        (playlist["id"],)).fetchone():
            report["skipped"] += 1
            return
        try:
            source_key, canonical_url = parse_source_url("youtube_playlist", playlist["playlist_url"])
        except ServiceError as exc:
            report["conflicts"].append({"table": "monitored_playlists", "id": playlist["id"],
                                        "reason": exc.code})
            return
        source_id = source_identity("youtube_playlist", source_key)
        if conn.execute("SELECT 1 FROM source_subscriptions WHERE source_id=?", (source_id,)).fetchone():
            report["conflicts"].append({"table": "monitored_playlists", "id": playlist["id"],
                                        "reason": "duplicate_identity"})
            return
        # Contract: never infer playlist consent from enabled=1 or a taste flag;
        # shorter legacy intervals normalize to the 15-minute floor.
        self._insert_source(
            conn, source_id=source_id, kind="youtube_playlist", source_key=source_key,
            canonical_url=canonical_url, display_name=_safe_text(playlist.get("name"), 200),
            interval=max(MIN_POLL_INTERVAL_MIN, int(playlist.get("poll_interval_min") or 0)),
            now=now, detection_enabled=bool(playlist.get("enabled", 1)),
            legacy_playlist_id=playlist["id"], hold_until_ms=hold_until)
        try:
            seen_ids = json.loads(playlist.get("last_seen_video_ids") or "[]")
        except (TypeError, ValueError):
            seen_ids = []
        for video_id in seen_ids if isinstance(seen_ids, list) else []:
            if not isinstance(video_id, str) or not _VIDEO_ID_RE.match(video_id):
                continue
            corpus = self._corpus_row(conn, video_id)
            state = "observed"
            committed_at = None
            linked = None
            if corpus is not None:
                state = "deleted" if corpus.get("deleted_at") else "committed"
                linked = corpus["video_id"]
                committed_at = None if state == "deleted" else now
            conn.execute(
                "INSERT OR IGNORE INTO source_items (item_id, source_id, entry_id, capture_key, "
                "canonical_url, title, published_at_ms, first_seen_ms, last_seen_ms, "
                "first_scan_revision, first_seen_consent_epoch, metadata_json, eligibility, "
                "enrolled_epoch, state, video_id, committed_at_ms) "
                "VALUES (?,?,?,?,?,NULL,NULL,?,?,0,NULL,?,'none',NULL,?,?,?)",
                (item_identity(source_id, video_id), source_id, video_id,
                 capture_key_for("youtube_playlist", source_key, video_id), video_watch_url(video_id),
                 now, now, canonical_json({"identity_method": "legacy_cursor", "legacy": True}),
                 state, linked, committed_at))
            report["items_imported"] += 1
        report["playlists_imported"] += 1

    # ======================================================================
    # Post-commit classification handoff (contract section of that name)
    # ======================================================================
    @endpoint
    def configure_classification_policy(self, context, args):
        """Trusted operator only; source consent can never set this singleton."""
        if getattr(context, "operator", False) is not True:
            fail("user_intent_required", "Trusted local operator required")
        if set(args) != {"version_id", "prompt_hash"} or type(args["version_id"]) is not str \
                or type(args["prompt_hash"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", args["prompt_hash"]):
            fail("validation_error", "version_id and a 64-hex prompt_hash are required")
        now = self._now()
        with self.store.write() as conn:
            version = _row(conn.execute("SELECT status FROM shelf_versions WHERE version_id=?",
                                        (args["version_id"],)).fetchone())
            if version is None or version["status"] not in ("approved", "active"):
                fail("validation_error", "An approved or active taxonomy version is required")
            conn.execute(
                "INSERT INTO source_classification_policy (singleton, version_id, prompt_hash, "
                "configured_by, configured_at_ms) VALUES (1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE "
                "SET version_id=excluded.version_id, prompt_hash=excluded.prompt_hash, "
                "configured_by=excluded.configured_by, configured_at_ms=excluded.configured_at_ms",
                (args["version_id"], args["prompt_hash"], "operator", now))
            # A waiting handoff becomes dispatchable again.
            conn.execute(
                "UPDATE source_classification_outbox SET state='pending', updated_at_ms=? "
                "WHERE state='waiting_configuration'", (now,))
        return success(version_id=args["version_id"], prompt_hash=args["prompt_hash"],
                       configured_at_ms=now)

    def dispatch_classification_outbox(self, now: int | None = None, *, limit: int = 10) -> list[dict]:
        """Deterministic local service calls only: freeze the binding, call the
        existing ``prepare_run`` outside the transaction, verify, mark enqueued."""
        now = self._now() if now is None else int(now)
        with self.store.read() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM source_classification_outbox WHERE state='pending' "
                "ORDER BY committed_at_ms, capture_key LIMIT ?", (int(limit),)).fetchall()]
        return [self._dispatch_outbox_row(row, now) for row in rows]

    def _outbox_update(self, conn, capture_key: str, now: int, **fields) -> None:
        sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at_ms=?"
        conn.execute(f"UPDATE source_classification_outbox SET {sets} WHERE capture_key=?",
                     (*fields.values(), now, capture_key))

    def _dispatch_outbox_row(self, row: dict, now: int) -> dict:
        capture_key, video_id = row["capture_key"], row["video_id"]
        base = {"capture_key": capture_key, "video_id": video_id}
        try:
            with self.store.write() as conn:
                current = _row(conn.execute(
                    "SELECT * FROM source_classification_outbox WHERE capture_key=?",
                    (capture_key,)).fetchone())
                if current is None or current["state"] != "pending":
                    return {"outcome": "skipped", **base}
                policy = _row(conn.execute(
                    "SELECT * FROM source_classification_policy WHERE singleton=1").fetchone())
                if policy is None:
                    # Step 1: no policy means waiting_configuration, visible with the item.
                    self._outbox_update(conn, capture_key, now, state="waiting_configuration",
                                        last_error_code="no_policy")
                    return {"outcome": "waiting_configuration", **base}
                version = _row(conn.execute("SELECT status FROM shelf_versions WHERE version_id=?",
                                            (policy["version_id"],)).fetchone())
                if version is None or version["status"] not in ("approved", "active"):
                    self._outbox_update(conn, capture_key, now, state="waiting_configuration",
                                        last_error_code="taxonomy_not_approved")
                    return {"outcome": "waiting_configuration", **base}
                item = _row(conn.execute("SELECT * FROM yoinks WHERE video_id=? AND deleted_at IS NULL",
                                         (video_id,)).fetchone())
                if item is None:
                    self._outbox_update(conn, capture_key, now, state="blocked",
                                        last_error_code="item_deleted")
                    return {"outcome": "blocked", "code": "item_deleted", **base}
                import library_cards
                clips = [dict(c) for c in conn.execute(
                    "SELECT * FROM clips WHERE video_id=? ORDER BY seq", (video_id,)).fetchall()]
                card = library_cards.build_card(
                    item, clips, profile="librarian",
                    corpus_text=library_cards.read_corpus_head(item.get("corpus_path")))
                # Step 2: freeze the binding and the deterministic run id.
                run_id = classification_run_id(capture_key)
                if current["run_id"] is None:
                    self._outbox_update(conn, capture_key, now, run_id=run_id,
                                        version_id=policy["version_id"],
                                        prompt_hash=policy["prompt_hash"],
                                        source_revision=card["source_revision"])
                    frozen = {"run_id": run_id, "version_id": policy["version_id"],
                              "prompt_hash": policy["prompt_hash"],
                              "source_revision": card["source_revision"]}
                else:
                    frozen = {k: current[k] for k in ("run_id", "version_id", "prompt_hash", "source_revision")}
        except sqlite3.OperationalError as exc:
            log.warning("outbox dispatch storage unavailable for %s: %s", capture_key, type(exc).__name__)
            return {"outcome": "service_unavailable", **base}
        # Step 3: outside the write transaction, the existing Phase 2 service.
        result = self._prepare_run(frozen, video_id)
        code = None if result.get("ok") else (result.get("error") or {}).get("code", "service_unavailable")
        if code not in (None, "idempotency_conflict"):
            with self.store.write() as conn:
                state = "waiting_configuration" if code in ("taxonomy_conflict",) else "pending"
                self._outbox_update(conn, capture_key, now, state=state, last_error_code=code)
            return {"outcome": state, "code": code, **base}
        # Step 4: verify the run before adopting it.
        with self.store.write() as conn:
            verified, work_id, reason = self._verify_run(conn, frozen, video_id)
            if verified:
                self._outbox_update(conn, capture_key, now, state="enqueued", work_id=work_id,
                                    last_error_code=None)
                return {"outcome": "enqueued", "run_id": frozen["run_id"], "work_id": work_id, **base}
            self._outbox_update(conn, capture_key, now, state="blocked",
                                last_error_code="classification_conflict")
            return {"outcome": "blocked", "code": "classification_conflict", "reason": reason, **base}

    def _prepare_run(self, frozen: dict, video_id: str) -> dict:
        if self.index is None:
            return error_envelope("service_unavailable", "Phase 2 service requires the shared index")
        try:
            from library_work import RequestContext as LibraryContext
            service = self.index.library_service()
            return service.prepare_run(
                LibraryContext(authenticated=True, operator=True),
                {"run_id": frozen["run_id"], "version_id": frozen["version_id"],
                 "video_ids": [video_id], "prompt_hash": frozen["prompt_hash"]})
        except Exception as exc:
            log.exception("prepare_run unavailable")
            return error_envelope("service_unavailable", type(exc).__name__)

    @staticmethod
    def _verify_run(conn, frozen: dict, video_id: str) -> tuple[bool, str | None, str | None]:
        run = _row(conn.execute("SELECT * FROM library_runs WHERE run_id=?", (frozen["run_id"],)).fetchone())
        if run is None:
            return False, None, "run_missing"
        if run["version_id"] != frozen["version_id"]:
            return False, None, "version_mismatch"
        try:
            policy = json.loads(run["policy_json"] or "{}")
        except ValueError:
            policy = {}
        if policy.get("prompt_hash") != frozen["prompt_hash"]:
            return False, None, "prompt_mismatch"
        manifest = [dict(r) for r in conn.execute(
            "SELECT * FROM library_manifest WHERE run_id=?", (frozen["run_id"],)).fetchall()]
        if len(manifest) != 1 or manifest[0]["video_id"] != video_id:
            return False, None, "manifest_mismatch"
        if manifest[0]["source_revision"] != frozen["source_revision"]:
            return False, None, "source_revision_mismatch"
        work = _row(conn.execute(
            "SELECT work_id FROM library_work WHERE run_id=? AND video_id=?",
            (frozen["run_id"], video_id)).fetchone())
        if work is None:
            return False, None, "work_missing"
        return True, work["work_id"], None


# ===========================================================================
# Legacy projection helpers (contract, "Migration 0028 schema": old flags and
# delete routes are compatibility projections; they never become a second
# scheduler authority and never physically delete referenced rows)
# ===========================================================================
def tables_present(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_subscriptions'").fetchone()
    return row is not None


def legacy_source_id(conn, *, feed_id: int | None = None, playlist_id: int | None = None) -> str | None:
    if not tables_present(conn):
        return None
    if feed_id is not None:
        row = conn.execute("SELECT source_id FROM source_subscriptions WHERE legacy_feed_id=?",
                           (int(feed_id),)).fetchone()
    elif playlist_id is not None:
        row = conn.execute("SELECT source_id FROM source_subscriptions WHERE legacy_playlist_id=?",
                           (int(playlist_id),)).fetchone()
    else:
        row = None
    return row[0] if row else None


def legacy_set_detection(conn, *, enabled: bool, feed_id: int | None = None,
                         playlist_id: int | None = None, now: int | None = None) -> bool:
    """Mirror an old enabled flag onto the authoritative detection flag."""
    source_id = legacy_source_id(conn, feed_id=feed_id, playlist_id=playlist_id)
    if source_id is None:
        return False
    now = int(time.time() * 1000) if now is None else int(now)
    cur = conn.execute(
        "UPDATE source_subscriptions SET detection_enabled=?, updated_at_ms=? "
        "WHERE source_id=? AND archived=0", (1 if enabled else 0, now, source_id))
    return bool(cur.rowcount)


def legacy_archive(conn, *, feed_id: int | None = None, playlist_id: int | None = None,
                   now: int | None = None) -> str | None:
    """Old delete routes archive the source, release unstarted reservations and
    keep every referenced row. Returns the archived source id, or None when
    the legacy id has no subscription."""
    source_id = legacy_source_id(conn, feed_id=feed_id, playlist_id=playlist_id)
    if source_id is None:
        return None
    now = int(time.time() * 1000) if now is None else int(now)
    source = dict(conn.execute("SELECT * FROM source_subscriptions WHERE source_id=?",
                               (source_id,)).fetchone())
    if source["archived"]:
        return source_id
    released = 0
    for row in conn.execute(
            "SELECT * FROM source_capture_starts WHERE source_id=? AND state='reserved'",
            (source_id,)).fetchall():
        SourceSubscriptionService._release(conn, dict(row), now, "archived")
        released += 1
    conn.execute(
        "UPDATE source_subscriptions SET archived=1, detection_enabled=0, consent_state='off', "
        "boundary='none', revision=revision+1, updated_at_ms=? WHERE source_id=?", (now, source_id))
    conn.execute(
        "UPDATE source_detection_cursors SET poll_owner_token=NULL, poll_consent_epoch=NULL, "
        "poll_lease_expires_ms=NULL WHERE source_id=?", (source_id,))
    fresh = dict(conn.execute("SELECT * FROM source_subscriptions WHERE source_id=?",
                              (source_id,)).fetchone())
    response = success(operation_key=f"legacy-archive-{source_id[-16:]}-{fresh['revision']}",
                       changed=True, source_id=source_id, before_revision=source["revision"],
                       after_revision=fresh["revision"], consent_state="off",
                       consent_epoch=fresh["consent_epoch"], boundary="none",
                       released_reservations=released, in_flight=[], recorded_at_ms=now,
                       authority="archive")
    conn.execute(
        "INSERT OR IGNORE INTO source_consent_receipts (operation_key, source_id, request_hash, "
        "session_hash, authority, old_state, new_state, before_revision, after_revision, "
        "consent_epoch, response_json, created_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (response["operation_key"], source_id, digest({"legacy_archive": source_id,
                                                        "revision": fresh["revision"]}),
         "legacy_route", "archive", source["consent_state"], "off", source["revision"],
         fresh["revision"], fresh["consent_epoch"], canonical_json(response), now))
    return source_id


def legacy_register(conn, *, kind: str, url: str, feed_id: int | None = None,
                    playlist_id: int | None = None, display_name=None, interval=None,
                    detection_enabled: bool = True, now: int | None = None) -> str | None:
    """Old add routes project a new registry row as an off source (no consent,
    no receipt, no hold). Returns the source id, or None when the Phase 3
    tables are absent or the URL is not a supported standing source."""
    if not tables_present(conn):
        return None
    existing = legacy_source_id(conn, feed_id=feed_id, playlist_id=playlist_id)
    if existing is not None:
        return existing
    try:
        source_key, canonical_url = parse_source_url(kind, url)
    except ServiceError:
        return None
    source_id = source_identity(kind, source_key)
    if conn.execute("SELECT 1 FROM source_subscriptions WHERE source_id=?", (source_id,)).fetchone():
        return None  # identity already registered under another legacy row
    now = int(time.time() * 1000) if now is None else int(now)
    SourceSubscriptionService._insert_source(
        conn, source_id=source_id, kind=kind, source_key=source_key, canonical_url=canonical_url,
        display_name=_safe_text(display_name, 200),
        interval=interval or DEFAULT_POLL_INTERVAL_MIN, now=now,
        detection_enabled=detection_enabled, legacy_feed_id=feed_id,
        legacy_playlist_id=playlist_id)
    return source_id


def legacy_started_episode_ids(conn, feed_id: int) -> list[int]:
    """Episode ids whose source item currently holds a ``started`` ledger row:
    the only podcast episodes the old capture helpers may act on."""
    if not tables_present(conn):
        return []
    rows = conn.execute(
        "SELECT i.legacy_episode_id FROM source_capture_starts st "
        "JOIN source_items i ON i.item_id=st.item_id "
        "JOIN source_subscriptions s ON s.source_id=st.source_id "
        "WHERE s.legacy_feed_id=? AND st.state='started' AND i.legacy_episode_id IS NOT NULL",
        (int(feed_id),)).fetchall()
    return [int(r[0]) for r in rows]


def project_podcast_episode(conn, source: dict, item_id: str, entry_id: str, title,
                            audio_url, page_url, published_raw, duration_raw, now_iso: str) -> int | None:
    """Keep the old podcast_episodes projection in step for a legacy-linked
    feed so the existing download/transcribe/publish pipeline has its row.
    Never sets auto_ingest_requested; the ledger authorizes capture."""
    feed_id = source.get("legacy_feed_id")
    if feed_id is None:
        return None
    try:
        conn.execute(
            "INSERT OR IGNORE INTO podcast_episodes (feed_id, guid, title, audio_url, "
            "episode_page_url, duration_seconds, published_at, description, status, discovered_at, "
            "auto_ingest_requested) VALUES (?,?,?,?,?,?,?,NULL,'new',?,0)",
            (int(feed_id), entry_id, title, audio_url, page_url, _duration_seconds(duration_raw),
             published_raw, now_iso))
        row = conn.execute("SELECT id FROM podcast_episodes WHERE feed_id=? AND guid=?",
                           (int(feed_id), entry_id)).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    conn.execute("UPDATE source_items SET legacy_episode_id=COALESCE(legacy_episode_id, ?) "
                 "WHERE item_id=?", (int(row[0]), item_id))
    return int(row[0])


def _duration_seconds(raw) -> int | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        if ":" not in text:
            return int(float(text))
        parts = [int(p) for p in text.split(":")]
    except (TypeError, ValueError):
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


# ===========================================================================
# Module-level conveniences for transports
# ===========================================================================
def open_service(path, **kwargs) -> SourceSubscriptionService:
    """A standalone-connection service (two-connection tests, second scheduler)."""
    return SourceSubscriptionService(path=path, **kwargs)
