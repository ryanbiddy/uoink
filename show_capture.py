"""Save a whole show: every episode of a YouTube channel, a playlist, a
podcast feed or a pasted list of links, as transcripts only.

The user pastes a source; Uoink lists every episode (in the background),
shows the count and a rough time and disk estimate, and saves nothing until
the user presses Start. Each run is a JSON file under
``DATA_ROOT/show-captures/`` with one state per episode (queued, running,
done, failed with a reason, or skipped), written atomically after every
change, so a run survives a helper restart and picks up where it was.

No parallel capture machinery. A YouTube episode is one row on the existing
download queue (``pending_yoinks`` + the serial retry worker) in a
transcript-only mode: captions first, local ASR only when the run opted in,
and the queue's own bot-check and 429 back-off. A podcast episode goes
through the existing podcast download and local transcription job. The show
feeds one episode at a time and only while the queue has no other work, so
a capture the user makes meanwhile goes first. While YouTube's bot-check
cooldown is on, the run waits instead of asking again.

This module is pure over an injected backend (see ``Backend``), so tests run
it against saved fixtures with no helper, network or model. server.py binds
the real backend and runs ``tick`` on a background thread.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlparse

import list_imports
import podcasts
import source_subscriptions

JOB_DIRNAME = "show-captures"
SCHEMA = 1

KIND_CHANNEL = "youtube_channel"
KIND_PLAYLIST = "youtube_playlist"
KIND_PODCAST = "podcast_feed"
KIND_URL_LIST = "url_list"
KINDS = (KIND_CHANNEL, KIND_PLAYLIST, KIND_PODCAST, KIND_URL_LIST)
KIND_LABELS = {KIND_CHANNEL: "YouTube channel", KIND_PLAYLIST: "YouTube playlist",
               KIND_PODCAST: "Podcast feed", KIND_URL_LIST: "List of links"}

# Job states. listing -> ready -> running <-> waiting / paused -> done.
LISTING, READY, RUNNING, WAITING, PAUSED = "listing", "ready", "running", "waiting", "paused"
CANCELLED, DONE, FAILED = "cancelled", "done", "failed"
ACTIVE_STATES = (RUNNING, WAITING)
FINAL_STATES = (CANCELLED, DONE, FAILED)

# Episode states.
EP_QUEUED, EP_RUNNING, EP_DONE, EP_FAILED, EP_SKIPPED = "queued", "running", "done", "failed", "skipped"
EP_STATES = (EP_QUEUED, EP_RUNNING, EP_DONE, EP_FAILED, EP_SKIPPED)

MAX_EPISODES = 5000
LIST_WINDOW = 500
MAX_LOST = 3              # an episode whose queue row vanished is retried this often
MAX_JOBS_KEPT = 30        # finished runs past this are pruned, oldest first
SKIPS_PER_TICK = 500      # already-saved episodes settled per tick without starting one
# A host that refuses (429, 5xx, timeouts) or fails this many episodes in a
# row pauses the run; before that each refusal waits HOST_BACKOFF_SEC,
# doubled per refusal in a row, at most HOST_BACKOFF_MAX_SEC.
MAX_HOST_FAILURES = 5
HOST_BACKOFF_SEC = 120
HOST_BACKOFF_MAX_SEC = 3600

# Rough estimate inputs (shown to the user as "about"). A queued caption save
# is two small YouTube requests plus the queue's 30 s pacing. Local Whisper
# speed varies a lot by computer; 12 minutes per audio hour is a laptop CPU.
CAPTION_EPISODE_SEC = 45
PODCAST_EPISODE_OVERHEAD_SEC = 60
ASR_MIN_PER_AUDIO_HOUR = 12
AUDIO_MB_PER_MIN = 1.0
TRANSCRIPT_KB_PER_MIN = 6
THUMBNAIL_KB = 60
DEFAULT_EPISODE_MIN = 30

REASON_ALREADY_SAVED = "Already in your library."
REASON_REMOVED = "You removed this one from your library."
REASON_DUPLICATE_IN_LIST = "Listed twice in this source."
REASON_NO_AUDIO = "This episode has no audio link in the feed."
REASON_LOST = "Uoink lost track of this one after a restart three times."
REASON_CANCELLED_IN_QUEUE = "Removed from the download queue."
REASON_NEEDS_ASR = "Podcast episodes need local transcription. Turn it on to save this show."
REASON_LIVE = "This is a live or upcoming stream. Save it on its own once it has ended."
REASON_HOST_DOWN = ("The show's host failed {n} episodes in a row, so Uoink stopped asking. "
                    "Resume to try again later.")
_LIVE_STATUSES = ("is_live", "is_upcoming")

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
# "name:" at the start, not followed by a port number ("example.com:8080").
_SCHEME_PREFIX = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:(?!\d)")
_CHANNEL_PATH = re.compile(
    r"^/(?P<base>@[A-Za-z0-9._-]{1,100}|channel/UC[A-Za-z0-9_-]{10,40}|c/[^/]{1,100}|user/[^/]{1,100})"
    r"(?:/(?P<tab>[A-Za-z]+))?/?$")
_CHANNEL_TABS = ("videos", "streams", "shorts")

_lock = threading.RLock()
_listing: set[str] = set()


class ShowCaptureError(ValueError):
    """A user-facing problem with a request, with a short machine code."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class EpisodeError(Exception):
    """Starting one episode failed for a reason worth showing the user."""


