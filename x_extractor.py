"""X (Twitter) post text + self-thread extractor (U-15, v3.2.6).

Captures the text of an X post, plus the earlier posts in the author's own
reply chain. The public syndication endpoint supplies the chain links. It
cuts long posts short (see x_fulltext). The full text then comes from the
open X tab when the extension saves the post the person is looking at
(``dom_post``), or from FxTwitter API v2, a free community service, only
when the person turned on ``fxtwitter_enrichment_enabled`` (off by
default since 3.18.0). Otherwise the save keeps X's copy and is marked
cut off (``metadata.text_cut_off``) so the dashboard can offer both fixes.
No API key or login is required. Renders to markdown and returns an `extract_result` in
page_extractor's shape so page_extractor.persist_page_yoink can land it as
a yoink with source_type='x_thread'.

Honest scope, stated rather than papered over: the syndication endpoint
serves one post at a time and only links UPWARD (each post names its
parent). Starting from the shared URL we walk the author's own chain to
the root; posts BELOW the shared one are not reachable without
authenticated GraphQL, so a thread captured from its first post yields
that post only. The markdown says what was captured.

fetch is separated from parse/walk/render so everything below the network
is unit-testable against fixtures. Transport (HTTP route + flag gate) is
owned by server.py.
"""
from __future__ import annotations

import copy
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import x_article_extractor
import x_fulltext
from uoink_core import x_evidence

SOURCE_TYPE = "x_thread"
SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
FXTWITTER_STATUS_URL = "https://api.fxtwitter.com/2/status/{tweet_id}"
# The endpoint answers this UA reliably; same choice yt-dlp ships.
USER_AGENT = "Googlebot"
DOM_PROVIDER = "X page"  # text the extension read from the person's open X tab


def _app_version() -> str:
    try:
        from helper._version import __version__
        return str(__version__)
    except Exception:  # a stripped install still names itself
        return "3"


# FxTwitter's docs ask callers to name themselves.
FXTWITTER_USER_AGENT = f"Uoink/{_app_version()} (+https://uoink.app)"
MAX_THREAD_HOPS = 25  # ancestor cap so a hostile chain can't loop us
# Most a single answer may be. One post's JSON is a few KB; an Article body
# from FxTwitter can be a few hundred KB.
SYNDICATION_MAX_BYTES = 1024 * 1024
FXTWITTER_MAX_BYTES = 2 * 1024 * 1024


def is_post_id(value) -> bool:
    """An X post or Article id: ASCII digits only (``"²".isdigit()`` is True)."""
    text = str(value or "")
    return 0 < len(text) <= 25 and text.isascii() and text.isdigit()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """X and FxTwitter answer in place. A redirect is refused, so a request
    never lands on another host; the 3xx surfaces as an HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urlopen(request, timeout):
    """Every HTTP request this module sends goes through here."""
    return _OPENER.open(request, timeout=timeout)


def _read_body(resp, limit: int, service: str) -> str:
    raw = resp.read(limit + 1)
    if len(raw) > limit:
        raise XFetchError(f"{service} sent a bigger answer than one post needs.", "unavailable")
    return raw.decode("utf-8", errors="replace")

_STATUS_RE = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d+)",
    re.IGNORECASE,
)

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def is_x_status_url(url: str) -> bool:
    return bool(_STATUS_RE.match((url or "").strip()))


def is_x_article_url(url: str) -> bool:
    """True for an X long-form Article URL (/<handle>/article/<id> or
    /i/article/<id>). These are NOT posts: the public syndication endpoint
    doesn't serve them, so the caller routes them to a best-effort web-page
    capture with honest copy rather than the /status/ text path.

    A1 (authoritative routing): this delegates to the single canonical
    definition in x_article_extractor so classify (this module, via the
    server capture classifier) and persist (x_article_extractor) can never
    disagree on what an Article is. Do not reintroduce a local regex here."""
    return x_article_extractor.is_x_article_url(url)


def tweet_id_from_url(url: str) -> str | None:
    m = _STATUS_RE.match((url or "").strip())
    return m.group(1) if m else None


def _js_base36(val: float) -> str:
    """JS Number.prototype.toString(36) for positive finite doubles.
    Port of yt-dlp's js_number_to_string digit emitter (jsinterp.py,
    Unlicense), radix fixed at 36, because the syndication token must
    match the browser's output digit for digit."""
    if val == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    fraction, integer = math.modf(val)
    delta = max(math.nextafter(0.0, math.inf), math.ulp(val) / 2)
    digits: list[int] = []  # fractional digit values
    while fraction >= delta:
        delta *= 36
        fraction, digit = math.modf(fraction * 36)
        digits.append(int(digit))
        needs_rounding = fraction > 0.5 or (fraction == 0.5 and int(digit) & 1)
        if needs_rounding and fraction + delta > 1:
            for index in reversed(range(len(digits))):
                if digits[index] + 1 < 36:
                    digits[index] += 1
                    break
                digits.pop()
            else:
                integer += 1
            break
    int_part = ""
    integer = int(integer)
    while integer:
        integer, r = divmod(integer, 36)
        int_part = alphabet[r] + int_part
    out = int_part or "0"
    if digits:
        out += "." + "".join(alphabet[d] for d in digits)
    return out


