"""Opt-in, one-shot ScrapeCreators discovery. No work occurs on import.

Transport is injectable and returns TransportResponse; production uses a pinned,
non-redirecting urllib opener. Run receipts save normalized candidates, request
identity, accounting and errors, never raw vendor responses. Endpoint
paths and fields are pinned to the OpenAPI examples fetched on 2026-10-16 under
tests/fixtures/scrapecreators/openapi/ (each records its source URL and date).
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import heapq
import itertools
import json
import math
import os
import re
import secrets
import threading
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from library_resources import ResourceError, _invalid
from research_playbooks import compute_outliers
from uoink_core.storage import _atomic_write_text


BASE_URL = "https://api.scrapecreators.com"
TIMEOUT_SEC = 8
MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 3
MAX_CANDIDATES = 60
MAX_RUN_BYTES = 256 * 1024
MAX_RUN_FILES_PER_PACKET = 24
INTENT_TTL_SEC = 5 * 60
BALANCE_ENDPOINT = "/v1/credit-balance"

# Explicit endpoint/field table. Never search arbitrary nested vendor objects.
# None means the supplied example has no such field; never infer missing metrics.
ENDPOINTS = {
    ("creator", "tiktok"): {
        "path": "/v3/tiktok/profile/videos", "rows": "aweme_list", "cursor": "max_cursor",
        "id": "aweme_id", "url": "url", "author": "author.unique_id", "caption": "desc",
        "date": "create_time", "duration": "video.duration", "duration_scale": 1000,
        "metrics": ("statistics.play_count", "statistics.digg_count", "statistics.comment_count", "statistics.share_count")},
    ("creator", "instagram"): {
        "path": "/v1/instagram/user/reels", "rows": "items", "cursor": "max_id",
        "url": "url", "author": "user.username", "caption": "caption.text",
        "date": "taken_at", "duration": "image_versions2.scrubber_spritesheet_info_candidates.default.video_length", "duration_scale": 1,
        "metrics": ("play_count", "like_count", "comment_count", None)},
    ("creator", "youtube"): {
        "path": "/v1/youtube/channel-videos", "rows": "videos", "cursor": "continuationToken",
        "url": "url", "author": None, "caption": "title",
        "date": "publishedTime", "duration": "lengthSeconds", "duration_scale": 1,
        "metrics": ("viewCountInt", None, None, None)},
    ("creator", "youtube_shorts"): {
        "path": "/v1/youtube/channel/shorts", "rows": "shorts", "cursor": "continuationToken",
        "url": "url", "author": None, "caption": "title",
        "date": "publishDate", "duration": "durationMs", "duration_scale": 1000,
        "metrics": ("viewCountInt", "likeCountInt", "commentCountInt", None)},
    ("keyword", "tiktok"): {
        "path": "/v1/tiktok/search/keyword", "rows": "search_item_list", "cursor": "cursor",
        "id": "aweme_id", "url": "url", "author": "author.unique_id", "caption": "desc",
        "date": "create_time", "duration": "video.duration", "duration_scale": 1000,
        "metrics": ("statistics.play_count", "statistics.digg_count", "statistics.comment_count", "statistics.share_count")},
    ("keyword", "youtube"): {
        "path": "/v1/youtube/search", "rows": "videos", "cursor": "continuationToken",
        "url": "url", "author": "channel.handle", "caption": "title",
        "date": "publishedTime", "duration": "lengthSeconds", "duration_scale": 1,
        "metrics": ("viewCountInt", None, None, None)},
}
_PATHS = frozenset(spec["path"] for spec in ENDPOINTS.values()) | {BALANCE_ENDPOINT}
_network_lock = threading.Lock()
_queue_lock = threading.Lock()
_last_sent_at = None


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes
    url: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def _validate_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != "api.scrapecreators.com"
            or parsed.path not in _PATHS or parsed.fragment):
        raise _invalid("discovery_host_refused")


def transport(method, url, headers, timeout, max_bytes):
    """Read at most cap+1 bytes, including errors. Never follow any redirect."""
    _validate_url(url)
    if method != "GET":
        raise _invalid("discovery_method_refused")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return TransportResponse(response.code, response.read(max_bytes + 1), response.geturl())


def _text(value, limit):
    if not isinstance(value, str):
        return None
    return "".join(c for c in value if c >= " " and not 0x7f <= ord(c) < 0xa0
                   and not 0xd800 <= ord(c) <= 0xdfff)[:limit]


def _number(value):
    try:
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            return value
    except OverflowError:
        pass
    return None


def _field(row, path):
    for name in (path or "").split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(name)
    return row


def _stamp(value):
    try:
        if _number(value) is not None:
            return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()
        if isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc).astimezone(dt.timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return None  # Relative vendor dates are not invented absolute dates.


def validate_arguments(arguments, *, balance=False):
    allowed = {"confirm_credits", "user_intent_token"}
    if not balance:
        allowed |= {"mode", "platform", "handle", "channel_id", "query", "pages"}
    if not isinstance(arguments, dict) or set(arguments) - allowed:
        raise _invalid("discovery_arguments")
    args = dict(arguments)
    token = args.pop("user_intent_token", None)
    if token is not None and (not isinstance(token, str) or not 1 <= len(token) <= 256):
        raise _invalid("user_intent_token")
    if "confirm_credits" in args and type(args["confirm_credits"]) is not int:
        raise _invalid("confirm_credits")
    if balance:
        return args, token
    if (not isinstance(args.get("mode"), str) or not isinstance(args.get("platform"), str)
            or (args["mode"], args["platform"]) not in ENDPOINTS):
        raise _invalid("discovery_mode_platform")
    pages = args.setdefault("pages", 1)
    if type(pages) is not int or not 1 <= pages <= MAX_PAGES:
        raise _invalid("pages")
    for name, limit in (("handle", 100), ("query", 200), ("channel_id", 100)):
        if name not in args:
            continue
        value = args[name]
        if not isinstance(value, str) or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in value):
            raise _invalid(name)
        value = value.strip()
        if name == "handle":
            value = value.removeprefix("@")
        if not 1 <= len(value) <= limit:
            raise _invalid(name)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise _invalid(name) from None
        args[name] = value
    if args["mode"] == "keyword":
        if "query" not in args or "handle" in args or "channel_id" in args:
            raise _invalid("query")
    else:
        if "query" in args or ("handle" in args) == ("channel_id" in args):
            raise _invalid("handle_or_channel_id")
        if "channel_id" in args and (not args["platform"].startswith("youtube")
                or not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", args["channel_id"])):
            raise _invalid("channel_id")
    return args, token


def validate_queue_arguments(arguments):
    """T6's queue tool shares the same operation-bound dashboard capability."""
    if not isinstance(arguments, dict) or set(arguments) - {"run_id", "keys", "user_intent_token"}:
        raise _invalid("discovery_queue_arguments")
    args = dict(arguments)
    token = args.pop("user_intent_token", None)
    if token is not None and (not isinstance(token, str) or not 1 <= len(token) <= 256):
        raise _invalid("user_intent_token")
    if not isinstance(args.get("run_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", args["run_id"]):
        raise _invalid("run_id")
    keys = args.get("keys")
    if (not isinstance(keys, list) or not 1 <= len(keys) <= 10
            or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key) for key in keys)):
        raise _invalid("keys")
    args["keys"] = sorted(set(keys))
    return args, token