class RunBlocked(Exception):
    """No episode of this run can start until the user fixes something."""


class Backend(Protocol):
    def list_youtube(self, url: str, start: int, end: int) -> dict: ...
    def fetch_feed(self, url: str) -> bytes: ...
    # True (or a reason string, such as REASON_REMOVED) when the episode is
    # not to be saved: an indexed library item, or one the user removed.
    def in_library(self, job: dict, episode: dict) -> bool | str: ...
    def queue_busy(self) -> bool: ...
    def bot_check(self) -> dict: ...
    def asr_problem(self, kind: str) -> str | None: ...
    def start_episode(self, job: dict, episode: dict) -> dict: ...
    # {"state": "running" | "done" | "skipped" | "failed" | "lost" | "waiting"
    #  | "retry", ...}. "retry" means the host refused for now (429, 5xx, a
    # timeout): the episode goes back in line and the run waits. "failed"
    # may carry host_failure=True so failures in a row pause the run.
    def episode_status(self, job: dict, episode: dict) -> dict: ...
    # False when the episode can't be stopped and will finish on its own
    # (a transcription already running, say); anything else means stopped.
    def cancel_episode(self, job: dict, episode: dict) -> bool | None: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        # Queue rows store local wall time without a zone.
        moment = moment.astimezone()
    return moment.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Classify what the user pasted
# ---------------------------------------------------------------------------

def classify(text: str) -> dict:
    """Pasted text -> {kind, url, ...}, or raise ShowCaptureError."""
    raw = (text or "").strip()
    if not raw:
        raise ShowCaptureError("Paste a YouTube channel, a playlist, a podcast feed or a list of links.",
                               "empty")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > 1 or len(raw.split()) > 1:
        ids = list_imports.extract_youtube_ids(raw)
        if not ids:
            raise ShowCaptureError("Uoink found no YouTube video links in that list.", "unsupported")
        return {"kind": KIND_URL_LIST, "url": None, "ids": ids[:MAX_EPISODES],
                "lines": len(lines), "truncated": len(ids) > MAX_EPISODES}
    # Only a bare host name ("youtube.com/@name") gets https:// in front.
    # Anything with a scheme (file:, javascript:, ftp://) is read as written
    # and refused below unless it is http(s).
    try:
        u = urlparse(raw if _SCHEME_PREFIX.match(raw) else "https://" + raw)
    except ValueError:
        raise ShowCaptureError("That doesn't look like a link.", "invalid_url") from None
    if u.scheme.lower() not in ("http", "https") or not u.hostname:
        raise ShowCaptureError("That doesn't look like a link.", "invalid_url")
    host = u.hostname.lower()
    if host in _YT_HOSTS or host == "youtu.be":
        list_id = (parse_qs(u.query).get("list") or [""])[0]
        if list_id:
            try:
                spec = list_imports.classify(raw)
            except list_imports.ImportListError as exc:
                raise ShowCaptureError(str(exc), "unsupported") from None
            return {"kind": KIND_PLAYLIST, "url": spec["url"], "id": spec["id"]}
        match = _CHANNEL_PATH.match(u.path or "")
        if host != "youtu.be" and match:
            tab = (match.group("tab") or "").lower()
            tab = tab if tab in _CHANNEL_TABS else "videos"
            return {"kind": KIND_CHANNEL, "url": f"https://www.youtube.com/{match.group('base')}/{tab}"}
        raise ShowCaptureError(
            "That YouTube link is one video. Paste a channel (youtube.com/@name) or a playlist link.",
            "unsupported")
    if host in ("podcasts.apple.com", "open.spotify.com"):
        raise ShowCaptureError("Paste the show's RSS feed link. Most podcast sites list it.",
                               "unsupported")
    # The same address checks a followed podcast feed gets, before the run
    # is stored: no loopback, private or link-local hosts, no credentials.
    # The fetch itself checks the resolved address again.
    try:
        url = source_subscriptions.normalize_podcast_feed_url(u._replace(fragment="").geturl())
    except source_subscriptions.ServiceError:
        raise ShowCaptureError(
            "Uoink can't read a feed from that address. Paste the show's public feed link.",
            "invalid_url") from None
    return {"kind": KIND_PODCAST, "url": url}


