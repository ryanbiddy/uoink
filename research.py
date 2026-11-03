"""Local research runs and consent-gated discovery; no server or model imports.

Parsers and ranking consume data only. Fetchers take (query, limit), except
HackerTube's zero-argument listing; library and YouTube are backend callbacks.
Collection never reads or writes the run store. The caller serializes each
run's merge and save with its run lock; RUN_LOCK protects only store operations.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from typing import Any
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

import list_imports


SOURCE_KINDS = ("library", "youtube", "podcast", "hn", "hackertube", "reddit")
NETWORK_KINDS = SOURCE_KINDS[1:]
DEFAULT_SOURCE_KINDS = SOURCE_KINDS[:-1]
RUN_ID_PATTERN = r"^rr_[0-9]{14}_[0-9a-f]{8}$"
RUN_LOCK = threading.RLock()
_RUN_LOCKS: dict[str, threading.Lock] = {}
MAX_CANDIDATES_POOL = 500
USER_AGENT = list_imports.USER_AGENT
FETCH_TIMEOUT_SEC = 20
FETCH_MAX_BYTES = 8 * 1024 * 1024
PODCAST_HOSTS = ("podcasts.apple.com", "anchor.fm", "podcasters.spotify.com")
PODCAST_HOST_SUFFIXES = ("libsyn.com", "simplecast.com", "transistor.fm",
                         "buzzsprout.com", "megaphone.fm")
_YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_TOKENS = re.compile(r"\w+", re.UNICODE)
_STOP_WORDS = frozenset("""
    a about above after again against all an and any are as at be because been
    before being below between both but by can could did do does down during each
    few for from further had has have here how if in into is it its itself may
    might more most myself not of on once only or other our ourselves out over own
    same should so some such than that the their them themselves then there these
    they this those through to too under until up us very was we were what when
    where which while who whom why will with would you your yourself yourselves
""".split())


class ResearchError(ValueError):
    """A safe user-facing message with a stable error code."""

    def __init__(self, message: str, code: str = "invalid_arguments"):
        super().__init__(message)
        self.code = code


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ResearchError(f"{name} must be an integer from {low} to {high}.")
    return value


def normalize_scope(scope: dict) -> dict:
    if not isinstance(scope, dict) or set(scope) - {
            "question", "max_sources", "source_kinds", "since", "max_asr_minutes"}:
        raise ResearchError("Research scope contains unknown fields.")
    question = scope.get("question")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise ResearchError("question must contain 1 to 500 characters.", "invalid_question")
    kinds = scope.get("source_kinds", list(DEFAULT_SOURCE_KINDS))
    if (not isinstance(kinds, list) or any(not isinstance(k, str) or k not in SOURCE_KINDS for k in kinds)
            or len(set(kinds)) != len(kinds)):
        raise ResearchError("source_kinds must be a list of distinct supported sources.", "invalid_source_kinds")
    since = scope.get("since")
    if "since" in scope:
        try:
            if not isinstance(since, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", since):
                raise ValueError
            date.fromisoformat(since)
        except ValueError:
            raise ResearchError("since must be a valid YYYY-MM-DD date.", "invalid_since") from None
    normalized = {
        "question": question.strip(),
        "max_sources": _integer(scope.get("max_sources", 12), "max_sources", 1, 30),
        "source_kinds": list(kinds),
        "max_asr_minutes": _integer(scope.get("max_asr_minutes", 120), "max_asr_minutes", 0, 1440),
    }
    if since is not None:
        normalized["since"] = since
    return normalized


def normalize_consent(value) -> list[str]:
    """Only settings supply consent; malformed values grant nothing."""
    return [kind for kind in NETWORK_KINDS if isinstance(value, list) and kind in value]


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or re.fullmatch(RUN_ID_PATTERN, run_id) is None:
        raise ResearchError("Invalid research run id.", "invalid_run_id")
    return run_id


def run_lock(run_id: str):
    """Serialize a run's read/merge/write without locking other runs or fetches."""
    validate_run_id(run_id)
    with RUN_LOCK:
        return _RUN_LOCKS.setdefault(run_id, threading.Lock())