def normalize_author(value):
    """Match handles and YouTube channel IDs without inventing an identity."""
    value = _text(value, 200) or ""
    value = value.strip().removeprefix("@")
    if value.startswith("channel/"):
        value = value[len("channel/"):]
    return value


def parse_candidates(payload, args, backend):
    spec = ENDPOINTS[(args["mode"], args["platform"])]
    rows = _field(payload, spec["rows"])
    if not isinstance(rows, list):
        raise _invalid("discovery_response_shape")
    if (args["mode"], args["platform"]) == ("keyword", "youtube"):
        # The pinned search example has a separate shorts list with the same
        # fields as videos. Tag it explicitly; canonical URLs are watch URLs.
        shorts = payload.get("shorts", [])
        if not isinstance(shorts, list):
            raise _invalid("discovery_response_shape")
        rows = [(row, "youtube") for row in rows] + [(row, "youtube_shorts") for row in shorts]
    else:
        rows = [(row, args["platform"]) for row in rows]
    result, seen = [], set()
    for raw, candidate_platform in rows:
        row = _field(raw, spec["row"]) if "row" in spec else raw
        if not isinstance(row, dict):
            continue
        url = _field(row, spec.get("url"))
        if not isinstance(url, str) or len(url) > 2048:
            continue
        canonical, platform = backend._normalize_video_url(url)
        expected = "youtube" if args["platform"] == "youtube_shorts" else args["platform"]
        if not canonical or platform != expected:
            continue
        parsed = urlparse(canonical)
        video_id = (parse_qs(parsed.query).get("v", [None])[0] if platform == "youtube"
                    else parsed.path.rstrip("/").split("/")[-1])
        if platform == "tiktok":
            # The profile OpenAPI example pairs another post's URL with this
            # row's aweme_id and metrics. Never rank one post and capture another.
            video_id = _field(row, spec["id"])
            if not isinstance(video_id, str) or not re.fullmatch(r"[0-9]{1,32}", video_id):
                continue
            match = re.fullmatch(r"/@[^/]+/video/([0-9]+)/?", parsed.path)
            if not match or match[1] != video_id:
                author = _field(row, spec["author"])
                if not isinstance(author, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,100}", author):
                    continue
                canonical, platform = backend._normalize_video_url(
                    f"https://www.tiktok.com/@{author}/video/{video_id}")
                if not canonical or platform != "tiktok":
                    continue
        if not video_id or (platform, video_id) in seen:
            continue
        seen.add((platform, video_id))
        duration = _number(_field(row, spec["duration"]))
        result.append({
            "key": hashlib.sha256(canonical.encode()).hexdigest()[:24],
            "url": canonical, "platform": candidate_platform, "video_id": video_id,
            "author_handle": normalize_author(_field(row, spec["author"]) or
                                               args.get("handle") or args.get("channel_id"))[:100],
            "caption": _text(_field(row, spec["caption"]), 300) or "",
            "published_at": _stamp(_field(row, spec["date"])),
            "duration_s": duration / spec["duration_scale"] if duration is not None else None,
            "metrics": {name: _number(_field(row, path)) for name, path in
                        zip(("views", "likes", "comments", "shares"), spec["metrics"])},
            "lift": None, "label": "none", "in_library": False,
            "state": "new", "pending_id": None,
        })
        if len(result) >= MAX_CANDIDATES:
            break
    cursor = _field(payload, spec["cursor"])
    if cursor in (None, "", 0, "0"):
        cursor = None
    elif type(cursor) not in (str, int) or len(str(cursor)) > 2048:
        raise _invalid("discovery_cursor")
    # Conservative: any vendor rows beyond the cap mean omitted data.
    return result, cursor, len(rows) > MAX_CANDIDATES