# ---------------------------------------------------------------------------
# Storage (one JSON file per run, atomic writes)
# ---------------------------------------------------------------------------

def _dir(data_root: Path) -> Path:
    return Path(data_root) / JOB_DIRNAME


def _path(data_root: Path, job_id: str) -> Path:
    if not re.fullmatch(r"show_[0-9a-f]{12}", job_id or ""):
        raise ShowCaptureError("That run doesn't exist.", "not_found")
    return _dir(data_root) / f"{job_id}.json"


def _write(data_root: Path, job: dict) -> None:
    folder = _dir(data_root)
    folder.mkdir(parents=True, exist_ok=True)
    job["counts"] = counts(job)
    job["updated_at"] = _iso(_utcnow())
    target = folder / f"{job['id']}.json"
    tmp = folder / f".{job['id']}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)


def load(data_root: Path, job_id: str) -> dict:
    path = _path(data_root, job_id)
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ShowCaptureError("That run doesn't exist.", "not_found") from None
    except (OSError, ValueError):
        raise ShowCaptureError("That run's record can't be read.", "unreadable") from None
    if not isinstance(job, dict) or job.get("schema") != SCHEMA:
        raise ShowCaptureError("That run's record can't be read.", "unreadable")
    return job


# Parsed run files by path, kept while the file's mtime and size are the
# same, so the scheduler pass and the dashboard's polls don't re-read every
# run each time. The dicts are shared: callers must not change them.
_parsed: dict[str, tuple[tuple[int, int, int], dict]] = {}


def list_jobs(data_root: Path) -> list[dict]:
    """Every readable run, oldest first. Read-only: change a run with update()."""
    folder = _dir(data_root)
    jobs = []
    seen = set()
    for path in sorted(folder.glob("show_*.json")) if folder.is_dir() else []:
        key = str(path)
        seen.add(key)
        try:
            stat = path.stat()
            # Every write replaces the file, so its file id changes too
            # (a coarse clock can give two writes the same mtime).
            stamp = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            cached = _parsed.get(key)
            if cached is not None and cached[0] == stamp:
                job = cached[1]
            else:
                job = json.loads(path.read_text(encoding="utf-8"))
                _parsed[key] = (stamp, job)
        except (OSError, ValueError):
            continue
        if isinstance(job, dict) and job.get("schema") == SCHEMA:
            jobs.append(job)
    for key in [k for k in _parsed if k.startswith(str(folder)) and k not in seen]:
        _parsed.pop(key, None)
    jobs.sort(key=lambda j: (j.get("created_at") or "", j.get("id") or ""))
    return jobs


def update(data_root: Path, job_id: str, change: Callable[[dict], Any]) -> dict:
    """Read, change and write one run under the module lock."""
    with _lock:
        job = load(data_root, job_id)
        change(job)
        _write(data_root, job)
        return job


def _prune(data_root: Path) -> None:
    finished = [j for j in list_jobs(data_root) if j.get("state") in FINAL_STATES]
    for job in finished[:max(0, len(finished) - MAX_JOBS_KEPT)]:
        try:
            _path(data_root, job["id"]).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def counts(job: dict) -> dict:
    out = {state: 0 for state in EP_STATES}
    for ep in job.get("episodes") or []:
        out[ep.get("state", EP_QUEUED)] = out.get(ep.get("state", EP_QUEUED), 0) + 1
    out["total"] = len(job.get("episodes") or [])
    return out


def _public_episode(ep: dict) -> dict:
    return {key: ep.get(key) for key in (
        "key", "title", "url", "duration_seconds", "published_at", "state", "reason",
        "attempts", "video_id", "updated_at")}


def view(job: dict, *, episodes: bool = False, failures_limit: int = 500,
         episodes_limit: int | None = None) -> dict:
    """What the dashboard and API see: no handles, at most ``failures_limit``
    failures, and the episodes only when asked (the first
    ``episodes_limit`` of them when given)."""
    eps = job.get("episodes") or []
    current = next((e for e in eps if e.get("state") == EP_RUNNING), None)
    failed = [e for e in eps if e.get("state") == EP_FAILED]
    out = {key: job.get(key) for key in (
        "id", "kind", "url", "title", "state", "reason", "wait_until", "asr",
        "created_at", "started_at", "finished_at", "updated_at", "listing_note")}
    out["kind_label"] = KIND_LABELS.get(job.get("kind"), "Show")
    out["counts"] = counts(job)
    out["estimate"] = estimate(job)
    out["current"] = _public_episode(current) if current else None
    out["failures"] = [_public_episode(e) for e in failed[:failures_limit]]
    out["failures_total"] = len(failed)
    if episodes:
        out["episodes"] = [_public_episode(e) for e in eps[:episodes_limit]]
    return out