def syndication_token(tweet_id: str) -> str:
    """((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')"""
    value = (int(tweet_id) / 1e15) * math.pi
    return _js_base36(value).replace("0", "").replace(".", "")


class XFetchError(ValueError):
    """A syndication failure with a machine-readable ``kind`` (gone,
    rate_limited, unavailable, network) for callers that pace themselves,
    such as the repair job. Still a ValueError with the same user copy."""

    def __init__(self, message: str, kind: str, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


def fetch_syndication_json(tweet_id: str, *, timeout: int = 20) -> dict:
    """GET the syndication payload for one post. Raises XFetchError with an
    actionable message on the ways X refuses: the endpoint 404s deleted,
    protected, AND blocked requests alike, so the copy says so instead of
    guessing."""
    if not is_post_id(tweet_id):
        raise XFetchError("That isn't an X post id.", "unavailable")
    query = urllib.parse.urlencode({
        "id": str(int(tweet_id)),
        "token": syndication_token(tweet_id),
        "lang": "en",
    })
    req = urllib.request.Request(f"{SYNDICATION_URL}?{query}", headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with _urlopen(req, timeout) as resp:
            raw = _read_body(resp, SYNDICATION_MAX_BYTES, "X")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise XFetchError(
                "X returned 404 for this post. That can mean deleted, "
                "protected account, or X refusing the public endpoint "
                "right now. Nothing was saved.", "gone")
        if e.code == 429:
            raise XFetchError("X is rate-limiting (429). Wait a minute and "
                              "try again.", "rate_limited",
                              x_fulltext._retry_after(e.headers))
        raise XFetchError(f"X returned HTTP {e.code}.", "unavailable")
    except urllib.error.URLError as e:
        raise XFetchError(f"Couldn't reach X: {e.reason}", "network")
    except (TimeoutError, OSError) as e:
        raise XFetchError(f"Couldn't reach X: {e}", "network")
    if not raw.strip():
        raise XFetchError("X answered with an empty body. It blocks this "
                          "endpoint sometimes; try again later.", "unavailable")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise XFetchError("X didn't return JSON (block page or outage).", "unavailable")
    if not isinstance(data, dict):
        raise XFetchError("Unexpected X response shape.", "unavailable")
    if data.get("__typename") == "TweetTombstone":
        raise XFetchError("X served a tombstone: this post is unavailable "
                          "(deleted, restricted, or withheld).", "gone")
    return data


def fetch_tweet_json(tweet_id: str, *, timeout: int = 20, fxtwitter: bool = False,
                     dom_post: dict | None = None) -> dict:
    """The syndication payload, completed where X cut it short. ``dom_post``
    is the post text the extension read from the open X tab (stays on the
    computer). ``fxtwitter`` is the user's opt-in third-party lookup."""
    data = fetch_syndication_json(tweet_id, timeout=timeout)
    return complete_payload(data, tweet_id, timeout=timeout,
                            fxtwitter=fxtwitter, dom_post=dom_post)


def _needs_full_text(evidence: dict) -> bool:
    quote = evidence.get("quote") or {}
    return (evidence.get("text_completeness") == "truncated"
            or quote.get("text_completeness") == "truncated")


def complete_payload(data: dict, tweet_id: str, *, timeout: int = 20,
                     fxtwitter: bool = False, dom_post: dict | None = None) -> dict:
    """Add full text to one syndication payload. Never loses evidence: a
    failed or refused lookup is recorded in ``provider_status`` and the
    syndication copy stays. Shared by fetched posts and embedded parents."""
    if not isinstance(data.get("_uoink_x_evidence"), dict):
        data = dict(data, _uoink_x_evidence=x_evidence.shape(data))
    if dom_post and data["_uoink_x_evidence"].get("text_completeness") == "truncated":
        data = merge_dom_post(data, dom_post)
    if fxtwitter and _needs_full_text(data["_uoink_x_evidence"]):
        try:
            status = fetch_fxtwitter_status(tweet_id, timeout=timeout)
        except XFetchError as exc:
            data = _merge_full_text(data, None, "FxTwitter", failure=_fxtwitter_failure(exc))
        else:
            data = _merge_full_text(data, status, "FxTwitter")
    return data


def merge_dom_post(data: dict, dom_post: dict) -> dict:
    """Take the text the extension read from the open X tab when it is a
    longer copy of what syndication gave (x_fulltext.extends). The page is
    the person's own logged-in view, so a match counts as the whole post
    unless the page still showed a "Show more" control."""
    evidence = data.get("_uoink_x_evidence") or x_evidence.shape(data)
    text = dom_post.get("text") if isinstance(dom_post, dict) else None
    same_post = (isinstance(dom_post, dict) and is_post_id(dom_post.get("id"))
                 and str(dom_post.get("id")) == str(evidence.get("id") or ""))
    if not isinstance(text, str) or not same_post or not x_fulltext.extends(evidence["text"], text[:100000]):
        evidence = x_evidence.sanitize_urls(evidence)
        evidence["provider_status"][DOM_PROVIDER] = "not used (text didn't match the post)"
        return dict(data, _uoink_x_evidence=evidence)
    page = x_evidence.shape({"id_str": evidence["id"], "text": text[:100000],
                             "user": {"name": evidence["author"].get("name"),
                                      "screen_name": evidence["author"].get("handle")}}, DOM_PROVIDER)
    merged = x_evidence.merge(evidence, page)
    if merged["capture_provider"] == DOM_PROVIDER:
        shown_more = bool(dom_post.get("show_more"))
        merged["text_completeness"] = "unknown" if shown_more else "complete"
        merged["text_completeness_reason"] = (
            "page still showed Show more" if shown_more else "full post text read from the open X tab")
    enriched = dict(data, text=merged["text"], _uoink_x_evidence=merged)
    if merged["capture_provider"] == DOM_PROVIDER:
        enriched["_uoink_full_text_source"] = "x-page"
    return enriched


def post_text_record(tweet_id: str, *, timeout: int = 15, fxtwitter: bool = False,
                     dom_post: dict | None = None, _fetch_syndication=None, _complete=None) -> dict:
    """One post's text for callers that save it outside an x_thread capture
    (a video capture's Description, the cut-off repair). Raises XFetchError
    when syndication refuses (``kind`` gone means deleted or protected).

    ``long_post`` is True when X marked the post as cut off, which is the
    only reliable signal: a post that is simply 270 characters long is not
    a long post. ``complete`` is True when the text is the whole post."""
    data = (_fetch_syndication or fetch_syndication_json)(tweet_id, timeout=timeout)
    first = x_evidence.shape(data)
    long_post = first["text_completeness"] == "truncated"
    quote_long = ((first.get("quote") or {}).get("text_completeness") == "truncated")
    data = (_complete or complete_payload)(dict(data, _uoink_x_evidence=first), tweet_id,
                                           timeout=timeout, fxtwitter=fxtwitter, dom_post=dom_post)
    evidence = x_evidence.sanitize_urls(data["_uoink_x_evidence"])
    quote = evidence.get("quote") or {}
    fx_status = (evidence.get("provider_status") or {}).get("FxTwitter")
    return {
        "id": str(tweet_id),
        "long_post": long_post,
        "complete": evidence["text_completeness"] == "complete" or (
            not long_post and evidence["text_completeness"] != "truncated"),
        "quote_long": quote_long,
        "quote_complete": not quote or quote.get("text_completeness") != "truncated",
        "quote_text": x_evidence.expanded_text(quote) if quote.get("text") else "",
        "text": evidence["text"],
        "provider": evidence["capture_provider"],
        "text_completeness": evidence["text_completeness"],
        "description": description_text(evidence),
        "evidence": evidence,
        # Why FxTwitter didn't help, for callers that pace themselves.
        "fxtwitter_status": fx_status,
        "fxtwitter_retry_after": fxtwitter_cooldown_left() if fx_status == "rate limited" else None,
    }


def description_text(evidence: dict) -> str:
    """The saved Description for an X video: the post's text with links
    expanded from the response (no extra request), then the quoted post."""
    body = x_evidence.expanded_text(evidence).strip()
    quote = evidence.get("quote") or {}
    quoted = x_evidence.expanded_text(quote).strip() if quote.get("text") else ""
    if quoted:
        handle = ((quote.get("author") or {}).get("handle") or "").strip()
        who = f"@{handle}" if handle else "another post"
        where = f" ({quote['url']})" if x_evidence.safe_url(quote.get("url")) else ""
        body = (body + "\n\n" if body else "") + f"Quoting {who}{where}:\n{quoted}"
    return body


# ---- FxTwitter (opt-in) ---------------------------------------------------
# A free community service (api.fxtwitter.com, FxEmbed, MIT). It sees the ID
# of the post being saved. Asked only when the person turned it on and X's
# copy is cut off. One request per post, a short cache, and a cool-down
# after it says slow down or fails, so Uoink never floods it.
FXTWITTER_CACHE_SEC = 30 * 60
FXTWITTER_CACHE_MAX = 256
FXTWITTER_COOLDOWN_SEC = (60, 120, 300, 900)
FXTWITTER_SWITCHED_OFF = "FxTwitter is switched off in Settings, Capture."
_fx_lock = threading.Lock()
_fx_state = {"cache": {}, "cooldown_until": 0.0, "strikes": 0}
_fx_clock = time.monotonic  # tests move it forward instead of waiting
# The user's switch, read fresh before every FxTwitter request. The helper
# registers a reader of fxtwitter_enrichment_enabled at import. Unset (or a
# reader that fails) means off, so nothing reaches FxTwitter by accident.
_fxtwitter_gate = None


def set_fxtwitter_gate(gate) -> None:
    global _fxtwitter_gate
    _fxtwitter_gate = gate


def fxtwitter_allowed() -> bool:
    gate = _fxtwitter_gate
    if gate is None:
        return False
    try:
        return gate() is True
    except Exception:  # a settings read that fails is "off"
        return False


def fxtwitter_cooldown_left() -> float:
    """Seconds until FxTwitter may be asked again (0 when it may now)."""
    with _fx_lock:
        return max(0.0, _fx_state["cooldown_until"] - _fx_clock())


def reset_fxtwitter_state() -> None:
    """Forget cached answers and any cool-down (tests, settings changes)."""
    with _fx_lock:
        _fx_state.update(cache={}, cooldown_until=0.0, strikes=0)


def _fx_backoff(retry_after: float | None = None) -> float:
    with _fx_lock:
        _fx_state["strikes"] += 1
        step = FXTWITTER_COOLDOWN_SEC[min(_fx_state["strikes"], len(FXTWITTER_COOLDOWN_SEC)) - 1]
        wait = min(max(float(retry_after or 0), step), FXTWITTER_COOLDOWN_SEC[-1])
        _fx_state["cooldown_until"] = _fx_clock() + wait
        return wait


def fetch_fxtwitter_status(tweet_id: str, *, timeout: int = 20) -> dict:
    """The FxTwitter v2 ``status`` object for one post. The one place Uoink
    contacts FxTwitter: it reads the user's switch first, every time, so a
    caller that passed ``fxtwitter=True`` a while ago still stops the moment
    the switch goes off. Raises XFetchError: disabled (switch off),
    rate_limited (also while cooling down), gone, unavailable, network."""
    if not fxtwitter_allowed():
        raise XFetchError(FXTWITTER_SWITCHED_OFF, "disabled")
    if not is_post_id(tweet_id):
        raise XFetchError("That isn't an X post id.", "unavailable")
    tweet_id = str(int(tweet_id))
    now = _fx_clock()
    with _fx_lock:
        cached = _fx_state["cache"].get(tweet_id)
        if cached and now - cached[0] < FXTWITTER_CACHE_SEC:
            return copy.deepcopy(cached[1])
        if now < _fx_state["cooldown_until"]:
            raise XFetchError("FxTwitter asked Uoink to slow down. Try again in a few minutes.",
                              "rate_limited", _fx_state["cooldown_until"] - now)
    req = urllib.request.Request(FXTWITTER_STATUS_URL.format(tweet_id=tweet_id), headers={
        "User-Agent": FXTWITTER_USER_AGENT, "Accept": "application/json"})
    try:
        with _urlopen(req, timeout) as resp:
            raw = _read_body(resp, FXTWITTER_MAX_BYTES, "FxTwitter")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise XFetchError("FxTwitter couldn't find this post.", "gone")
        if e.code == 429:
            wait = _fx_backoff(x_fulltext._retry_after(e.headers))
            raise XFetchError("FxTwitter asked Uoink to slow down.", "rate_limited", wait)
        if e.code >= 500:
            _fx_backoff()
        raise XFetchError(f"FxTwitter returned HTTP {e.code}.", "unavailable")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _fx_backoff()
        raise XFetchError(f"Couldn't reach FxTwitter: {getattr(e, 'reason', e)}", "network")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise XFetchError("FxTwitter didn't return JSON.", "unavailable")
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(status, dict):
        code = payload.get("code") if isinstance(payload, dict) else None
        raise XFetchError("FxTwitter has no readable copy of this post.",
                          "gone" if code in (401, 404) else "unavailable")
    if status.get("type") == "tombstone":
        raise XFetchError("FxTwitter says this post is unavailable.", "gone")
    with _fx_lock:
        _fx_state["strikes"] = 0
        cache = _fx_state["cache"]
        cache[tweet_id] = (_fx_clock(), copy.deepcopy(status))
        while len(cache) > FXTWITTER_CACHE_MAX:
            cache.pop(next(iter(cache)))
    return status


def fetch_fxtwitter_status_json(tweet_id: str, *, timeout: int = 20) -> dict | None:
    """Best-effort wrapper: the v2 envelope {code, status} or None."""
    try:
        return {"code": 200, "status": fetch_fxtwitter_status(tweet_id, timeout=timeout)}
    except (XFetchError, ValueError):
        return None


def _fxtwitter_failure(exc: XFetchError) -> str:
    return {"gone": "post unavailable", "rate_limited": "rate limited",
            "network": "request failed", "disabled": "switched off"}.get(
                exc.kind, "unavailable or invalid response")


def _merge_fxtwitter_full_text(syndication: dict,
                               fxtwitter: dict | None) -> dict:
    """Retain all available evidence, including on a failed supplement."""
    status = fxtwitter.get("status") if isinstance(fxtwitter, dict) else None
    valid = (isinstance(status, dict) and fxtwitter.get("code") == 200
             and status.get("type") != "tombstone")
    return _merge_full_text(syndication, status if valid else None, "FxTwitter")


_FULL_TEXT_SOURCE = {"FxTwitter": "fxtwitter-v2"}


def _merge_full_text(syndication: dict, status: dict | None, provider: str, *,
                     failure: str = "unavailable or invalid response") -> dict:
    """Merge one provider's record of the same post into the syndication
    evidence. The longer text wins (x_evidence.merge); a missing, invalid or
    mismatched record only adds a provider_status note."""
    evidence = syndication.get("_uoink_x_evidence") or x_evidence.shape(syndication)
    expected_id = str(syndication.get("id_str") or syndication.get("id") or "")
    status_id = str((status or {}).get("id_str") or (status or {}).get("id") or "")
    if isinstance(status, dict) and is_post_id(expected_id) and status_id == expected_id:
        evidence = x_evidence.merge(evidence, x_evidence.shape(status, provider))
    else:
        evidence = x_evidence.sanitize_urls(evidence)
        evidence["provider_status"][provider] = failure
    enriched = dict(syndication)
    enriched["text"] = evidence["text"]
    enriched["_uoink_x_evidence"] = evidence
    if evidence["capture_provider"] in _FULL_TEXT_SOURCE:
        enriched["_uoink_full_text_source"] = _FULL_TEXT_SOURCE[evidence["capture_provider"]]
    return enriched


def _shape_tweet(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Unexpected X response shape.")
    evidence = x_evidence.sanitize_urls(payload.get("_uoink_x_evidence")) or x_evidence.shape(payload)
    return {
        "id": evidence["id"],
        "author_name": evidence["author"]["name"] or "Unknown",
        "author_handle": evidence["author"]["handle"] or "",
        "text": evidence["text"],
        "created_at": payload.get("created_at") or "",
        "in_reply_to_id": evidence["in_reply_to_id"],
        "in_reply_to_handle": evidence["in_reply_to_handle"].strip(),
        "photo_count": sum(m["type"] == "photo" for m in evidence["media"]),
        "has_video": any(m["type"] in {"video", "gif"} for m in evidence["media"]),
        "evidence": evidence,
        "full_text_source": payload.get("_uoink_full_text_source"),
        "parent_payload": payload.get("parent") if isinstance(payload.get("parent"), dict) else None,
    }


def collect_thread(tweet_id: str, *, timeout: int = 20, _fetch=None, _supplement=None,
                   fxtwitter: bool = False, dom_post: dict | None = None) -> list[dict]:
    """Fetch the shared post, then walk the author's own reply chain upward
    to the root (or MAX_THREAD_HOPS). Returns tweets in reading order,
    root first. Uses the embedded `parent` payload when the endpoint
    includes it, refetching by id otherwise. A missing ancestor stops the
    walk without failing the capture: you still get everything below it.
    ``dom_post`` (the open tab's text) only ever applies to the shared post."""
    if _fetch is None:
        def fetcher(post_id, **kwargs):
            page = dom_post if str(post_id) == str(tweet_id) else None
            return fetch_tweet_json(post_id, fxtwitter=fxtwitter, dom_post=page, **kwargs)

        def complete_parent(payload, post_id):
            return complete_payload(payload, post_id, timeout=timeout, fxtwitter=fxtwitter)
    else:
        # An injected fetcher never unexpectedly opens a live supplement request.
        fetcher, complete_parent = _fetch, None
    if _supplement is not None:
        # Test injection: an FxTwitter-shaped record for an embedded parent.
        def complete_parent(payload, post_id):
            try:
                extra = _supplement(post_id, timeout=timeout)
            except (ValueError, OSError):
                extra = None
            return _merge_fxtwitter_full_text(payload, extra)
    first = fetcher(tweet_id, timeout=timeout)
    if _fetch is not None and dom_post and isinstance(first, dict):
        evidence = first.get("_uoink_x_evidence") or x_evidence.shape(first)
        if evidence.get("text_completeness") == "truncated":
            first = merge_dom_post(dict(first, _uoink_x_evidence=evidence), dom_post)
    start = _shape_tweet(first)
    chain = [start]
    hops = 0
    current = start
    seen = {start["id"]}
    while current["in_reply_to_id"]:
        parent_id = current["in_reply_to_id"]
        def missing(reason):
            current["evidence"]["missing_parent"] = {"id": parent_id, "reason": reason}
        if not current["in_reply_to_handle"]:
            missing("author unknown")
            break
        if current["in_reply_to_handle"].lower() != start["author_handle"].lower():
            missing("outside same-author scope")
            break
        if hops >= MAX_THREAD_HOPS or parent_id in seen:
            missing("ancestor limit reached" if hops >= MAX_THREAD_HOPS else "cycle detected")
            break
        hops += 1
        parent_payload = current["parent_payload"]
        try:
            if parent_payload and str(parent_payload.get("id_str") or "") == current["in_reply_to_id"]:
                if complete_parent and not parent_payload.get("_uoink_x_evidence"):
                    parent_payload = complete_parent(parent_payload, parent_id)
                parent = _shape_tweet(parent_payload)
            else:
                parent = _shape_tweet(fetcher(current["in_reply_to_id"],
                                              timeout=timeout))
        except (ValueError, OSError):
            missing("unavailable or request failed")
            break  # ancestor gone; keep what we have
        if parent["id"] != parent_id or not x_evidence.has_content(parent["evidence"]):
            missing("unavailable or invalid response")
            break
        if parent["author_handle"].lower() != start["author_handle"].lower():
            missing("outside same-author scope")
            break
        chain.append(parent)
        seen.add(parent["id"])
        current = parent
    chain.reverse()
    return chain


def _snippet(text: str, limit: int = 60) -> str:
    flat = re.sub(r"\s+", " ", (text or "")).strip()
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def render_markdown(tweets: list[dict], source_url: str) -> str:
    root = tweets[0]
    handle = f"@{root['author_handle']}" if root["author_handle"] else "unknown account"
    title = f"{root['author_name']} ({handle}) on X"
    lines = [f"# {title}", ""]
    count = len(tweets)
    lines.append(f"**Source:** {source_url}")
    lines.append("")
    scope = (f"{count} post{'s' if count != 1 else ''} captured: the shared "
             "post and the earlier posts in the author's own chain. Replies "
             "below the shared post aren't served by X's public endpoint.")
    lines += [f"*{scope}*", ""]
    for index, tweet in enumerate(tweets, start=1):
        lines.append(f"## {index}/{count}")
        lines.extend(x_evidence.render_post(tweet["evidence"]))
        extras = []
        if tweet["photo_count"]:
            extras.append(f"{tweet['photo_count']} photo{'s' if tweet['photo_count'] != 1 else ''}")
        if tweet["has_video"]:
            extras.append("video (capture it with the regular Uoink button)")
        meta = " · ".join(filter(None, [tweet["created_at"], ", ".join(extras)]))
        if meta:
            lines.append("")
            lines.append(f"*{meta}*")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


_ARTICLE_LINK_RE = re.compile(r"^https?://(?:www\.)?(?:x|twitter)\.com/(?:i|[A-Za-z0-9_]{1,15})/article/(\d+)",
                              re.IGNORECASE)


def linked_article(post: dict) -> dict | None:
    """The X Article a post consists of, when its only content is a link to
    one: {id, url, title, preview}. None for posts with their own words."""
    attachment = (post.get("attachments") or {}).get("article")
    attachment = attachment if isinstance(attachment, dict) else {}
    article_id = str(attachment.get("rest_id") or "")
    for link in post.get("expanded_links") or []:
        match = _ARTICLE_LINK_RE.match(str(link.get("expanded_url") or ""))
        if match and not article_id:
            article_id = match.group(1)
    if not is_post_id(article_id):
        return None
    words = re.sub(r"https?://\S+", " ", post.get("text") or "").strip()
    if words:
        return None
    return {"id": article_id, "url": f"https://x.com/i/article/{article_id}",
            "title": str(attachment.get("title") or "").strip(),
            "preview": str(attachment.get("preview_text") or "").strip()}


def _article_from_fxtwitter(post: dict, article: dict, fetch) -> dict | None:
    """FxTwitter (opt-in) returns the Article's Draft.js body; shape it as
    an x_article extract_result. None when it has no body to offer."""
    try:
        payload = fetch(post["id"])
    except (ValueError, OSError):
        payload = None
    status = payload.get("status") if isinstance(payload, dict) else None
    return article_from_status(post, article, status)


def article_from_status(post: dict, article: dict, status) -> dict | None:
    """An x_article extract_result from FxTwitter's record of the post that
    links to the Article. None when it has no body for it."""
    if (not isinstance(status, dict) or not is_post_id(post.get("id"))
            or str(status.get("id") or "") != post["id"]):
        return None
    body = status.get("article") if isinstance(status.get("article"), dict) else None
    if not body:
        return None
    markdown, images = x_fulltext.article_markdown(body)
    author = status.get("author") if isinstance(status.get("author"), dict) else {}
    return x_article_extractor.build_full_text_result({
        "url": article["url"], "title": str(body.get("title") or article["title"]),
        "author_name": str(author.get("name") or post["author"].get("name") or ""),
        "author_handle": str(author.get("screen_name") or post["author"].get("handle") or ""),
        "markdown": markdown, "images": images, "post_url": post.get("url"),
        "published": body.get("created_at"),
    }, provider="FxTwitter")


def cut_off_help(tweets: list[dict], article: dict | None, canonical: str) -> dict | None:
    """What the dashboard needs to offer the two fixes for a save that
    holds X's cut-off copy: {reason, open_url, title?}. None when whole."""
    if article:
        return {"reason": "article", "open_url": article["url"], "title": article.get("title") or ""}
    for tweet in tweets:
        evidence = tweet["evidence"]
        quote = evidence.get("quote") or {}
        if evidence.get("text_completeness") == "truncated" or quote.get("text_completeness") == "truncated":
            return {"reason": "long_post", "open_url": canonical}
    return None


def article_capture(tweet_id: str, *, timeout: int = 15) -> dict | None:
    """For the cut-off repair: the x_article result for a saved post that
    only links to an X Article, or None when FxTwitter has no body for it.
    Unlike extract_x_thread this raises XFetchError with its ``kind``
    (gone, also for a tombstone; rate_limited; disabled; unavailable;
    network), so the job can pace itself and keep a gone post as it is."""
    data = fetch_syndication_json(tweet_id, timeout=timeout)
    evidence = x_evidence.sanitize_urls(x_evidence.shape(data))
    article = linked_article(evidence)
    if not article:
        raise XFetchError("The post no longer links only to an X Article.", "not_article")
    status = fetch_fxtwitter_status(tweet_id, timeout=timeout)
    return article_from_status(evidence, article, status)


def extract_x_thread(url: str, *, timeout: int = 20, _fetch=None, _supplement=None,
                     fxtwitter: bool = False, dom_post: dict | None = None, _fx_article=None) -> dict:
    """Fetch + walk + render an X post chain into an extract_result dict
    shaped for page_extractor.persist_page_yoink. `_fetch` is the test
    injection point. Returns {ok: False, code, error} on any failure.

    ``dom_post`` is the post text the extension read from the open X tab.
    A post whose only content is a link to an X Article is the Article:
    with ``fxtwitter`` on, its body comes back as an x_article result
    (``source_type`` key set). Otherwise the post is saved with what X gave
    and ``metadata.text_cut_off`` names the fix (cut_off_help)."""
    tweet_id = tweet_id_from_url(url)
    if not tweet_id:
        return {"ok": False, "code": "bad_url",
                "error": "Not an X post URL (expected x.com/<user>/status/<id>)."}
    try:
        tweets = collect_thread(tweet_id, timeout=timeout, _fetch=_fetch, _supplement=_supplement,
                                fxtwitter=fxtwitter, dom_post=dom_post)
    except ValueError as e:
        return {"ok": False, "code": "fetch_failed", "error": str(e)}
    except Exception as e:  # defensive: malformed payloads
        return {"ok": False, "code": "parse_failed",
                "error": f"Couldn't parse the X response: {e}"}
    if not tweets:
        return {"ok": False, "code": "parse_failed",
                "error": "X answered but no post came back."}
    article = linked_article(tweets[-1]["evidence"])
    if article and (fxtwitter or _fx_article):
        fetch = _fx_article or (lambda post_id: fetch_fxtwitter_status_json(post_id, timeout=timeout))
        found = _article_from_fxtwitter(tweets[-1]["evidence"], article, fetch)
        if found:
            return found
    if len(tweets) == 1 and not x_evidence.has_content(tweets[0]["evidence"]):
        return {"ok": False, "code": "empty",
                "error": "That post has no text to capture. For a video "
                         "post, use the regular Uoink button."}

    root = tweets[0]
    full_text_sources = sorted({tweet["full_text_source"] for tweet in tweets
                                if tweet.get("full_text_source")})
    full_text_posts = sum(1 for tweet in tweets if tweet.get("full_text_source"))
    canonical = (f"https://x.com/{root['author_handle']}/status/{tweet_id}"
                 if root["author_handle"] else f"https://x.com/i/status/{tweet_id}")
    markdown = render_markdown(tweets, canonical)
    handle = f"@{root['author_handle']}" if root["author_handle"] else "X post"
    help_ = cut_off_help(tweets, article, f"https://x.com/{tweets[-1]['author_handle'] or 'i'}/status/{tweet_id}")
    return {
        "ok": True,
        "url": canonical,
        "title": (f"{handle}: {article['title']}" if article and article.get("title")
                  else f"{handle}: {_snippet(root['text']) or 'X post'}"),
        "markdown": markdown,
        "metadata": {
            "author_name": root["author_name"],
            "author_handle": root["author_handle"],
            "tweets_captured": len(tweets),
            "capture_scope": "shared post + earlier same-author chain",
            "photo_count": sum(t["photo_count"] for t in tweets),
            "has_video": any(t["has_video"] for t in tweets),
            "full_text_posts": full_text_posts,
            "text_cut_off": help_,
            "x_capture": x_evidence.capture([t["evidence"] for t in tweets]),
        },
        "extraction_engine": "+".join(["x-syndication", *full_text_sources]),
        "extracted_at": _now_iso(),
        "links": [dict(link, href=x_evidence.safe_url(link.get("expanded_url")) or x_evidence.safe_url(link.get("url")))
                  for t in tweets for link in t["evidence"]["expanded_links"]
                  if x_evidence.safe_url(link.get("expanded_url")) or x_evidence.safe_url(link.get("url"))],
        # This route persists descriptors; it has never downloaded post photos.
        "images": [{"src": m["url"], "alt": m["alt_text"]}
                   for t in tweets for m in t["evidence"]["media"]
                   if m["type"] == "photo" and x_evidence.safe_url(m["url"])],
        "screenshot_path": None,
        "tweets_captured": len(tweets),
        "text_cut_off": help_,
    }