def _redact(value, key):
    """Redact decoded strings too: JSON escapes must not hide an echoed key."""
    if isinstance(value, str):
        return value.replace(key, "[redacted]")
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, dict):
        return {_redact(name, key): _redact(item, key) for name, item in value.items()}
    return value


def _baselines(candidates, fetched_at):
    rows = [{"kind": "discovery", "item_id": c["video_id"], "url": c["url"],
             "platform": "youtube" if c["platform"] == "youtube_shorts" else c["platform"],
             "source_type": "video" if c["platform"] == "youtube" else "short_video",
             "title": c["caption"], "upload_date": c["published_at"],
             "metric": {**c["metrics"], "as_of": fetched_at}} for c in candidates]
    baselines = compute_outliers(rows)
    for candidate, row in zip(candidates, rows):
        metric = row["metric"]
        candidate.update(lift=metric["lift"], label=metric["label"] if metric["label"] != "too fresh" else "none")
    return baselines


def _run_scope(args):
    """Filesystem-safe request identity, including a digest of the full target.

    The readable prefix is only a label. The digest prevents long handles,
    Unicode, punctuation or keyword searches from colliding after sanitizing.
    Creator handles match case-insensitively, as in the local playbook reader.
    """
    field = next(name for name in ("handle", "channel_id", "query") if name in args)
    value = args[field].casefold() if field == "handle" else args[field]
    label = re.sub(r"[^a-zA-Z0-9_]", "_", value)[:16]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{args['mode']}-{args['platform']}-{field}-{label}-{digest}"