def _utc(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if isinstance(now, date) and not isinstance(now, datetime):
        now = datetime.combine(now, datetime.min.time(), tzinfo=timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)


def timestamp(now=None) -> str:
    return _utc(now).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_path(data_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)  # Validate before even resolving a filesystem path.
    root = Path(data_root).resolve()
    path = root / "research" / run_id / "run.json"
    if not path.resolve().is_relative_to(root):
        raise ResearchError("Invalid research run location.", "invalid_run_id")
    return path


def create_run(data_root: Path, scope: dict, *, now=None) -> dict:
    scope = normalize_scope(scope)
    with RUN_LOCK:
        while True:
            run_id = f"rr_{_utc(now):%Y%m%d%H%M%S}_{secrets.token_hex(4)}"
            if not _run_path(data_root, run_id).parent.exists():
                break
        run = {"run_id": run_id, "scope": scope, "created_at": timestamp(now),
               "candidates": [], "candidates_pool": [], "discover_calls": []}
        save_run(data_root, run)
        return run


def save_run(data_root: Path, run: dict) -> None:
    path = _run_path(data_root, run.get("run_id"))
    with RUN_LOCK:
        tmp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".run-", suffix=".tmp", delete=False) as stream:
                tmp = Path(stream.name)
                json.dump(run, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError):
            raise ResearchError("Could not save the research run.", "store_failed") from None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass  # Keep the safe store error if cleanup also fails.


def load_run(data_root: Path, run_id: str) -> dict:
    path = _run_path(data_root, run_id)
    with RUN_LOCK:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(run, dict) or run.get("run_id") != run_id:
                raise ValueError
            return run
        except FileNotFoundError:
            raise ResearchError("Research run not found.", "not_found") from None
        except (OSError, ValueError):
            raise ResearchError("Could not read the research run.", "store_failed") from None


def list_runs(data_root: Path, limit: int = 20) -> list[dict]:
    _integer(limit, "limit", 1, 1000)
    with RUN_LOCK:
        root = Path(data_root) / "research"
        runs = []
        for path in sorted(root.glob("rr_*"), reverse=True):
            if re.fullmatch(RUN_ID_PATTERN, path.name):
                try:
                    runs.append(load_run(data_root, path.name))
                except ResearchError:
                    continue
            if len(runs) >= limit:
                break
        return runs


def normalize_discovery(args: dict) -> dict:
    if not isinstance(args, dict) or set(args) - {"run_id", "queries", "per_query"}:
        raise ResearchError("Discovery accepts only run_id, queries and per_query.")
    run_id = validate_run_id(args.get("run_id"))
    queries = args.get("queries")
    if (not isinstance(queries, list) or not 1 <= len(queries) <= 8
            or any(not isinstance(q, str) or not 1 <= len(q) <= 200 or not q.strip() for q in queries)):
        raise ResearchError("queries must contain 1 to 8 strings of 1 to 200 characters.")
    return {"run_id": run_id, "queries": [q.strip() for q in queries],
            "per_query": _integer(args.get("per_query", 10), "per_query", 1, 20)}


def _text(value, cap=4000):
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.split())
    clean = "".join(ch for ch in collapsed if unicodedata.category(ch) not in {"Cc", "Cf"})
    return " ".join(clean.split())[:cap]


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _published(value):
    try:
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
        if isinstance(value, str):
            if re.fullmatch(r"[0-9]{8}", value):
                value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
            return date.fromisoformat(value[:10]).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _url(value):
    if (not isinstance(value, str) or len(value) > 2048
            or any(ch.isspace() or unicodedata.category(ch) in {"Cc", "Cf"} for ch in value)):
        return ""
    try:
        parsed = urlparse(value)
        port = parsed.port  # Invalid and out-of-range ports raise ValueError.
        host = (parsed.hostname or "").lower().rstrip(".")
        if (parsed.scheme not in ("http", "https") or not host or "@" in parsed.netloc
                or "\\" in parsed.netloc or "%" in host or port == 0
                or parsed.netloc.endswith(":")
                or host in {"localhost", "local"} or host.endswith((".local", ".localhost"))):
            return ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and (address.is_loopback or address.is_private
                or address.is_link_local or address.is_reserved or address.is_unspecified
                or address.is_multicast):
            return ""
        return value
    except ValueError:
        return ""


