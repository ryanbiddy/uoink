"""Uoink Relay: a tiny personal inbox for links shared from a phone.

Each user deploys their own copy (see docs/relay.md). The phone POSTs a link
with the push token; the Uoink helper on the desktop lists pending links with
the pull token, captures each one locally and deletes it here. A link and its
optional note are the only things stored, and every key expires after seven
days through the store's native TTL.

The relay also serves a small phone page (GET /phone) that the Uoink dashboard
opens through a QR code, so the phone needs no hand-built Shortcut.

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
import struct
import sys
import threading
import time
import unicodedata
import zlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
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


# --------------------------------------------------------------------------
# The phone page (GET /phone). The Uoink dashboard shows a QR code that opens
# https://<relay>/phone#t=<push token>. The token sits in the URL fragment, so
# it is never sent to this server or written to a log. The page keeps it in
# the phone's localStorage and removes it from the address bar.
# --------------------------------------------------------------------------
_PHONE_STYLE = """
:root{color-scheme:light dark;--bg:#fafafa;--card:#fff;--text:#1b1b1b;--muted:#5d5d5d;--line:#dcdcdc;--acid:#FFD23F;--on-acid:#1b1b1b;--ok:#0d6b2b;--bad:#b3261e;--link:#0b57d0}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--card:#1c1c1c;--text:#f2f2f2;--muted:#a8a8a8;--line:#333;--ok:#6fd28a;--bad:#ff8a80;--link:#8ab4f8}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
main{max-width:34rem;margin:0 auto;padding:20px 16px 40px}
h1{margin:0;font-size:1.5rem;line-height:1.2}
h2{margin:0 0 8px;font-size:1.05rem}
p{margin:0 0 10px;overflow-wrap:anywhere}
a{color:var(--link)}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}
.mark{display:inline-block;width:14px;height:14px;border-radius:4px;background:var(--acid);margin-right:8px}
.pill{font-size:.8rem;padding:4px 10px;border-radius:99px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.pill.on{border-color:var(--ok);color:var(--ok)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0 0 14px}
.muted{color:var(--muted);font-size:.92rem}
textarea,input{width:100%;font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px;min-height:48px}
textarea{min-height:96px;resize:vertical}
button{font:inherit;min-height:48px;padding:10px 18px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
button.primary{background:var(--acid);border-color:var(--acid);color:var(--on-acid);font-weight:600}
button:disabled{opacity:.55}
:focus-visible{outline:3px solid var(--link);outline-offset:2px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.result{min-height:1.5em;margin:10px 0 0}
.result.ok{color:var(--ok)}
.result.bad{color:var(--bad)}
details{border-top:1px solid var(--line);padding:10px 0}
details:first-of-type{border-top:0}
summary{cursor:pointer;min-height:44px;display:flex;align-items:center;font-weight:600}
summary::after{content:"+";margin-left:auto;padding-left:12px;color:var(--muted);font-weight:400}
details[open] summary::after{content:"−"}
ol{margin:6px 0 10px;padding-left:1.3rem}
li{margin:0 0 6px;overflow-wrap:anywhere}
[hidden]{display:none!important}
"""

_PHONE_SCRIPT = r"""
(function () {
  "use strict";
  var KEY = "uoink-relay-push-token";
  var memory = "";
  var pending = "";
  function $(id) { return document.getElementById(id); }
  function read() {
    try { return window.localStorage.getItem(KEY) || memory; } catch (e) { return memory; }
  }
  function write(value) {
    memory = value || "";
    try {
      if (value) window.localStorage.setItem(KEY, value); else window.localStorage.removeItem(KEY);
    } catch (e) {}
  }
  function validToken(value) { return typeof value === "string" && /^[\x21-\x7e]{32,}$/.test(value); }
  function tokenFrom(text) {
    var match = /[#&]t=([^&\s]+)/.exec(text || "");
    if (!match) return "";
    try { return decodeURIComponent(match[1]); } catch (e) { return ""; }
  }

  // Take the token out of the address bar at once.
  var fresh = tokenFrom(window.location.hash);
  if (window.location.hash) {
    try { window.history.replaceState(null, "", window.location.pathname + window.location.search); } catch (e) {}
  }
  if (validToken(fresh)) {
    var stored = read();
    if (!stored) {
      write(fresh);
    } else if (stored === fresh) {
      say($("pairresult"), "Already paired", "ok");
    } else {
      pending = fresh;
      say($("pairresult"), "This link would pair this phone with a different key. Pair with the new key?", "");
    }
  }

  var UA = navigator.userAgent || "";
  var isIOS = /iPhone|iPad|iPod/.test(UA) || (/Macintosh/.test(UA) && navigator.maxTouchPoints > 1);
  var isAndroid = /Android/.test(UA);

  function say(el, text, kind) { el.textContent = text; el.className = "result" + (kind ? " " + kind : ""); }

  function paired() { return validToken(read()); }
  function render() {
    var on = paired();
    $("pill").textContent = on ? "Paired" : "Not paired";
    $("pill").className = "pill" + (on ? " on" : "");
    $("unpaired").hidden = on;
    $("sendcard").hidden = !on;
    $("forget").hidden = !on;
    $("shortcutcopy").hidden = !on;
    $("pairnotice").hidden = !$("pairresult").textContent;
    $("pairchoice").hidden = !pending;
  }

  function explain(status, data) {
    if (status === 401) return "This phone's key doesn't match your relay. Scan the QR code in Uoink again.";
    if (status === 403) return "That key can't add links. Scan the QR code in Uoink again.";
    if (status === 429) return "The relay is busy or full right now. Try again in a minute.";
    if (status === 400 || status === 413 || status === 415) {
      return "That didn't look like a link." + ((data && data.error) ? " (" + data.error + ")" : "");
    }
    return "The relay had a problem (" + status + "). Try again in a minute.";
  }

  // A free Render service sleeps after 15 quiet minutes and takes about a
  // minute to wake. A network failure or a 502/503/504 gets automatic retries.
  var WAKE_MS = 90000;
  function send(body, outEl) {
    var token = read();
    if (!validToken(token)) { say(outEl, "This phone isn't paired yet. Scan the QR code in Uoink.", "bad"); return Promise.resolve(false); }
    var started = Date.now();
    say(outEl, "Sending...", "");
    function attempt() {
      var controller = typeof AbortController === "function" ? new AbortController() : null;
      var timer = controller ? window.setTimeout(function () { controller.abort(); }, 20000) : 0;
      function again() {
        if (Date.now() - started >= WAKE_MS) {
          say(outEl, "Couldn't reach the relay. Check your connection and try again.", "bad");
          return false;
        }
        say(outEl, "Waking your relay, this can take a minute. Hang on, trying again automatically.", "");
        return new Promise(function (resolve) { window.setTimeout(resolve, 4000); }).then(attempt);
      }
      return fetch("/v1/links", {
        method: "POST",
        headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller ? controller.signal : undefined,
        cache: "no-store",
        referrerPolicy: "no-referrer"
      }).then(function (response) {
        if (timer) window.clearTimeout(timer);
        if (response.status === 502 || response.status === 503 || response.status === 504) return again();
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (response.status === 201) { say(outEl, "Sent. Uoink picks it up the next time it checks on your computer.", "ok"); return true; }
          if (response.status === 200) { say(outEl, "That link is already waiting for Uoink.", "ok"); return true; }
          say(outEl, explain(response.status, data), "bad");
          return false;
        });
      }, function () {
        if (timer) window.clearTimeout(timer);
        return again();
      });
    }
    return attempt();
  }

  $("sendform").addEventListener("submit", function (event) {
    event.preventDefault();
    var text = $("link").value.trim();
    if (!text) { say($("result"), "Paste a link first.", "bad"); return; }
    $("sendbtn").disabled = true;
    send({ url: text }, $("result")).then(function (ok) {
      $("sendbtn").disabled = false;
      if (ok) { $("link").value = ""; $("sharedbox").hidden = true; }
    });
  });

  $("pairform").addEventListener("submit", function (event) {
    event.preventDefault();
    var token = tokenFrom($("pairlink").value);
    if (!validToken(token)) { say($("pairresult"), "That isn't a pairing link from Uoink.", "bad"); render(); return; }
    write(token);
    pending = "";
    $("pairlink").value = "";
    say($("pairresult"), "Paired with the new key", "ok");
    render();
  });

  $("pairnew").addEventListener("click", function () {
    if (!pending) return;
    write(pending);
    pending = "";
    say($("pairresult"), "Paired with the new key", "ok");
    render();
  });
  $("pairkeep").addEventListener("click", function () {
    pending = "";
    say($("pairresult"), "Kept the current key", "ok");
    render();
  });

  $("forget").addEventListener("click", function () {
    write("");
    pending = "";
    say($("pairresult"), "", "");
    say($("result"), "", "");
    render();
  });

  function copyText(value, out) {
    function done(ok) { say(out, ok ? "Copied." : "Couldn't copy. Press and hold the text instead.", ok ? "ok" : "bad"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(function () { done(true); }, function () { done(false); });
      return;
    }
    done(false);
  }
  $("copyaddr").addEventListener("click", function () { copyText(window.location.origin + "/v1/links", $("copyresult")); });
  $("copykey").addEventListener("click", function () {
    if (paired()) copyText("Bearer " + read(), $("copyresult"));
  });

  // Android share target: the manifest sends a shared link here as ?url=&text=&title=.
  // Any web page or message can open /phone?url=... on a paired phone, so a
  // share is never sent by itself. It fills the box and waits for Send.
  var params = new URLSearchParams(window.location.search);
  var shared = [];
  ["url", "text", "title"].forEach(function (name) {
    var value = (params.get(name) || "").trim();
    if (!value) return;
    for (var i = 0; i < shared.length; i++) {
      if (shared[i].indexOf(value) !== -1) return;
      if (value.indexOf(shared[i]) !== -1) { shared[i] = value; return; }
    }
    shared.push(value);
  });
  if (shared.length) {
    try { window.history.replaceState(null, "", window.location.pathname); } catch (e) {}
    $("link").value = shared.join(" ");
    $("sharedbox").hidden = false;
    if (paired()) {
      say($("sharedresult"), "Shared from another app. Send it to Uoink? Check the link below, then tap Send.", "");
    } else {
      say($("sharedresult"), "This phone isn't paired yet, so nothing was sent. Scan the QR code in Uoink, then send it from the box below.", "bad");
    }
  }

  var which = isIOS ? "ios" : (isAndroid ? "android" : "");
  if (which) { var det = $("how-" + which); if (det) det.open = true; }
  if (isIOS) $("iosonly").hidden = false;
  render();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/phone-sw.js", { scope: "/phone" }).catch(function () {});
  }
})();
"""

_PHONE_BODY = """<main>
<div class="top"><h1><span class="mark"></span>Send to Uoink</h1><span class="pill" id="pill">Not paired</span></div>
<div class="card" id="pairnotice" hidden>
<p class="result" id="pairresult" role="status"></p>
<div class="row" id="pairchoice" hidden><button class="primary" id="pairnew" type="button">Pair with new key</button><button id="pairkeep" type="button">Keep current</button></div>
</div>
<div class="card" id="unpaired" hidden>
<h2>Pair this phone</h2>
<p>Open Uoink on your computer, go to Settings, then Phone inbox, and scan the QR code with this phone's camera. That opens this page with the key it needs.</p>
<details><summary>Pair with a link instead</summary>
<form id="pairform"><p class="muted">In Uoink, choose Copy pairing link, send it to this phone and paste it here.</p>
<input id="pairlink" type="text" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Pairing link">
<div class="row"><button class="primary" type="submit">Pair</button></div></form></details>
</div>
<div class="card" id="sharedbox" hidden><h2>Shared link</h2><p class="result" id="sharedresult" role="status"></p></div>
<div class="card" id="sendcard">
<h2>Paste a link</h2>
<form id="sendform">
<textarea id="link" rows="3" inputmode="url" autocapitalize="off" spellcheck="false" aria-label="Link to send" placeholder="Paste a link here"></textarea>
<div class="row"><button class="primary" id="sendbtn" type="submit">Send</button></div>
<p class="result" id="result" role="status" aria-live="polite"></p>
</form>
<p class="muted">Uoink on your computer captures it the next time it checks. The relay deletes it after pickup, or after 7 days.</p>
</div>
<div class="card">
<h2>Send faster</h2>
<details id="how-android"><summary>Android: add to Home Screen</summary>
<ol><li>In Chrome, open the menu and choose Install app or Add to Home screen.</li>
<li>After that, Uoink shows up in the share sheet. Share a link from YouTube, X or any page and pick Uoink.</li></ol></details>
<details id="how-ios"><summary>iPhone: add to Home Screen</summary>
<ol><li>In Safari, tap Share, then Add to Home Screen.</li>
<li>Open it from your Home Screen to paste links quickly. If it says Not paired, open Pair with a link and paste the pairing link from Uoink.</li></ol></details>
<details id="iosonly" hidden><summary>iPhone: Send from the Share sheet</summary>
<p class="muted">iPhone web pages can't appear in the Share sheet, so make a one-time Shortcut. It takes about two minutes.</p>
<ol><li>Open the Shortcuts app and tap the plus button. Name it Send to Uoink.</li>
<li>Open the shortcut's details and turn on Show in Share Sheet. Allow URLs and Text.</li>
<li>Add the action Get Contents of URL. Paste this address with the first button below.</li>
<li>Tap Show More. Set Method to POST. Add the header Authorization and paste its value with the second button below.</li>
<li>Set Request Body to JSON. Add a Text field named url and set it to Shortcut Input.</li>
<li>Done. Share any page and pick Send to Uoink.</li></ol>
<div class="row" id="shortcutcopy"><button id="copyaddr" type="button">Copy address</button><button id="copykey" type="button">Copy Authorization value</button></div>
<p class="result" id="copyresult" role="status"></p></details>
</div>
<p class="muted">This page talks only to your own relay. Nothing is tracked, and there are no ads or outside scripts.</p>
<div class="row"><button id="forget" type="button" hidden>Forget this phone</button></div>
</main>"""


def _csp_hash(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


_PHONE_HTML = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
               "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
               "<meta name=\"robots\" content=\"noindex,nofollow\">"
               "<meta name=\"theme-color\" content=\"#FFD23F\">"
               "<meta name=\"mobile-web-app-capable\" content=\"yes\">"
               "<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">"
               "<meta name=\"apple-mobile-web-app-title\" content=\"Uoink\">"
               "<link rel=\"icon\" href=\"/phone-icon-192.png\">"
               "<link rel=\"manifest\" href=\"/phone.webmanifest\">"
               "<link rel=\"apple-touch-icon\" href=\"/phone-icon-180.png\">"
               "<title>Send to Uoink</title><style>" + _PHONE_STYLE + "</style></head><body>"
               + _PHONE_BODY + "<script>" + _PHONE_SCRIPT + "</script></body></html>").encode("utf-8")
_PHONE_CSP = ("default-src 'none'; script-src " + _csp_hash(_PHONE_SCRIPT)
              + "; style-src " + _csp_hash(_PHONE_STYLE)
              + "; img-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
              "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_PHONE_SW = (b"// Uoink Relay phone page. A fetch handler lets Android treat the page as "
             b"installable; it stores nothing.\n"
             b"self.addEventListener('fetch', function () {});\n")
_PHONE_ASSET_CSP = "default-src 'none'; frame-ancestors 'none'"
PHONE_ICON_SIZES = (180, 192, 512)

_PHONE_MANIFEST = json.dumps({
    "name": "Send to Uoink",
    "short_name": "Uoink",
    "description": "Send links from this phone to Uoink on your computer.",
    "id": "/phone",
    "start_url": "/phone",
    "scope": "/phone",
    "display": "standalone",
    "background_color": "#FFD23F",
    "theme_color": "#FFD23F",
    "icons": [
        {"src": "/phone-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/phone-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
    "share_target": {
        "action": "/phone",
        "method": "GET",
        "enctype": "application/x-www-form-urlencoded",
        "params": {"title": "title", "text": "text", "url": "url"},
    },
}, ensure_ascii=False).encode("utf-8")


def _png(width: int, height: int, rows: list) -> bytes:
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


@lru_cache(maxsize=None)
def phone_icon(size: int) -> bytes:
    """A flat Uoink-yellow square with a dark U, drawn here so the relay
    needs no image files or libraries. Full bleed, so it also works masked."""
    yellow, dark = (0xFF, 0xD2, 0x3F), (0x1B, 0x1B, 0x1B)
    half = size * 0.19            # centre line to the outer edge of the U
    stroke = size * 0.095
    top, centre_y = size * 0.27, size * 0.55
    rows = []
    for y in range(size):
        row = bytearray(yellow * size)
        py = y + 0.5
        spans = []
        if top <= py <= centre_y:
            spans = [(size / 2 - half, size / 2 - half + stroke), (size / 2 + half - stroke, size / 2 + half)]
        elif centre_y < py <= centre_y + half:
            dy = py - centre_y
            outer = (half * half - dy * dy) ** 0.5
            inner_sq = (half - stroke) ** 2 - dy * dy
            inner = inner_sq ** 0.5 if inner_sq > 0 else 0.0
            spans = [(size / 2 - outer, size / 2 - inner), (size / 2 + inner, size / 2 + outer)]
        for left, right in spans:
            for x in range(max(0, int(left + 0.5)), min(size, int(right + 0.5))):
                row[x * 3:x * 3 + 3] = bytes(dark)
        rows.append(row)
    return _png(size, size, rows)


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
        if path == "/phone":
            self._begin("/phone")
            return self._send(200, _PHONE_HTML, "text/html; charset=utf-8", _PHONE_CSP)
        if path == "/phone.webmanifest":
            self._begin("/phone.webmanifest")
            return self._send(200, _PHONE_MANIFEST, "application/manifest+json; charset=utf-8", _PHONE_ASSET_CSP)
        if path == "/phone-sw.js":
            self._begin("/phone-sw.js")
            return self._send(200, _PHONE_SW, "text/javascript; charset=utf-8", _PHONE_ASSET_CSP)
        icon = re.fullmatch(r"/phone-icon-(\d+)\.png", path)
        if icon and int(icon.group(1)) in PHONE_ICON_SIZES:
            self._begin("/phone-icon")
            return self._send(200, phone_icon(int(icon.group(1))), "image/png", _PHONE_ASSET_CSP)
        if path == "/v1/pairing":
            # Same limiter as every other authed route. The pull token already
            # belongs to the same person as the push token, so showing the
            # push token to it widens nothing that matters (docs/relay.md).
            self._begin("/v1/pairing")
            if not self._authorize("pull"):
                return None
            return self._json(200, {"ok": True, "push_token": self.relay.config.push_token})
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