def recent_runs(data_root, *, now=None, mode=None, platform=None, handle=None,
                channel_id=None, query=None, include_keyword=False, youtube_author=None):
    """Bounded discovery input for packet builders: at most 24 file reads.

    Filter filenames by request identity BEFORE applying the read budget, so
    unrelated newer runs cannot displace a creator's newest snapshot. Supplying
    a handle without a platform includes that creator's supported platforms.
    Empty failed receipts carry a -failed filename marker and use no reads.
    Packet builders must use this iterator to benefit from the read cap.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    root = Path(data_root) / "discovery" / "runs"
    if not root.resolve().is_relative_to(Path(data_root).resolve()):
        return
    earliest = now - dt.timedelta(days=30)
    months = sorted({(earliest + dt.timedelta(days=n)).strftime("%Y-%m") for n in range(31)}, reverse=True)
    target = {k: v for k, v in (("handle", handle), ("channel_id", channel_id), ("query", query)) if v is not None}
    scopes = set()
    if target:
        for candidate_mode, candidate_platform in ENDPOINTS:
            if ((mode is not None and mode != candidate_mode)
                    or (platform is not None and platform != candidate_platform)):
                continue
            targets = [target]
            if youtube_author and candidate_mode == "creator" and candidate_platform.startswith("youtube"):
                field = "channel_id" if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", youtube_author) else "handle"
                targets.append({field: youtube_author})
            for candidate_target in targets:
                try:
                    args, _ = validate_arguments({"mode": candidate_mode, "platform": candidate_platform, **candidate_target})
                    scopes.add(_run_scope(args))
                except ResourceError:
                    continue
        if not scopes:
            return
    patterns = [f"*-{scope}-*.json" for scope in scopes] if scopes else ["*.json"]
    remaining = MAX_RUN_FILES_PER_PACKET
    def read_patterns(patterns, *, keywords=False):
        nonlocal remaining
        folders = [root / month for month in months if (root / month).exists()
                   and (root / month).resolve().is_relative_to(root.resolve())]
        # Share the read budget across target platforms, including prior
        # months. Heavy use on one platform must not hide another's newest run.
        batches = [heapq.nlargest(remaining, (path for folder in folders for path in folder.glob(pattern)
                                             if not path.name.endswith("-failed.json")))
                   for pattern in sorted(patterns)]
        for batch in itertools.zip_longest(*batches):
            for path in batch:
                if path is None:
                    continue
                if remaining == 0:
                    return
                remaining -= 1
                try:
                    if not path.resolve().is_relative_to(root.resolve()):
                        continue
                    with path.open("rb") as stream:
                        raw = stream.read(MAX_RUN_BYTES + 1)
                    if len(raw) > MAX_RUN_BYTES:
                        continue
                    run = json.loads(raw)
                    if not isinstance(run, dict):
                        continue
                    if not keywords and scopes and _run_scope(run) not in scopes:
                        continue
                    if not keywords and ((mode is not None and run.get("mode") != mode)
                            or (platform is not None and run.get("platform") != platform)):
                        continue
                    fetched = dt.datetime.fromisoformat(run["fetched_at"])
                    if (run.get("provider") == "scrapecreators" and earliest <= fetched <= now
                            and isinstance(run.get("candidates"), list) and len(run["candidates"]) <= MAX_CANDIDATES):
                        if keywords and (run.get("mode") != "keyword" or not any(
                                isinstance(c, dict) and normalize_author(c.get("author_handle")).casefold()
                                in {normalize_author(handle or channel_id).casefold(),
                                    normalize_author(youtube_author).casefold() if c.get("platform") in
                                    ("youtube", "youtube_shorts") and youtube_author else None}
                                for c in run["candidates"])):
                            continue
                        yield run
                except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
                    continue

    yield from read_patterns(patterns)
    # Search filenames identify queries, not creators. Scan only their bounded
    # remainder, after the target-filtered creator reads, and match row authors.
    if include_keyword and (handle is not None or channel_id is not None) and remaining:
        keyword_platforms = ("youtube", "tiktok") if platform is None else (
            "youtube" if platform == "youtube_shorts" else platform,)
        yield from read_patterns([f"*-keyword-{p}-query-*.json" for p in keyword_platforms], keywords=True)


def purge_expired_runs(data_root, *, now=None):
    """The existing daily purge calls this; only our dated run files qualify."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=90)
    root = Path(data_root) / "discovery" / "runs"
    if not root.exists() or not root.resolve().is_relative_to(Path(data_root).resolve()):
        return 0
    purged = 0
    for folder in root.iterdir():
        if not re.fullmatch(r"\d{4}-\d{2}", folder.name) or not folder.is_dir():
            continue
        if not folder.resolve().is_relative_to(root.resolve()):
            continue
        for path in folder.glob("*.json"):
            # The generated filename supplies the date; never open unbounded
            # vendor data or delete unknown files based only on their mtime.
            if not re.fullmatch(r"\d{8}T\d{12}Z-(?:(?:creator|keyword)-(?:tiktok|instagram|youtube|youtube_shorts)-"
                                r"(?:handle|channel_id|query)-[A-Za-z0-9_]{1,16}-[0-9a-f]{24}-)?[0-9a-f]{16}(?:-failed)?\.json", path.name):
                continue
            try:
                created = dt.datetime.strptime(path.name.split("-")[0], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=dt.timezone.utc)
                if created < cutoff and path.resolve().is_relative_to(root.resolve()):
                    path.unlink()
                    purged += 1
            except (OSError, ValueError):
                continue
    return purged