def _youtube_id(url):
    if (urlparse(url).hostname or "").lower() not in {
            "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        return None
    ids = list_imports.extract_youtube_ids(url)
    return ids[0] if ids else None


def _candidate(key, kind, url, title, channel="", duration=None, published=None,
               description="", *, in_library=False, capturable=True, signals=None):
    return {"key": key, "kind": kind, "url": url, "title": _text(title, 500),
            "channel": _text(channel, 200), "duration_s": _number(duration),
            "published": _published(published), "description": _text(description),
            "has_captions": None, "in_library": in_library, "capturable": capturable,
            "signals": {"found_by": [], **(signals or {})}, "why_ranked": [],
            "score": 0.0, "est_capture": "unknown"}


def _rows(payload, field):
    if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
        raise ResearchError("The source returned an invalid response.", "invalid_response")
    return [row for row in payload[field] if isinstance(row, dict)]


def parse_ytsearch(payload: Any) -> list[dict]:
    rows = _rows(payload, "entries")
    originals = {}
    for row in rows:
        ident = row.get("id")
        if isinstance(ident, str) and _YT_ID.fullmatch(ident):
            originals.setdefault(ident, row)
    out = []
    for ident, row in originals.items():
        title = _text(row.get("title"), 500)
        if title.casefold() in {"[private video]", "[deleted video]"}:
            continue
        out.append(_candidate("yt:" + ident, "youtube", list_imports.watch_url(ident),
                              title, row.get("channel") or row.get("uploader"), row.get("duration"),
                              row.get("upload_date") or row.get("timestamp"), row.get("description"),
                              signals={"view_count": _number(row.get("view_count"))}))
    return out


def _podcast_host(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (host in PODCAST_HOSTS
            or (host == "open.spotify.com" and parsed.path.startswith("/episode/"))
            or any(host == suffix or host.endswith("." + suffix) for suffix in PODCAST_HOST_SUFFIXES))


def parse_hn_search(payload: Any) -> list[dict]:
    out = []
    for row in _rows(payload, "hits"):
        url = _url(row.get("url"))
        ident = str(row.get("objectID") or "")
        if not ident.isascii() or not ident.isdigit():
            continue
        signals = {"hn_points": _number(row.get("points")),
                   "hn_comments": _number(row.get("num_comments")),
                   "hn_url": f"https://news.ycombinator.com/item?id={ident}"}
        video_id = _youtube_id(url)
        story = row.get("story_text") if isinstance(row.get("story_text"), str) else ""
        video_ids = list(dict.fromkeys(([video_id] if video_id else [])
                                      + list_imports.extract_youtube_ids(story)))
        for found_id in video_ids:
            # HN's created_at dates the submission, not the talk.
            out.append(_candidate("yt:" + found_id, "youtube", list_imports.watch_url(found_id),
                                  row.get("title"), description=story, signals=signals))
        if url and not video_id and _podcast_host(url):
            out.append(_candidate("hn:" + ident, "podcast", url, row.get("title"),
                                  description=story, capturable=False, signals=signals))
    return out


def parse_hackertube(payload: Any, query: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ResearchError("HackerTube returned an invalid response.", "invalid_response")
    terms = {term for term in _TOKENS.findall(query.casefold())
             if len(term) >= 3 and term not in _STOP_WORDS}
    if not terms:
        return []
    originals = {}
    for row in payload:
        ident = row.get("vid") if isinstance(row, dict) else None
        if isinstance(ident, str) and _YT_ID.fullmatch(ident):
            originals.setdefault(ident, row)
    out = []
    for ident, row in originals.items():
        text = " ".join(_text(row.get(field)) for field in
                        ("title", "channel", "why_hn", "note", "summary", "category"))
        if not terms.intersection(_TOKENS.findall(text.casefold())):
            continue
        note = _text(row.get("why_hn") or row.get("note"))
        candidate = _candidate("yt:" + ident, "youtube", list_imports.watch_url(ident),
                               row.get("title"), row.get("channel"), row.get("duration_s"),
                               row.get("published"), row.get("summary") or note,
                               signals={"hackertube_quality": _number(row.get("score"))})
        candidate.update(credit=list_imports.HACKERTUBE_CREDIT, note=note)
        out.append(candidate)
        if len(out) >= 100:
            break
    return out


def parse_itunes_episodes(payload: Any) -> list[dict]:
    out = []
    for row in _rows(payload, "results"):
        audio = _url(row.get("episodeUrl"))
        page = _url(row.get("trackViewUrl"))
        if not (audio or page):
            continue
        duration = _number(row.get("trackTimeMillis"))
        key = "pod:" + hashlib.sha1((audio or page).encode("utf-8")).hexdigest()[:12]
        candidate = _candidate(key, "podcast", audio or page, row.get("trackName"),
                               row.get("collectionName"), duration / 1000 if duration is not None else None,
                               row.get("releaseDate"), row.get("description"), capturable=bool(audio))
        candidate.update(episodeUrl=audio or None, trackViewUrl=page or None,
                         feedUrl=_url(row.get("feedUrl")) or None)
        out.append(candidate)
    return out


def parse_library(rows: Any) -> list[dict]:
    if not isinstance(rows, list):
        raise ResearchError("Library search returned an invalid response.", "invalid_response")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = _text(row.get("video_id"), 200)
        audio = (_url(row.get("enclosure_url")) or _url(row.get("url"))) if ident.startswith("ep_") else ""
        url = _url(row.get("source_url")) or _url(row.get("url"))
        video_id = _youtube_id(url) or (ident if not url and _YT_ID.fullmatch(ident) else None)
        if not (ident or url):
            continue
        key = ("pod:" + hashlib.sha1(audio.encode("utf-8")).hexdigest()[:12] if audio else
               "yt:" + video_id if video_id else "lib:" + (ident or hashlib.sha1(url.encode()).hexdigest()[:12]))
        candidate = _candidate(key, "podcast" if audio else "youtube" if video_id else "library",
                               audio or (list_imports.watch_url(video_id) if video_id else url),
                               row.get("title"), row.get("channel"), row.get("duration"),
                               row.get("published"), row.get("description"), in_library=True)
        if type(row.get("has_captions")) is bool:
            candidate["has_captions"] = row["has_captions"]
        if audio:
            candidate["episodeUrl"] = audio
        out.append(candidate)
    return out


def merge_candidates(candidates: list[dict]) -> list[dict]:
    """Keep richer metadata and accumulate independent discovery signals."""
    merged = {}
    for candidate in candidates:
        key = candidate["key"]
        if key not in merged:
            merged[key] = deepcopy(candidate)
            continue
        target = merged[key]
        for field, value in candidate.items():
            if field in {"signals", "score", "why_ranked", "est_capture"}:
                continue
            if field in {"in_library", "capturable", "has_captions"}:
                if value is True or target.get(field) is None:
                    target[field] = value
            elif not target.get(field) and value is not None:
                target[field] = deepcopy(value)
        signals = target["signals"]
        for name, value in candidate["signals"].items():
            if name == "found_by":
                for found in value:
                    if found not in signals["found_by"]:
                        signals["found_by"].append(deepcopy(found))
            elif isinstance(value, (float, int)):
                signals[name] = max(signals.get(name) or 0, value)
            elif not signals.get(name):
                signals[name] = value
    return list(merged.values())


def _rank_pool(candidates: list[dict], queries: list[str], scope: dict, *, now) -> list[dict]:
    """Score the full pool before either the channel cap or the response limit."""
    today = _utc(now).date()
    since = scope.get("since")
    pool = [deepcopy(c) for c in merge_candidates(candidates)
            if not since or not c.get("published") or c["published"] >= since]
    docs = [Counter(_TOKENS.findall(" ".join(c.get(f) or "" for f in
            ("title", "description", "channel")).casefold())) for c in pool]
    terms = sorted(set(_TOKENS.findall(" ".join(queries).casefold())))
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / len(docs) if docs else 1
    frequency = {term: sum(term in doc for doc in docs) for term in terms}
    for candidate, doc, length in zip(pool, docs, lengths):
        bm25 = 0.0
        for term in terms:
            tf = doc[term]
            if tf:
                idf = math.log1p((len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                bm25 += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / (average or 1)))
        signals = candidate["signals"]
        factors = [("BM25 relevance", bm25), ("HN points", math.log1p(signals.get("hn_points") or 0) * 0.5)]
        if since:
            published = candidate.get("published")
            age = max(0, (today - date.fromisoformat(published)).days) if published else None
            factors.append(("Recency", math.exp(-age / 365) * 0.5 if age is not None else 0.0))
        duration = candidate.get("duration_s")
        length_bonus = (0.0 if duration is None else 0.5 if 900 <= duration <= 5400
                        else -0.5 if duration < 300 or duration > 10800 else 0.0)
        factors.extend([("Length", length_bonus),
                        ("Library or captions", 0.3 if candidate["in_library"] or candidate["has_captions"] is True else 0.0),
                        # HackerTube scores in the saved fixture exceed 10; do not clamp them.
                        ("HackerTube quality", (signals.get("hackertube_quality") or 0) / 10 * 0.3)])
        candidate["score"] = round(sum(value for _, value in factors), 6)
        candidate["why_ranked"] = [f"{name}: {value:+.6f}" for name, value in factors]
        candidate["est_capture"] = (
            "unknown" if not candidate["capturable"] and not candidate["in_library"] else
            "captions" if candidate["in_library"] or candidate["has_captions"] is True else
            f"asr ~{max(1, math.ceil(duration / 300))} min" if duration is not None and duration > 0 else
            "unknown")
    pool.sort(key=lambda c: (-c["score"], c["key"]))
    return pool


def _shortlist(pool: list[dict], scope: dict) -> tuple[list[dict], int]:
    counts, diverse, capped = Counter(), [], 0
    for candidate in pool:
        channel = candidate["channel"].casefold()
        if channel and counts[channel] >= 3:
            capped += 1
            continue
        if channel:
            counts[channel] += 1
        diverse.append(candidate)
    return diverse[:scope["max_sources"] * 2], capped


def rank_candidates(candidates: list[dict], queries: list[str], scope: dict, *, now) -> tuple[list[dict], int]:
    return _shortlist(_rank_pool(candidates, queries, scope, now=now), scope)


def merge_and_rank(run: dict, collected: dict, queries: list[str], *, now,
                   library_ids=()) -> dict:
    """Pure merge against all prior queries; retain the pool before diversity caps."""
    candidates = merge_candidates([*run.get("candidates_pool", run.get("candidates", [])),
                                   *collected["candidates"]])
    for candidate in candidates:
        if candidate["key"].startswith("yt:") and candidate["key"][3:] in library_ids:
            candidate["in_library"] = True
    all_queries = list(dict.fromkeys([query for call in run.get("discover_calls", [])
                                     for query in call["queries"]] + queries))
    scope = normalize_scope(run["scope"])
    pool = _rank_pool(candidates, all_queries, scope, now=now)[:MAX_CANDIDATES_POOL]
    ranked, capped = _shortlist(pool, scope)
    return {**collected, "candidates": ranked, "candidates_pool": pool,
            "capped_by_channel": capped}


def http_get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SEC) as response:
            raw = response.read(FETCH_MAX_BYTES + 1)
        if len(raw) > FETCH_MAX_BYTES:
            raise ResearchError("The source response is too large.", "too_large")
        return json.loads(raw.decode("utf-8"))
    except ResearchError:
        raise
    except urllib.error.HTTPError as error:
        code = "rate_limited" if error.code == 429 else "fetch_failed"
        raise ResearchError("The source could not complete the search.", code) from None
    except (OSError, ValueError):
        raise ResearchError("The source could not be read.", "fetch_failed") from None


def fetch_hn(query, limit):
    return http_get_json("https://hn.algolia.com/api/v1/search?" + urlencode(
        {"query": query, "tags": "story", "hitsPerPage": limit}))


def fetch_itunes(query, limit):
    return http_get_json("https://itunes.apple.com/search?" + urlencode(
        {"media": "podcast", "entity": "podcastEpisode", "limit": limit, "term": query}))


def fetch_hackertube():
    return http_get_json("https://hackertube.org/api/list?n=100&offset=0")


def collect(run: dict, queries: list[str], per_query: int = 10, *, fetchers: dict,
            consented_kinds: list[str]) -> dict:
    """Fetch and parse this call's candidates, without reading or writing the store."""
    args = normalize_discovery({"run_id": run["run_id"], "queries": queries, "per_query": per_query})
    queries = args["queries"]
    scope = normalize_scope(run["scope"])
    consent = normalize_consent(consented_kinds)
    adapters = {"hn": fetch_hn, "podcast": fetch_itunes, "hackertube": fetch_hackertube, **fetchers}
    parsers = {"library": parse_library, "youtube": parse_ytsearch,
               "hn": parse_hn_search, "podcast": parse_itunes_episodes}
    candidates, counts, skipped, errors = [], {}, [], []

    def record_error(kind, query, error):
        safe_codes = {"unavailable", "fetch_failed", "rate_limited", "invalid_response", "too_large"}
        code = error.code if isinstance(error, ResearchError) and error.code in safe_codes else "fetch_failed"
        errors.append({"kind": kind, "query": query, "code": code,
                       "message": f"{kind} discovery could not complete."})
        return code
    # Library always precedes remote calls, even if source_kinds was reordered.
    kinds = sorted(scope["source_kinds"], key=lambda k: k != "library")
    for kind in kinds:
        counts[kind] = 0
        if kind == "reddit":
            skipped.append({"kind": kind, "reason": "reddit_search_off_in_mvp"})
            continue
        if kind != "library" and kind not in consent:
            skipped.append({"kind": kind, "reason": "needs_consent"})
            continue
        fetch = adapters.get(kind)
        seen = set()
        listing, listing_error = None, None
        if kind == "hackertube":
            try:
                listing = fetch()
            except Exception as error:
                listing_error = error
        for index, query in enumerate(queries[:4] if kind == "podcast" else queries):
            try:
                if fetch is None:
                    raise ResearchError("The source is unavailable.", "unavailable")
                if listing_error is not None:
                    raise listing_error
                if kind == "podcast" and index:
                    adapters.get("sleep", time.sleep)(3)
                rows = (parse_hackertube(listing, query) if kind == "hackertube"
                        else parsers[kind](fetch(query, per_query))[:per_query])
                for candidate in rows:
                    candidate["signals"]["found_by"] = [{"source": kind, "query": query}]
                    candidates.append(candidate)
                    seen.add(candidate["key"])
                counts[kind] = len(seen)
            except Exception as error:
                if record_error(kind, query, error) == "rate_limited":
                    break
        if kind == "podcast" and len(queries) > 4:
            skipped.append({"kind": kind, "reason": "itunes_call_cap"})
    return {"candidates": candidates, "by_source": counts, "skipped": skipped, "errors": errors}


def discover(run: dict, queries: list[str], per_query: int = 10, *, fetchers: dict,
             consented_kinds: list[str], now) -> dict:
    """In-memory convenience wrapper; persisted callers reload before merging."""
    collected = collect(run, queries, per_query, fetchers=fetchers, consented_kinds=consented_kinds)
    return merge_and_rank(run, collected, queries, now=now)