def estimate(job: dict) -> dict:
    """Rough cost of saving what is still to save, for the confirm step."""
    eps = job.get("episodes") or []
    todo = [e for e in eps if e.get("state") in (EP_QUEUED, EP_RUNNING)]
    known = [e["duration_seconds"] / 60 for e in todo
             if isinstance(e.get("duration_seconds"), (int, float)) and e["duration_seconds"] > 0]
    average = (sum(known) / len(known)) if known else DEFAULT_EPISODE_MIN
    minutes = sum(known) + average * (len(todo) - len(known))
    podcast = job.get("kind") == KIND_PODCAST
    asr_minutes = minutes * ASR_MIN_PER_AUDIO_HOUR / 60
    if podcast:
        work_minutes = asr_minutes + len(todo) * PODCAST_EPISODE_OVERHEAD_SEC / 60
        asr_extra = 0.0
    else:
        work_minutes = len(todo) * CAPTION_EPISODE_SEC / 60
        asr_extra = asr_minutes if job.get("asr") else 0.0
    disk_mb = (minutes * TRANSCRIPT_KB_PER_MIN + (0 if podcast else len(todo) * THUMBNAIL_KB)) / 1024
    if podcast:
        # Podcast saves keep each episode's audio, the same as saving one
        # episode from Podcasts. YouTube audio for local ASR is deleted after.
        disk_mb += minutes * AUDIO_MB_PER_MIN
    return {
        "to_save": len(todo),
        "already_saved": sum(1 for e in eps if e.get("state") == EP_SKIPPED),
        "audio_minutes": round(minutes),
        "durations_known": len(known),
        "hours": round(work_minutes / 60, 1),
        "asr_hours_at_most": round(asr_extra / 60, 1),
        "asr_hours_if_all": round(asr_minutes / 60, 1),
        "disk_mb": round(disk_mb, 1),
        "audio_download_mb_at_most": round(minutes * AUDIO_MB_PER_MIN) if (podcast or job.get("asr")) else 0,
        "needs_asr": podcast,
    }


# ---------------------------------------------------------------------------
# Creating and listing a run
# ---------------------------------------------------------------------------

def _yt_episode(item: dict) -> dict:
    return {"key": f"yt:{item['video_id']}", "video_id": item["video_id"],
            "url": item.get("url") or list_imports.watch_url(item["video_id"]),
            "title": item.get("title") or "", "duration_seconds": item.get("duration_seconds"),
            "published_at": None, "state": EP_QUEUED, "reason": None, "attempts": 0}


def _podcast_episode(item: dict) -> dict:
    guid = str(item.get("guid") or "")
    ep = {"key": "pod:" + hashlib.sha1(guid.encode("utf-8")).hexdigest()[:16], "guid": guid,
          "video_id": None, "url": item.get("episode_page_url") or item.get("audio_url"),
          "audio_url": item.get("audio_url"), "episode_page_url": item.get("episode_page_url"),
          "title": (item.get("title") or "")[:300],
          "duration_seconds": item.get("duration_seconds"),
          "published_at": item.get("published_at"),
          "description": (item.get("description") or "")[:2000] or None,
          "state": EP_QUEUED, "reason": None, "attempts": 0}
    if not ep["audio_url"]:
        ep["state"], ep["reason"] = EP_SKIPPED, REASON_NO_AUDIO
    return ep


def create(data_root: Path, text: str) -> dict:
    """Classify the paste and save a new run in the listing state. Nothing
    is fetched here; ``tick`` (or ``run_listing``) lists it in the background."""
    spec = classify(text)
    now = _iso(_utcnow())
    job = {
        "schema": SCHEMA, "id": "show_" + uuid.uuid4().hex[:12], "kind": spec["kind"],
        "url": spec.get("url"), "title": None, "state": LISTING, "reason": None,
        "wait_until": None, "asr": False, "created_at": now, "started_at": None,
        "finished_at": None, "listing_note": None, "episodes": [],
        "_source": ({"ids": spec.get("ids"), "lines": spec.get("lines"),
                     "truncated": bool(spec.get("truncated"))}
                    if spec["kind"] == KIND_URL_LIST else {}),
    }
    with _lock:
        _write(data_root, job)
        _prune(data_root)
    return job