class DiscoveryService:
    def __init__(self, backend, *, transport=transport, clock=time.time,
                 monotonic=time.monotonic, sleep=time.sleep):
        self.backend = backend
        self.transport = transport
        self.clock, self.monotonic, self.sleep = clock, monotonic, sleep
        self._intents = {}
        self._mint_times = []
        self._intent_lock = threading.Lock()
        # Only normalized receipts, never credentials or raw provider payloads.
        # Keep failed saves until an explicit local retry succeeds.
        self._unsaved_runs = {}

    def _now(self):
        return dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc)

    @staticmethod
    def _operation(args, balance, *, queue=False):
        return {"tool": "queue_discovered" if queue else "test_key" if balance else "discover_candidates",
                "arguments": {k: v for k, v in args.items() if k != "confirm_credits"}}

    def mint_intent(self, body, *, origin, session_hash):
        """Only the token/origin-gated HTTP route calls this, never an MCP tool.

        A helper-token holder can omit browser metadata; this is not proof of
        a human click. The route checks supplied browser origins for CSRF.

        Body: {confirmed:true, operation:{tool:'discover_candidates'|'test_key'|'queue_discovered',
        arguments:{...}}}. The capability is single-use and operation-bound.
        """
        try:
            if (not isinstance(body, dict) or set(body) != {"confirmed", "operation"}
                    or body["confirmed"] is not True or not origin or not session_hash):
                raise _invalid("discovery_intent")
            operation = body["operation"]
            if (not isinstance(operation, dict) or set(operation) != {"tool", "arguments"}
                    or operation["tool"] not in ("discover_candidates", "test_key", "queue_discovered")):
                raise _invalid("discovery_operation")
            balance = operation["tool"] == "test_key"
            queue = operation["tool"] == "queue_discovered"
            args, token = (validate_queue_arguments(operation["arguments"]) if queue else
                           validate_arguments(operation["arguments"], balance=balance))
            if token is not None:
                raise _invalid("discovery_intent")
            now = self.clock()
            with self._intent_lock:
                self._mint_times = [t for t in self._mint_times if t > now - 60]
                self._intents = {k: v for k, v in self._intents.items() if v[0] > now}
                if len(self._mint_times) >= 30:
                    raise ResourceError("rate_limited", details={"retry_after_ms": 60000})
                token = secrets.token_urlsafe(32)
                self._intents[hashlib.sha256(token.encode()).hexdigest()] = (
                    now + INTENT_TTL_SEC, origin, session_hash, self._operation(args, balance, queue=queue))
                self._mint_times.append(now)
            return {"ok": True, "user_intent_token": token, "expires_at": now + INTENT_TTL_SEC}
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    def _consume_intent(self, token, args, balance, origin, session_hash, *, queue=False):
        if token is None:
            return False
        with self._intent_lock:
            digest = hashlib.sha256(token.encode()).hexdigest()
            saved = self._intents.get(digest)
            if (not saved or saved[0] <= self.clock() or saved[1:] !=
                    (origin, session_hash, self._operation(args, balance, queue=queue))):
                raise _invalid("invalid_user_intent")
            del self._intents[digest]
        return True

    def authorize_queue(self, arguments, *, origin="", session_hash=""):
        """T6 calls this before enqueueing picks. No provider/key/ledger access."""
        try:
            args, token = validate_queue_arguments(arguments)
            consent = self._consume_intent(token, args, False, origin, session_hash, queue=True)
            if not consent and self.backend._read_settings().get("scrapecreators_agent_calls_enabled") is not True:
                raise _invalid("user_intent_required")
            return {"ok": True, "arguments": args}
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    def _run_path(self, run_id):
        # Resolve exactly one dated file; no directory walk or caller path.
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", run_id):
            raise _invalid("run_id")
        try:
            stamp = dt.datetime.strptime(run_id.split("-")[0], "%Y%m%dT%H%M%S%fZ")
        except ValueError:
            raise ResourceError("resource_not_found") from None
        path = Path(self.backend.DATA_ROOT) / "discovery" / "runs" / stamp.strftime("%Y-%m") / (run_id + ".json")
        if not path.resolve().is_relative_to(Path(self.backend.DATA_ROOT).resolve()):
            raise _invalid("discovery_storage_path")
        return path

    def _load_run(self, run_id):
        path = self._run_path(run_id)
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_RUN_BYTES + 1)
        except FileNotFoundError:
            raise ResourceError("resource_not_found") from None
        if len(raw) > MAX_RUN_BYTES:
            raise _invalid("discovery_run_too_large")
        run = json.loads(raw)
        if (not isinstance(run, dict) or run.get("run_id") != run_id
                or run.get("provider") != "scrapecreators"
                or not isinstance(run.get("candidates"), list)
                or len(run["candidates"]) > MAX_CANDIDATES
                or any(not isinstance(c, dict) for c in run["candidates"])):
            raise _invalid("discovery_run_invalid")
        return run

    def _candidate_url(self, candidate):
        url = candidate.get("url")
        if not isinstance(url, str) or len(url) > 2048:
            return None
        canonical, platform = self.backend._normalize_video_url(url)
        expected = candidate.get("platform")
        expected = "youtube" if expected == "youtube_shorts" else expected
        if not canonical or platform not in ("youtube", "tiktok", "instagram") or platform != expected:
            return None
        parsed = urlparse(canonical)
        vid = (parse_qs(parsed.query).get("v", [None])[0] if platform == "youtube"
               else parsed.path.rstrip("/").split("/")[-1])
        return canonical if vid and vid == candidate.get("video_id") else None

    def _refresh_candidates(self, idx, run):
        """Caller holds the index lock. Never resurrect a deleted capture."""
        for candidate in run["candidates"]:
            canonical = self._candidate_url(candidate)
            if canonical is None:
                continue
            candidate["url"] = canonical
            existing = idx.get_yoink(candidate["video_id"])
            candidate["in_library"] = bool(existing and not existing.get("deleted_at"))
            if candidate["in_library"]:
                candidate["state"] = "captured"
                continue
            # An active row from another run (or a prior interrupted save)
            # counts too. Do not page list_pending and miss an older live row.
            pending = idx._conn.execute(
                "SELECT pending_id,status FROM pending_yoinks WHERE url=? "
                "AND (status IN ('pending','running','publishing') OR pending_id=?) "
                "ORDER BY CASE WHEN status IN ('pending','running','publishing') THEN 0 ELSE 1 END, pending_id DESC LIMIT 1",
                (canonical, candidate.get("pending_id"))).fetchone()
            if pending:
                candidate["pending_id"] = pending["pending_id"]
                candidate["state"] = (
                    "queued" if pending["status"] in ("pending", "running", "publishing") else
                    "deleted" if existing and existing.get("deleted_at") else
                    "failed" if pending["status"] == "failed" else
                    "cancelled" if pending["status"] == "cancelled" else "unavailable")
            elif existing and existing.get("deleted_at"):
                candidate["state"] = "deleted"
            elif candidate.get("pending_id") is not None:
                # Terminal rows may have been purged. Retain the last receipt
                # only when it recorded an actual failure or cancellation.
                if candidate.get("state") not in ("failed", "cancelled"):
                    candidate["state"] = "unavailable"
            elif candidate.get("state") in ("captured", "deleted", "unavailable"):
                candidate["state"] = "unavailable"
            else:
                candidate["state"] = "new"

    def read_run(self, run_id):
        """Read a saved run and lazily reconcile normal capture queue state."""
        try:
            with _queue_lock:
                run = self._load_run(run_id)
                idx = self.backend._get_index()
                with idx._lock:
                    self._refresh_candidates(idx, run)
                    self._save_run(run)
                return run
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    def queue_discovered(self, arguments, *, origin="", session_hash=""):
        authorized = self.authorize_queue(arguments, origin=origin, session_hash=session_hash)
        if authorized.get("ok") is not True:
            return authorized
        try:
            args = authorized["arguments"]
            with _queue_lock:
                run = self._load_run(args["run_id"])
                idx = self.backend._get_index()
                queued, skipped = [], []
                with idx._lock:
                    self._refresh_candidates(idx, run)
                    candidates = {c.get("key"): c for c in run["candidates"]}
                    for key in args["keys"]:
                        candidate = candidates.get(key)
                        canonical = self._candidate_url(candidate) if candidate else None
                        reason = ("unknown_key" if candidate is None else
                                  "unsupported_url" if canonical is None else
                                  "in_library" if candidate["in_library"] else
                                  "already_queued" if candidate.get("state") == "queued" else None)
                        if reason:
                            skipped.append({"key": key, "reason": reason})
                            continue
                        # The retry worker compares local naive ISO strings.
                        # Credits/run timestamps use UTC, but queue dates must
                        # use the backend clock, as mobile playlists do.
                        pending_id, inserted = idx.enqueue_pending_once(
                            canonical, 30, retry_after=self.backend._now_iso())
                        candidate.update(pending_id=pending_id, state="queued")
                        if inserted:
                            queued.append({"key": key, "pending_id": pending_id})
                        else:
                            skipped.append({"key": key, "reason": "already_queued"})
                        # Duplicate URLs inside a saved file cannot enqueue twice.
                        self._refresh_candidates(idx, run)
                    self._save_run(run)
                return {"ok": True, "run_id": run["run_id"], "queued": queued,
                        "skipped": skipped, "candidates": run["candidates"]}
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    @staticmethod
    def _bucket(conn, key):
        row = conn.execute("SELECT value FROM memory_layer WHERE key=?", (key,)).fetchone()
        value = json.loads(row[0]) if row else {}
        if not isinstance(value, dict):
            raise _invalid("discovery_ledger_invalid")
        for field in ("calls", "credits", "failures"):
            if field in value and (type(value[field]) is not int or value[field] < 0):
                raise _invalid("discovery_ledger_invalid")
        return value

    def _credits_today(self, idx):
        with idx._lock:
            return self._bucket(idx._conn, "usage.scrapecreators.day." + self._now().strftime("%Y-%m-%d")).get("credits", 0)

    def _record(self, idx, endpoint, sent_at, *, cap, failure=False):
        stamp = sent_at.isoformat()
        month_key = "usage.scrapecreators." + endpoint.strip("/").replace("/", "_") + "." + sent_at.strftime("%Y-%m")
        day_key = "usage.scrapecreators.day." + sent_at.strftime("%Y-%m-%d")
        with idx.write_transaction() as conn:
            month = self._bucket(conn, month_key)
            if failure:
                month["failures"] = month.get("failures", 0) + 1
                buckets = ((month_key, month),)
            else:
                day = self._bucket(conn, day_key)
                if day.get("credits", 0) >= cap:
                    raise _invalid("daily_cap_reached")
                day["credits"] = day.get("credits", 0) + 1
                month.update(calls=month.get("calls", 0) + 1, credits=month.get("credits", 0) + 1,
                             failures=month.get("failures", 0), last_call_at=stamp)
                buckets = ((day_key, day), (month_key, month))
            for key, value in buckets:
                conn.execute("INSERT INTO memory_layer(key,value,updated_at) VALUES(?,?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                             (key, json.dumps(value, allow_nan=False), stamp))

    def discover_candidates(self, arguments, *, origin="", session_hash=""):
        return self._call(arguments, balance=False, origin=origin, session_hash=session_hash)

    def test_key(self, arguments, *, origin="", session_hash=""):
        return self._call(arguments, balance=True, origin=origin, session_hash=session_hash)

    def _call(self, arguments, *, balance, origin, session_hash):
        # Both HTTP and later MCP adapters receive the standard error envelope,
        # even for unexpected exceptions. Never render or log vendor errors.
        try:
            args, token = validate_arguments(arguments, balance=balance)
            planned = 1 if balance else args["pages"]
            if "confirm_credits" in args and args["confirm_credits"] != planned:
                raise _invalid("confirm_credits_mismatch")
            settings = self.backend._read_settings()
            if settings.get("scrapecreators_enabled") is not True:
                raise _invalid("discovery_disabled")
            key = self.backend._get_saved_scrapecreators_key()
            if not key:
                raise _invalid("scrapecreators_key_required")
            if any(key in args.get(field, "") for field in ("handle", "channel_id", "query")):
                raise _invalid("discovery_sensitive_input")
            if settings.get("scrapecreators_key_invalid") and not balance:
                raise _invalid("scrapecreators_key_invalid")
            cap = settings.get("scrapecreators_daily_credit_cap", 25)
            if type(cap) is not int or not 1 <= cap <= 500:
                raise _invalid("daily_cap_invalid")
            idx = self.backend._get_index()
            today = self._credits_today(idx)
            if today + planned > cap:
                raise _invalid("daily_cap_reached")
            if "confirm_credits" not in args:
                return {"ok": True, "needs_confirmation": True, "credits_planned": planned,
                        "credits_today": today, "daily_cap": cap,
                        **({"notice": "Checking the balance may use a credit."} if balance else {})}
            if not _network_lock.acquire(blocking=False):
                raise ResourceError("rate_limited", details={"retry_after_ms": 1000})
            try:
                if self._credits_today(idx) + planned > cap:
                    raise _invalid("daily_cap_reached")
                consent = self._consume_intent(token, args, balance, origin, session_hash)
                if not consent and settings.get("scrapecreators_agent_calls_enabled") is not True:
                    raise _invalid("user_intent_required")
                return self._run(idx, args, key, cap, balance, consent=consent)
            finally:
                _network_lock.release()
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    def _run(self, idx, args, key, cap, balance, *, consent):
        global _last_sent_at
        spec = None if balance else ENDPOINTS[(args["mode"], args["platform"])]
        endpoint = BALANCE_ENDPOINT if balance else spec["path"]
        params = {} if balance else {"trim": "true"}
        for name in ("handle", "channel_id", "query"):
            if name in args:
                params["channelId" if name == "channel_id" else name] = args[name]
        now = self._now()
        scope = "" if balance else _run_scope(args) + "-"
        run = {"ok": True, "run_id": now.strftime("%Y%m%dT%H%M%S%fZ-") + scope + secrets.token_hex(8),
               "provider": "scrapecreators", "endpoint": endpoint, "fetched_at": now.isoformat(),
               "credits_used": 0, "daily_cap": cap,
               "coverage": {"pages": 0, "items": 0, "truncated": False, "next_cursor_present": False},
               "candidates": []}
        if not balance:
            run.update({name: args[name] for name in ("mode", "platform", "handle", "channel_id", "query") if name in args})
        seen, cursors = set(), set()
        for _ in range(1 if balance else args["pages"]):
            charged = False
            try:
                url = BASE_URL + endpoint + ("?" + urlencode(params) if params else "")
                _validate_url(url)
                # Reject accidental credential input/echo before it can reach a URL.
                if key in url or any(key in str(value) for value in params.values()):
                    raise _invalid("discovery_sensitive_input")
                if _last_sent_at is not None:
                    delay = 1 - (self.monotonic() - _last_sent_at)
                    if delay > 0:
                        self.sleep(delay)
                current = self.backend._read_settings()
                if current.get("scrapecreators_enabled") is not True:
                    raise _invalid("discovery_disabled")
                if not consent and current.get("scrapecreators_agent_calls_enabled") is not True:
                    raise _invalid("user_intent_required")
                if self.backend._get_saved_scrapecreators_key() != key:
                    raise _invalid("scrapecreators_key_changed")
                if current.get("scrapecreators_key_invalid") and not balance:
                    raise _invalid("scrapecreators_key_invalid")
                cap = current.get("scrapecreators_daily_credit_cap", 25)
                if type(cap) is not int or not 1 <= cap <= 500:
                    raise _invalid("daily_cap_invalid")
                run["daily_cap"] = cap
                sent_at = self._now()
                self._record(idx, endpoint, sent_at, cap=cap)
                charged = True
                run["credits_used"] += 1
                _last_sent_at = self.monotonic()
                response = self.transport("GET", url, {"x-api-key": key, "User-Agent": "Uoink/" + self.backend.VERSION}, TIMEOUT_SEC, MAX_BYTES)
                if response.url != url:
                    raise _invalid("discovery_redirect_refused")
                if 300 <= response.status < 400:
                    raise _invalid("discovery_redirect_refused")
                if response.status in (401, 403):
                    self.backend._mark_scrapecreators_key_invalid(expected_key=key)
                    raise _invalid("scrapecreators_key_invalid")
                if response.status != 200:
                    raise _invalid("discovery_rate_limited" if response.status == 429 else "discovery_upstream_error")
                if not isinstance(response.body, bytes) or len(response.body) > MAX_BYTES:
                    raise _invalid("discovery_response_too_large")
                payload = _redact(json.loads(response.body.decode("utf-8"), parse_constant=lambda _: None), key)
                if not isinstance(payload, dict):
                    raise _invalid("discovery_response_shape")
                run["coverage"]["pages"] += 1
                if balance:
                    amount = _number(payload.get("creditCount"))
                    if amount is None:
                        raise _invalid("discovery_response_shape")
                    run["balance"] = amount
                    self.backend._mark_scrapecreators_key_invalid(False, expected_key=key)
                    break
                candidates, cursor, truncated = parse_candidates(payload, args, self.backend)
                fetched = []
                for candidate in candidates:
                    if candidate["key"] in seen:
                        continue
                    if len(run["candidates"]) == MAX_CANDIDATES:
                        truncated = True
                        break
                    seen.add(candidate["key"])
                    # Keep the entire normalized page before consulting SQLite.
                    # A local lookup failure must not discard paid candidates.
                    run["candidates"].append(candidate)
                    fetched.append(candidate)
                run["coverage"].update(truncated=run["coverage"]["truncated"] or truncated,
                                        next_cursor_present=cursor is not None)
                for candidate in fetched:
                    existing = idx.get_yoink(candidate["video_id"])
                    candidate["in_library"] = bool(existing and not existing.get("deleted_at"))
                    if candidate["in_library"]:
                        candidate["state"] = "captured"
                    elif existing and existing.get("deleted_at"):
                        candidate["state"] = "deleted"
                if cursor is None:
                    break
                if str(cursor) in cursors or len(run["candidates"]) == MAX_CANDIDATES:
                    run["coverage"]["truncated"] = True
                    break
                cursors.add(str(cursor))
                params[spec["cursor"]] = cursor
            except Exception as exc:
                if charged:
                    try:
                        self._record(idx, endpoint, sent_at, cap=cap, failure=True)
                    except Exception:
                        # The spend was recorded before sending. A failed local
                        # failure-counter update cannot erase the paid receipt.
                        pass
                error = exc if isinstance(exc, ResourceError) else ResourceError("internal_error")
                run.update(error.envelope())
                run["last_error"] = run["error"]
                break  # Sent requests count even on timeout, 401, 429 or 5xx.
        try:
            run["credits_today"] = self._credits_today(idx)
        except Exception:
            # Report an unknown daily total, never a made-up zero. The next
            # paid call still fails closed on its normal ledger preflight.
            run["credits_today"] = None
            if run["ok"]:
                run.update(ResourceError("internal_error").envelope())
                run["last_error"] = run["error"]
        run["coverage"]["items"] = len(run["candidates"])
        run["coverage"]["truncated"] |= run["coverage"]["next_cursor_present"]
        if not balance:
            # The outcome is final before the first save. Keep failed receipts
            # addressable by ID while letting packet readers exclude them by
            # filename, before spending their bounded file-read budget.
            if not run["candidates"] and run["ok"] is False:
                run["run_id"] += "-failed"
            run["baselines"] = _baselines(run["candidates"], run["fetched_at"])
            # Keep the single-group convenience field without attributing one
            # group's median to a mixed video/Shorts result.
            run["baseline"] = run["baselines"][0] if len(run["baselines"]) == 1 else None
            with _queue_lock:
                self._save_discovery_result(run)
        return run

    def _save_discovery_result(self, run, *, exclusive=False):
        """A disk failure must not turn paid results into an empty error."""
        try:
            self._save_run(run, exclusive=exclusive)
        except Exception:
            run["save_failed"] = True
            self._unsaved_runs[run["run_id"]] = copy.deepcopy(run)

    def retry_save(self, arguments):
        """Save a retained receipt only; no provider, key, ledger or queue work."""
        try:
            if not isinstance(arguments, dict) or set(arguments) != {"run_id"}:
                raise _invalid("discovery_save_arguments")
            run_id = arguments["run_id"]
            path = self._run_path(run_id)
            with _queue_lock:
                retained = self._unsaved_runs.get(run_id)
                if retained is None:
                    return self._load_run(run_id)  # An already completed retry.
                run = copy.deepcopy(retained)
                run.pop("save_failed", None)
                # Never overwrite a receipt changed by another process.
                if path.exists():
                    if self._load_run(run_id) != run:
                        raise _invalid("discovery_save_conflict")
                else:
                    self._save_discovery_result(run, exclusive=True)
                if not run.get("save_failed"):
                    self._unsaved_runs.pop(run_id, None)
                return run
        except ResourceError as exc:
            return exc.envelope()
        except Exception:
            return ResourceError("internal_error").envelope()

    def _save_run(self, run, *, exclusive=False):
        raw = json.dumps(run, ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > MAX_RUN_BYTES:
            raise _invalid("discovery_run_too_large")
        path = self._run_path(run["run_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if exclusive:
            # Publish a complete file without replacing any destination that
            # appeared after the conflict check (including another process).
            with tempfile.TemporaryDirectory(prefix=".save-", dir=path.parent) as staging:
                staged = Path(staging) / path.name
                _atomic_write_text(staged, raw)
                os.link(staged, path)
        else:
            _atomic_write_text(path, raw)
