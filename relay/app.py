"""Uoink Relay: a tiny personal inbox for links shared from a phone.

Each user deploys their own copy (see docs/relay.md). The phone POSTs a link
with the push token; the Uoink helper on the desktop lists pending links with
the pull token, captures each one locally and deletes it here. A link and its
optional note are the only things stored, and every key expires after seven
days through the store's native TTL.

Standard library only, except redis-py for Render Key Value.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import signal
import sys
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("uoink-relay")

KEY_PREFIX = "uoink-relay:"
LINK_PREFIX = KEY_PREFIX + "link:"
URL_PREFIX = KEY_PREFIX + "url:"
TTL_SECONDS = 7 * 24 * 60 * 60          # 604800: Key Value EX does the purge
MAX_URL_CHARS = 2048
MAX_NOTE_CHARS = 500
MAX_BODY_BYTES = 16 * 1024
MAX_PENDING = 500
MAX_LIST = 100
MIN_TOKEN_CHARS = 32
AUTH_FAIL_LIMIT = 30
AUTH_FAIL_WINDOW_SEC = 10 * 60
PUSH_LIMIT = 60
PUSH_WINDOW_SEC = 60
DEFAULT_PORT = 10000
DOCS_URL = "https://github.com/ryanbiddy/uoink/blob/main/docs/relay.md"

_ID_RE = re.compile(r"\A\d{13}-[0-9a-f]{12}\Z")
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?'\"*"
_CLOSERS = {")": "(", "]": "[", "}": "{"}
# Bidi overrides and isolates are format characters, not Cc, but they can
# disguise a note's text in a dashboard. Drop them with the control characters.
_BIDI_CONTROLS = set("‪‫‬‭‮⁦⁧⁨⁩")
_NOTE_EDGE_SEPARATORS = " -–—|:;,.·•"


class ConfigError(RuntimeError):
    """The relay refuses to start; the message says what to fix."""


class InboxFull(RuntimeError):
    pass


class ShareError(ValueError):
    """A shared body did not contain an acceptable link or note."""


def _iso(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Storage. Both stores expose the same five operations, so the inbox logic
# runs unchanged on Render Key Value and in memory.
# --------------------------------------------------------------------------
class MemoryStore:
    """Local development and tests only (RELAY_DEV_MEMORY=1)."""

    kind = "memory"

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[1] <= self._clock():
            self._data.pop(key, None)
            return None
        return item[0]

    def ping(self) -> bool:
        return True

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (value, self._clock() + ttl)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._live(key)

    def delete(self, *keys: str) -> int:
        removed = 0
        with self._lock:
            for key in keys:
                if self._live(key) is not None:
                    del self._data[key]
                    removed += 1
        return removed

    def keys(self, prefix: str) -> list[str]:
        with self._lock:
            return [key for key in list(self._data) if key.startswith(prefix) and self._live(key) is not None]


class KeyValueStore:
    """Render Key Value (Valkey 8, Redis-compatible) through redis-py.

    The client only needs set(ex=), get, delete, scan_iter and ping, which
    keeps a fake client in the tests honest about what is called.
    """

    kind = "keyvalue"

    def __init__(self, client):
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> "KeyValueStore":
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - deploy-time guard
            raise ConfigError("RELAY_KEYVALUE_URL is set but redis-py is not installed. "
                              "Run pip install -r requirements.txt.") from exc
        return cls(redis.Redis.from_url(
            url, decode_responses=True, socket_timeout=5,
            socket_connect_timeout=5, health_check_interval=30))

    @staticmethod
    def _text(value):
        return value.decode("utf-8") if isinstance(value, bytes) else value

    def ping(self) -> bool:
        return bool(self._client.ping())

    def set(self, key: str, value: str, ttl: int) -> None:
        self._client.set(key, value, ex=int(ttl))

    def get(self, key: str) -> str | None:
        return self._text(self._client.get(key))

    def delete(self, *keys: str) -> int:
        return int(self._client.delete(*keys)) if keys else 0

    def keys(self, prefix: str) -> list[str]:
        # The prefix holds only letters, digits, '-' and ':', so it is a
        # literal MATCH pattern with no glob characters to escape.
        return [self._text(key) for key in self._client.scan_iter(match=prefix + "*", count=500)]


# --------------------------------------------------------------------------
# The inbox.
# --------------------------------------------------------------------------
class Inbox:
    def __init__(self, store, *, clock: Callable[[], float] = time.time,
                 ttl: int = TTL_SECONDS, max_pending: int = MAX_PENDING):
        self.store = store
        self._clock = clock
        self._ttl = ttl
        self._max_pending = max_pending
        # One process serves a free instance. The lock keeps dedupe and the
        # cap exact there; across several paid instances a race can at worst
        # queue the same link twice, which the desktop captures idempotently.
        self._lock = threading.Lock()

    @staticmethod
    def _url_key(url: str) -> str:
        return URL_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _load(self, link_id: str) -> dict | None:
        raw = self.store.get(LINK_PREFIX + link_id)
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except ValueError:
            return None
        return record if isinstance(record, dict) and record.get("id") == link_id else None

    def _expires_at(self, record: dict) -> str:
        return _iso(int(record.get("created_ms", 0)) / 1000 + self._ttl)

    def pending_ids(self) -> list[str]:
        ids = [key[len(LINK_PREFIX):] for key in self.store.keys(LINK_PREFIX)]
        return sorted(i for i in ids if _ID_RE.match(i))

    def add(self, url: str, note: str | None) -> tuple[dict, bool]:
        """Return (link, created). An already-pending URL returns its link."""
        with self._lock:
            url_key = self._url_key(url)
            existing_id = self.store.get(url_key)
            if existing_id:
                existing = self._load(existing_id)
                if existing is not None:
                    return {"id": existing["id"], "expires_at": self._expires_at(existing)}, False
            if len(self.pending_ids()) >= self._max_pending:
                raise InboxFull("inbox full")
            now = self._clock()
            created_ms = int(now * 1000)
            link_id = f"{created_ms:013d}-{secrets.token_hex(6)}"
            record = {"id": link_id, "url": url, "note": note,
                      "created_at": _iso(now), "created_ms": created_ms}
            self.store.set(LINK_PREFIX + link_id, json.dumps(record, ensure_ascii=False), self._ttl)
            self.store.set(url_key, link_id, self._ttl)
            return {"id": link_id, "expires_at": self._expires_at(record)}, True

    def list(self, limit: int = MAX_LIST) -> list[dict]:
        links = []
        for link_id in self.pending_ids():
            record = self._load(link_id)
            if record is None:
                continue  # expired between the scan and the read
            links.append({"id": record["id"], "url": record.get("url"),
                          "note": record.get("note"), "created_at": record.get("created_at")})
            if len(links) >= limit:
                break
        return links

    def delete(self, link_id: str) -> bool:
        if not _ID_RE.match(link_id or ""):
            return False
        with self._lock:
            record = self._load(link_id)
            if record is None:
                return False
            url_key = self._url_key(str(record.get("url") or ""))
            keys = [LINK_PREFIX + link_id]
            if self.store.get(url_key) == link_id:
                keys.append(url_key)
            self.store.delete(*keys)
            return True


# --------------------------------------------------------------------------
# Shared-text parsing.
# --------------------------------------------------------------------------
def validate_url(value: str) -> str:
    """Return the URL unchanged, or raise ShareError with a plain reason."""
    if not isinstance(value, str) or not value:
        raise ShareError("url is required")
    if len(value) > MAX_URL_CHARS:
        raise ShareError(f"url is longer than {MAX_URL_CHARS} characters")
    if any(ch.isspace() or unicodedata.category(ch) == "Cc" for ch in value):
        raise ShareError("url contains spaces or control characters")
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        raise ShareError("url is not valid") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise ShareError("url must start with http:// or https://")
    if "@" in parts.netloc:
        raise ShareError("url must not contain a username or password")
    if not parts.hostname:
        raise ShareError("url needs a host")
    return value


def _trim_url_match(candidate: str) -> str:
    while candidate:
        last = candidate[-1]
        if last in _TRAILING_PUNCT:
            candidate = candidate[:-1]
        elif last in _CLOSERS and candidate.count(last) > candidate.count(_CLOSERS[last]):
            candidate = candidate[:-1]
        else:
            break
    return candidate


def extract_url(text: str) -> tuple[str | None, str, str | None]:
    """First valid http(s) URL in shared text: (url, remaining text, reason)."""
    reason = None
    for match in _URL_IN_TEXT_RE.finditer(text or ""):
        candidate = _trim_url_match(match.group(0))
        try:
            url = validate_url(candidate)
        except ShareError as exc:
            reason = reason or str(exc)
            continue
        start = match.start()
        remaining = text[:start] + " " + text[start + len(candidate):]
        return url, remaining, None
    return None, text or "", reason


def clean_note(value: str | None, *, derived: bool) -> str | None:
    """Strip control characters; collapse whitespace. A note you typed must
    fit; text left over from a share is trimmed to fit instead."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ShareError("note must be a string")
    kept = []
    for ch in value:
        if ch in "\t\r\n":
            kept.append(" ")
        elif unicodedata.category(ch) == "Cc" or ch in _BIDI_CONTROLS:
            continue
        else:
            kept.append(ch)
    note = " ".join("".join(kept).split())
    if derived:
        note = note.strip(_NOTE_EDGE_SEPARATORS)
        if len(note) > MAX_NOTE_CHARS:
            note = note[:MAX_NOTE_CHARS - 1].rstrip() + "…"
    elif len(note) > MAX_NOTE_CHARS:
        raise ShareError(f"note is longer than {MAX_NOTE_CHARS} characters")
    return note or None


