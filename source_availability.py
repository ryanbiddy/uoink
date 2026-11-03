"""Polite source checks. Saved media is never modified or removed here."""

from __future__ import annotations

import json
import re
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

STATUSES = {"available", "deleted", "private", "region_blocked", "unknown"}
GONE = {"deleted", "private", "region_blocked"}
MAX_REQUESTS_PER_RUN = 25
MAX_ROWS_PER_RUN = 100
RECHECK_DAYS = 7
RUN_INTERVAL_MIN = 60
HOST_INTERVAL_SEC = 2.0
TIMEOUT_SEC = 10
MAX_BODY_BYTES = 512 * 1024

try:
    _VERSION = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
except OSError:
    _VERSION = "unknown"
USER_AGENT = f"Uoink/{_VERSION} availability check (+https://uoink.app)"


def _utc(value=None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _stamp(value) -> datetime | None:
    try:
        return _utc(value) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def default_fetch(method, url, headers, timeout, max_bytes):
    """One SSRF-checked HTTP hop, with bounded reads and HTTP errors as data."""
    from source_subscriptions import public_http_open

    try:
        response = public_http_open(
            url, method=method, headers={**headers, "User-Agent": USER_AGENT},
            timeout=timeout, follow_redirects=False,
        )
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return (response.code, dict(response.headers.items()),
                response.read(max_bytes)
                if method != "HEAD" and max_bytes and not 300 <= response.code < 400 else b"")


def _json(body):
    try:
        return json.loads(body)
    except (ValueError, UnicodeError):
        return None


def _http_url(value) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() in ("http", "https") and parsed.hostname:
            return value.strip()
    except ValueError:
        pass
    return ""


def _on_host(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _checker(row, url):
    platform = str(row.get("platform") or "").strip().lower()
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if platform == "podcast" or str(row.get("source_type") or "").strip().lower() == "episode":
        return "podcast"
    if platform == "youtube" or any(_on_host(host, d) for d in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return "youtube"
    if platform in ("x", "twitter") or any(_on_host(host, d) for d in ("x.com", "twitter.com")):
        return "x"
    if platform == "reddit" or any(_on_host(host, d) for d in ("reddit.com", "redd.it")):
        return "reddit"
    return "web"


def _watch_url(url, video_id):
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").split("/")
    candidate = (parse_qs(parsed.query).get("v") or [None])[0]
    if _on_host(parsed.hostname or "", "youtu.be"):
        candidate = parts[0]
    elif len(parts) > 1 and parts[0] in ("shorts", "embed", "live"):
        candidate = parts[1]
    candidate = candidate or video_id
    if not isinstance(candidate, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return ""
    return "https://www.youtube.com/watch?" + urlencode({"v": candidate})


def _playability(body):
    text = body.decode("utf-8", errors="replace")
    for match in re.finditer(r'"playabilityStatus"\s*:\s*', text):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[match.end():])
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        status = data.get("status")
        wording = json.dumps({key: data.get(key) for key in ("reason", "messages", "errorScreen")}).lower()
        if status == "OK":
            return "available"
        if status == "LOGIN_REQUIRED" and "private" in wording:
            return "private"
        if status == "UNPLAYABLE" and ("country" in wording or "region" in wording):
            return "region_blocked"
        if status == "ERROR" and re.search(
                r"\b(?:unavailable|removed|terminated|does not exist|no longer available)\b", wording):
            return "deleted"
    return "unknown"


def _generic_status(status):
    if 200 <= status < 300:
        return "available"
    return {404: "deleted", 410: "deleted", 451: "region_blocked"}.get(status, "unknown")


def _check(row, request):
    meta = _json(row.get("metadata_json") or "{}")
    meta = meta if isinstance(meta, dict) else {}
    url = _http_url(meta.get("url")) or _http_url(meta.get("episode_page_url"))
    checker = _checker(row, url)
    if checker == "podcast":
        url = _http_url(meta.get("audio_url")) or url
    if not url:
        return "unknown", None, "No HTTP source URL", checker

    if checker == "youtube":
        watch = _watch_url(url, row["video_id"])
        if not watch:
            return "unknown", None, "No YouTube video ID", checker
        code, _, _ = request("GET", "https://www.youtube.com/oembed?" +
                             urlencode({"url": watch, "format": "json"}), max_bytes=64 * 1024)
        observed = {200: "available", 404: "deleted"}.get(code, "unknown")
        if code in (401, 403):
            code, _, body = request("GET", watch, max_bytes=MAX_BODY_BYTES)
            observed = _playability(body) if 200 <= code < 300 else "unknown"
    elif checker == "x":
        code, _, _ = request("GET", "https://publish.twitter.com/oembed?" +
                             urlencode({"url": url, "omit_script": 1}), max_bytes=64 * 1024)
        observed = {200: "available", 404: "deleted", 403: "private"}.get(code, "unknown")
    elif checker == "reddit":
        parsed = urlsplit(url)
        match = re.search(r"/comments/([a-zA-Z0-9]+)(?:/|$)", parsed.path)
        post_id = match.group(1) if match else None
        if _on_host(parsed.hostname or "", "redd.it"):
            post_id = parsed.path.strip("/")
        if not post_id or not re.fullmatch(r"[a-zA-Z0-9]+", post_id):
            return "unknown", None, "No Reddit post ID", checker
        code, _, body = request("GET", f"https://www.reddit.com/comments/{post_id}.json?limit=1&raw_json=1",
                                max_bytes=MAX_BODY_BYTES)
        data = _json(body)
        observed = "unknown"
        if code == 404:
            observed = "deleted"
        elif code == 403 and isinstance(data, dict) and data.get("reason") == "private":
            observed = "private"
        elif code == 200:
            try:
                post = data[0]["data"]["children"][0]["data"]
                removed = (post.get("removed_by_category") or
                           post.get("selftext") == "[removed]" or
                           (post.get("selftext") == "[deleted]" and post.get("author") == "[deleted]"))
                observed = "deleted" if removed else "available"
            except (TypeError, KeyError, IndexError, AttributeError):
                pass  # A truncated JSON response is not evidence of removal.
    else:
        code, _, _ = request("HEAD", url, max_bytes=0)
        if checker == "web" and code in (405, 501):
            code, _, _ = request("GET", url, headers={"Range": "bytes=0-0"}, max_bytes=1)
        observed = _generic_status(code)
    return observed, code, f"HTTP {code}", checker


class _RequestLimit(Exception):
    pass


class _HostBackoff(Exception):
    pass


class _AdmissionRefused(Exception):
    pass


class _TransportError(Exception):
    pass


class _TooManyRedirects(Exception):
    pass


def _backoff_seconds(headers, now, strikes):
    retry = headers.get("retry-after")
    delay = None
    if retry is not None:
        try:
            delay = int(retry)
        except (ValueError, TypeError, OverflowError):
            try:
                delay = (_utc(parsedate_to_datetime(retry)) - now).total_seconds()
            except (ValueError, TypeError, OverflowError, AttributeError):
                pass
    if delay is None:
        delay = 3600 * 2 ** min(max(0, strikes), 6)
    return max(3600, min(48 * 3600, delay))


class _Requests:
    def __init__(self, index, fetch, clock, sleep, limit, summary):
        self.index, self.fetch, self.clock, self.sleep = index, fetch, clock, sleep
        self.limit, self.summary = limit, summary
        self.logical_now = _utc(clock())
        self.transport_errors = 0
        self.blocked = set()

    def moment(self):
        self.logical_now = max(self.logical_now, _utc(self.clock()))
        return self.logical_now

    def __call__(self, method, url, *, headers=None, max_bytes=MAX_BODY_BYTES):
        from source_subscriptions import ServiceError

        for _ in range(11):  # Redirects consume the same run budget as every other request.
            url = _http_url(url)
            if not url:
                raise _AdmissionRefused
            if self.summary["requests"] >= self.limit:
                raise _RequestLimit
            host = (urlsplit(url).hostname or "").lower().rstrip(".")
            state = self.index.availability_host(host)
            now = self.moment()
            until = _stamp(state.get("backoff_until"))
            if host in self.blocked or (until and until > now):
                self.blocked.add(host)
                raise _HostBackoff
            last = _stamp(state.get("last_request_at"))
            if last:
                delay = min(HOST_INTERVAL_SEC, max(0, HOST_INTERVAL_SEC - (now - last).total_seconds()))
                if delay:
                    self.sleep(delay)
                    # Frozen injected clocks still advance by the requested sleep.
                    self.logical_now = now + timedelta(seconds=delay)
                    now = self.moment()
            try:
                code, response_headers, body = self.fetch(
                    method, url, {"User-Agent": USER_AGENT, "Accept-Encoding": "identity", **(headers or {})},
                    TIMEOUT_SEC, max_bytes)
            except Exception as exc:
                if isinstance(exc, ServiceError) and exc.code in ("unsupported_source", "validation_error"):
                    raise _AdmissionRefused from exc
                self.summary["requests"] += 1
                self.index.set_availability_host(
                    host, backoff_until=state.get("backoff_until"), strikes=state.get("strikes", 0),
                    last_request_at=_iso(now))
                self.transport_errors += 1
                raise _TransportError(type(exc).__name__) from exc
            self.summary["requests"] += 1
            self.transport_errors = 0
            response_headers = {key.lower(): value for key, value in response_headers.items()}
            if code in (429, 503):
                delay = _backoff_seconds(response_headers, self.moment(), state.get("strikes", 0))
                self.index.set_availability_host(
                    host, backoff_until=_iso(self.moment() + timedelta(seconds=delay)),
                    strikes=state.get("strikes", 0) + 1, last_request_at=_iso(now))
                self.blocked.add(host)
                raise _HostBackoff
            # Redirects and auth walls must not reset repeated backoff strikes
            # before a fallback reaches the same overloaded host again.
            self.index.set_availability_host(
                host, strikes=0 if 200 <= code < 300 else state.get("strikes", 0),
                last_request_at=_iso(now))
            if code in (301, 302, 303, 307, 308) and response_headers.get("location"):
                try:
                    target = _http_url(urljoin(url, response_headers["location"]))
                except ValueError:
                    target = ""
                if not target:
                    raise _AdmissionRefused
                url = target
                continue
            return code, response_headers, body
        raise _TooManyRedirects


def _record(index, video_id, observation, now, summary):
    observed, code, detail, checker = observation
    previous = index.availability_record(video_id)
    status = previous.get("status", "unknown")
    fields = {"last_checked_at": _iso(now), "http_status": code, "detail": detail, "checker": checker}
    if observed == "unknown":
        errors = previous.get("consecutive_errors", 0) + 1
        fields.update(consecutive_errors=errors,
                      next_check_at=_iso(now + timedelta(days=7 if errors >= 3 else 1)))
    else:
        fields.update(consecutive_errors=0, next_check_at=_iso(now + timedelta(days=RECHECK_DAYS)))
        pending_since = _stamp(previous.get("pending_since"))
        if observed in GONE and observed != status:
            if (previous.get("pending_status") != observed or pending_since is None
                    or now - pending_since > timedelta(days=7)):
                fields.update(pending_status=observed, pending_since=_iso(now),
                              next_check_at=_iso(now + timedelta(days=1)))
            elif now - pending_since < timedelta(hours=20):
                fields["next_check_at"] = _iso(pending_since + timedelta(days=1))
            else:
                fields.update(status=observed, status_changed_at=_iso(now),
                              pending_status=None, pending_since=None,
                              gone_since=(previous.get("gone_since") if status in GONE else None) or _iso(now))
                summary["confirmed_gone"] += 1
                if status not in GONE:
                    summary["newly_gone"].append(video_id)
        else:
            fields.update(status=observed, pending_status=None, pending_since=None)
            if observed == "available":
                fields["gone_since"] = None
            if observed != status:
                fields["status_changed_at"] = _iso(now)
    index.record_availability(video_id, **fields)


def run_once(index, *, fetch=None, now=None, sleep=None, max_requests=MAX_REQUESTS_PER_RUN):
    """Check a bounded batch. ``now`` accepts a UTC datetime, ISO string or clock.

    An offline abort discards the final transport-error streak while keeping
    earlier observations. Backed-off and unfinished items stay due.
    """
    clock = now if callable(now) else lambda: _utc(now)
    started = _utc(clock())
    summary = {"requests": 0, "checked": 0, "confirmed_gone": 0, "newly_gone": [],
               "backed_off_hosts": [], "aborted": False}
    requests = _Requests(index, fetch or default_fetch, clock, sleep or time.sleep,
                         min(MAX_REQUESTS_PER_RUN, max(0, int(max_requests))), summary)
    index.set_availability_run_state(last_run_started_at=_iso(started),
                                     last_run_finished_at=None, last_run_json=None)
    observations = []
    error_streak = set()
    try:
        offset = 0
        exhausted = False
        while summary["requests"] < requests.limit and offset < MAX_ROWS_PER_RUN and not exhausted:
            rows = index.availability_due(
                _iso(started), min(MAX_REQUESTS_PER_RUN, MAX_ROWS_PER_RUN - offset), offset=offset)
            if not rows:
                break
            offset += len(rows)
            for row in rows:
                if summary["requests"] >= requests.limit:
                    exhausted = True
                    break
                try:
                    observation = _check(row, requests)
                except _RequestLimit:
                    exhausted = True
                    break
                except _HostBackoff:
                    continue
                except _AdmissionRefused:
                    observation = ("unknown", None, "Not a public address", "admission")
                except _TooManyRedirects:
                    observation = ("unknown", None, "Too many redirects", "redirect")
                except _TransportError as exc:
                    if requests.transport_errors == 1:
                        error_streak.clear()
                    error_streak.add(len(observations))
                    observation = ("unknown", None, str(exc), "transport")
                except Exception as exc:
                    observation = ("unknown", None, type(exc).__name__, "transport")
                if requests.transport_errors == 0:
                    error_streak.clear()
                observations.append((row["video_id"], observation, requests.moment()))
                summary["checked"] += 1
                if requests.transport_errors >= 5:
                    summary["aborted"] = exhausted = True
                    break
        for position, (video_id, observation, observed_at) in enumerate(observations):
            if not summary["aborted"] or position not in error_streak:
                _record(index, video_id, observation, observed_at, summary)
        return summary
    except Exception:
        summary["aborted"] = True
        raise
    finally:
        summary["backed_off_hosts"] = sorted(requests.blocked)
        index.set_availability_run_state(last_run_finished_at=_iso(requests.moment()),
                                         last_run_json=json.dumps(summary, sort_keys=True))


def is_due_to_run(index, now) -> bool:
    state = index.availability_run_state()
    stamps = [_stamp(state.get(key)) for key in ("last_run_started_at", "last_run_finished_at")]
    last = max((stamp for stamp in stamps if stamp is not None), default=None)
    return last is None or _utc(now) - last >= timedelta(minutes=RUN_INTERVAL_MIN)
