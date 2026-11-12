"""Podcast suggestions: episodes worth saving, picked from what is already saved.

Off by default. When the user turns "Suggest podcasts" on, Uoink takes the few
words that recur most across the titles of saved items and sends only those
words to Apple's podcast search (itunes.apple.com). No titles, transcripts,
URLs or channel names from the library are ever sent. The answer is scored
locally against the taste profile (taste_scoring), cached in a small JSON
file, and shown from that cache when offline.

This module owns no HTTP server code. Fetching is injected (``fetch`` and
``lookup``) so tests run with no network. The default fetchers reuse
research.http_get_json, which carries the size cap, timeout and error mapping
the Research feature already trusts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from urllib.parse import urlencode, urlparse

import taste_scoring

log = logging.getLogger("uoink.suggestions")

CACHE_NAME = "podcast_suggestions.json"
REFRESH_INTERVAL_SEC = 24 * 3600      # at most one refresh a day
FAILURE_BACKOFF_SEC = 3600            # after a failed try, wait an hour
MIN_MANUAL_INTERVAL_SEC = 600         # "Refresh" is allowed every 10 minutes
MAX_TERMS = 4                         # iTunes calls per refresh
PER_TERM_LIMIT = 20
MAX_ITEMS = 12
MAX_PER_SHOW = 2
MIN_TERM_COUNT = 2                    # a word must recur in 2+ saved titles
MIN_LIBRARY_ITEMS = 5                 # below this there is nothing to learn from
INTER_CALL_DELAY_SEC = 3              # same politeness as Research
MAX_DISMISSED = 500

DISCLOSURE = ("When this is on, Uoink sends a few topic words from what you save "
              "(never titles, links or transcripts) to Apple's podcast search "
              "(itunes.apple.com) about once a day. Artwork loads from Apple too.")

_EXTRA_STOPWORDS = {
    "about", "with", "have", "will", "just", "more", "most", "like", "they", "them",
    "their", "there", "then", "than", "these", "those", "been", "were", "which",
    "who", "can", "get", "use", "using", "make", "need", "know", "really", "every",
    "everything", "things", "thing", "people", "life", "time", "show", "podcast",
    "interview", "talk", "live", "make", "made", "going", "way", "one", "two",
    "week", "day", "today", "now", "all", "any", "not", "its", "our", "has",
}

_lock = threading.Lock()
_refresh_lock = threading.Lock()


class SuggestionError(Exception):
    """A user-presentable failure (never carries raw network text)."""

    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


# ---- cache -----------------------------------------------------------------

def _cache_path(data_root) -> str:
    return os.path.join(str(data_root), CACHE_NAME)


def _empty_cache() -> dict:
    return {"version": 1, "refreshed_ts": 0.0, "attempt_ts": 0.0, "terms": [],
            "items": [], "dismissed": [], "saved": [], "last_error": None}


def load_cache(data_root) -> dict:
    cache = _empty_cache()
    try:
        with open(_cache_path(data_root), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return cache
    if not isinstance(raw, dict):
        return cache
    for key in ("refreshed_ts", "attempt_ts"):
        try:
            cache[key] = float(raw.get(key) or 0.0)
        except (TypeError, ValueError):
            pass
    for key in ("terms", "items", "dismissed", "saved"):
        if isinstance(raw.get(key), list):
            cache[key] = raw[key]
    # Artwork is re-checked on read too, so a cache written before the host
    # check existed never reaches the dashboard with another host.
    cache["items"] = [{**i, "artwork": artwork_url(i.get("artwork"))}
                      for i in cache["items"] if isinstance(i, dict) and i.get("id")]
    cache["dismissed"] = [str(d) for d in cache["dismissed"]][-MAX_DISMISSED:]
    cache["saved"] = [str(d) for d in cache["saved"]][-MAX_DISMISSED:]
    if isinstance(raw.get("last_error"), str):
        cache["last_error"] = raw["last_error"][:80]
    return cache


def save_cache(data_root, cache: dict) -> None:
    path = _cache_path(data_root)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, path)
    except OSError as exc:  # a failed write must never break the dashboard
        log.warning("suggestions: cache write failed: %s", exc)


# ---- library side (local only) ----------------------------------------------

def _norm_title(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _norm_url(url) -> str:
    try:
        p = urlparse(str(url or "").strip())
    except ValueError:
        return ""
    if not p.netloc:
        return ""
    return (p.netloc.lower() + p.path).rstrip("/")


def top_terms(idx, profile: dict | None = None, *, limit: int = MAX_TERMS) -> list[tuple[str, int]]:
    """The words that recur most across saved titles, as (word, how many saves).

    Only words that appear in at least MIN_TERM_COUNT different saved items
    count, so one long title never becomes a topic. Words the user listed in
    their avoid note are skipped. Load the current taste profile when none is
    supplied, so the disclosure preview and refresh use the same filtering."""
    if profile is None:
        profile = taste_scoring.build_taste_profile(idx)
    try:
        rows = idx.search_yoinks_for_memory(limit=200).get("results") or []
    except Exception as exc:
        log.warning("suggestions: could not read the library: %s", exc)
        return []
    avoid = {t for t in (profile or {}).get("avoid_terms", []) if t}
    counts: dict[str, int] = {}
    phrase_counts: dict[str, int] = {}

    def keep(tok):
        return (len(tok) >= 3 and not tok.isdigit()
                and tok not in taste_scoring._STOPWORDS and tok not in _EXTRA_STOPWORDS
                and not any(a in tok or tok in a for a in avoid))

    def vote(text):
        for tok in set(taste_scoring._tokenize(text)):
            if tok in _EXTRA_STOPWORDS or any(a in tok or tok in a for a in avoid):
                continue
            counts[tok] = counts.get(tok, 0) + 1
        # Two-word phrases ("claude code", "product market") search far more
        # precisely than single words, so recurring ones go first.
        words = re.findall(r"[a-z0-9]+", str(text or "").lower())
        pairs = {f"{a} {b}" for a, b in zip(words, words[1:]) if keep(a) and keep(b)}
        for phrase in pairs:
            phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

    for row in rows:
        vote(row.get('title'))
    # Shows already followed count too: one vote per show, from the show title.
    try:
        import podcasts
        for feed in podcasts.list_feeds(idx):
            vote(feed.get("title"))
    except Exception as exc:
        log.info("suggestions: followed shows unavailable: %s", exc)
    phrases = sorted(((t, n) for t, n in phrase_counts.items() if n >= MIN_TERM_COUNT),
                     key=lambda kv: (-kv[1], kv[0]))[:limit]
    in_phrase = {w for p, _ in phrases for w in p.split()}
    words = sorted(((t, n) for t, n in counts.items()
                    if n >= MIN_TERM_COUNT and t not in in_phrase),
                   key=lambda kv: (-kv[1], kv[0]))
    return (phrases + words)[:limit]


def mentions_term(term: str, *texts) -> bool:
    """True when every word of the search term appears in the episode's own
    title or description. Apple's search also matches show names and authors,
    which brings in unrelated shows."""
    haystack = set(re.findall(r"[a-z0-9]+", " ".join(str(t or "") for t in texts).lower()))
    return all(word in haystack for word in term.split())


def library_size(idx) -> int:
    try:
        with idx._lock:
            return int(idx._conn.execute(
                "SELECT COUNT(*) FROM yoinks WHERE deleted_at IS NULL").fetchone()[0])
    except Exception:
        return 0


def readiness(idx) -> dict:
    """Local only, no network. Says whether there is enough saved to suggest
    from, and exactly which words a refresh would send."""
    size = library_size(idx)
    terms = top_terms(idx) if size >= MIN_LIBRARY_ITEMS else []
    return {"library_size": size, "enough": bool(terms),
            "terms": [w for w, _ in terms]}


def library_fingerprints(idx) -> tuple[set, set]:
    """(normalized titles, normalized audio URLs) of everything already saved or
    on its way in. Used only to drop duplicates; never sent anywhere."""
    titles: set[str] = set()
    urls: set[str] = set()
    try:
        with idx._lock:
            for (title,) in idx._conn.execute(
                    "SELECT title FROM yoinks WHERE deleted_at IS NULL"):
                key = _norm_title(title)
                if key:
                    titles.add(key)
            for (audio,) in idx._conn.execute(
                    "SELECT audio_url FROM podcast_episodes WHERE yoink_video_id IS NOT NULL "
                    "OR status IN ('queued','downloaded','transcribed')"):
                key = _norm_url(audio)
                if key:
                    urls.add(key)
    except Exception as exc:
        log.warning("suggestions: library fingerprint failed: %s", exc)
    return titles, urls


# ---- Apple's search ----------------------------------------------------------

def _research():
    import research  # lazy: keeps this module cheap to import
    return research


def default_fetch(term: str, limit: int):
    return _research().http_get_json("https://itunes.apple.com/search?" + urlencode(
        {"media": "podcast", "entity": "podcastEpisode", "limit": limit, "term": term}))


def default_lookup(collection_id):
    return _research().http_get_json("https://itunes.apple.com/lookup?" + urlencode(
        {"id": collection_id, "entity": "podcast"}))


def _http_url(value) -> str:
    text = str(value or "").strip()
    try:
        p = urlparse(text)
    except ValueError:
        return ""
    return text[:600] if p.scheme in ("http", "https") and p.netloc else ""


ARTWORK_HOST_SUFFIX = ".mzstatic.com"   # Apple's image CDN (is1-ssl.mzstatic.com ...)


def artwork_url(value) -> str:
    """The artwork URL when it is https on Apple's image CDN, else "".

    The dashboard loads it as an <img>, so a stray host in Apple's JSON would
    become a request to someone else. The host is compared exactly after
    parsing; any other artwork is dropped and the card shows its letter tile."""
    url = _http_url(value)
    if not url:
        return ""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError:
        return ""
    if (p.scheme != "https" or p.username is not None or p.password is not None
            or port not in (None, 443)):
        return ""
    return url if host.endswith(ARTWORK_HOST_SUFFIX) else ""


def _clip(value, n) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:n]


def parse_episodes(payload) -> list[dict]:
    rows = payload.get("results") if isinstance(payload, dict) else None
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        title = _clip(row.get("trackName"), 300)
        audio = _http_url(row.get("episodeUrl"))
        page = _http_url(row.get("trackViewUrl"))
        if not title or not (audio or page):
            continue
        ident = str(row.get("trackId") or audio or page)
        art = next((a for a in (artwork_url(row.get(k)) for k in
                                ("artworkUrl160", "artworkUrl600", "artworkUrl60")) if a), "")
        millis = row.get("trackTimeMillis")
        out.append({
            "id": "sg_" + hashlib.sha1(ident.encode("utf-8")).hexdigest()[:12],
            "title": title,
            "show": _clip(row.get("collectionName"), 200),
            "show_id": str(row.get("collectionId") or "")[:20],
            "episode_url": audio,
            "page_url": page,
            "feed_url": _http_url(row.get("feedUrl")),
            "artwork": art,
            "duration_s": int(millis / 1000) if isinstance(millis, (int, float)) and millis > 0 else None,
            "released": _clip(row.get("releaseDate"), 40),
            "description": _clip(row.get("description"), 400),
        })
    return out


# ---- refresh ------------------------------------------------------------------

def _reason(term: str, count: int, scored: dict, show: str) -> str:
    if scored.get("matched", {}).get("channel") and any(
            "saved this channel" in r for r in scored.get("reasons", [])):
        return f"Because you have saved from {show} before"
    word = "thing" if count == 1 else "things"
    return f"Because you saved {count} {word} about {term}"


def refresh(idx, data_root, *, enabled: bool, fetch=None, now=None, sleep=None,
            force: bool = False) -> dict:
    """Refresh the cached list from Apple when it is due. Never raises.

    Returns {status, items?}. status is one of: off, fresh, not_enough, busy,
    refreshed, failed. A failure leaves the last good list in place."""
    if not enabled:
        return {"status": "off"}
    clock = now or time.time
    nap = sleep or time.sleep
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "busy"}
    try:
        t = float(clock())
        cache = load_cache(data_root)
        since_ok = t - cache["refreshed_ts"]
        since_try = t - cache["attempt_ts"]
        if force:
            if since_try < MIN_MANUAL_INTERVAL_SEC:
                return {"status": "fresh"}
        elif since_ok < REFRESH_INTERVAL_SEC or since_try < FAILURE_BACKOFF_SEC:
            return {"status": "fresh"}
        if library_size(idx) < MIN_LIBRARY_ITEMS:
            return {"status": "not_enough"}
        profile = taste_scoring.build_taste_profile(idx)
        terms = top_terms(idx, profile)
        if not terms:
            return {"status": "not_enough"}
        titles, urls = library_fingerprints(idx)
        dismissed = set(cache["dismissed"]) | set(cache["saved"])
        getter = fetch or default_fetch
        pool: dict[str, dict] = {}
        ok_calls, error_code = 0, None
        for n, (term, count) in enumerate(terms):
            if n:
                nap(INTER_CALL_DELAY_SEC)
            try:
                episodes = parse_episodes(getter(term, PER_TERM_LIMIT))
            except Exception as exc:
                error_code = getattr(exc, "code", None) or "fetch_failed"
                log.info("suggestions: search failed (%s)", error_code)
                if error_code == "rate_limited":
                    break
                continue
            ok_calls += 1
            for ep in episodes:
                if (ep["id"] in dismissed or ep["id"] in pool
                        or _norm_title(ep["title"]) in titles
                        or (ep["episode_url"] and _norm_url(ep["episode_url"]) in urls)
                        or not mentions_term(term, ep["title"], ep["description"])):
                    continue
                scored = taste_scoring.score_candidate(
                    profile, {"title": ep["title"], "channel": ep["show"]})
                if scored["blocked"]:
                    continue
                low_title = ep["title"].lower()
                bonus = (0.1 if term in low_title else 0.0) + (
                    0.03 if term in ep["description"].lower() else 0.0)
                ep["score"] = round(scored["score"] + bonus, 4)
                ep["term"] = term
                ep["reason"] = _reason(term, count, scored, ep["show"])
                pool[ep["id"]] = ep
        if not ok_calls:
            error = error_code or "fetch_failed"
            _commit_refresh(data_root, attempt_ts=t, last_error=error)
            return {"status": "failed", "error": error}
        ranked = sorted(pool.values(), key=lambda e: (-e["score"], e["title"]))
        per_term_cap = max(3, -(-MAX_ITEMS // len(terms)))
        picked, by_term, by_show = [], {}, {}
        for ep in ranked:
            show_key = ep["show"].lower()
            if by_term.get(ep["term"], 0) >= per_term_cap or by_show.get(show_key, 0) >= MAX_PER_SHOW:
                continue
            picked.append(ep)
            by_term[ep["term"]] = by_term.get(ep["term"], 0) + 1
            by_show[show_key] = by_show.get(show_key, 0) + 1
            if len(picked) >= MAX_ITEMS:
                break
        picked.sort(key=lambda e: (-e["score"], e["title"]))
        kept = _commit_refresh(data_root, items=picked, terms=[w for w, _ in terms],
                               attempt_ts=t, refreshed_ts=t, last_error=None)
        return {"status": "refreshed", "count": len(kept["items"])}
    finally:
        _refresh_lock.release()


def _commit_refresh(data_root, **fields) -> dict:
    """Write a refresh's results without losing what happened while it waited
    on Apple. Under the same lock as every other cache write, reload the cache
    as it is now and change only the fields a refresh owns. Dismissals and
    saves made meanwhile stay (and drop matching new items), and a feed URL
    looked up meanwhile carries over to the same item."""
    with _lock:
        latest = load_cache(data_root)
        if "items" in fields:
            gone = set(latest["dismissed"]) | set(latest["saved"])
            known = {i["id"]: i for i in latest["items"]}
            items = []
            for item in fields["items"]:
                if item["id"] in gone:
                    continue
                if not item.get("feed_url") and known.get(item["id"], {}).get("feed_url"):
                    item = {**item, "feed_url": known[item["id"]]["feed_url"]}
                items.append(item)
            fields["items"] = items
        latest.update(fields)
        save_cache(data_root, latest)
        return latest


def is_due(data_root, now=None) -> bool:
    """True when an automatic refresh would run (a day since the last good one,
    and an hour since the last failed try)."""
    t = float((now or time.time)())
    cache = load_cache(data_root)
    return (t - cache["refreshed_ts"] >= REFRESH_INTERVAL_SEC
            and t - cache["attempt_ts"] >= FAILURE_BACKOFF_SEC)


def refreshing() -> bool:
    return _refresh_lock.locked()


# ---- reads and small writes -------------------------------------------------------

def current(data_root, idx=None, *, keep=()) -> dict:
    """What the shelf shows: the cached list minus dismissed, saved and (when an
    index is given) anything that has since landed in the library.

    ``keep`` holds suggestion ids whose save is still running or failed. Those
    stay on the shelf so the card can show progress, the error and Try again:
    the save itself writes the episode row that would otherwise hide it.
    Dismissing one still hides it."""
    cache = load_cache(data_root)
    keep = set(keep or ())
    hidden = set(cache["dismissed"]) | set(cache["saved"])
    titles, urls = library_fingerprints(idx) if idx is not None else (set(), set())
    items = [i for i in cache["items"]
             if i["id"] not in hidden
             and (i["id"] in keep
                  or (_norm_title(i.get("title")) not in titles
                      and not (i.get("episode_url") and _norm_url(i["episode_url"]) in urls)))]
    return {"items": items, "terms": cache["terms"], "refreshed_ts": cache["refreshed_ts"],
            "last_error": cache["last_error"]}


def get_item(data_root, sid: str) -> dict | None:
    for item in load_cache(data_root)["items"]:
        if item.get("id") == sid:
            return item
    return None


def dismiss(data_root, sid: str) -> bool:
    with _lock:
        cache = load_cache(data_root)
        if sid not in cache["dismissed"]:
            cache["dismissed"].append(sid)
            cache["dismissed"] = cache["dismissed"][-MAX_DISMISSED:]
            save_cache(data_root, cache)
        return True


def mark_saved(data_root, sid: str) -> None:
    with _lock:
        cache = load_cache(data_root)
        if sid not in cache["saved"]:
            cache["saved"].append(sid)
            cache["saved"] = cache["saved"][-MAX_DISMISSED:]
            save_cache(data_root, cache)


def resolve_feed_url(data_root, sid: str, *, lookup=None) -> str:
    """The show's RSS feed for a suggestion, from the cached result or one
    iTunes lookup by show id (an id Apple gave us, nothing from the library)."""
    import podcasts
    item = get_item(data_root, sid)
    if item is None:
        raise SuggestionError("That suggestion is gone. Refresh the list.", "not_found")
    feed = item.get("feed_url") or ""
    if not feed:
        if not item.get("show_id"):
            raise SuggestionError("This show has no feed Uoink can follow.", "no_feed")
        try:
            payload = (lookup or default_lookup)(item["show_id"])
        except Exception:
            raise SuggestionError("Couldn't reach Apple to find the feed. Try again later.",
                                  "fetch_failed") from None
        rows = payload.get("results") if isinstance(payload, dict) else None
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("feedUrl"):
                feed = _http_url(row["feedUrl"])
                break
        if feed:
            with _lock:
                cache = load_cache(data_root)
                for cached in cache["items"]:
                    if cached.get("id") == sid:
                        cached["feed_url"] = feed
                save_cache(data_root, cache)
    valid = podcasts._validate_feed_url(feed) if feed else None
    if not valid:
        raise SuggestionError("This show has no feed Uoink can follow.", "no_feed")
    return valid