def resolve_share(url_field, texts: list, note) -> tuple[str, str | None]:
    """Turn a share (a url field, any free text, a typed note) into a link.

    A url field that is itself a URL wins. Otherwise the first http(s) URL in
    the url field, then each text, is used and the words around it become the
    note when none was typed (iOS shares often send "Title https://...").
    """
    if url_field is not None and not isinstance(url_field, str):
        raise ShareError("url must be a string")
    if note is not None and not isinstance(note, str):
        raise ShareError("note must be a string")
    typed_note = clean_note(note, derived=False) if note is not None else None
    sources = [s for s in [url_field, *texts] if isinstance(s, str) and s.strip()]
    if url_field and url_field.strip():
        try:
            url = validate_url(url_field.strip())
        except ShareError:
            url = None
        if url is not None:
            leftover = next((s for s in texts if isinstance(s, str) and s.strip()), None)
            return url, typed_note or clean_note(leftover, derived=True)
    reason = None
    for index, text in enumerate(sources):
        url, remaining, why = extract_url(text)
        if url is None:
            reason = reason or why
            continue
        derived = clean_note(remaining, derived=True)
        if derived is None and index + 1 < len(sources):
            derived = clean_note(sources[index + 1], derived=True)
        return url, typed_note or derived
    raise ShareError(reason or "no http(s) link found")