class _ListingStopped(Exception):
    """The run was cancelled or dismissed while it was being listed."""


def _list_youtube(backend: Backend, url: str,
                  still_listing: Callable[[], bool] = lambda: True) -> tuple[str, list[dict], bool]:
    """Every video of a channel tab or playlist, in windows of LIST_WINDOW
    through the list import's yt-dlp flat listing. Returns (title, items,
    truncated). Before each window it stops if the run was cancelled, and
    fails with the reason while YouTube's bot-check cooldown is on. The last
    window asks for one video past MAX_EPISODES, so ``truncated`` is only
    true when there really is more."""
    title, items = "", []
    start = 1
    while start <= MAX_EPISODES:
        if not still_listing():
            raise _ListingStopped()
        try:
            cooldown = backend.bot_check() or {}
        except Exception:
            cooldown = {}
        if cooldown.get("active"):
            minutes = max(1, -(-int(cooldown.get("seconds_left") or 0) // 60))
            raise ShowCaptureError(
                f"YouTube asked Uoink to slow down, so listing stopped. Try again in {minutes} minutes.",
                "fetch_failed")
        end = min(start + LIST_WINDOW - 1, MAX_EPISODES)
        if end == MAX_EPISODES:
            end += 1
        payload = backend.list_youtube(url, start, end)
        entries = payload.get("entries") if isinstance(payload, dict) else None
        raw_count = len(entries) if isinstance(entries, list) else 0
        if raw_count:
            # Live and upcoming streams can't be saved until they end.
            payload = {**payload, "entries": [
                e for e in entries
                if not (isinstance(e, dict) and e.get("live_status") in _LIVE_STATUSES)]}
        try:
            window_title, batch, _total = list_imports.parse_ytdlp_flat_playlist(payload)
        except list_imports.ImportListError as exc:
            raise ShowCaptureError(str(exc), "fetch_failed") from None
        title = title or window_title
        items.extend(batch)
        if raw_count < (end - start + 1):
            return title, items, False
        start = end + 1
    return title, items[:MAX_EPISODES], True


def run_listing(data_root: Path, job_id: str, backend: Backend) -> dict:
    """List every episode of a run's source and settle what is already saved.
    Runs on a background thread. A failure leaves the run failed with the
    reason; nothing is saved either way."""
    job = load(data_root, job_id)
    note = None
    capped = f"Listed the first {MAX_EPISODES:,} episodes."
    try:
        if job["kind"] in (KIND_CHANNEL, KIND_PLAYLIST):
            title, items, truncated = _list_youtube(
                backend, job["url"], lambda: _still_listing(data_root, job_id))
            episodes = [_yt_episode(item) for item in items]
            if truncated:
                note = capped
        elif job["kind"] == KIND_PODCAST:
            body = backend.fetch_feed(job["url"])
            try:
                parsed = podcasts.parse_feed_body(body, limit=MAX_EPISODES + 1)
            except Exception:
                raise ShowCaptureError("That link isn't a podcast feed Uoink can read.",
                                       "not_a_feed") from None
            title = (parsed.get("feed") or {}).get("title") or "Podcast"
            items = parsed.get("episodes") or []
            episodes = [_podcast_episode(item) for item in items[:MAX_EPISODES]]
            if len(items) > MAX_EPISODES:
                note = capped
        else:
            source = job.get("_source") or {}
            ids = source.get("ids") or []
            title = f"{len(ids)} links"
            episodes = [_yt_episode(list_imports._item(vid)) for vid in ids]
            lines = int(source.get("lines") or 0)
            if source.get("truncated"):
                note = f"Listed the first {MAX_EPISODES:,} links. The rest are left out."
            elif lines > len(ids):
                note = (f"Found {len(ids)} YouTube links in {lines} lines. "
                        "Other lines are left out.")
    except _ListingStopped:
        return job
    except ShowCaptureError as exc:
        return _finish_listing(data_root, job_id, error=str(exc))
    except Exception:
        return _finish_listing(data_root, job_id, error="Uoink couldn't list that source. Try again later.")
    seen: set[str] = set()
    unique = []
    for ep in episodes:
        if ep["key"] in seen:
            continue
        seen.add(ep["key"])
        unique.append(ep)
    for ep in unique:
        if ep["state"] == EP_QUEUED:
            try:
                saved = backend.in_library(job, ep)
            except Exception:
                saved = False
            if saved:
                ep["state"], ep["reason"] = EP_SKIPPED, _skip_reason(saved)
    return _finish_listing(data_root, job_id, title=title, episodes=unique, note=note)


def _still_listing(data_root: Path, job_id: str) -> bool:
    try:
        return load(data_root, job_id).get("state") == LISTING
    except ShowCaptureError:
        return False


def _skip_reason(saved) -> str:
    return saved if isinstance(saved, str) and saved else REASON_ALREADY_SAVED


def _finish_listing(data_root, job_id, *, error=None, title=None, episodes=None, note=None) -> dict:
    def change(job):
        if job.get("state") != LISTING:
            return  # cancelled while listing
        if error:
            job["state"], job["reason"] = FAILED, error
            job["finished_at"] = _iso(_utcnow())
            return
        job["title"] = (title or "")[:300] or KIND_LABELS.get(job["kind"])
        job["episodes"] = episodes or []
        job["listing_note"] = note
        job["state"] = READY if job["episodes"] else FAILED
        if not job["episodes"]:
            job["reason"] = "That source has no episodes Uoink can save."
            job["finished_at"] = _iso(_utcnow())
    return update(data_root, job_id, change)


# ---------------------------------------------------------------------------
# User actions
# ---------------------------------------------------------------------------

def start(data_root: Path, job_id: str, backend: Backend, *, asr: bool = False) -> dict:
    job = load(data_root, job_id)
    if job.get("state") != READY:
        raise ShowCaptureError("This run has already started.", "invalid_state")
    asr = bool(asr)
    if job["kind"] == KIND_PODCAST and not asr:
        raise ShowCaptureError(REASON_NEEDS_ASR, "needs_asr")
    if asr:
        problem = backend.asr_problem(job["kind"])
        if problem:
            raise ShowCaptureError(problem, "asr_unavailable")

    def change(job):
        if job.get("state") != READY:
            raise ShowCaptureError("This run has already started.", "invalid_state")
        job.update(state=RUNNING, reason=None, asr=asr, started_at=_iso(_utcnow()))
    return update(data_root, job_id, change)


def pause(data_root: Path, job_id: str) -> dict:
    def change(job):
        if job.get("state") not in ACTIVE_STATES:
            raise ShowCaptureError("Only a running save can be paused.", "invalid_state")
        job.update(state=PAUSED, reason=None, wait_until=None)
    return update(data_root, job_id, change)


def resume(data_root: Path, job_id: str) -> dict:
    def change(job):
        if job.get("state") != PAUSED:
            raise ShowCaptureError("Only a paused save can be resumed.", "invalid_state")
        job.update(state=RUNNING, reason=None, host_failures=0)
    return update(data_root, job_id, change)


def cancel(data_root: Path, job_id: str, backend: Backend) -> dict:
    """Stop the run. An episode in flight is stopped when its backend can
    (a queued YouTube row, a podcast download); one that can't be stopped
    (a transcription already running, a row already publishing) finishes,
    is recorded, and nothing starts after it."""
    def change(job):
        if job.get("state") in FINAL_STATES:
            raise ShowCaptureError("This run has already ended.", "invalid_state")
        for ep in job.get("episodes") or []:
            if ep.get("state") == EP_RUNNING:
                try:
                    stopped = backend.cancel_episode(job, ep) is not False
                except Exception:
                    stopped = False
                if stopped:
                    ep.update(state=EP_QUEUED, reason=None)
                else:
                    ep["finishing"] = True
        job.update(state=CANCELLED, reason=None, wait_until=None, finished_at=_iso(_utcnow()))
    return update(data_root, job_id, change)


def retry_failed(data_root: Path, job_id: str, backend: Backend, *, asr: bool | None = None) -> dict:
    job = load(data_root, job_id)
    if asr:
        problem = backend.asr_problem(job["kind"])
        if problem:
            raise ShowCaptureError(problem, "asr_unavailable")

    def change(job):
        failed = [ep for ep in job.get("episodes") or [] if ep.get("state") == EP_FAILED]
        if not failed:
            raise ShowCaptureError("Nothing failed in this run.", "invalid_state")
        if job.get("state") in (LISTING, READY, CANCELLED):
            raise ShowCaptureError("Start the run first.", "invalid_state")
        for ep in failed:
            ep.update(state=EP_QUEUED, reason=None, attempts=0)
            for handle in ("pending_id", "podcast_job_id", "episode_id"):
                ep.pop(handle, None)
        if asr is not None:
            job["asr"] = bool(asr)
        # A paused run stays paused, and a run waiting out a bot check or a
        # busy host keeps its wait (and its reason) until that time.
        if job.get("state") in (PAUSED, WAITING):
            job["finished_at"] = None
        else:
            job.update(state=RUNNING, reason=None, finished_at=None)
    return update(data_root, job_id, change)


def dismiss(data_root: Path, job_id: str) -> None:
    with _lock:
        job = load(data_root, job_id)
        if job.get("state") not in FINAL_STATES + (READY,):
            raise ShowCaptureError("Pause or cancel the run first.", "invalid_state")
        _path(data_root, job_id).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# The scheduler pass
# ---------------------------------------------------------------------------

def _set_episode(ep: dict, state: str, reason: str | None = None, **extra) -> None:
    ep.update(state=state, reason=reason, updated_at=_iso(_utcnow()), **extra)


def _poll(job: dict, ep: dict, backend: Backend, now: datetime) -> bool:
    """Update one in-flight episode. True when it is still in flight."""
    try:
        status = backend.episode_status(job, ep)
    except Exception:
        return True
    state = status.get("state")
    if state in ("done", "skipped"):
        job["host_failures"] = 0
    if state == "done":
        _set_episode(ep, EP_DONE, None, video_id=status.get("video_id") or ep.get("video_id"))
    elif state == "skipped":
        _set_episode(ep, EP_SKIPPED, status.get("reason") or REASON_ALREADY_SAVED)
    elif state == "failed":
        _set_episode(ep, EP_FAILED, status.get("reason") or "Uoink couldn't save this one.")
        if status.get("host_failure"):
            _host_failed(job, now, None)
            return False
        job["host_failures"] = 0
    elif state == "retry":
        # The host refused for now: back in line, and the run waits.
        ep["attempts"] = int(ep.get("attempts") or 0) + 1
        for handle in ("pending_id", "podcast_job_id", "episode_id"):
            ep.pop(handle, None)
        _set_episode(ep, EP_QUEUED, None)
        _host_failed(job, now, _parse_iso(status.get("until")))
        return False
    elif state == "lost":
        ep["attempts"] = int(ep.get("attempts") or 0) + 1
        for handle in ("pending_id", "podcast_job_id"):
            ep.pop(handle, None)
        if ep["attempts"] >= MAX_LOST:
            _set_episode(ep, EP_FAILED, REASON_LOST)
        else:
            _set_episode(ep, EP_QUEUED, None)
    elif state == "waiting":
        if job.get("state") in ACTIVE_STATES:
            job.update(state=WAITING, reason=status.get("reason") or "bot_check",
                       wait_until=status.get("until"))
        return True
    else:
        if job.get("state") == WAITING:
            job.update(state=RUNNING, reason=None, wait_until=None)
        return True
    if job.get("state") == WAITING:
        job.update(state=RUNNING, reason=None, wait_until=None)
    return False


def _host_failed(job: dict, now: datetime, until: datetime | None) -> None:
    """One more refusal or failure from the source's host, in a row. The
    run waits longer each time, and pauses with the reason after
    MAX_HOST_FAILURES in a row."""
    failures = int(job.get("host_failures") or 0) + 1
    job["host_failures"] = failures
    if job.get("state") not in ACTIVE_STATES:
        return
    if failures >= MAX_HOST_FAILURES:
        job.update(state=PAUSED, reason=REASON_HOST_DOWN.format(n=failures), wait_until=None)
        return
    if until is None or until <= now:
        delay = min(HOST_BACKOFF_SEC * 2 ** (failures - 1), HOST_BACKOFF_MAX_SEC)
        until = now + timedelta(seconds=delay)
    job.update(state=WAITING, reason="host_busy", wait_until=_iso(until))


def _finish_if_complete(job: dict) -> None:
    eps = job.get("episodes") or []
    if job.get("state") in ACTIVE_STATES and not any(
            e.get("state") in (EP_QUEUED, EP_RUNNING) for e in eps):
        job.update(state=DONE, reason=None, wait_until=None, finished_at=_iso(_utcnow()))


def ensure_listing(data_root: Path, job_id: str, backend: Backend, *,
                   spawn: Callable[[Callable[[], Any]], Any] | None = None) -> bool:
    """List a run in the background unless that is already happening. A run
    left in the listing state by a restart is listed again. True when a
    listing was started."""
    with _lock:
        if job_id in _listing:
            return False
        _listing.add(job_id)

    def listing():
        try:
            run_listing(data_root, job_id, backend)
        except Exception:
            try:
                _finish_listing(data_root, job_id,
                                error="Uoink couldn't list that source. Try again later.")
            except ShowCaptureError:
                pass  # dismissed while it was listing: nothing left to record
        finally:
            with _lock:
                _listing.discard(job_id)
    (spawn or (lambda fn: threading.Thread(target=fn, name="show-listing", daemon=True).start()))(listing)
    return True


def tick(data_root: Path, backend: Backend, *, now: datetime | None = None,
         spawn: Callable[[Callable[[], Any]], Any] | None = None) -> None:
    """One scheduler pass: settle in-flight episodes, then start at most one.

    Never starts anything for a run the user has not started. At most one
    episode is in flight across every run, and none starts while the
    download queue has other work or YouTube's bot-check cooldown is on."""
    now = now or _utcnow()
    jobs = list_jobs(data_root)
    for job in jobs:
        if job.get("state") == LISTING:
            ensure_listing(data_root, job["id"], backend, spawn=spawn)

    in_flight = False
    for job in jobs:
        # A cancelled run still settles an episode that couldn't be stopped,
        # and nothing new starts until it has.
        if job.get("state") not in (RUNNING, WAITING, PAUSED, CANCELLED):
            continue
        if not any(e.get("state") == EP_RUNNING for e in job.get("episodes") or []):
            continue
        with _lock:
            try:
                fresh = load(data_root, job["id"])
            except ShowCaptureError:
                continue
            ep = next((e for e in fresh.get("episodes") or [] if e.get("state") == EP_RUNNING), None)
            if ep is None:
                continue
            before = json.dumps(fresh, sort_keys=True)
            still = _poll(fresh, ep, backend, now)
            if not still:
                ep.pop("finishing", None)
            in_flight = in_flight or still
            _finish_if_complete(fresh)
            if json.dumps(fresh, sort_keys=True) != before:
                _write(data_root, fresh)
    if in_flight:
        return

    for job in jobs:
        if job.get("state") not in ACTIVE_STATES:
            continue
        with _lock:
            try:
                fresh = load(data_root, job["id"])
            except ShowCaptureError:
                continue
            if fresh.get("state") not in ACTIVE_STATES:
                continue
            before = json.dumps(fresh, sort_keys=True)
            started = _feed(fresh, backend, now)
            _finish_if_complete(fresh)
            # A run that is only waiting (a bot check, a busy queue) is not
            # rewritten every pass.
            if json.dumps(fresh, sort_keys=True) != before:
                _write(data_root, fresh)
        if started or fresh.get("state") == RUNNING:
            # One run feeds at a time, oldest first. A run that is waiting
            # out YouTube lets the next run (a podcast, say) go meanwhile.
            return


def _feed(job: dict, backend: Backend, now: datetime) -> bool:
    """Start the next episode of one active run. True when one started."""
    status = {}
    if job.get("kind") != KIND_PODCAST:
        # A podcast feed's audio host is not YouTube, so only YouTube runs
        # wait out YouTube's bot check.
        try:
            status = backend.bot_check() or {}
        except Exception:
            status = {}
    if status.get("active"):
        until = now + timedelta(seconds=int(status.get("seconds_left") or 0))
        reason = status.get("reason") if status.get("reason") in ("bot_check", "rate_limited") else "bot_check"
        job.update(state=WAITING, reason=reason, wait_until=_iso(until))
        return False
    if job.get("state") == WAITING:
        until = _parse_iso(job.get("wait_until"))
        if until is not None and until > now:
            return False
        job.update(state=RUNNING, reason=None, wait_until=None)
    try:
        busy = backend.queue_busy()
    except Exception:
        busy = True
    if busy:
        job["reason"] = "queue_busy"
        return False
    if job.get("reason") == "queue_busy":
        job["reason"] = None
    skipped = 0
    for ep in job.get("episodes") or []:
        if ep.get("state") != EP_QUEUED:
            continue
        try:
            saved = backend.in_library(job, ep)
        except Exception:
            saved = False
        if saved:
            _set_episode(ep, EP_SKIPPED, _skip_reason(saved))
            skipped += 1
            if skipped >= SKIPS_PER_TICK:
                return False
            continue
        try:
            handle = backend.start_episode(job, ep) or {}
        except RunBlocked as exc:
            # Every episode would fail the same way (transcription isn't set
            # up, say), so the run pauses with the reason instead.
            job.update(state=PAUSED, reason=str(exc) or "Paused.", wait_until=None)
            return False
        except EpisodeError as exc:
            _set_episode(ep, EP_FAILED, str(exc) or "Uoink couldn't start this one.")
            return False
        except Exception:
            _set_episode(ep, EP_FAILED, "Uoink couldn't start this one.")
            return False
        ep.update({k: v for k, v in handle.items() if k in (
            "pending_id", "podcast_job_id", "episode_id", "downloaded_audio")})
        _set_episode(ep, EP_RUNNING, None)
        return True
    return False