# --------------------------------------------------------------------------
# Abuse limits.
# --------------------------------------------------------------------------
class SlidingWindow:
    """At most `limit` events per key in `window` seconds. Bounded memory."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float], max_keys: int = 10000):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        events = self._events.get(key)
        if events is None:
            return deque()
        while events and events[0] <= now - self.window:
            events.popleft()
        if not events:
            self._events.pop(key, None)
        return events

    def exceeded(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, self._clock())) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            events = self._prune(key, now)
            if key not in self._events:
                if len(self._events) >= self._max_keys:
                    self._events.pop(next(iter(self._events)))
                self._events[key] = events
            events.append(now)


# --------------------------------------------------------------------------
# Configuration.
# --------------------------------------------------------------------------
@dataclass
class Config:
    push_token: str
    pull_token: str
    store: object
    port: int = DEFAULT_PORT
    clock: Callable[[], float] = field(default=time.time)


def _check_token(name: str, value: str | None) -> str:
    if not value:
        raise ConfigError(f"{name} is not set. Set it to a random value of at least "
                          f"{MIN_TOKEN_CHARS} characters (render.yaml generates one).")
    if len(value) < MIN_TOKEN_CHARS:
        raise ConfigError(f"{name} is shorter than {MIN_TOKEN_CHARS} characters.")
    if any(ch.isspace() or unicodedata.category(ch) == "Cc" for ch in value):
        raise ConfigError(f"{name} must not contain spaces or control characters.")
    return value


def load_config(environ=None, *, clock: Callable[[], float] = time.time,
                keyvalue_factory=KeyValueStore.from_url) -> Config:
    env = os.environ if environ is None else environ
    push = _check_token("RELAY_PUSH_TOKEN", env.get("RELAY_PUSH_TOKEN"))
    pull = _check_token("RELAY_PULL_TOKEN", env.get("RELAY_PULL_TOKEN"))
    if hmac.compare_digest(push.encode("utf-8"), pull.encode("utf-8")):
        raise ConfigError("RELAY_PUSH_TOKEN and RELAY_PULL_TOKEN must be different.")
    raw_port = env.get("PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
        if not 0 < port < 65536:
            raise ValueError
    except ValueError:
        raise ConfigError("PORT must be a number from 1 to 65535.") from None
    if env.get("RELAY_KEYVALUE_URL"):
        store = keyvalue_factory(env["RELAY_KEYVALUE_URL"])
    elif env.get("RELAY_DEV_MEMORY") == "1":
        store = MemoryStore(clock)
    else:
        raise ConfigError("No store configured. Set RELAY_KEYVALUE_URL to the Key Value "
                          "connection string, or RELAY_DEV_MEMORY=1 for a local test run.")
    return Config(push_token=push, pull_token=pull, store=store, port=port, clock=clock)


# --------------------------------------------------------------------------
# HTTP.
# --------------------------------------------------------------------------
_PAGE_STYLE = ("body{font:16px/1.5 system-ui,sans-serif;max-width:36rem;margin:3rem auto;"
               "padding:0 1rem;color:#1b1b1b;background:#fafafa}"
               "a{color:#0b57d0}"
               "@media (prefers-color-scheme:dark){body{color:#eee;background:#151515}a{color:#8ab4f8}}")
_PAGE = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
         "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
         "<meta name=\"robots\" content=\"noindex\">"
         "<title>Uoink Relay</title><style>" + _PAGE_STYLE + "</style></head><body>"
         "<h1>Uoink Relay</h1>"
         "<p>This is a private inbox. It holds links shared from a phone until Uoink "
         "on a computer picks them up, then deletes them. Links that wait longer than "
         "7 days are deleted too.</p>"
         "<p>There is nothing to see here without a token.</p>"
         "<p><a href=\"" + DOCS_URL + "\">How the Uoink Relay works</a></p>"
         "</body></html>").encode("utf-8")
_PAGE_STYLE_HASH = base64.b64encode(hashlib.sha256(_PAGE_STYLE.encode("utf-8")).digest()).decode("ascii")
_PAGE_CSP = (f"default-src 'none'; style-src 'sha256-{_PAGE_STYLE_HASH}'; "
             "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_JSON_CSP = "default-src 'none'; frame-ancestors 'none'"


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "uoink-relay"
    sys_version = ""
    # Bound slow clients; the relay never needs a long-held connection.
    timeout = 15

    # The stdlib logs the request line (path and IP) for every request and
    # error. Replace it with the method/route/status/duration line below.
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return

    def version_string(self):
        return "uoink-relay"

    # ---- plumbing -----------------------------------------------------
    @property
    def relay(self) -> "RelayServer":
        return self.server  # type: ignore[return-value]

    def _begin(self, route: str) -> None:
        self._route = route
        self._started = time.monotonic()
        self._body_read = False

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _finish_log(self, status: int) -> None:
        elapsed_ms = (time.monotonic() - getattr(self, "_started", time.monotonic())) * 1000
        log.info("%s %s %d %.0fms", self.command if self.command in
                 ("GET", "POST", "DELETE", "PUT", "PATCH") else "OTHER",
                 getattr(self, "_route", "other"), status, elapsed_ms)

    def _drain(self) -> None:
        """Read a rejected request's body (bounded) so the client sees the
        error instead of a connection reset."""
        if self._body_read or self.command not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        self._body_read = True
        self.close_connection = True
        try:
            remaining = min(int(self.headers.get("Content-Length") or 0), 4 * MAX_BODY_BYTES)
        except ValueError:
            return
        deadline = time.monotonic() + 1.0
        try:
            while remaining > 0 and time.monotonic() < deadline:
                self.connection.settimeout(max(0.05, deadline - time.monotonic()))
                chunk = self.rfile.read1(min(remaining, 8192))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def _send(self, status: int, body: bytes, content_type: str, csp: str,
              extra: dict | None = None) -> None:
        if status >= 400:
            self._drain()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", csp)
        self._common_headers()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        # Log before the body goes out, so the line exists by the time the
        # client has its answer.
        self._finish_log(status)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict, extra: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", _JSON_CSP, extra)

    def _error(self, status: int, message: str, extra: dict | None = None) -> None:
        self._json(status, {"ok": False, "error": message}, extra)

    def _client_ip(self) -> str:
        """The address Render's proxy saw: the LAST X-Forwarded-For entry,
        which the proxy appends. Earlier entries come from the client and
        can be forged, so they never change the key."""
        forwarded = self.headers.get("X-Forwarded-For") or ""
        last = forwarded.rsplit(",", 1)[-1].strip()
        return last or self.client_address[0]

    def _token_role(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.strip().partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None
        given = token.encode("utf-8")
        # Compare against both tokens every time.
        is_push = hmac.compare_digest(given, self.relay.config.push_token.encode("utf-8"))
        is_pull = hmac.compare_digest(given, self.relay.config.pull_token.encode("utf-8"))
        if is_push:
            return "push"
        if is_pull:
            return "pull"
        return None

    def _authorize(self, role: str) -> bool:
        # The token decides first: a valid push or pull token is never
        # refused, so nobody can lock the phone out by failing from (or
        # claiming) its address. Only missing or wrong tokens are counted
        # and throttled.
        actual = self._token_role()
        if actual is None:
            ip = self._client_ip()
            if self.relay.auth_failures.exceeded(ip):
                self._error(429, "too many failed attempts; try again later",
                            {"Retry-After": str(AUTH_FAIL_WINDOW_SEC)})
                return False
            self.relay.auth_failures.hit(ip)
            self._error(401, "missing or invalid token", {"WWW-Authenticate": "Bearer"})
            return False
        if actual != role:
            self._error(403, "the " + actual + " token can't do this")
            return False
        return True

    def _read_body(self) -> bytes | None:
        if (self.headers.get("Transfer-Encoding") or "").strip():
            self._error(411, "send a Content-Length")
            return None
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            self._error(411, "send a Content-Length")
            return None
        if length < 0:
            self._error(400, "bad Content-Length")
            return None
        if length > MAX_BODY_BYTES:
            self._error(413, f"body is larger than {MAX_BODY_BYTES} bytes")
            return None
        body = self.rfile.read(length) if length else b""
        self._body_read = True
        return body

    # ---- routes -------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib name
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._begin("/healthz")
            store = self.relay.inbox.store
            try:
                healthy = bool(store.ping())
            except Exception:
                healthy = False
            return self._json(200 if healthy else 503, {"ok": healthy, "store": store.kind})
        if path == "/":
            self._begin("/")
            return self._send(200, _PAGE, "text/html; charset=utf-8", _PAGE_CSP)
        if path == "/v1/links":
            self._begin("/v1/links")
            if not self._authorize("pull"):
                return None
            try:
                links = self.relay.inbox.list(MAX_LIST)
            except Exception:
                return self._error(503, "store unavailable")
            return self._json(200, {"ok": True, "links": links})
        self._begin("other")
        return self._error(405 if path.startswith("/v1/links/") else 404,
                           "method not allowed" if path.startswith("/v1/links/") else "not found")

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/v1/links":
            self._begin("other")
            return self._error(404, "not found")
        self._begin("/v1/links")
        if not self._authorize("push"):
            return None
        if self.relay.pushes.exceeded("push"):
            return self._error(429, "too many links this minute; try again shortly",
                               {"Retry-After": str(PUSH_WINDOW_SEC)})
        self.relay.pushes.hit("push")
        body = self._read_body()
        if body is None:
            return None
        try:
            url, note = self._parse_share(body)
        except ShareError as exc:
            return self._error(400, str(exc))
        except _UnsupportedType:
            return self._error(415, "send JSON, a form, or plain text")
        try:
            link, created = self.relay.inbox.add(url, note)
        except InboxFull:
            return self._error(429, "inbox full")
        except Exception:
            return self._error(503, "store unavailable")
        payload = {"ok": True, **link}
        if not created:
            payload["duplicate"] = True
        return self._json(201 if created else 200, payload)

    def do_DELETE(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not path.startswith("/v1/links/"):
            self._begin("other")
            return self._error(404, "not found")
        self._begin("/v1/links/{id}")
        if not self._authorize("pull"):
            return None
        link_id = path[len("/v1/links/"):]
        try:
            deleted = self.relay.inbox.delete(link_id)
        except Exception:
            return self._error(503, "store unavailable")
        if not deleted:
            return self._error(404, "no such link")
        return self._json(200, {"ok": True})

    def _method_not_allowed(self):
        self._begin("other")
        return self._error(405, "method not allowed")

    do_PUT = do_PATCH = do_OPTIONS = _method_not_allowed  # noqa: N815

    # ---- body formats -------------------------------------------------
    def _parse_share(self, body: bytes) -> tuple[str, str | None]:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise ShareError("body must be UTF-8") from None
        if content_type == "application/json":
            try:
                data = json.loads(text or "null")
            except ValueError:
                raise ShareError("body is not valid JSON") from None
            if not isinstance(data, dict):
                raise ShareError("JSON body must be an object")
            url = data.get("url")
            if isinstance(url, list) and url and all(isinstance(item, str) for item in url):
                # A share sheet can hand a Shortcut several items (text and URL).
                url = " ".join(url)
            return resolve_share(url, [data.get("text"), data.get("title")], data.get("note"))
        if content_type == "application/x-www-form-urlencoded":
            try:
                fields = parse_qs(text, keep_blank_values=False, max_num_fields=20, strict_parsing=False)
            except ValueError:
                raise ShareError("form has too many fields") from None

            def first(name):
                values = fields.get(name)
                return values[0] if values else None
            return resolve_share(first("url"), [first("text"), first("title")], first("note"))
        if content_type == "text/plain":
            return resolve_share(None, [text], None)
        raise _UnsupportedType()


class _UnsupportedType(Exception):
    pass


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config: Config):
        self.config = config
        self.inbox = Inbox(config.store, clock=config.clock)
        self.auth_failures = SlidingWindow(AUTH_FAIL_LIMIT, AUTH_FAIL_WINDOW_SEC, config.clock)
        self.pushes = SlidingWindow(PUSH_LIMIT, PUSH_WINDOW_SEC, config.clock)
        super().__init__(address, RelayHandler)

    def handle_error(self, request, client_address):
        # The default prints a traceback with the client address to stderr.
        log.warning("request handler error")


def make_server(config: Config, host: str = "0.0.0.0", port: int | None = None) -> RelayServer:
    return RelayServer((host, config.port if port is None else port), config)


def main(environ=None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(environ)
    except ConfigError as exc:
        print(f"uoink-relay will not start: {exc}", file=sys.stderr)
        return 2
    server = make_server(config)
    log.info("uoink-relay listening on port %d (store: %s)", config.port, config.store.kind)
    try:
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    except (ValueError, AttributeError):
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
