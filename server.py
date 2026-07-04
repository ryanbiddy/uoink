r"""Local HTTP server for the Uoink browser extension.

Runs on http://127.0.0.1:5179. Pure stdlib — no fastapi/flask required.
Reuses parse_srt/slugify/fmt_time from yt_extract.py.

Endpoints:
    GET  /ping
    POST /extract           single-video, drops in Desktop\Uoink\
    POST /session/start
    POST /session/add       runs extraction into the session folder
    POST /session/close     concatenates per-video yoink.md files into corpus.md
    POST /session/cancel
    GET  /session/list
    GET  /session/active
    GET  /dashboard          helper-served local dashboard
"""

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import keyring as _keyring
except Exception as _keyring_error:  # pragma: no cover - env-specific
    _keyring = None
    _KEYRING_IMPORT_ERROR = str(_keyring_error)
else:
    _KEYRING_IMPORT_ERROR = None

# --- Import helpers from the existing CLI script ---------------------------
HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))


def _read_version() -> str:
    try:
        from helper._version import __version__ as version
    except Exception:
        try:
            version = (HERE / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            # Defense in depth: a missing/unreadable version source (e.g. an
            # installer that failed to ship it) must not crash the helper at
            # import before it can bind the port. Degrade to a sentinel so the
            # post-install verifier can report a concrete mismatch.
            return "0.0.0-unknown"
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError(f"Invalid VERSION file value: {version!r}")
    return version

# When shipped via the Windows installer, ffmpeg.exe lives next to server.py
# in a `bin\` folder. Prepend it to PATH so subprocess calls (`ffmpeg ...`)
# find the bundled binary without depending on the user's environment. No-op
# in dev where bin\ doesn't exist — falls back to whatever's on PATH.
_BIN_DIR = HERE / "bin"
if _BIN_DIR.is_dir():
    os.environ["PATH"] = str(_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

from yt_extract import parse_srt, slugify, fmt_time  # noqa: E402
import index  # noqa: E402  -- local SQLite library-index module
import _platform  # noqa: E402  -- cross-platform path / OS helpers
import migrate_install  # noqa: E402  -- one-time Yoink->Uoink install migration
import channels  # noqa: E402  -- v2.5 P3 your-channel registry + recognition
import uoink_reliability  # noqa: E402  -- optional local Whisper reliability checks
import workspaces  # noqa: E402  -- v3 P4 build-workspace state + assembler
import claims  # noqa: E402  -- v3 A2 claim extraction + verification (Loki-inspired)
import scripts as p5_scripts  # noqa: E402  -- v3 P5 script studio backend
import memory_layer  # noqa: E402  -- v2.5 S4 markdown taste/user memory
import podcasts  # noqa: E402  -- v3.1 podcast RSS feed registry + polling
import whisper_runner  # noqa: E402  -- v3.1 WhisperX transcription (lazy)
import mobile_playlists  # noqa: E402  -- v3.1 mobile->desktop playlist bridge
import voice_dna  # noqa: E402  -- v3.2 voice DNA banned-phrase guard
import writing_studio  # noqa: E402  -- v3.2 Writing Studio (tweet/blog)
import page_extractor  # noqa: E402  -- v3.2 Universal Site Uoinking
import source_manifest  # noqa: E402  -- v3.2.1 site/dashboard product manifests
import openapi_bridge  # noqa: E402  -- v3.3 OpenAPI bridge for non-MCP AIs
import reddit_extractor  # noqa: E402  -- v3.3 Reddit thread capture (.json)


def _extract_page_to_prose(url: str) -> str | None:
    """v3.2 synergy bridge: Writing Studio's URL anchor ingestion calls
    this to convert a URL into prose. We wrap page_extractor.extract_page
    with enforce_allowlist=False (user-explicit save is consent enough)
    and return the markdown body. Returns None on failure so the anchor
    still saves with raw_text=NULL."""
    try:
        result = page_extractor.extract_page(
            _get_index(), url,
            render_mode=page_extractor.RENDER_MODE_STATIC,
            include_screenshot=False,
            follow_links_depth=0,
            enforce_allowlist=False)
    except Exception as e:
        log.warning("style anchor URL extraction failed: %s", e)
        return None
    if not result.get("ok"):
        return None
    return result.get("markdown") or None


# Sprint 21 split: pure filesystem helpers now live in uoink_core.storage and
# are re-exported here so existing call sites are unchanged.
from uoink_core.storage import (  # noqa: E402
    _atomic_write_text,
    _is_writable_dir,
    _path_under_any,
    _topic_folder_name,
)

# --- Constants -------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 5179
VERSION = _read_version()
DASHBOARD_PATH = HERE / "assets" / "dashboard" / "index.html"

# v2.5: per-file sidecar data-shape version. v2.5+ writers stamp every new
# sidecar with this; older sidecars (v2.1.x) have no field and are treated as
# 1 by _upgrade_sidecar() on read. Distinct from the SQL migration version and
# from index.py's CURRENT_YOINK_SCHEMA -- the on-disk JSON has its own shape
# axis from the index row. Bump when sidecar fields the v2.5+ readers depend on
# change shape (not just contents).
CURRENT_SIDECAR_SCHEMA = 2


def _upgrade_sidecar(data: dict) -> dict:
    """Lazy v1 -> v2 up-convert on read. v1 sidecars lack `schema_version` and
    the v2.5 fields (facet entries, engagement pointer). We don't rewrite the
    file -- this returns a dict the caller can safely treat as v2, leaving the
    persistent v1 sidecar untouched until a natural re-ingest stamps it. Unknown
    extra fields pass through verbatim (forward-compat)."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if not isinstance(out.get("schema_version"), int):
        out["schema_version"] = 1
    # v2 defaults -- additive, never destructive. Readers that don't need
    # these keys ignore them; readers that do will see explicit None instead
    # of a missing key (cleaner downstream code).
    out.setdefault("facets", None)              # filled by S1 classification
    out.setdefault("engagement_summary", None)  # pointer-only; events live in SQL
    return out


# v2.5 S1 facet enums (model-agnostic classification). The MCP agent supplies
# these values via classify_facets; the server validates against these lists
# but never CALLS an LLM itself. BYO Anthropic batch is opt-in via
# /facets/backfill?confirm=true (when an API key is set).
FORMAT_ENUM = ("one_shot", "talking_head", "tutorial", "listicle", "narrative",
               "vlog", "interview", "screen_recording", "broll_heavy")
PERF_TIER_ENUM = ("over", "average", "under")
LENGTH_BUCKET_ENUM = ("short", "medium", "long", "deep")  # <4m | 4-15 | 15-30 | >30


# Human labels for the S1 enums, so the Library filter chips read like
# English instead of leaking raw storage keys (G-12 / QA #15:
# screen_recording -> "Screen recording"). The backend supplies the label
# alongside the raw value so the frontend never hardcodes its own map.
_FACET_LABELS = {
    "format": {
        "one_shot": "One shot", "talking_head": "Talking head",
        "tutorial": "Tutorial", "listicle": "Listicle",
        "narrative": "Narrative", "vlog": "Vlog", "interview": "Interview",
        "screen_recording": "Screen recording", "broll_heavy": "B-roll heavy",
    },
    "performance_tier": {
        "over": "Overperformed", "average": "Average",
        "under": "Underperformed",
    },
    "length_bucket": {
        "short": "Short (under 4m)", "medium": "Medium (4-15m)",
        "long": "Long (15-30m)", "deep": "Deep (30m+)",
    },
    "hook_type": {
        "curiosity_gap": "Curiosity gap", "question": "Question",
        "contrarian": "Contrarian", "story_open": "Story open",
        "promise_list": "Promise / list", "demo": "Demo",
        "authority": "Authority", "stakes": "Stakes", "other": "Other",
    },
}


def _humanize_facet(col: str, value: str) -> str:
    """Human label for a facet value. Falls back to a de-underscored,
    sentence-cased form for free-text facets (channel, topic) and any enum
    value not in the explicit map."""
    mapped = _FACET_LABELS.get(col, {}).get(value)
    if mapped:
        return mapped
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def _length_bucket_from_seconds(secs) -> str | None:
    """Bucket a video duration into one of LENGTH_BUCKET_ENUM."""
    try:
        s = int(secs)
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return None
    if s < 240:    return "short"
    if s < 900:    return "medium"
    if s < 1800:   return "long"
    return "deep"


def _perf_tier(channel_views: list, current_views) -> str | None:
    """Channel-relative percentile-rank heuristic: top third = over, bottom
    third = under, middle third = average. Returns None if the channel has
    fewer than 3 prior yoinks (not enough signal yet) or no current view
    count. KISS first-ship version of the S1 performance-tier axis -- agents
    can override by passing performance_tier explicitly to classify_facets."""
    try:
        cv = int(current_views)
    except (TypeError, ValueError):
        return None
    samples = [v for v in (channel_views or []) if isinstance(v, int) and v >= 0]
    if len(samples) < 3:
        return None
    samples.sort()
    # Percentile rank of cv within samples (>= cv count divided by N).
    below = sum(1 for v in samples if v < cv)
    pct = below / len(samples)
    if pct >= 0.66:
        return "over"
    if pct <= 0.33:
        return "under"
    return "average"


def _validate_facets(body: dict) -> tuple[dict, str | None]:
    """Pull + validate facet fields from a request body. Unknown values for a
    bounded enum return an error string; missing fields are OK (partial
    classification). Returns (clean_dict, error_or_None)."""
    out: dict = {}
    for key, enum in (("format", FORMAT_ENUM),
                      ("performance_tier", PERF_TIER_ENUM),
                      ("length_bucket", LENGTH_BUCKET_ENUM)):
        v = body.get(key)
        if v is None or v == "":
            continue
        if v not in enum:
            return {}, f"{key} must be one of {list(enum)}"
        out[key] = v
    # Free-form strings (no enum gate; keep them reasonable).
    for key in ("production_style", "topic", "hook_type"):
        v = body.get(key)
        if v is None or v == "":
            continue
        if not isinstance(v, str) or len(v) > 64:
            return {}, f"{key} must be a string <= 64 chars"
        out[key] = v.strip()
    # Tags -- list of short strings.
    raw_tags = body.get("tags")
    if raw_tags is not None:
        if not isinstance(raw_tags, list) or not all(isinstance(t, str) for t in raw_tags):
            return {}, "tags must be a list of strings"
        out["__tags"] = [t.strip().lower() for t in raw_tags if t and t.strip()][:32]
    return out, None
# Tier 2 GUI: served by the /splash route and wrapped by uoink_splash.py at
# first boot for each installed version (gated by
# %LOCALAPPDATA%\Uoink\.first-run-done containing VERSION).
SPLASH_PATH = HERE / "assets" / "splash" / "index.html"
ALLOWED_ORIGINS = {
    "https://www.youtube.com",
    "https://m.youtube.com",
    "https://youtube.com",
}

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SUBPROCESS_KW = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _splash_should_spawn(sentinel: Path) -> bool:
    """Show the splash once per installed version.

    v2.2 visual smoke caught that a plain "file exists" sentinel suppresses the
    splash on upgrades. Keep the same file path for compatibility, but treat its
    contents as the last version that showed the splash.
    """
    try:
        return sentinel.read_text(encoding="utf-8").strip() != VERSION
    except OSError:
        return True

# ---- Hardening limits (P1-3 / P1-4) ---------------------------------------
MAX_BODY_BYTES = 64 * 1024            # 64KB POST body cap
MAX_SCREENSHOTS = 200                  # cap per video
PLAYLIST_VIDEO_CAP = 10                # v2 Playlist Mode first-ship cap
MAX_SERVED_FILE_BYTES = 10 * 1024 * 1024
LONG_VIDEO_SECONDS = 2 * 60 * 60       # 2 hours -- log warning above this
LONG_VIDEO_MODE_FULL = "full"
LONG_VIDEO_MODE_CHUNKED = "chunked"
# A-01 spec A: lite recovery. When a long extract fails, retry by landing the
# high-value transcript and shedding the fragile/expensive work -- keep the
# full captions, take sparse screenshots (~1 per 5 min), and skip the comments
# fetch. Cheaper and less fragile than the full path, without segmenting the
# download (that's the reserve, spec B / chunked).
LONG_VIDEO_MODE_LITE = "lite"
LONG_VIDEO_MODES = (LONG_VIDEO_MODE_FULL, LONG_VIDEO_MODE_CHUNKED,
                    LONG_VIDEO_MODE_LITE)
# Lite mode forces the screenshot interval to at least this (1 per 5 min), so
# a 2-hour video yields a couple dozen frames instead of hundreds.
LITE_SHOT_INTERVAL_SEC = 5 * 60
# Chunked mode downloads at most six representative 10-minute windows. It
# keeps the full subtitle track, but bounds the heavy media download/decode
# work to one hour and runs screenshot extraction one window at a time.
LONG_VIDEO_CHUNK_SECONDS = 10 * 60
LONG_VIDEO_MAX_CHUNKS = 6
LONG_VIDEO_CHUNK_BUDGET_SECONDS = (
    LONG_VIDEO_CHUNK_SECONDS * LONG_VIDEO_MAX_CHUNKS
)
YTDLP_TIMEOUT_SEC = 30 * 60            # download timeout FLOOR (short videos)
# v3.2.4: a flat 30-min download timeout is the prime suspect for long-video
# failures -- a throttled 2-hour download legitimately exceeds it, and the
# old error told users to raise the *screenshot interval*, which can't help a
# download timeout. We now scale the budget with the video's real duration
# (clamped) so a 2-hour video gets room, while a stuck download still can't
# hang the extract lock forever.
YTDLP_TIMEOUT_PER_VIDEO_SEC = 0.5      # 0.5s of download budget per second of video
YTDLP_TIMEOUT_HARD_CAP_SEC = 2 * 60 * 60  # never wait more than 2 hours
COMMENTS_TIMEOUT_SEC = 5 * 60
# Screenshot decode also scales: a 2-hour source takes ffmpeg longer to walk
# than a 5-minute one even at the same shot interval.
FFMPEG_TIMEOUT_SEC = 15 * 60           # screenshot timeout FLOOR
FFMPEG_TIMEOUT_PER_VIDEO_SEC = 0.25
CLIPBOARD_SCREENSHOT_CAP_DEFAULT = 4
CLIPBOARD_SCREENSHOT_CAP_MAX = 12
RELIABILITY_MODEL_NAME = "tiny"
RELIABILITY_DEFAULT_THRESHOLD = 0.5


def _env_float(name: str, default: float, *, low: float, high: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(low, min(high, value))


PLAYLIST_SLEEP_SEC = _env_float("YOINK_PLAYLIST_SLEEP_SEC", 5.0, low=0.0, high=120.0)
PLAYLIST_RATE_LIMIT_BACKOFF_BASE_SEC = 30.0
PLAYLIST_RATE_LIMIT_BACKOFF_MAX_SEC = 5 * 60.0

# ---- Auth token (P0-1) ----------------------------------------------------
# Per-install random token. Persisted next to server.py (which lives in the
# install root -- %LOCALAPPDATA%\Uoink on Windows, ~/Library/Application
# Support/Uoink on macOS -- in the shipped product, or in the dev repo
# directory in dev mode; gitignored either way). The extension fetches
# this via /token (gated by chrome-extension:// origin) on first launch
# and includes it in X-Uoink-Token on every subsequent request. The legacy
# X-Yoink-Token header is still accepted through the v2.x alias window.
TOKEN_PATH = HERE / "token.txt"
# Sprint 19.5 Stage 1: DATA_ROOT is now resolved by _platform.user_data_dir
# so the same helper runs on Windows + macOS without per-call branches.
DATA_ROOT = _platform.user_data_dir()
RELIABILITY_MODEL_ROOT = DATA_ROOT / "models" / "whisper"
SETTINGS_PATH = DATA_ROOT / "settings.json"
JOBS_PATH = DATA_ROOT / "jobs.json"
TAXONOMY_PATH = DATA_ROOT / "taxonomy.json"
KEYRING_SERVICE = "Uoink"
# Legacy Credential Manager service name from the Yoink era. The first-run
# install migration (migrate_install.py) copies the saved Anthropic key from
# this service to KEYRING_SERVICE; kept here so both the migration and any
# fallback read can reference one source of truth.
KEYRING_SERVICE_LEGACY = "Yoink"
KEYRING_ANTHROPIC_USERNAME = "anthropic_key"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_VERSION = "2023-06-01"
# Pricing source: Anthropic Claude pricing docs, verified 2026-05-12:
# https://docs.claude.com/en/docs/about-claude/pricing
ANTHROPIC_PRICING_INPUT_PER_MILLION = 1.00
ANTHROPIC_PRICING_OUTPUT_PER_MILLION = 5.00
ANTHROPIC_CI_EST_INPUT_TOKENS = 5_000
ANTHROPIC_CI_EST_OUTPUT_TOKENS = 500
ANTHROPIC_HOOK_EST_INPUT_TOKENS = 1_200
ANTHROPIC_HOOK_EST_OUTPUT_TOKENS = 80


def _load_or_create_token() -> str:
    if TOKEN_PATH.exists():
        try:
            existing = TOKEN_PATH.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            pass
    fresh = secrets.token_urlsafe(32)
    try:
        TOKEN_PATH.write_text(fresh, encoding="utf-8")
        # Best-effort: tighten file perms on POSIX. On Windows, ACLs default
        # to user-only for files in %LOCALAPPDATA%, so chmod is a no-op but
        # harmless.
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except OSError:
            pass
    except OSError:
        # Non-fatal: keep an in-memory token for the session. Persistence is
        # nice-to-have; auth still works within this server's lifetime.
        pass
    return fresh


TOKEN = _load_or_create_token()

# /token rate limit -- defends the relaxed Origin gate. The legitimate
# caller (the extension) fetches /token once per install plus the rare 403
# retry, so 10/min is comfortable for real use and tight enough that a
# noisy script can't grind through tokens hunting for racing conditions.
_TOKEN_RATE_LIMIT = 10
_TOKEN_RATE_WINDOW_SEC = 60.0
_token_request_times: list[float] = []
_token_rate_lock = threading.Lock()
# Canonical client-identification header value. The legacy "yoink-extension"
# value is still accepted through the v2.x alias window so a not-yet-updated
# extension build keeps passing the /token gate.
_UOINK_CLIENT_HEADER_VALUE = "uoink-extension"
_YOINK_CLIENT_HEADER_VALUE = "yoink-extension"


def _check_token_rate_limit() -> bool:
    import time
    now = time.monotonic()
    with _token_rate_lock:
        # Drop stale entries (older than the window) and decide.
        cutoff = now - _TOKEN_RATE_WINDOW_SEC
        kept = [t for t in _token_request_times if t > cutoff]
        if len(kept) >= _TOKEN_RATE_LIMIT:
            _token_request_times[:] = kept
            return False
        kept.append(now)
        _token_request_times[:] = kept
    return True


# POST /taxonomy/correct rate limit (Sprint 17). Corrections are
# user-initiated (a click in the popup), so 30/min is generous for real
# use and still caps a runaway client.
_TAXONOMY_CORRECT_RATE_LIMIT = 30
_TAXONOMY_CORRECT_RATE_WINDOW_SEC = 60.0
_taxonomy_correct_request_times: list[float] = []
_taxonomy_correct_rate_lock = threading.Lock()


def _check_taxonomy_correct_rate_limit() -> bool:
    now = time.monotonic()
    with _taxonomy_correct_rate_lock:
        cutoff = now - _TAXONOMY_CORRECT_RATE_WINDOW_SEC
        kept = [t for t in _taxonomy_correct_request_times if t > cutoff]
        if len(kept) >= _TAXONOMY_CORRECT_RATE_LIMIT:
            _taxonomy_correct_request_times[:] = kept
            return False
        kept.append(now)
        _taxonomy_correct_request_times[:] = kept
    return True


# GET /memory/search rate limit (Sprint 18). Heavier than /recent because
# it runs an FTS5 query; 60/min is generous for a human paging the memory
# page and still caps a runaway client.
_MEMORY_SEARCH_RATE_LIMIT = 60
_MEMORY_SEARCH_RATE_WINDOW_SEC = 60.0
_memory_search_request_times: list[float] = []
_memory_search_rate_lock = threading.Lock()


def _check_memory_search_rate_limit() -> bool:
    now = time.monotonic()
    with _memory_search_rate_lock:
        cutoff = now - _MEMORY_SEARCH_RATE_WINDOW_SEC
        kept = [t for t in _memory_search_request_times if t > cutoff]
        if len(kept) >= _MEMORY_SEARCH_RATE_LIMIT:
            _memory_search_request_times[:] = kept
            return False
        kept.append(now)
        _memory_search_request_times[:] = kept
    return True


# /queue/* rate limits (Sprint 19 / C4). /queue/status is poll-friendly
# (60/min) so the popup can refresh a queue banner; the mutating endpoints
# are 30/min, matching /taxonomy/correct.
_QUEUE_STATUS_RATE_LIMIT = 60
_QUEUE_STATUS_RATE_WINDOW_SEC = 60.0
_queue_status_request_times: list[float] = []
_queue_status_rate_lock = threading.Lock()

_QUEUE_MUTATE_RATE_LIMIT = 30
_QUEUE_MUTATE_RATE_WINDOW_SEC = 60.0
_queue_mutate_request_times: list[float] = []
_queue_mutate_rate_lock = threading.Lock()


def _check_queue_status_rate_limit() -> bool:
    now = time.monotonic()
    with _queue_status_rate_lock:
        cutoff = now - _QUEUE_STATUS_RATE_WINDOW_SEC
        kept = [t for t in _queue_status_request_times if t > cutoff]
        if len(kept) >= _QUEUE_STATUS_RATE_LIMIT:
            _queue_status_request_times[:] = kept
            return False
        kept.append(now)
        _queue_status_request_times[:] = kept
    return True


def _check_queue_mutate_rate_limit() -> bool:
    """Shared limiter for /queue/cancel and /queue/retry-now."""
    now = time.monotonic()
    with _queue_mutate_rate_lock:
        cutoff = now - _QUEUE_MUTATE_RATE_WINDOW_SEC
        kept = [t for t in _queue_mutate_request_times if t > cutoff]
        if len(kept) >= _QUEUE_MUTATE_RATE_LIMIT:
            _queue_mutate_request_times[:] = kept
            return False
        kept.append(now)
        _queue_mutate_request_times[:] = kept
    return True


def _valid_iso_date(value: str) -> bool:
    """True if value is a well-formed YYYY-MM-DD date."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


# ---- v3.1 P2 role inference -----------------------------------------------
# Bounded enum; mixed = "show me everything, don't bias the dashboard."
ROLE_CREATOR = "creator"
ROLE_RESEARCHER = "researcher"
ROLE_MARKETER = "marketer"
ROLE_MIXED = "mixed"
_ROLE_ENUM = (ROLE_CREATOR, ROLE_RESEARCHER, ROLE_MARKETER, ROLE_MIXED)


def _normalize_role(value) -> str:
    """Clamp a settings.role value to the bounded enum. Unknown values
    (including None and pre-v3.1 settings.json files that omit the field)
    fall back to ``mixed`` so the dashboard surfaces every facet."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _ROLE_ENUM:
            return v
    return ROLE_MIXED


def _role_facet_emphasis(role: str) -> dict:
    """Return the per-role dashboard sort + filter-chip emphasis the
    dashboard reads on load. Pure mapping; the dashboard owns the UI."""
    role = _normalize_role(role)
    if role == ROLE_CREATOR:
        return {
            "primary": ["hook_type", "format", "performance_tier"],
            "secondary": ["length_bucket", "channel"],
            "default_sort": "performance_tier",
        }
    if role == ROLE_RESEARCHER:
        return {
            "primary": ["topic", "entity", "channel"],
            "secondary": ["hook_type", "yoinked_at"],
            "default_sort": "yoinked_at",
        }
    if role == ROLE_MARKETER:
        return {
            "primary": ["channel", "audience", "hook_type"],
            "secondary": ["performance_tier", "topic"],
            "default_sort": "performance_tier",
        }
    # mixed
    return {
        "primary": ["topic", "hook_type", "format", "channel"],
        "secondary": ["performance_tier", "length_bucket"],
        "default_sort": "yoinked_at",
    }


# ---- v3.1 live stream detection -------------------------------------------
# yt-dlp exposes ``is_live`` (bool) and the more granular ``live_status``
# enum: is_upcoming | is_live | post_live | was_live | not_live. We map
# everything to a bounded internal enum so the rest of the helper +
# the dashboard chip stay decoupled from yt-dlp's exact strings.
LIVE_STATE_NOT_LIVE = "not_live"
LIVE_STATE_LIVE = "live"          # currently broadcasting
LIVE_STATE_UPCOMING = "upcoming"  # scheduled, not started
LIVE_STATE_POST_LIVE = "post_live"  # broadcast ended; recording may not be exposed yet
LIVE_STATE_WAS_LIVE = "was_live"    # ended + recording available
_LIVE_STATES = (
    LIVE_STATE_NOT_LIVE, LIVE_STATE_LIVE, LIVE_STATE_UPCOMING,
    LIVE_STATE_POST_LIVE, LIVE_STATE_WAS_LIVE,
)

LIVE_BEHAVIOR_WAIT = "wait_for_end"
LIVE_BEHAVIOR_NOW = "extract_when_recorded"
_LIVE_BEHAVIORS = (LIVE_BEHAVIOR_WAIT, LIVE_BEHAVIOR_NOW)
_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large")

# How long to wait between live-stream retry attempts. Conservative -- a
# 2-hour broadcast doesn't need a 1-minute poll. Lined up with the
# existing rate-limit backoff so the retry worker doesn't need new code.
_LIVE_RETRY_INTERVAL_SEC = 600   # 10 minutes


def _detect_live_state(metadata: dict | None) -> str:
    """Map a yt-dlp metadata dict to our bounded enum. Returns
    LIVE_STATE_NOT_LIVE for anything that doesn't look live (which is the
    vast majority of yoinked content)."""
    if not isinstance(metadata, dict):
        return LIVE_STATE_NOT_LIVE
    raw = (metadata.get("live_status") or "").strip().lower()
    if raw == "is_live":
        return LIVE_STATE_LIVE
    if raw == "is_upcoming":
        return LIVE_STATE_UPCOMING
    if raw == "post_live":
        return LIVE_STATE_POST_LIVE
    if raw == "was_live":
        return LIVE_STATE_WAS_LIVE
    # Fallback: the older ``is_live`` boolean. Treat True as currently
    # broadcasting (it's the dominant case when live_status is missing).
    if metadata.get("is_live") is True:
        return LIVE_STATE_LIVE
    return LIVE_STATE_NOT_LIVE


def _normalize_live_behavior(value) -> str:
    """Clamp settings.live_stream_behavior to the bounded enum. Unknown /
    None falls back to wait_for_end (the gentler default)."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _LIVE_BEHAVIORS:
            return v
    return LIVE_BEHAVIOR_WAIT


# ---- Settings (v2.1 BYO Anthropic key) ------------------------------------
class CredentialStoreError(RuntimeError):
    """Raised when the OS credential store cannot read/write a saved key."""


def _default_settings() -> dict:
    return {
        "comment_intelligence_enabled": False,
        "hook_type_enabled": False,
        "smart_screenshot_picker_enabled": False,
        "clipboard_screenshot_cap": CLIPBOARD_SCREENSHOT_CAP_DEFAULT,
        "transcript_reliability_auto_check": False,
        "claim_verification_enabled": False,   # v3 A2 -- opt-in
        # v3.1 P2 role inference -- one of: creator, researcher, marketer,
        # mixed. Default "mixed" so the dashboard surfaces every facet
        # axis until the user (or onboarding) picks. Drives Library
        # default sort + filter-chip emphasis per ROADMAP P2.
        "role": "mixed",
        # v3.1 live stream behavior. wait_for_end (default) -> we queue the
        # URL and re-attempt periodically until the broadcast ends and a
        # recording is available. extract_when_recorded -> we attempt
        # immediately and fail with a "still live" message if no recording
        # is exposed yet (user picks when to retry).
        "live_stream_behavior": "wait_for_end",
        # v3.1 WhisperX preference. Actual model download/execution is handled
        # by the A1/podcast backend; the dashboard can persist the user choice
        # ahead of that worker landing.
        "whisper_model": "base",
        # v3.1 WhisperX diarization default. On = diarize interview-format
        # content automatically (ROADMAP P5/track D guidance). Off = ASR
        # only; user can still enable per-call via the endpoint body.
        "diarization_default": False,
        # v3.2 Writing Studio -- soft-warn Voice DNA scan. When False, the
        # scan is skipped entirely. Per Ryan's locked answer #3 the default
        # is True (warn on slop, don't auto-block).
        "voice_dna_warnings_enabled": True,
        # v3.2 Writing Studio -- whether the dashboard exposes the
        # "skip warnings this generation" affordance. Default True; users
        # who never want the warning surface can hide it via Settings.
        "voice_dna_show_per_generation_toggle": True,
        # v3.3 D-20 -- the dashboard shows source screenshots before the X
        # intent handoff. The picker is visible by default; preselecting every
        # screenshot is intentionally off so the user chooses what travels.
        "writing_show_screenshot_picker": True,
        "writing_default_attach_all_screenshots": False,
        "anthropic_key_invalid": False,
        # v2.1 rename: set True after the one-time post-migration
        # post-migration toast has fired, so it never repeats.
        "post_migration_toast_shown": False,
        "updated_at": None,
    }


def _normalize_settings(data: dict) -> dict:
    clean = _default_settings()
    if isinstance(data, dict):
        clean.update(data)
    clean.pop("anthropic_key", None)
    clean["comment_intelligence_enabled"] = bool(
        clean.get("comment_intelligence_enabled")
    )
    clean["hook_type_enabled"] = bool(clean.get("hook_type_enabled"))
    clean["smart_screenshot_picker_enabled"] = bool(
        clean.get("smart_screenshot_picker_enabled")
    )
    clean["transcript_reliability_auto_check"] = bool(
        clean.get("transcript_reliability_auto_check")
    )
    clean["voice_dna_warnings_enabled"] = bool(
        clean.get("voice_dna_warnings_enabled", True)
    )
    clean["voice_dna_show_per_generation_toggle"] = bool(
        clean.get("voice_dna_show_per_generation_toggle", True)
    )
    clean["writing_show_screenshot_picker"] = bool(
        clean.get("writing_show_screenshot_picker", True)
    )
    clean["writing_default_attach_all_screenshots"] = bool(
        clean.get("writing_default_attach_all_screenshots", False)
    )
    try:
        cap = int(clean.get("clipboard_screenshot_cap"))
    except (TypeError, ValueError):
        cap = CLIPBOARD_SCREENSHOT_CAP_DEFAULT
    clean["clipboard_screenshot_cap"] = max(
        0,
        min(CLIPBOARD_SCREENSHOT_CAP_MAX, cap),
    )
    clean["anthropic_key_invalid"] = bool(clean.get("anthropic_key_invalid"))
    clean["post_migration_toast_shown"] = bool(
        clean.get("post_migration_toast_shown")
    )
    model = str(clean.get("whisper_model") or "base").strip().lower()
    clean["whisper_model"] = model if model in _WHISPER_MODELS else "base"
    return clean


def _read_settings() -> dict:
    with _settings_lock:
        data: dict = {}
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
            except (OSError, json.JSONDecodeError) as e:
                log.warning("settings read failed: %s", e)
        return _normalize_settings(data)


def _write_settings(data: dict) -> None:
    with _settings_lock:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        clean = _normalize_settings(data)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
        try:
            os.chmod(SETTINGS_PATH, 0o600)
        except OSError:
            pass


def _credential_store_error() -> CredentialStoreError | None:
    if _keyring is None:
        detail = (
            f"keyring import failed: {_KEYRING_IMPORT_ERROR}"
            if _KEYRING_IMPORT_ERROR else
            "keyring is not installed"
        )
        return CredentialStoreError(
            "Anthropic API key storage unavailable. Install keyring or run the "
            f"Windows installer. Details: {detail}"
        )
    return None


def _get_saved_anthropic_key() -> str:
    err = _credential_store_error()
    if err:
        log.debug("%s", err)
        return ""
    try:
        key = _keyring.get_password(KEYRING_SERVICE, KEYRING_ANTHROPIC_USERNAME)
        if key:
            return key
        # Alias window: if the install migration hasn't yet copied the key
        # from the legacy "Yoink" service (e.g. keyring was briefly
        # unavailable at first boot), still honour the old entry so AI
        # features don't silently break. migrate_install.py performs the
        # one-time copy; this is the read-time safety net.
        legacy = _keyring.get_password(
            KEYRING_SERVICE_LEGACY, KEYRING_ANTHROPIC_USERNAME
        )
        return legacy or ""
    except Exception as e:
        log.warning("credential read failed: %s", e)
        return ""


def _store_saved_anthropic_key(key: str) -> None:
    key = (key or "").strip()
    err = _credential_store_error()
    if err:
        if key:
            raise err
        return
    try:
        if key:
            _keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_ANTHROPIC_USERNAME,
                key,
            )
        else:
            try:
                _keyring.delete_password(
                    KEYRING_SERVICE,
                    KEYRING_ANTHROPIC_USERNAME,
                )
            except Exception:
                # Missing entries and unavailable delete backends both mean
                # the credential is no longer retrievable by Yoink.
                pass
    except Exception as e:
        raise CredentialStoreError(f"credential write failed: {e}") from e


def _migrate_plaintext_anthropic_key() -> None:
    """Move legacy settings.json anthropic_key into the OS credential store."""
    if not SETTINGS_PATH.exists():
        return
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("settings migration skipped: read failed (%s)", e)
        return
    if not isinstance(raw, dict) or "anthropic_key" not in raw:
        return

    legacy_key = raw.get("anthropic_key")
    clean = _normalize_settings(raw)
    if isinstance(legacy_key, str) and legacy_key.strip():
        try:
            _store_saved_anthropic_key(legacy_key.strip())
            clean["anthropic_key_invalid"] = False
            log.info("Migrated Anthropic API key from settings.json to keyring")
        except CredentialStoreError as e:
            log.error("settings migration failed: %s", e)
            return
    clean["updated_at"] = _now_iso()
    try:
        _write_settings(clean)
    except OSError as e:
        log.warning("settings migration cleanup failed: %s", e)


def _public_settings(data: dict | None = None) -> dict:
    data = data or _read_settings()
    key = _get_saved_anthropic_key()
    return {
        "comment_intelligence_enabled": bool(data.get("comment_intelligence_enabled")),
        "hook_type_enabled": bool(data.get("hook_type_enabled")),
        "smart_screenshot_picker_enabled": bool(
            data.get("smart_screenshot_picker_enabled")
        ),
        "clipboard_screenshot_cap": int(
            data.get("clipboard_screenshot_cap", CLIPBOARD_SCREENSHOT_CAP_DEFAULT)
        ),
        "transcript_reliability_auto_check": bool(
            data.get("transcript_reliability_auto_check")
        ),
        "transcript_reliability_model": _reliability_model_status(),
        # v3 A2: default OFF -- claims are extracted on every yoink only when
        # ON; otherwise extraction is per-claim, user-triggered.
        "claim_verification_enabled": bool(
            data.get("claim_verification_enabled")),
        "anthropic_key_set": bool(key and not data.get("anthropic_key_invalid")),
        # Tier 2 dashboard Settings tab additions:
        "anthropic_key_masked": _mask_anthropic_key(key),
        "output_dir": str(DESKTOP_ROOT),
        "output_dir_pending_restart": bool(
            data.get("output_dir")
            and str(Path(data["output_dir"]).expanduser()) != str(DESKTOP_ROOT)
        ),
        "autostart": _autostart_enabled(),
        "topics": (_load_topics() or {}).get("topics", []),
        # v2.5 S4: optional Obsidian vault mirror for TASTE.md + USER.md.
        # When set, every write to the markdown memory layer also drops a
        # copy at <vault>/Uoink/. Vault picker UI is a Codex/AG follow-up
        # PR; this field is the contract.
        "obsidian_vault_path": (data.get("obsidian_vault_path") or "") or None,
        # v3.1 P2 -- role drives dashboard default sort + filter chip
        # emphasis. Always returned; the dashboard reads this on load.
        "role": _normalize_role(data.get("role")),
        # v3.1: live stream behavior + the bounded supported list so the
        # Settings UI can render the radio without hard-coding enum strings.
        "live_stream_behavior": _normalize_live_behavior(
            data.get("live_stream_behavior")),
        "live_stream_behavior_supported": list(_LIVE_BEHAVIORS),
        "whisper_model": data.get("whisper_model") or "base",
        "whisper_models_supported": list(_WHISPER_MODELS),
        "diarization_default": bool(data.get("diarization_default")),
        # Helper-side runtime probe so the dashboard can show
        # "WhisperX not installed -- install via Setup" without a
        # separate endpoint roundtrip.
        "whisperx_runtime_available": whisper_runner.is_whisperx_available(),
        # v3.2 Writing Studio settings.
        "voice_dna_warnings_enabled": bool(
            data.get("voice_dna_warnings_enabled", True)),
        "voice_dna_show_per_generation_toggle": bool(
            data.get("voice_dna_show_per_generation_toggle", True)),
        "writing_show_screenshot_picker": bool(
            data.get("writing_show_screenshot_picker", True)),
        "writing_default_attach_all_screenshots": bool(
            data.get("writing_default_attach_all_screenshots", False)),
    }


def _anthropic_estimated_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * ANTHROPIC_PRICING_INPUT_PER_MILLION
        + (output_tokens / 1_000_000) * ANTHROPIC_PRICING_OUTPUT_PER_MILLION,
        6,
    )


def _anthropic_pricing_payload() -> dict:
    ci = _anthropic_estimated_cost(
        ANTHROPIC_CI_EST_INPUT_TOKENS,
        ANTHROPIC_CI_EST_OUTPUT_TOKENS,
    )
    hook = _anthropic_estimated_cost(
        ANTHROPIC_HOOK_EST_INPUT_TOKENS,
        ANTHROPIC_HOOK_EST_OUTPUT_TOKENS,
    )
    return {
        "model": ANTHROPIC_MODEL,
        "display_model": "Claude Haiku 4.5",
        "input_per_million": ANTHROPIC_PRICING_INPUT_PER_MILLION,
        "output_per_million": ANTHROPIC_PRICING_OUTPUT_PER_MILLION,
        "est_tokens": {
            "ci": {
                "input": ANTHROPIC_CI_EST_INPUT_TOKENS,
                "output": ANTHROPIC_CI_EST_OUTPUT_TOKENS,
            },
            "hook": {
                "input": ANTHROPIC_HOOK_EST_INPUT_TOKENS,
                "output": ANTHROPIC_HOOK_EST_OUTPUT_TOKENS,
            },
        },
        "est_per_video": {
            "ci": ci,
            "hook": hook,
            "both": round(ci + hook, 6),
        },
        "source": "https://docs.claude.com/en/docs/about-claude/pricing",
        "source_checked": "2026-05-12",
    }


def _mark_anthropic_key_invalid() -> None:
    data = _read_settings()
    try:
        _store_saved_anthropic_key("")
    except CredentialStoreError as e:
        log.warning("credential invalid-key clear failed: %s", e)
    data["anthropic_key_invalid"] = True
    data["updated_at"] = _now_iso()
    try:
        _write_settings(data)
    except OSError as e:
        log.warning("settings invalid-key write failed: %s", e)


def _anthropic_key_for_feature(feature_flag: str) -> str | None:
    data = _read_settings()
    key = _get_saved_anthropic_key()
    if not data.get(feature_flag):
        return None
    if data.get("anthropic_key_invalid"):
        return None
    return key.strip() or None


def _saved_anthropic_key() -> str | None:
    """Return the saved key for explicit/on-demand tool calls.

    Feature flags gate automatic background work, but MCP tools are user-
    initiated calls from an agent. Those should only require that a valid
    key exists, not that the background feature toggle is enabled.
    """
    data = _read_settings()
    key = _get_saved_anthropic_key()
    if data.get("anthropic_key_invalid"):
        return None
    return key.strip() or None


def _anthropic_key_available() -> str | None:
    return _anthropic_key_for_feature("comment_intelligence_enabled")


class AnthropicAPIError(Exception):
    def __init__(self, status: int | None, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _short_reason(reason: str, *, api_key: str | None = None) -> str:
    msg = re.sub(r"\s+", " ", str(reason or "unknown error")).strip()
    if api_key:
        msg = msg.replace(api_key, "[redacted]")
    return msg[:180] if len(msg) > 180 else msg


# Strip filesystem paths (Windows or Unix) before persisting an error
# string. Windows: ``X:\...`` (one literal backslash per separator). Unix:
# ``/...``. The URL pattern runs first below so a userinfo-bearing URL
# is replaced as a unit rather than slashed-up piece by piece.
_PATH_SANITIZE_RE = re.compile(r"[A-Za-z]:\\[^\s]+|/[^\s]+")
# Strip URLs that carry HTTP basic-auth userinfo (rare but possible: e.g.
# yt-dlp surfacing the request URL in an error). Match scheme://user@host
# and replace the whole URL with a placeholder.
_USERINFO_URL_RE = re.compile(r"https?://[^@\s/]+@[^\s]+")


def _sanitize_error(msg: str, *, max_len: int = 200) -> str:
    """Strip filesystem paths and userinfo-bearing URLs from an error
    string before persisting it (Sprint 19.6 / Fix 8 / audit F3).

    The rate-limit retry queue persists last_error across helper restarts;
    a raw friendly_error string can include yt-dlp's last stderr line,
    which sometimes echoes the install path or the request URL with
    embedded credentials. Sanitise to ``<path>`` / ``<url>`` and cap
    length so the queue stays free of PII even if the upstream tool
    leaks it."""
    if not msg:
        return ""
    # URL pass first so a userinfo URL is replaced as a unit -- otherwise
    # the path regex would only catch the trailing /-prefixed portion and
    # leave the credentials visible.
    cleaned = _USERINFO_URL_RE.sub("<url>", str(msg))
    cleaned = _PATH_SANITIZE_RE.sub("<path>", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def _anthropic_error_reason(status: int, body: str) -> str:
    try:
        parsed = json.loads(body or "{}")
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict) and err.get("message"):
            return str(err.get("message"))
        if isinstance(parsed, dict) and parsed.get("message"):
            return str(parsed.get("message"))
    except json.JSONDecodeError:
        pass
    return f"Anthropic API returned HTTP {status}"


def _anthropic_messages(api_key: str, *, system: str, user: str,
                        max_tokens: int = 800) -> dict:
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise AnthropicAPIError(
            e.code,
            _short_reason(_anthropic_error_reason(e.code, body), api_key=api_key),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AnthropicAPIError(
            None,
            _short_reason(f"network error contacting Anthropic: {e}", api_key=api_key),
        ) from None

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise AnthropicAPIError(None, f"Anthropic returned invalid JSON: {e}") from None
    if not isinstance(parsed, dict):
        raise AnthropicAPIError(None, "Anthropic returned an unexpected response")
    return parsed


def _anthropic_text(resp: dict) -> str:
    pieces = []
    for part in resp.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "text":
            pieces.append(str(part.get("text") or ""))
    text = "\n".join(pieces).strip()
    if not text:
        raise AnthropicAPIError(None, "Anthropic returned an empty response")
    return text


def _test_anthropic_key(api_key: str) -> tuple[bool, str | None, int | None]:
    if not api_key:
        return False, "API key is required", None
    try:
        _anthropic_messages(
            api_key,
            system="Reply with exactly: ok",
            user="hi",
            max_tokens=4,
        )
        return True, None, None
    except AnthropicAPIError as e:
        return False, e.reason, e.status

# Invoke yt-dlp via the same interpreter rather than relying on PATH. pip's
# --user install puts yt-dlp.exe in %APPDATA%\Python\PythonXX\Scripts which
# isn't on PATH by default on Windows, so a bare "yt-dlp" call fails.
#
# v3.2 fix for v3.1.3 QA-42 (X/Twitter "Bad guest token"):
# Twitter rotated their anonymous guest-token contract. yt-dlp 2026.3.17
# (the PyPI latest) ships a workaround that uses the syndication API
# instead of the guest-token-gated GraphQL endpoint. We have to opt in
# explicitly via --extractor-args. The arg is a no-op for other
# platforms, so we bake it into the canonical command instead of
# threading platform-detection through every yt-dlp call site.
# Reference: yt-dlp's twitter:api extractor-arg, values are
#   {legacy, syndication, graphql}.
YTDLP_CMD = [sys.executable, "-m", "yt_dlp",
              "--extractor-args", "twitter:api=syndication"]

# Hard cap on the video file yt-dlp downloads before ffmpeg runs. yt-dlp
# pulls the whole file to disk first; on a small disk a few livestream-length
# pulls could fill it. 2 GB is comfortably above a 4-hour 1080p video but
# bails out on multi-hour livestream VODs.
YTDLP_MAX_FILESIZE_BYTES = 2 * 1024 * 1024 * 1024

def _get_desktop_dir() -> Path:
    """Cross-platform Desktop folder. Sprint 19.5 Stage 1 moved the actual
    resolution into _platform.desktop_dir (Windows known-folder API on
    Windows so OneDrive Desktop redirection is followed; ~/Desktop on
    macOS + Linux); this thin wrapper stays so callers don't all need
    updating in the same commit, and so the function name still reads
    naturally at the call site."""
    return _platform.desktop_dir()


def _get_output_root() -> Path:
    """Return the Uoink output root.

    Dev mode can set UOINK_OUTPUT_DIR (legacy: YOINK_OUTPUT_DIR) to keep
    personal uoinks out of a repo that happens to live on the Desktop. The
    override must already exist and be writable; otherwise Uoink falls back
    to the Desktop\\Uoink folder.

    v2.1 rename behaviour: a fresh install saves to Desktop\\Uoink. An
    upgraded install keeps saving to the existing Desktop\\Yoink folder
    until the user opts in to move it (the Desktop-corpus move is a separate,
    user-confirmed step surfaced in the extension popup -- see
    migrate_install.py). Once Desktop\\Uoink exists it always wins, so the
    flip happens automatically after the opt-in move completes. This avoids
    splitting a user's corpus across two folders before they've chosen to
    migrate it.

    A second fallback, _LOCALAPPDATA_OUTPUT, kicks in at startup if even
    the Desktop path turns out to be unwritable -- see
    _apply_output_root_fallback (Sprint 19, Wave 1 Fix 4 carryover)."""
    override = (os.environ.get("UOINK_OUTPUT_DIR")
                or os.environ.get("YOINK_OUTPUT_DIR") or "").strip()
    if override:
        try:
            candidate = Path(override).expanduser().resolve()
            if _is_writable_dir(candidate):
                return candidate
        except OSError:
            pass
    # User-chosen output folder (dashboard Settings, Tier 2). Persisted in
    # settings.json and honored at startup, just like the env override above
    # (env still wins so dev/test can force a path). Applied at start rather
    # than mutating DESKTOP_ROOT live, so in-flight extractions never see the
    # root move under them.
    try:
        chosen = (_read_settings().get("output_dir") or "").strip()
    except Exception:
        chosen = ""
    if chosen:
        try:
            candidate = Path(chosen).expanduser().resolve()
            if _is_writable_dir(candidate):
                return candidate
        except OSError:
            pass
    desktop = _get_desktop_dir()
    new_root = desktop / "Uoink"
    legacy_root = desktop / "Yoink"
    if new_root.exists():
        return new_root
    if legacy_root.exists():
        return legacy_root
    return new_root


# Last-resort output root used when DESKTOP_ROOT turns out to be unwritable
# at startup. Lives inside DATA_ROOT (%LOCALAPPDATA%\Uoink on Windows /
# ~/Library/Application Support/Uoink on macOS), which is reliably
# writable since DATA_ROOT itself is required for the helper to work.
# Sprint 19.5 Stage 1 kept the historical _LOCALAPPDATA_OUTPUT name --
# the underlying value is cross-platform via _platform.user_data_dir.
_LOCALAPPDATA_OUTPUT = DATA_ROOT / "output"

DESKTOP_ROOT = _get_output_root()
SESSIONS_ROOT = DESKTOP_ROOT / "_sessions"
# Set True by _apply_output_root_fallback when the active root has been
# moved to _LOCALAPPDATA_OUTPUT. Surfaced in /health and /diagnose so the
# popup can warn the user their yoinks are no longer on the Desktop.
_OUTPUT_ROOT_FALLBACK = False


def _apply_output_root_fallback() -> None:
    """If DESKTOP_ROOT can't be written to at startup, swap it (and
    SESSIONS_ROOT) over to _LOCALAPPDATA_OUTPUT. Sets _OUTPUT_ROOT_FALLBACK
    so /health and /diagnose can warn. /file accepts both candidates
    either way, so legacy yoinks still on the Desktop remain readable."""
    global DESKTOP_ROOT, SESSIONS_ROOT, _OUTPUT_ROOT_FALLBACK
    try:
        DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("output root: cannot create %s -- %s", DESKTOP_ROOT, e)
    if _is_writable_dir(DESKTOP_ROOT):
        return
    fallback = _LOCALAPPDATA_OUTPUT
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error(
            "output root fallback: cannot create %s either -- %s; staying on %s",
            fallback, e, DESKTOP_ROOT)
        return
    if not _is_writable_dir(fallback):
        log.error(
            "output root fallback: %s exists but is not writable -- "
            "staying on %s", fallback, DESKTOP_ROOT)
        return
    log.warning(
        "OUTPUT ROOT FALLBACK: '%s' is not writable; switching to '%s'",
        DESKTOP_ROOT, fallback)
    DESKTOP_ROOT = fallback
    SESSIONS_ROOT = fallback / "_sessions"
    _OUTPUT_ROOT_FALLBACK = True


def _allowed_roots() -> set[Path]:
    """All filesystem roots /file is permitted to serve from. The active
    output root plus every fallback candidate -- after a fallback, or before
    the user opts in to move their Desktop corpus, they may still have
    uoinks under Desktop\\Uoink OR legacy yoinks under Desktop\\Yoink whose
    thumbnails the Memory page needs to render."""
    roots: set[Path] = set()
    desktop = _get_desktop_dir()
    for candidate in (DESKTOP_ROOT, desktop / "Uoink", desktop / "Yoink",
                      _LOCALAPPDATA_OUTPUT):
        try:
            roots.add(candidate.resolve())
        except OSError:
            pass
    return roots


# --- Logging ---------------------------------------------------------------
LOG_PATH = HERE / "server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("uoink")

# Serialize extractions — yt-dlp + ffmpeg are I/O heavy.
_extract_lock = threading.Lock()
# Serialize session.json mutations to keep the on-disk state consistent.
_session_lock = threading.Lock()

# v2.1 persists public job snapshots to jobs.json. Worker internals stay
# process-local; on restart, non-terminal jobs are marked failed so users have
# an audit trail but must restart the extraction manually.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOB_TERMINAL_STATES = {"completed", "cancelled", "failed"}

# ---- /jobs/stream SSE (Tier 2) -------------------------------------------
# Live job/queue push for the dashboard Activity tab + the extension popup
# queue (one stream, two consumers). Header-gated like every other read
# endpoint and consumed via fetch()+stream, NOT EventSource -- so the token is
# sent in the X-Uoink-Token header and never lands in a URL (the ?token= query
# fallback was deliberately removed; see _request_token). Event schema lives in
# docs/tier-2-contracts.md. Emits the same _public_job shape /jobs returns.
_SSE_MAX_STREAMS = 8          # cap concurrent streams (local single-user helper)
_SSE_TICK_SEC = 1.0           # poll job/queue state this often
_SSE_HEARTBEAT_SEC = 15.0     # keepalive comment cadence
_sse_count_lock = threading.Lock()
_sse_active = [0]

_settings_lock = threading.Lock()
_corpus_update_lock = threading.Lock()
# Serializes read-modify-write of the per-video <slug>.json sidecar. The
# comments / hook-type / comment-intelligence workers run concurrently for the
# same video; without this lock two of them can interleave read->read->write
# ->write and silently drop one worker's fields.
_sidecar_update_lock = threading.Lock()
_taxonomy_lock = threading.Lock()

# ===========================================================================
# Library index (Sprint 15) -- SQLite + FTS5. See index.py.
# ===========================================================================
INDEX_PATH = DATA_ROOT / "index.db"
_index_singleton: "index.Index | None" = None
_index_open_lock = threading.Lock()
# True from an index.db corruption-recovery (open_or_recover) until the
# rebuilding backfill scan finishes. Surfaced in /health as index_recovering.
_index_recovering = False

# Backfill scan progress, polled via GET /index/backfill-status.
_backfill_state = {"state": "idle", "current": 0, "total": 0}
_backfill_lock = threading.Lock()
_backfill_cancel = threading.Event()


def _get_index() -> "index.Index":
    """Process-wide Index handle, opened lazily. A corrupt index.db is
    quarantined and rebuilt (open_or_recover); recovery sets the
    _index_recovering flag the backfill clears when it finishes."""
    global _index_singleton, _index_recovering
    with _index_open_lock:
        if _index_singleton is None:
            idx, recovered = index.Index.open_or_recover(INDEX_PATH)
            _index_singleton = idx
            if recovered:
                _index_recovering = True
        return _index_singleton


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_hms(value) -> float | None:
    """Inverse of yt_extract.fmt_time: 'HH:MM:SS' -> seconds. Falls back to a
    plain numeric coercion so a raw number also works."""
    if not isinstance(value, str):
        return _as_float(value)
    parts = value.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    secs = 0
    for n in nums:
        secs = secs * 60 + n
    return float(secs)


def _youtube_deep_link(video_id: str, seconds) -> str:
    """A watch URL deep-linked to a timestamp -- the citations contract."""
    vid = (video_id or "").strip()
    try:
        t = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        t = 0
    return f"https://youtube.com/watch?v={vid}&t={t}s"


def compute_health(sidecar: dict) -> dict:
    """A per-video extraction health snapshot (A5), computed at extraction
    time. Stored on the sidecar under `health` and in the index. The
    comments / hook / comment-intelligence background workers finish *after*
    this snapshot, so those fields report in-progress status, not the final
    result."""
    comments = sidecar.get("comments")
    comments_status = sidecar.get("comments_status") or "unknown"
    if isinstance(comments, list) and len(comments) >= 5:
        comments_health = "ok"
    elif isinstance(comments, list) and comments:
        comments_health = "ok -- fewer than 5 comments"
    elif comments_status == "pending":
        comments_health = "pending"
    else:
        comments_health = "missing"
    return {
        "transcript": "ok" if sidecar.get("transcript") else "missing",
        "screenshots": "ok" if sidecar.get("screenshots") else "missing",
        "comments": comments_health,
        "hook": sidecar.get("hook_type_status") or "skipped",
        "comment_intelligence": sidecar.get("comment_intelligence_status") or "skipped",
    }


def _reliability_model_status() -> dict:
    model_file = RELIABILITY_MODEL_ROOT / f"{RELIABILITY_MODEL_NAME}.pt"
    cached = model_file.exists()
    if not cached and RELIABILITY_MODEL_ROOT.exists():
        cached = any(RELIABILITY_MODEL_ROOT.glob("*.pt"))
    return {
        "model": RELIABILITY_MODEL_NAME,
        "model_root": str(RELIABILITY_MODEL_ROOT),
        "cached": bool(cached),
        "estimated_download_mb": 150,
    }


def _transcript_text_from_sidecar(sidecar: dict) -> str:
    return "\n".join(
        str(item.get("text") or "").strip()
        for item in (sidecar.get("transcript") or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    )


def _folder_for_video_id(video_id: str) -> tuple[Path | None, dict | None]:
    vid = (video_id or "").strip()
    if not vid:
        return None, None
    row = _get_index().get_yoink(vid)
    if not row or row.get("deleted_at"):
        return None, None
    sidecar_path = Path(row.get("sidecar_path") or "")
    if not sidecar_path.is_file():
        return None, None
    return sidecar_path.parent, row


def _read_sidecar_for_folder(folder: Path) -> tuple[Path, dict]:
    sidecar_path = folder / f"{folder.name}.json"
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    return sidecar_path, data


def _write_reliability_to_sidecar(folder: Path, reliability: dict) -> dict:
    with _sidecar_update_lock:
        sidecar_path, data = _read_sidecar_for_folder(folder)
        data["reliability"] = reliability
        _atomic_write_text(sidecar_path, json.dumps(data, ensure_ascii=False, indent=2))
        return data


def _render_reliability_summary(reliability: dict) -> str:
    status = reliability.get("status") or "unknown"
    if status == "completed":
        count = int(reliability.get("span_count") or 0)
        if count:
            line = f"⚠️ {count} low-confidence spans flagged."
        else:
            line = "No low-confidence spans flagged."
        return (
            "## Transcript Reliability\n"
            "<!-- RELIABILITY_START -->\n"
            f"{line}\n\n"
            f"- Model: `{reliability.get('model') or RELIABILITY_MODEL_NAME}`\n"
            f"- Threshold: `{reliability.get('threshold')}`\n"
            "<!-- RELIABILITY_END -->\n"
        )
    reason = _sanitize_error(str(reliability.get("error") or reliability.get("reason") or status))
    return (
        "## Transcript Reliability\n"
        "<!-- RELIABILITY_START -->\n"
        f"Transcript Reliability: {status} - {reason}\n"
        "<!-- RELIABILITY_END -->\n"
    )


def _replace_reliability_section(corpus_path: Path, reliability: dict) -> None:
    try:
        md = corpus_path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("reliability md update: read failed (%s)", e)
        return
    block = _render_reliability_summary(reliability).strip() + "\n"
    pattern = re.compile(
        r"\n?## Transcript Reliability\n<!-- RELIABILITY_START -->.*?<!-- RELIABILITY_END -->\n?",
        re.S,
    )
    if pattern.search(md):
        updated = pattern.sub("\n\n" + block, md).rstrip() + "\n"
    else:
        updated = md.rstrip() + "\n\n" + block
    try:
        _atomic_write_text(corpus_path, updated)
    except OSError as e:
        log.warning("reliability md update: write failed (%s)", e)


def _download_reliability_audio(url: str, tmp_dir: Path,
                                cancel_event: threading.Event | None = None) -> Path:
    _run_subprocess(
        [
            *YTDLP_CMD,
            "-f", "bestaudio/best",
            "-o", str(tmp_dir / "audio.%(ext)s"),
            url,
        ],
        cancel_event=cancel_event,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=YTDLP_TIMEOUT_SEC,
    )
    candidates = [p for p in tmp_dir.glob("audio.*") if p.is_file()]
    if not candidates:
        raise RuntimeError("yt-dlp produced no audio file")
    return candidates[0]


def _compute_transcript_reliability(
    video_id: str,
    *,
    folder: Path | None = None,
    audio_path: Path | None = None,
    threshold: float = RELIABILITY_DEFAULT_THRESHOLD,
    allow_model_download: bool = False,
    force: bool = False,
) -> dict:
    """Compute/cache transcript reliability for one saved yoink.

    Endpoint-triggered calls can re-download audio into a temp folder. The
    extraction-time call passes the just-downloaded video file before it is
    deleted, avoiding a second network request.
    """
    if folder is None:
        folder, _row = _folder_for_video_id(video_id)
    if folder is None:
        return {"ok": False, "error": "yoink not found"}

    sidecar_path, sidecar = _read_sidecar_for_folder(folder)
    vid = (sidecar.get("video_id") or video_id or "").strip()
    if not vid:
        return {"ok": False, "error": "yoink has no video_id"}
    existing = sidecar.get("reliability")
    if isinstance(existing, dict) and existing.get("status") == "completed" and not force:
        return {"ok": True, "reliability": existing, "cached": True}

    transcript_text = _transcript_text_from_sidecar(sidecar)
    if not transcript_text:
        reliability = {
            "status": "skipped",
            "reason": "no transcript",
            "spans": [],
            "span_count": 0,
            "computed_at": _now_iso(),
        }
        _write_reliability_to_sidecar(folder, reliability)
        return {"ok": True, "reliability": reliability, "cached": False}

    if not allow_model_download and not _reliability_model_status()["cached"]:
        reliability = {
            "status": "skipped",
            "reason": "model_not_downloaded",
            "model": RELIABILITY_MODEL_NAME,
            "model_root": str(RELIABILITY_MODEL_ROOT),
            "spans": [],
            "span_count": 0,
            "computed_at": _now_iso(),
        }
        _write_reliability_to_sidecar(folder, reliability)
        return {"ok": False, "error": "Whisper model not downloaded", "reliability": reliability}

    def run_detection(path: Path) -> dict:
        spans = uoink_reliability.detect_unreliable_spans(
            transcript_text,
            path,
            threshold=threshold,
            model_name=RELIABILITY_MODEL_NAME,
            model_root=RELIABILITY_MODEL_ROOT,
        )
        return {
            "status": "completed",
            "model": RELIABILITY_MODEL_NAME,
            "model_root": str(RELIABILITY_MODEL_ROOT),
            "threshold": threshold,
            "spans": [s.to_dict() for s in spans],
            "span_count": len(spans),
            "computed_at": _now_iso(),
        }

    try:
        if audio_path is not None and Path(audio_path).is_file():
            reliability = run_detection(Path(audio_path))
        else:
            url = (sidecar.get("url") or "").strip()
            if not url:
                return {"ok": False, "error": "yoink has no source URL"}
            with tempfile.TemporaryDirectory(prefix="uoink-reliability-") as tmp:
                audio = _download_reliability_audio(url, Path(tmp))
                reliability = run_detection(audio)
    except Exception as e:
        reliability = {
            "status": "failed",
            "error": _sanitize_error(str(e)),
            "model": RELIABILITY_MODEL_NAME,
            "threshold": threshold,
            "spans": [],
            "span_count": 0,
            "computed_at": _now_iso(),
        }
        _write_reliability_to_sidecar(folder, reliability)
        return {"ok": False, "error": reliability["error"], "reliability": reliability}

    sidecar = _write_reliability_to_sidecar(folder, reliability)
    corpus = _resolve_corpus_path(folder)
    if corpus:
        _replace_reliability_section(corpus, reliability)
    try:
        sidecar["health"] = compute_health(sidecar)
        _index_yoink(folder, sidecar, corpus, sidecar_path)
    except Exception as e:
        log.warning("reliability index refresh failed: %s", e)
    return {"ok": True, "reliability": reliability, "cached": False}


def _citations_from_sidecar(sidecar: dict, folder: Path) -> list[dict]:
    """Build the citation map (A4) from a parsed sidecar: one row per
    transcript chunk and one per screenshot, each with a timestamped
    YouTube deep link."""
    video_id = (sidecar.get("video_id") or "").strip()
    out: list[dict] = []
    for i, seg in enumerate(sidecar.get("transcript") or []):
        if not isinstance(seg, dict):
            continue
        start = _as_float(seg.get("start"))
        out.append({
            "kind": "transcript_chunk",
            "seq": i,
            "timestamp_start": start,
            "timestamp_end": _as_float(seg.get("end")),
            "text": seg.get("text"),
            "file_path": None,
            "youtube_deep_link": _youtube_deep_link(video_id, start),
        })
    for i, shot in enumerate(sidecar.get("screenshots") or []):
        if not isinstance(shot, dict):
            continue
        ts = _parse_hms(shot.get("timestamp"))
        rel = shot.get("path") or shot.get("filename") or ""
        out.append({
            "kind": "screenshot",
            "seq": i,
            "timestamp_start": ts,
            "timestamp_end": None,
            "text": None,
            "file_path": str(folder / rel) if rel else None,
            "youtube_deep_link": _youtube_deep_link(video_id, ts),
        })
    return out


def _index_yoink(folder: Path, sidecar: dict, corpus_path: Path | None,
                 sidecar_path: Path) -> bool:
    """Upsert one yoink + its citations into the library index. Best-effort
    and idempotent: callers (extraction hook, backfill) must treat a failure
    as non-fatal. Returns True if the row was indexed."""
    video_id = (sidecar.get("video_id") or "").strip()
    if not video_id:
        # video_id is the yoinks primary key + citations FK -- can't index.
        log.warning("index skip: no video_id for %s", folder)
        return False
    try:
        content = (corpus_path.read_text(encoding="utf-8")
                   if corpus_path and corpus_path.exists() else "")
    except OSError:
        content = ""
    record = {
        "video_id": video_id,
        "slug": folder.name,
        "channel": sidecar.get("channel"),
        "title": sidecar.get("title"),
        "topic": sidecar.get("topic"),
        "hook_type": sidecar.get("hook_type"),
        "yoinked_at": sidecar.get("yoinked_at") or _now_iso(),
        "corpus_path": str(corpus_path) if corpus_path else "",
        "sidecar_path": str(sidecar_path),
        "health_score_json": (
            json.dumps(sidecar["health"], ensure_ascii=False)
            if isinstance(sidecar.get("health"), dict) else None
        ),
        "metadata_json": json.dumps({
            "url": sidecar.get("url"),
            "platform": sidecar.get("platform") or _detect_platform_from_url(
                sidecar.get("url") or ""),
            "media_type": sidecar.get("media_type"),
            "content_type": sidecar.get("content_type"),
            "is_live": sidecar.get("is_live"),
            "live_status": sidecar.get("live_status"),
            "duration_seconds": sidecar.get("duration_seconds"),
            "view_count": sidecar.get("view_count"),
            "like_count": sidecar.get("like_count"),
            "upload_date": sidecar.get("upload_date"),
        }, ensure_ascii=False),
    }
    idx = _get_index()
    idx.upsert_yoink(record, content=content)
    idx.insert_citations(video_id, _citations_from_sidecar(sidecar, folder))
    return True


def _iter_corpus_folders():
    """Yield (folder, corpus_path) for every live yoink folder under
    DESKTOP_ROOT. Soft-deleted yoinks parked under _yoink-trash/ are
    skipped so the backfill never re-indexes a trashed video."""
    if not DESKTOP_ROOT.exists():
        return
    trash = _trash_root()
    for folder in DESKTOP_ROOT.rglob("*"):
        if not folder.is_dir():
            continue
        if folder == trash or trash in folder.parents:
            continue
        corpus = _resolve_corpus_path(folder)
        if corpus is not None:
            yield folder, corpus


def _run_backfill() -> None:
    """Index every on-disk yoink folder not already in index.db. Incremental
    (skips rows already present) and cancellable via _backfill_cancel."""
    global _index_recovering
    try:
        known = _get_index().all_video_ids()
    except Exception:
        log.exception("backfill: could not read the index")
        with _backfill_lock:
            _backfill_state.update(state="complete")
        return
    folders = list(_iter_corpus_folders())
    with _backfill_lock:
        _backfill_state.update(state="running", current=0, total=len(folders))
    done = 0
    indexed = 0
    for folder, corpus in folders:
        if _backfill_cancel.is_set():
            log.info("backfill cancelled at %d/%d", done, len(folders))
            break
        done += 1
        with _backfill_lock:
            _backfill_state["current"] = done
        sidecar_path = folder / f"{folder.name}.json"
        try:
            sidecar = (json.loads(sidecar_path.read_text(encoding="utf-8"))
                       if sidecar_path.exists() else {})
        except (OSError, json.JSONDecodeError):
            sidecar = {}
        video_id = (sidecar.get("video_id") or "").strip()
        if not video_id or video_id in known:
            continue  # unindexable, or already indexed (incremental skip)
        try:
            if _index_yoink(folder, sidecar, corpus, sidecar_path):
                indexed += 1
        except Exception:
            log.exception("backfill: failed to index %s", folder)
    with _backfill_lock:
        _backfill_state["state"] = "complete"
    _index_recovering = False
    log.info("backfill complete: scanned %d folder(s), indexed %d new", done, indexed)


def _start_backfill_thread() -> None:
    """Kick the backfill scan off in the background so a missing or
    freshly-recovered index.db never delays the bind or /health."""
    _backfill_cancel.clear()

    def _runner():
        try:
            _run_backfill()
        except Exception:
            log.exception("backfill thread crashed")
            with _backfill_lock:
                _backfill_state["state"] = "complete"

    threading.Thread(target=_runner, name="index-backfill", daemon=True).start()


# Markers in yoink.md so the comments section can be replaced after the
# background fetch finishes. HTML comments are invisible in rendered markdown.
COMMENTS_START_MARK = "<!-- yoink:comments-start -->"
COMMENTS_END_MARK = "<!-- yoink:comments-end -->"
CI_START_MARK = "<!-- yoink:comment-intelligence-start -->"
CI_END_MARK = "<!-- yoink:comment-intelligence-end -->"
HOOK_START_MARK = "<!-- HOOK_START -->"
HOOK_END_MARK = "<!-- HOOK_END -->"
HOOK_TYPES = {
    "curiosity_gap",
    "question",
    "contrarian",
    "story_open",
    "promise_list",
    "demo",
    "authority",
    "stakes",
    "other",
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_count(n) -> str:
    """13500 -> '13.5K', 1500000 -> '1.5M', 2_000_000_000 -> '2.0B'."""
    if n is None:
        return "—"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n < 0:
        return str(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# Subscribers use the same compact format. Aliased so callers can read clearly.
format_subscribers = format_count


def format_duration(seconds) -> str:
    """3725 -> '01:02:05', 245 -> '04:05'."""
    if seconds is None:
        return "—"
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    if seconds < 0:
        seconds = 0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_int(n) -> str:
    """29142 -> '29,142'. Used for views/likes/comments header fields."""
    if n is None:
        return "—"
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_likes(n) -> str:
    """Like counts are often hidden by YouTube and exposed as null by yt-dlp."""
    if n is None:
        return "not exposed by YouTube for this video"
    return _fmt_int(n)


def _fmt_iso_date(s) -> str:
    """yt-dlp returns upload_date as 'YYYYMMDD'. Convert to 'YYYY-MM-DD'."""
    if not s:
        return "—"
    s = str(s)
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


TOPICS_PATH = HERE / "topics.json"


def _load_topics() -> dict:
    """Read topics.json from project root. Returns a dict with a 'topics'
    list of {name, keywords} and a 'fallback' string. On any error (missing
    or malformed file) returns an empty topic list with a sane fallback so
    classification just degrades to 'Uncategorized'.
    """
    if not TOPICS_PATH.exists():
        log.warning("topics.json missing at %s — falling back to 'Uncategorized'",
                    TOPICS_PATH)
        return {"topics": [], "fallback": "Uncategorized"}
    try:
        return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("topics.json read failed: %s", e)
        return {"topics": [], "fallback": "Uncategorized"}


def _classify_topic(metadata: dict) -> str:
    """Pick the best topic name for this video by counting keyword
    substring matches across the title, description, tags, channel, and
    uploader. Topic with the most matches wins; ties go to the topic
    defined first in topics.json. Falls back when nothing matches.
    """
    haystack = " ".join([
        metadata.get("title") or "",
        metadata.get("description") or "",
        " ".join(metadata.get("tags") or []),
        metadata.get("channel") or "",
        metadata.get("uploader") or "",
    ]).lower()

    cfg = _load_topics()
    fallback = (cfg.get("fallback") or "Uncategorized").strip() or "Uncategorized"
    best_name = fallback
    best_score = 0

    for t in cfg.get("topics", []):
        name = (t.get("name") or "").strip()
        kws = t.get("keywords") or []
        if not name or not kws:
            continue
        score = sum(1 for kw in kws if kw and str(kw).lower() in haystack)
        if score > best_score:
            best_score = score
            best_name = name

    return best_name


# ---------------------------------------------------------------------------
# Metadata, thumbnail, channel context, comments
# ---------------------------------------------------------------------------
class PlaylistJobCancelled(Exception):
    """Raised inside a playlist worker when the user cancels the job."""


class ExtractionPhaseError(RuntimeError):
    """A user-actionable extraction failure with its pipeline phase attached."""

    def __init__(self, phase: str, message: str):
        super().__init__(message)
        self.phase = phase


def _raise_if_cancelled(cancel_event: threading.Event | None):
    if cancel_event is not None and cancel_event.is_set():
        raise PlaylistJobCancelled("playlist job cancelled")


def _terminate_process(proc: subprocess.Popen):
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


def _ytdlp_timeout_for(duration_seconds: float) -> int:
    """Download timeout budget for a video of `duration_seconds`.

    Floors at YTDLP_TIMEOUT_SEC (so short videos behave exactly as before),
    grows linearly with duration for long videos, and is hard-capped so a
    stuck download can never hold the extract lock indefinitely. A 2-hour
    (7200s) video gets max(1800, 3600) = 3600s; a 4-hour livestream VOD gets
    capped at YTDLP_TIMEOUT_HARD_CAP_SEC."""
    try:
        dur = max(0.0, float(duration_seconds or 0))
    except (TypeError, ValueError):
        dur = 0.0
    scaled = int(dur * YTDLP_TIMEOUT_PER_VIDEO_SEC)
    return max(YTDLP_TIMEOUT_SEC, min(scaled, YTDLP_TIMEOUT_HARD_CAP_SEC))


def _ffmpeg_timeout_for(duration_seconds: float) -> int:
    """Screenshot-extraction timeout budget, scaled like the download one."""
    try:
        dur = max(0.0, float(duration_seconds or 0))
    except (TypeError, ValueError):
        dur = 0.0
    scaled = int(dur * FFMPEG_TIMEOUT_PER_VIDEO_SEC)
    return max(FFMPEG_TIMEOUT_SEC, min(scaled, YTDLP_TIMEOUT_HARD_CAP_SEC))


def _normalize_long_video_mode(value) -> str:
    _valid = "'full', 'chunked', or 'lite'"
    if value is None or (isinstance(value, str) and not value.strip()):
        return LONG_VIDEO_MODE_FULL
    if not isinstance(value, str):
        raise ValueError(f"long_video_mode must be {_valid}")
    mode = value.strip().lower()
    if mode not in LONG_VIDEO_MODES:
        raise ValueError(f"long_video_mode must be {_valid}")
    return mode


def _long_video_chunks(duration_seconds: float) -> list[dict]:
    """Representative media windows for chunked extraction.

    Sources up to the one-hour budget are partitioned contiguously. Longer
    sources are sampled evenly from the opening through the ending so the
    heavy media work stays bounded while the subtitle download remains full.
    """
    try:
        duration = max(0, int(float(duration_seconds or 0)))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        return []

    count = min(
        LONG_VIDEO_MAX_CHUNKS,
        max(1, int((min(duration, LONG_VIDEO_CHUNK_BUDGET_SECONDS)
                    + LONG_VIDEO_CHUNK_SECONDS - 1)
                   // LONG_VIDEO_CHUNK_SECONDS)),
    )
    if duration <= LONG_VIDEO_CHUNK_BUDGET_SECONDS:
        starts = [i * LONG_VIDEO_CHUNK_SECONDS for i in range(count)]
    elif count == 1:
        starts = [0]
    else:
        last_start = max(0, duration - LONG_VIDEO_CHUNK_SECONDS)
        starts = [
            round(i * last_start / (count - 1))
            for i in range(count)
        ]

    chunks = []
    for i, start in enumerate(starts, 1):
        end = min(duration, start + LONG_VIDEO_CHUNK_SECONDS)
        chunks.append({
            "index": i,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": max(0, end - start),
        })
    return chunks


def _chunk_section_spec(chunk: dict) -> str:
    return (
        f"*{fmt_time(chunk['start_seconds'])}-"
        f"{fmt_time(chunk['end_seconds'])}"
    )


def _estimated_screenshot_count(durations: list[float], interval: int) -> int:
    step = max(1, int(interval))
    return sum(
        int((max(0.0, float(duration or 0)) + step - 1) // step)
        for duration in durations
    )


def _failure_phase(e: BaseException, fallback: str | None = None) -> str | None:
    phase = getattr(e, "phase", None)
    return phase if isinstance(phase, str) and phase else fallback


def _run_subprocess(cmd: list[str], *, cancel_event: threading.Event | None = None,
                    timeout: int | float | None = None, check: bool = True,
                    stdout=None, stderr=None, text: bool = False,
                    encoding: str | None = None,
                    errors: str | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess with optional cooperative cancellation.

    v1 callers pass no cancel_event and see normal subprocess behavior. v2
    playlist jobs pass a per-job Event so `/jobs/<id>/cancel` can terminate
    the active yt-dlp/ffmpeg process instead of waiting for a long timeout.
    """
    _raise_if_cancelled(cancel_event)
    proc = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        text=text,
        encoding=encoding,
        errors=errors,
        **SUBPROCESS_KW,
    )
    started = time.monotonic()
    while True:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process(proc)
            raise PlaylistJobCancelled("playlist job cancelled")
        try:
            out, err = proc.communicate(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if timeout is not None and (time.monotonic() - started) >= timeout:
                _terminate_process(proc)
                raise subprocess.TimeoutExpired(cmd, timeout)

    cp = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    if check and proc.returncode:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=out, stderr=err
        )
    return cp


_RATE_LIMIT_PATTERNS = (
    "http error 429",
    "rate limit",
    "rate-limit",
    "too many requests",
    "sign in to confirm you're not a bot",
    "confirm you're not a bot",
    "captcha",
)


def _error_text(e: BaseException) -> str:
    if isinstance(e, subprocess.CalledProcessError):
        stderr = (e.stderr.decode("utf-8", errors="ignore")
                  if isinstance(e.stderr, bytes) else (e.stderr or ""))
        stdout = (e.output.decode("utf-8", errors="ignore")
                  if isinstance(e.output, bytes) else (e.output or ""))
        return f"{stderr}\n{stdout}"
    return str(e)


def _is_rate_limit_error(e: BaseException) -> bool:
    text = _error_text(e).lower()
    return any(pat in text for pat in _RATE_LIMIT_PATTERNS)


def _sleep_with_cancel(seconds: float, cancel_event: threading.Event | None) -> None:
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while True:
        _raise_if_cancelled(cancel_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(1.0, remaining))


def _extract_generic_transcript(metadata: dict) -> list[dict]:
    """v3.1 universal extract: pull a flat transcript-like list out of
    yt-dlp's metadata dict for a generic URL. yt-dlp returns
    ``subtitles`` (uploader-provided) and ``automatic_captions`` (ASR)
    as dicts keyed by language. For the slim /extract/any sidecar we
    prefer uploader-provided; falling back to ASR. Returns [] when no
    captions are exposed -- the slim path is `transcript + thumbnail
    only`, and `+ thumbnail only` is acceptable per the prompt."""
    subs = metadata.get("subtitles") or {}
    auto = metadata.get("automatic_captions") or {}
    # Prefer English if present, then any uploader sub, then any auto.
    def _pick(d):
        if not isinstance(d, dict):
            return None
        for k in ("en", "en-US", "en-GB"):
            if k in d:
                return d[k]
        for v in d.values():
            if isinstance(v, list) and v:
                return v
        return None
    chosen = _pick(subs) or _pick(auto)
    if not chosen:
        return []
    # Find a JSON3 / VTT URL in the formats list; we don't fetch it
    # here (that'd be a separate outbound) -- instead we just note the
    # captions are available so the downstream Codex UI can offer a
    # button. The slim path keeps yoinks fast.
    return [
        {"language_track": (c.get("name") or c.get("ext") or "unknown"),
         "ext": c.get("ext"),
         "url": c.get("url")}
        for c in chosen[:5]
        if isinstance(c, dict)
    ]


def _fetch_metadata(url: str, *,
                    cancel_event: threading.Event | None = None) -> dict:
    """Single yt-dlp call that returns the full metadata blob without
    downloading the video. Used to derive the folder slug, fill the corpus
    header, and seed the thumbnail URL.
    """
    cp = _run_subprocess(
        [*YTDLP_CMD, "--dump-single-json", "--no-download", url],
        cancel_event=cancel_event,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=COMMENTS_TIMEOUT_SEC,
    )
    return json.loads(cp.stdout)


def _download_thumbnail(metadata: dict, output_folder: Path, *,
                        cancel_event: threading.Event | None = None) -> Path | None:
    """Download highest-resolution thumbnail to <folder>/thumbnail.jpg.
    Always re-encodes through ffmpeg so the output is jpg even if YouTube
    served webp/png. Returns the jpg path on success, None on failure.
    """
    thumbs = metadata.get("thumbnails") or []
    candidates = [t for t in thumbs if t.get("url")]
    if candidates:
        candidates.sort(
            key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
            reverse=True,
        )
        url = candidates[0]["url"]
    else:
        url = metadata.get("thumbnail")
    if not url:
        return None

    raw_path = output_folder / "thumbnail.raw"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(raw_path, "wb") as f:
            f.write(resp.read())
    except Exception as e:
        log.warning("thumbnail download failed: %s", e)
        return None

    jpg_path = output_folder / "thumbnail.jpg"
    try:
        _run_subprocess(
            ["ffmpeg", "-loglevel", "error", "-y",
             "-i", str(raw_path), str(jpg_path)],
            cancel_event=cancel_event,
            check=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
        log.warning("ffmpeg thumbnail convert failed: %s", stderr)
        return None
    finally:
        raw_path.unlink(missing_ok=True)

    return jpg_path if jpg_path.exists() else None


def _fetch_channel_context(channel_url: str) -> dict:
    """Best-effort fetch of channel description + last 5 video stubs.
    Returns {'description': str, 'recent_videos': [{title, view_count,
    upload_date}, ...]}. Empty dict-shape on failure.
    """
    empty = {"description": "", "recent_videos": []}
    if not channel_url:
        return empty

    # Prefer the /videos tab so we get videos (not playlists/shorts/featured).
    target = channel_url.rstrip("/")
    if not target.endswith("/videos"):
        target = target + "/videos"

    try:
        raw = subprocess.check_output(
            [*YTDLP_CMD, "--dump-single-json", "--flat-playlist",
             "--playlist-end", "5", target],
            text=True, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
            **SUBPROCESS_KW,
        )
    except Exception as e:
        log.warning("channel context fetch failed: %s", e)
        return empty

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("channel context parse failed: %s", e)
        return empty

    description = (data.get("description") or "").strip()
    entries = data.get("entries") or []
    recent = []
    for e in entries[:5]:
        if not isinstance(e, dict):
            continue
        recent.append({
            "title": e.get("title") or "",
            "view_count": e.get("view_count"),
            "upload_date": e.get("upload_date"),
        })
    return {"description": description, "recent_videos": recent}


def _render_comments(comments: list[dict]) -> str:
    """Render top comments as markdown. Each: bold author + meta, then
    blockquoted body. Preserves line breaks within a comment.
    """
    out = []
    for c in comments:
        author = (c.get("author") or "Anonymous").strip() or "Anonymous"
        text = (c.get("text") or "").strip()
        likes = c.get("like_count") or 0
        time_text = (c.get("time_text") or "").strip()
        meta = f"{format_count(likes)} likes"
        if time_text:
            meta += f", {time_text}"
        out.append(f"**{author}** ({meta})")
        for ln in (text.splitlines() or [""]):
            out.append(f"> {ln}" if ln else ">")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _replace_comments_section(yoink_path: Path, body: str) -> None:
    """Atomically rewrite the COMMENTS_START..COMMENTS_END block in yoink.md.
    Safe to call from a background thread.
    """
    with _corpus_update_lock:
        try:
            text = yoink_path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("could not read yoink.md to update comments: %s", e)
            return

        pattern = re.compile(
            re.escape(COMMENTS_START_MARK) + r".*?" + re.escape(COMMENTS_END_MARK),
            re.DOTALL,
        )
        replacement = f"{COMMENTS_START_MARK}\n{body.rstrip()}\n{COMMENTS_END_MARK}"
        new_text, n = pattern.subn(replacement, text, count=1)
        if n == 0:
            log.warning("comments markers not found in yoink.md; skipping update")
            return

        tmp = yoink_path.with_suffix(".md.tmp")
        try:
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(yoink_path)
        except OSError as e:
            log.warning("could not write yoink.md to update comments: %s", e)


def _shape_comment_for_sidecar(c: dict) -> dict:
    """Pick the fields a downstream consumer actually wants. yt-dlp's raw
    comment objects carry a lot of internal cruft (parent ids, author
    channel ids, thumbnails) that bloats the sidecar without value."""
    return {
        "author": c.get("author"),
        "text": c.get("text"),
        "like_count": c.get("like_count") or 0,
        "time_text": c.get("_time_text") or c.get("time_text"),
        "is_pinned": bool(c.get("is_pinned")),
        "is_favorited": bool(c.get("is_favorited")),
        "reply_count": c.get("reply_count") or 0,
    }


def _update_sidecar_comments(output_folder: Path, comments: list | None,
                              status: str) -> None:
    """Patch the JSON sidecar in place once the comments worker resolves.
    Best-effort: a missing or unwritable sidecar is logged and ignored
    (the markdown is still the user-facing artifact)."""
    sidecar_path = output_folder / f"{output_folder.name}.json"
    with _sidecar_update_lock:
        if not sidecar_path.exists():
            return
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("sidecar comments update: read failed (%s)", e)
            return
        data["comments"] = comments
        data["comments_status"] = status
        tmp = sidecar_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(sidecar_path)
        except OSError as e:
            log.warning("sidecar comments update: write failed (%s)", e)


def _extract_json_object(text: str, *, label: str = "AI response") -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AnthropicAPIError(None, f"{label} returned no JSON object")
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise AnthropicAPIError(None, f"{label} returned invalid JSON: {e}") from None
    if not isinstance(parsed, dict):
        raise AnthropicAPIError(None, f"{label} returned an unexpected shape")
    return parsed


def _clean_text(value, *, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _clean_for_prompt(value, *, limit: int = 500) -> str:
    """Tighter version of _clean_text used when the cleaned string is
    interpolated into an LLM prompt (Sprint 19.6 / Fix 3 / audit M2).
    Strips characters that could break out of quoted prompt context --
    double-quotes, backticks, and line breaks the model could mistake for
    an instruction boundary -- and the cleaned-then-collapsed string is
    safe to drop straight into a `"{value}"`-style template."""
    cleaned = _clean_text(value, limit=limit)
    if not cleaned:
        return ""
    return (cleaned
            .replace('"', "'")
            .replace("`", "'")
            .replace("\n", " ")
            .replace("\r", " "))


def _as_int(value, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_comment_analysis(data: dict) -> dict:
    themes = []
    for item in (data.get("top_themes") or [])[:5]:
        if not isinstance(item, dict):
            continue
        quotes = [
            _clean_text(q, limit=280)
            for q in (item.get("quotes") or item.get("representative_quotes") or [])[:2]
            if _clean_text(q)
        ]
        themes.append({
            "label": _clean_text(item.get("label"), limit=80) or "Theme",
            "description": _clean_text(item.get("description"), limit=500),
            "count": _as_int(item.get("count"), 0),
            "quotes": quotes,
        })

    products = []
    for item in (data.get("mentioned_products_tools") or data.get("products_tools") or [])[:20]:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("label"), limit=100)
        if not name:
            continue
        products.append({
            "name": name,
            "frequency": _as_int(item.get("frequency") or item.get("count"), 1),
        })

    disagreements = []
    for item in (data.get("notable_disagreements") or [])[:3]:
        if not isinstance(item, dict):
            continue
        samples = [
            _clean_text(q, limit=280)
            for q in (item.get("sample_comments") or item.get("quotes") or [])[:2]
            if _clean_text(q)
        ]
        disagreements.append({
            "description": _clean_text(item.get("description"), limit=500),
            "sample_comments": samples,
        })

    return {
        "model": ANTHROPIC_MODEL,
        "top_themes": themes,
        "mentioned_products_tools": products,
        "notable_disagreements": disagreements,
    }


def analyze_comments(comments: list[dict], *, api_key: str | None = None) -> dict:
    """Vendor-neutral internal interface for comment analysis.

    Future MCP can wrap this function directly as `analyze_comments`; the
    Anthropic-specific plumbing is intentionally hidden behind it.
    """
    key = (api_key or _anthropic_key_available() or "").strip()
    if not key:
        raise AnthropicAPIError(None, "Anthropic API key not configured")

    shaped = []
    for c in comments[:50]:
        text = _clean_text(c.get("text"), limit=1200)
        if not text:
            continue
        shaped.append({
            "author": _clean_text(c.get("author"), limit=80),
            "text": text,
            "like_count": _as_int(c.get("like_count"), 0),
        })
    if len(shaped) < 5:
        raise AnthropicAPIError(None, "not enough comments to analyze")

    system = (
        "You analyze YouTube comments for a creator-operator. Return valid JSON "
        "only. Do not include markdown. Cluster comments by meaning, identify "
        "mentioned products/tools, and describe substantive disagreements."
    )
    user = (
        "Analyze these top YouTube comments. Return this exact JSON shape:\n"
        "{\n"
        '  "top_themes": [{"label": string, "description": string, "count": number, "quotes": [string]}],\n'
        '  "mentioned_products_tools": [{"name": string, "frequency": number}],\n'
        '  "notable_disagreements": [{"description": string, "sample_comments": [string]}]\n'
        "}\n\n"
        "Rules: 3-5 top_themes, 1-2 quotes per theme, up to 20 products/tools, "
        "and 1-3 disagreements. If a category has no signal, return an empty "
        "array for that category.\n\n"
        f"Comments JSON:\n{json.dumps(shaped, ensure_ascii=False)}"
    )
    try:
        resp = _anthropic_messages(key, system=system, user=user, max_tokens=1200)
        return _normalize_comment_analysis(
            _extract_json_object(_anthropic_text(resp), label="Comment Intelligence")
        )
    except AnthropicAPIError as e:
        if e.status == 401:
            _mark_anthropic_key_invalid()
        raise


def _first_words(text: str, limit: int) -> str:
    words = re.split(r"\s+", (text or "").strip())
    words = [w for w in words if w]
    return " ".join(words[:limit])


def _hook_display_name(hook_type: str) -> str:
    return (hook_type or "other").replace("_", " ").title()


def _normalize_hook_analysis(data: dict) -> dict:
    hook_type = _clean_text(data.get("hook_type"), limit=80).lower()
    if hook_type not in HOOK_TYPES:
        hook_type = "other"
    return {
        "model": ANTHROPIC_MODEL,
        "hook_type": hook_type,
        "hook_explanation": _clean_text(data.get("hook_explanation"), limit=600),
    }


# The nine hook-type categories with one-line definitions, used as the
# system-prompt classification guide (Sprint 17 / A3). The names match
# HOOK_TYPES exactly.
_HOOK_TYPE_GUIDE = (
    "Hook type categories (pick exactly one):\n"
    "- curiosity_gap: teases an answer or outcome without revealing it, "
    "opening an information gap the viewer wants closed.\n"
    "- question: opens by directly asking the viewer a question.\n"
    "- contrarian: leads with a claim that challenges a common belief or "
    "consensus.\n"
    "- story_open: opens with a personal anecdote or a narrative scene.\n"
    "- promise_list: promises a specific list or count of takeaways, e.g. "
    "'5 ways to ...'.\n"
    "- demo: opens by showing the thing in action -- a visual or live "
    "demonstration.\n"
    "- authority: opens by establishing credentials, results, or proof of "
    "expertise.\n"
    "- stakes: opens by emphasizing what the viewer stands to gain or lose.\n"
    "- other: none of the above, or no identifiable hook pattern."
)


def _hook_fewshot_block(similar: list[dict]) -> str:
    """Format past user corrections as few-shot calibration anchors for the
    hook-type system prompt (A3). Empty string when there are none.

    Sprint 19.6 / Fix 3 / audit M2: every interpolated field is passed
    through _clean_for_prompt, which strips quotes / backticks / line
    breaks so an attacker-crafted title / channel / user_reason can't
    break out of the f-string quote context. Today single-user, so the
    attack is self-injection -- but the moment BACKLOG v2.5 publishes the
    corrections dataset, a malicious entry would otherwise rewrite every
    downstream classifier prompt that consumed it as a few-shot."""
    if not similar:
        return ""
    lines = ["", "",
             "Past corrections from this user (use as calibration anchors):"]
    for c in similar:
        title = _clean_for_prompt(c.get("title"), limit=160) or "(untitled)"
        channel = _clean_for_prompt(c.get("channel"), limit=120) or "(unknown channel)"
        original = _clean_for_prompt(c.get("original_hook_type"), limit=40)
        corrected = _clean_for_prompt(c.get("corrected_hook_type"), limit=40)
        line = (f'- Video "{title}" on channel "{channel}": classifier said '
                f'"{original}", user corrected to "{corrected}".')
        reason = _clean_for_prompt(c.get("user_reason"), limit=300)
        if reason:
            line += f' Reason: "{reason}"'
        lines.append(line)
    return "\n".join(lines)


# Appended to the hook-type system prompt -- elicits an explicit 1-5
# self-confidence score on a line after the JSON (Sprint 17 / A3).
_HOOK_CONFIDENCE_GUIDE = (
    "\n\nAfter the JSON, on a separate line, output your confidence as "
    "exactly `Confidence: N`, where N is an integer from 1 to 5:\n"
    "- 5 = very confident, hook clearly fits exactly one category\n"
    "- 4 = confident, mild ambiguity\n"
    "- 3 = moderate, hook could fit one of two categories\n"
    "- 2 = uncertain, hook fits 'other' or is borderline\n"
    "- 1 = guessing, no clear pattern"
)


def _parse_hook_confidence(text: str) -> int | None:
    """Pull the 1-5 confidence integer from a hook-type model response.
    Returns None when the model emitted no parseable score."""
    text = text or ""
    m = re.search(r"confidence\s*[:=]\s*([1-5])\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Looser fallback: "confidence" followed shortly by a 1-5 digit.
    m = re.search(r"confidence\D{0,12}([1-5])\b", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def analyze_hook_type(context: dict, *, api_key: str | None = None) -> dict:
    """Classify one video's opening style.

    A3 (Sprint 17): self-calibrating. Past user corrections relevant to the
    video (same channel, then topic, then recent) are fetched from the
    library index and injected as few-shot anchors. Kept vendor-neutral so
    the MCP tool surface stays decoupled from Anthropic.
    """
    key = (api_key or _anthropic_key_for_feature("hook_type_enabled") or "").strip()
    if not key:
        raise AnthropicAPIError(None, "Anthropic API key not configured")

    title = _clean_text(context.get("title"), limit=220)
    description = _clean_text(context.get("description"), limit=1200)
    if not title and not description:
        raise AnthropicAPIError(None, "no title or description to classify")

    payload = {
        "title": title,
        "channel": _clean_text(context.get("channel"), limit=160),
        "description": description,
        "transcript_first_250_words": _first_words(
            str(context.get("transcript") or ""), 250
        ),
        "top_comment": _clean_text(context.get("top_comment"), limit=600),
    }

    # A3: past corrections relevant to this video become few-shot anchors.
    # Best-effort -- an index failure must never fail the classification.
    similar: list[dict] = []
    video_id = (context.get("video_id") or "").strip()
    if video_id:
        try:
            similar = _get_index().similar_corrections(video_id, limit=8)
        except Exception as e:
            log.warning("hook similar-corrections fetch failed: %s", e)
            similar = []

    system = (
        "You classify YouTube video hook styles for a creator-operator.\n\n"
        + _HOOK_TYPE_GUIDE
        + _hook_fewshot_block(similar)
        + "\n\nReturn valid JSON only, of exactly this shape:\n"
        '{"hook_type": string, "hook_explanation": string}\n'
        "hook_type must be exactly one of the categories above. "
        "hook_explanation is one or two sentences on what makes the opening "
        "fit that type."
        + _HOOK_CONFIDENCE_GUIDE
    )
    user = (
        "Classify this video's hook style.\n\n"
        f"Video context JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        resp = _anthropic_messages(key, system=system, user=user, max_tokens=400)
        text = _anthropic_text(resp)
        analysis = _normalize_hook_analysis(
            _extract_json_object(text, label="Hook Type")
        )
    except AnthropicAPIError as e:
        if e.status == 401:
            _mark_anthropic_key_invalid()
        raise
    # Confidence rides on a separate line after the JSON; parse it off the
    # raw text. None when the model didn't emit a parseable score.
    analysis["confidence"] = _parse_hook_confidence(text)
    analysis["similar_corrections_used"] = len(similar)
    return analysis


def _render_hook_analysis(analysis: dict) -> str:
    return "\n".join([
        "## Hook Analysis",
        HOOK_START_MARK,
        f"**Hook Type:** {_hook_display_name(analysis.get('hook_type') or 'other')}",
        f"**Analysis:** {analysis.get('hook_explanation') or 'No explanation returned.'}",
        HOOK_END_MARK,
    ])


def _render_hook_failure(reason: str) -> str:
    return "\n".join([
        "## Hook Analysis",
        HOOK_START_MARK,
        f"Hook Type: analysis failed - {reason}",
        HOOK_END_MARK,
    ])


def _replace_hook_analysis_section(yoink_path: Path, body: str) -> None:
    with _corpus_update_lock:
        try:
            text = yoink_path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("could not read corpus to update Hook Type: %s", e)
            return

        pattern = re.compile(
            r"(?:^|\n)## Hook Analysis\s*\n"
            + re.escape(HOOK_START_MARK)
            + r".*?"
            + re.escape(HOOK_END_MARK)
            + r"\n?",
            re.DOTALL,
        )
        if pattern.search(text):
            new_text = pattern.sub("\n" + body.rstrip() + "\n\n", text, count=1)
        else:
            # Insert immediately after the top metadata block, before the first
            # horizontal rule that separates metadata from the rest of the corpus.
            marker = "\n---\n"
            if marker in text:
                new_text = text.replace(marker, "\n" + body.rstrip() + "\n\n---\n", 1)
            else:
                new_text = text.rstrip() + "\n\n" + body.rstrip() + "\n"

        tmp = yoink_path.with_suffix(".md.tmp")
        try:
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(yoink_path)
        except OSError as e:
            log.warning("could not write Hook Type section: %s", e)


def _update_sidecar_hook_type(output_folder: Path, *, status: str,
                              hook_type: str | None = None,
                              hook_explanation: str | None = None,
                              confidence: int | None = None,
                              error: str | None = None) -> None:
    sidecar_path = output_folder / f"{output_folder.name}.json"
    with _sidecar_update_lock:
        if not sidecar_path.exists():
            return
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("sidecar Hook Type update: read failed (%s)", e)
            return
        data["hook_type_status"] = status
        data["hook_type"] = hook_type
        data["hook_explanation"] = hook_explanation
        data["hook_type_confidence"] = confidence
        data["hook_type_error"] = error
        data["hook_type_updated_at"] = _now_iso()
        tmp = sidecar_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(sidecar_path)
        except OSError as e:
            log.warning("sidecar Hook Type update: write failed (%s)", e)


def _record_correction_in_sidecar(sidecar_path: Path, original: str,
                                  corrected: str) -> None:
    """Reflect a hook-type correction in the per-video sidecar (Sprint 17):
    promote hook_type to the corrected value and append an entry to the
    append-only hook_type_corrections log. Best-effort, serialised through
    _sidecar_update_lock."""
    with _sidecar_update_lock:
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("sidecar correction update: read failed (%s)", e)
            return
        data["hook_type"] = corrected
        log_entries = data.get("hook_type_corrections")
        if not isinstance(log_entries, list):
            log_entries = []
        log_entries.append({
            "original": original,
            "corrected": corrected,
            "corrected_at": _now_iso(),
        })
        data["hook_type_corrections"] = log_entries
        tmp = sidecar_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(sidecar_path)
        except OSError as e:
            log.warning("sidecar correction update: write failed (%s)", e)


def _append_hook_taxonomy(context: dict, analysis: dict) -> None:
    """Record a Hook Type classification in the library index, deduplicated
    by video_id (INSERT OR REPLACE). Best-effort -- a failure here must not
    fail the classification it accompanies."""
    video_id = (context.get("video_id") or "").strip()
    if not video_id:
        return
    try:
        _get_index().upsert_taxonomy({
            "video_id": video_id,
            "hook_type": analysis.get("hook_type"),
            "hook_explanation": analysis.get("hook_explanation"),
            "channel": context.get("channel") or None,
            "title": context.get("title") or None,
            "classified_at": _now_iso(),
            "confidence": analysis.get("confidence"),
        })
    except Exception as e:
        log.warning("hook taxonomy index write failed: %s", e)


def _migrate_taxonomy_json_to_index() -> None:
    """One-time: import a pre-Sprint-15 taxonomy.json into the index
    `taxonomy` table, then rename it to taxonomy.json.migrated. A no-op once
    the file is gone. On any error the source is left intact and the helper
    still boots."""
    if not TAXONOMY_PATH.exists():
        return
    try:
        raw = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else []
        idx = _get_index()
        imported = 0
        for row in rows:
            if isinstance(row, dict) and (row.get("video_id") or "").strip():
                idx.upsert_taxonomy(row)
                imported += 1
        TAXONOMY_PATH.replace(
            TAXONOMY_PATH.with_name(TAXONOMY_PATH.name + ".migrated"))
        log.info("Migrated %d taxonomy record(s) into the index", imported)
    except Exception:
        log.exception("taxonomy.json migration failed; leaving the file in place")


# v3.2.3: curated default style anchors bundled with the install. Same
# bundle-trap discipline as the v3.2.1 module fix -- this file MUST be listed
# in uoink.iss [Files] and staged by build.ps1, and verify_install.ps1 asserts
# it is present after install.
DEFAULT_STYLE_ANCHORS_PATH = HERE / "defaults" / "style_anchors.json"


def _seed_default_style_anchors() -> None:
    """Seed the curated default style anchors from the bundled
    defaults/style_anchors.json. Runs on every boot and inserts any default
    that is missing (idempotent per anchor), so upgrading users who already
    have custom anchors still get the defaults. No-op when the file is missing.
    Seeded anchors are inactive (active=0, is_default=1), so they don't count
    against the active cap and never override a user's curation."""
    try:
        if not DEFAULT_STYLE_ANCHORS_PATH.exists():
            log.info("default style anchors: %s not bundled; skipping seed",
                     DEFAULT_STYLE_ANCHORS_PATH)
            return
        data = json.loads(
            DEFAULT_STYLE_ANCHORS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            log.warning("default style anchors: JSON is not a list; skipping")
            return
        seeded = writing_studio.seed_default_anchors(_get_index(), data)
        if seeded:
            log.info("default style anchors: seeded %d on first run", seeded)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("default style anchors seed failed: %s", e)
    except Exception:
        log.exception("default style anchors seed: unexpected error")


def _query_taxonomy(*, channel: str | None = None,
                    hook_type: str | None = None,
                    limit: int = 50) -> list[dict]:
    """Hook taxonomy rows from the library index, newest classification
    first, with optional channel / hook_type filters. Return shape matches
    the pre-index file-backed version (video_id, hook_type,
    hook_explanation, channel, title, classified_at)."""
    hook_filter = (hook_type or "").strip().lower() or None
    channel_filter = (channel or "").strip() or None
    try:
        return _get_index().query_taxonomy(
            channel=channel_filter, hook_type=hook_filter, limit=limit,
        )
    except Exception as e:
        log.warning("taxonomy query failed: %s", e)
        return []


def _hook_type_context(metadata: dict, entries: list, top_comment: str | None = None) -> dict:
    transcript = " ".join(t for _s, _e, t in entries)
    return {
        "video_id": metadata.get("id") or "",
        "title": metadata.get("title") or "",
        "description": metadata.get("description") or "",
        "channel": metadata.get("channel") or metadata.get("uploader") or "",
        "transcript": transcript,
        "top_comment": top_comment or "",
    }


def _should_start_hook_type(metadata: dict) -> bool:
    if not _anthropic_key_for_feature("hook_type_enabled"):
        return False
    return bool((metadata.get("title") or "").strip()
                or (metadata.get("description") or "").strip())


def _hook_type_worker(output_folder: Path, yoink_path: Path,
                      context: dict) -> None:
    try:
        analysis = analyze_hook_type(context)
        _replace_hook_analysis_section(yoink_path, _render_hook_analysis(analysis))
        _update_sidecar_hook_type(
            output_folder,
            status="completed",
            hook_type=analysis.get("hook_type"),
            hook_explanation=analysis.get("hook_explanation"),
            confidence=analysis.get("confidence"),
        )
        _append_hook_taxonomy(context, analysis)
        log.info("Hook Type appended to %s", yoink_path)
    except AnthropicAPIError as e:
        reason = _short_reason(e.reason)
        if e.status == 401:
            _mark_anthropic_key_invalid()
            log.warning("Hook Type skipped: Anthropic API key invalid")
        else:
            log.warning("Hook Type failed: %s", reason)
        _replace_hook_analysis_section(yoink_path, _render_hook_failure(reason))
        _update_sidecar_hook_type(
            output_folder,
            status="failed",
            error=reason,
        )
    except Exception as e:
        reason = _short_reason(str(e))
        log.warning("Hook Type crashed: %s", reason)
        _replace_hook_analysis_section(yoink_path, _render_hook_failure(reason))
        _update_sidecar_hook_type(
            output_folder,
            status="failed",
            error=reason,
        )


def _start_hook_type_thread(output_folder: Path, yoink_path: Path,
                            metadata: dict, entries: list,
                            top_comment: str | None = None) -> threading.Thread | None:
    if not _should_start_hook_type(metadata):
        return None
    t = threading.Thread(
        target=_hook_type_worker,
        args=(output_folder, yoink_path,
              _hook_type_context(metadata, entries, top_comment)),
        name=f"hook-type-{output_folder.name}",
        daemon=True,
    )
    t.start()
    return t


def _render_comment_intelligence(analysis: dict) -> str:
    out = ["## Comment Intelligence", ""]

    out.append("### Top Themes")
    themes = analysis.get("top_themes") or []
    if not themes:
        out.append("- None found.")
    for t in themes:
        count = t.get("count") or 0
        out.append(
            f"- **{t.get('label') or 'Theme'}** ({count} comments): "
            f"{t.get('description') or 'No description.'}"
        )
        for q in t.get("quotes") or []:
            out.append(f"  - \"{q}\"")
    out.append("")

    out.append("### Mentioned Products/Tools")
    products = analysis.get("mentioned_products_tools") or []
    if not products:
        out.append("- None found.")
    for p in products:
        out.append(f"- **{p.get('name')}** ({p.get('frequency') or 1})")
    out.append("")

    out.append("### Notable Disagreements")
    disagreements = analysis.get("notable_disagreements") or []
    if not disagreements:
        out.append("- None found.")
    for d in disagreements:
        out.append(f"- {d.get('description') or 'Disagreement noted.'}")
        for q in d.get("sample_comments") or []:
            out.append(f"  - \"{q}\"")
    return "\n".join(out).rstrip()


def _replace_comment_intelligence_section(yoink_path: Path, body: str) -> None:
    block = f"{CI_START_MARK}\n{body.rstrip()}\n{CI_END_MARK}"
    with _corpus_update_lock:
        try:
            text = yoink_path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("could not read corpus to update Comment Intelligence: %s", e)
            return

        pattern = re.compile(
            re.escape(CI_START_MARK) + r".*?" + re.escape(CI_END_MARK),
            re.DOTALL,
        )
        if pattern.search(text):
            new_text = pattern.sub(block, text, count=1)
        elif COMMENTS_END_MARK in text:
            new_text = text.replace(COMMENTS_END_MARK, COMMENTS_END_MARK + "\n\n" + block, 1)
        else:
            new_text = text.rstrip() + "\n\n" + block + "\n"

        tmp = yoink_path.with_suffix(".md.tmp")
        try:
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(yoink_path)
        except OSError as e:
            log.warning("could not write Comment Intelligence section: %s", e)


def _update_sidecar_comment_intelligence(output_folder: Path, *,
                                         status: str,
                                         analysis: dict | None = None,
                                         error: str | None = None) -> None:
    sidecar_path = output_folder / f"{output_folder.name}.json"
    with _sidecar_update_lock:
        if not sidecar_path.exists():
            return
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("sidecar CI update: read failed (%s)", e)
            return
        data["comment_intelligence_status"] = status
        data["comment_intelligence"] = analysis
        data["comment_intelligence_error"] = error
        data["comment_intelligence_updated_at"] = _now_iso()
        tmp = sidecar_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(sidecar_path)
        except OSError as e:
            log.warning("sidecar CI update: write failed (%s)", e)


def _comment_intelligence_worker(output_folder: Path, yoink_path: Path,
                                 comments: list[dict]) -> None:
    if len(comments) < 5:
        return
    try:
        analysis = analyze_comments(comments)
        _replace_comment_intelligence_section(
            yoink_path,
            _render_comment_intelligence(analysis),
        )
        _update_sidecar_comment_intelligence(
            output_folder,
            status="fetched",
            analysis=analysis,
        )
        log.info("Comment Intelligence appended to %s", yoink_path)
    except AnthropicAPIError as e:
        reason = _short_reason(e.reason)
        if e.status == 401:
            _mark_anthropic_key_invalid()
            log.warning("Comment Intelligence skipped: Anthropic API key invalid")
        else:
            log.warning("Comment Intelligence failed: %s", reason)
        body = "## Comment Intelligence\n\n" + (
            f"Comment Intelligence: analysis failed - {reason}"
        )
        _replace_comment_intelligence_section(yoink_path, body)
        _update_sidecar_comment_intelligence(
            output_folder,
            status="failed",
            analysis=None,
            error=reason,
        )
    except Exception as e:
        reason = _short_reason(str(e))
        log.warning("Comment Intelligence crashed: %s", reason)
        body = f"## Comment Intelligence\n\nComment Intelligence: analysis failed - {reason}"
        _replace_comment_intelligence_section(yoink_path, body)
        _update_sidecar_comment_intelligence(
            output_folder,
            status="failed",
            analysis=None,
            error=reason,
        )


def _start_comment_intelligence_thread(output_folder: Path, yoink_path: Path,
                                       comments: list[dict]) -> threading.Thread | None:
    if len(comments) < 5 or not _anthropic_key_available():
        return None
    t = threading.Thread(
        target=_comment_intelligence_worker,
        args=(output_folder, yoink_path, comments[:50]),
        name=f"comment-intelligence-{output_folder.name}",
        daemon=True,
    )
    t.start()
    return t


# ===========================================================================
# Entity extraction (Sprint 16) -- A2 minimal.
# ===========================================================================
# Transcript words sent to the model, ~3000 tokens, capped for cost control.
_ENTITY_TRANSCRIPT_WORD_CAP = 2200


def _entity_transcript_text(sidecar: dict) -> str:
    """Flatten the sidecar transcript into timestamped lines for the entity
    extractor. Each chunk is prefixed with its start time in seconds so the
    model can attribute a real timestamp to every mention. Capped at
    _ENTITY_TRANSCRIPT_WORD_CAP words."""
    lines: list[str] = []
    for seg in sidecar.get("transcript") or []:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        ts = _as_float(seg.get("start"))
        lines.append(f"[{ts:.1f}] {text}" if ts is not None else text)
    return _first_words("\n".join(lines), _ENTITY_TRANSCRIPT_WORD_CAP)


def _update_sidecar_entity_extraction(output_folder: Path, *, status: str,
                                      error: str | None = None) -> None:
    """Patch the sidecar's entity_extraction_status / _error fields. Mirrors
    _update_sidecar_hook_type; serialised through _sidecar_update_lock so it
    cannot clobber a concurrent comments / hook / CI sidecar write."""
    sidecar_path = output_folder / f"{output_folder.name}.json"
    with _sidecar_update_lock:
        if not sidecar_path.exists():
            return
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("sidecar entity update: read failed (%s)", e)
            return
        data["entity_extraction_status"] = status
        data["entity_extraction_error"] = error
        data["entity_extraction_updated_at"] = _now_iso()
        tmp = sidecar_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(sidecar_path)
        except OSError as e:
            log.warning("sidecar entity update: write failed (%s)", e)


def extract_entities(transcript: str, *, title: str = "", channel: str = "",
                     api_key: str | None = None) -> list[dict]:
    """Vendor-neutral entity extraction over a video transcript.

    Returns a list of ``{name, type, mentions: [{timestamp, context}]}``
    dicts. Kept as a small Anthropic-free interface, mirroring
    analyze_comments / analyze_hook_type, so a future MCP surface can wrap
    it directly.
    """
    key = (api_key or _saved_anthropic_key() or "").strip()
    if not key:
        raise AnthropicAPIError(None, "Anthropic API key not configured")
    transcript = (transcript or "").strip()
    if not transcript:
        raise AnthropicAPIError(None, "no transcript to extract entities from")

    system = (
        "You extract named entities from a YouTube video transcript for a "
        "creator-operator's research library. Return valid JSON only, no "
        "markdown. Only include entities explicitly named in the transcript."
    )
    user = (
        "Extract the named entities from this video. Return this exact JSON "
        "shape:\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": string, "type": string, '
        '"mentions": [{"timestamp": number, "context": string}]}\n'
        "  ]\n"
        "}\n\n"
        "Allowed type values: person, tool, product, company, topic, other.\n"
        "Each transcript chunk is prefixed with its start time in seconds "
        "like [12.5]; use the nearest one for each mention's timestamp. "
        "context is a short quote (<=200 chars) of where the entity comes "
        "up. Merge repeated references to the same entity into one "
        "entities[] item with multiple mentions. Return an empty array if "
        "the transcript names no clear entities.\n\n"
        f"Title: {title}\nChannel: {channel}\n\nTranscript:\n{transcript}"
    )
    try:
        resp = _anthropic_messages(key, system=system, user=user, max_tokens=2500)
        data = _extract_json_object(_anthropic_text(resp), label="Entity extraction")
    except AnthropicAPIError as e:
        if e.status == 401:
            _mark_anthropic_key_invalid()
        raise
    entities = data.get("entities") if isinstance(data, dict) else None
    return [e for e in (entities or []) if isinstance(e, dict)]


def _extract_entities(output_folder: Path, video_id: str, sidecar: dict) -> None:
    """Entity extraction worker body (Sprint 16). Best-effort background
    thread: pulls named entities off the transcript via Claude Haiku and
    writes them into the library index. Never raises -- a failure just
    records entity_extraction_status="failed" on the sidecar, with no
    retry. Skipped silently when no Anthropic key is configured.

    Note: the brief sketched this as _extract_entities(video_id, corpus_md,
    sidecar). It takes output_folder instead of corpus_md -- the transcript
    is read from the structured sidecar (which carries per-chunk
    timestamps the markdown corpus would force a re-parse of), and the
    folder is needed to write the sidecar status the brief itself requires.
    """
    video_id = (video_id or "").strip()
    if not video_id:
        return
    transcript = _entity_transcript_text(sidecar)
    if not transcript:
        # No transcript (e.g. a video with no captions) -- nothing to do.
        _update_sidecar_entity_extraction(output_folder, status="skipped")
        return
    try:
        entities = extract_entities(
            transcript,
            title=_clean_text(sidecar.get("title"), limit=220),
            channel=_clean_text(sidecar.get("channel"), limit=160),
        )
        written = _get_index().record_entities(
            video_id, entities, source="transcript"
        )
        _update_sidecar_entity_extraction(output_folder, status="completed")
        log.info("entity extraction: %s -> %d entities, %d mentions",
                 output_folder.name, len(entities), written)
    except AnthropicAPIError as e:
        reason = _short_reason(e.reason)
        if e.status == 401:
            log.warning("entity extraction skipped: Anthropic API key invalid")
        else:
            log.warning("entity extraction failed: %s", reason)
        _update_sidecar_entity_extraction(
            output_folder, status="failed", error=reason
        )
    except Exception as e:
        reason = _short_reason(str(e))
        log.warning("entity extraction crashed: %s", reason)
        _update_sidecar_entity_extraction(
            output_folder, status="failed", error=reason
        )


def _start_entity_extraction_thread(output_folder: Path,
                                    video_id: str | None,
                                    sidecar: dict) -> threading.Thread | None:
    """Spawn the entity extraction worker. Returns None (skips silently) when
    no Anthropic key is configured or the video has no id -- mirrors the
    Hook Type / Comment Intelligence skip pattern."""
    if not _saved_anthropic_key() or not (video_id or "").strip():
        return None
    t = threading.Thread(
        target=_extract_entities,
        args=(output_folder, video_id, sidecar),
        name=f"entity-extraction-{output_folder.name}",
        daemon=True,
    )
    t.start()
    return t


def _comments_worker(url: str, output_folder: Path, yoink_path: Path,
                     metadata: dict | None = None, entries: list | None = None,
                     max_comments: int = 100, top_n: int = 50) -> None:
    """Background-thread body. Fetches comments via yt-dlp, rewrites the
    comments section of the corpus md AND patches the JSON sidecar with
    structured comment objects + a comments_status field. Never raises --
    failures leave the disabled/unavailable note + matching status.
    """
    shaped_comments: list[dict] = []

    def _start_hook_after_comments():
        if metadata is None or entries is None:
            return
        top_comment = shaped_comments[0].get("text") if shaped_comments else None
        _start_hook_type_thread(
            output_folder, yoink_path, metadata, entries, top_comment=top_comment
        )

    try:
        info_template = output_folder / "%(id)s_yoink_comments.%(ext)s"
        subprocess.run(
            [*YTDLP_CMD,
             "--write-info-json",
             "--write-comments",
             "--skip-download",
             "--extractor-args",
             f"youtube:max_comments={max_comments},all,all,all",
             "-o", str(info_template),
             url],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=COMMENTS_TIMEOUT_SEC,
            **SUBPROCESS_KW,
        )
        info_files = list(output_folder.glob("*_yoink_comments.info.json"))
        if not info_files:
            log.warning("comments info.json not found for %s", url)
            _replace_comments_section(yoink_path,
                "*Comments could not be retrieved.*")
            _update_sidecar_comments(output_folder, [], "unavailable")
            _start_hook_after_comments()
            return
        info = json.loads(info_files[0].read_text(encoding="utf-8"))
        raw_comments = info.get("comments") or []
        if not raw_comments:
            _replace_comments_section(yoink_path,
                "*Comments are disabled on this video.*")
            _update_sidecar_comments(output_folder, [], "disabled")
            _start_hook_after_comments()
            return
        ranked = sorted(
            raw_comments,
            key=lambda c: c.get("like_count") or 0,
            reverse=True,
        )[:top_n]
        shaped_comments = [_shape_comment_for_sidecar(c) for c in ranked]
        _replace_comments_section(yoink_path, _render_comments(ranked))
        _update_sidecar_comments(output_folder, shaped_comments, "fetched")
        _start_hook_after_comments()
        _start_comment_intelligence_thread(output_folder, yoink_path, shaped_comments)
        log.info("comments appended to %s (%d of %d)",
                 yoink_path, len(ranked), len(raw_comments))
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
        log.warning("comments yt-dlp failed: %s", stderr.splitlines()[-1] if stderr else e.returncode)
        _replace_comments_section(yoink_path,
            "*Comments are disabled on this video.*")
        _update_sidecar_comments(output_folder, [], "disabled")
        _start_hook_after_comments()
    except Exception as e:
        log.warning("comments worker crashed: %s", e)
        _replace_comments_section(yoink_path,
            "*Comments could not be retrieved.*")
        _update_sidecar_comments(output_folder, [], "unavailable")
        _start_hook_after_comments()


def _start_comments_thread(url: str, output_folder: Path,
                           yoink_path: Path,
                           metadata: dict | None = None,
                           entries: list | None = None) -> threading.Thread:
    t = threading.Thread(
        target=_comments_worker,
        args=(url, output_folder, yoink_path, metadata, entries),
        name=f"comments-{output_folder.name}",
        daemon=True,
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# yoink.md builder
# ---------------------------------------------------------------------------
def _build_yoink_md(metadata: dict, url: str, entries: list, shots: list,
                    interval: int, channel_ctx: dict,
                    yoinked_at: str, topic: str,
                    cap_warning: str | None = None,
                    shot_times: list[int] | None = None) -> str:
    """Produce the v1 corpus markdown. Comments section is a placeholder
    that the background worker rewrites once the fetch completes.
    """
    title = metadata.get("title") or "Untitled"
    channel = metadata.get("channel") or metadata.get("uploader") or "—"
    sub_count = format_subscribers(metadata.get("channel_follower_count"))
    upload_date = _fmt_iso_date(metadata.get("upload_date"))
    duration = format_duration(metadata.get("duration"))
    views = _fmt_int(metadata.get("view_count"))
    likes = _fmt_likes(metadata.get("like_count"))
    description = (metadata.get("description") or "").strip()
    tags = metadata.get("tags") or []
    chapters = metadata.get("chapters") or []

    parts: list[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append(f"**Channel:** {channel} ({sub_count} subscribers)")
    parts.append(
        f"**Uploaded:** {upload_date} | **Duration:** {duration} | "
        f"**Views:** {views} | **Likes:** {likes}"
    )
    parts.append(f"**URL:** {url}")
    parts.append(f"**Uoinked:** {yoinked_at}")
    parts.append(f"**Topic:** {topic}")
    if cap_warning:
        parts.append(f"**Note:** {cap_warning}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Thumbnail
    parts.append("## Thumbnail")
    parts.append("")
    parts.append("![Thumbnail](thumbnail.jpg)")
    parts.append("")

    # Description
    parts.append("## Description")
    parts.append("")
    parts.append(description if description else "*No description.*")
    parts.append("")

    # Tags
    parts.append("## Tags")
    parts.append("")
    parts.append(", ".join(tags) if tags else "No tags")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Transcript
    parts.append("## Transcript")
    parts.append("")
    if not entries:
        parts.append("*No captions available for this video.*")
        parts.append("")
    else:
        if chapters:
            # Group entries by chapter ranges. Chapters have start_time/end_time.
            for ch in chapters:
                ch_start = ch.get("start_time") or 0
                ch_end = ch.get("end_time")
                ch_title = ch.get("title") or "Chapter"
                parts.append(f"### Chapter: {ch_title} ({fmt_time(int(ch_start))})")
                parts.append("")
                for s, _e, t in entries:
                    if s < ch_start:
                        continue
                    if ch_end is not None and s >= ch_end:
                        continue
                    parts.append(f"[{fmt_time(int(s))}] {t}")
                parts.append("")
        else:
            for s, _e, t in entries:
                parts.append(f"[{fmt_time(int(s))}] {t}")
            parts.append("")
    parts.append("---")
    parts.append("")

    # Screenshots
    parts.append("## Screenshots")
    parts.append("")
    for i, shot in enumerate(shots):
        start = shot_times[i] if shot_times and i < len(shot_times) else i * interval
        ts = fmt_time(start)
        parts.append(f"### [{ts}]")
        parts.append("")
        parts.append(f"![Screenshot at {ts}](screenshots/{shot.name})")
        parts.append("")
    parts.append("---")
    parts.append("")

    # Top Comments — placeholder, filled in by the background worker.
    parts.append("## Top Comments")
    parts.append("")
    parts.append(COMMENTS_START_MARK)
    parts.append("*Fetching comments... they'll appear here when ready.*")
    parts.append(COMMENTS_END_MARK)
    parts.append("")
    parts.append("---")
    parts.append("")

    # Channel Context
    parts.append("## Channel Context")
    parts.append("")
    parts.append(f"**About {channel}:**")
    ch_desc = (channel_ctx.get("description") or "").strip()
    parts.append(ch_desc if ch_desc else "*No channel description available.*")
    parts.append("")
    parts.append("**Recent videos from this channel:**")
    recent = channel_ctx.get("recent_videos") or []
    if not recent:
        parts.append("- *No recent videos found.*")
    else:
        for v in recent:
            v_title = v.get("title") or "(untitled)"
            v_views = format_count(v.get("view_count"))
            v_date = _fmt_iso_date(v.get("upload_date"))
            parts.append(f"- {v_title} ({v_views} views, {v_date})")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("*[Uoinked with Uoink by ReplayRyan](https://uoink.app)*")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Extraction core (shared by /extract and /session/add)
# ---------------------------------------------------------------------------
def _run_extraction(url: str, interval: int, output_folder: Path,
                    *, open_explorer: bool = True,
                    metadata: dict | None = None,
                    topic: str | None = None,
                    generate_paste: bool = True,
                    long_video_mode: str = LONG_VIDEO_MODE_FULL,
                    cancel_event: threading.Event | None = None,
                    phase_callback=None) -> dict:
    """Yoink a single video into output_folder.

    Steps:
      1. Fetch full metadata (cached as metadata.json) — already done if the
         caller passed `metadata` (avoids a second yt-dlp call).
      2. Download highest-res thumbnail to thumbnail.jpg.
      3. Download video + subs, run ffmpeg screenshots, parse the SRT.
      4. Fetch lightweight channel context (description + last 5 videos).
      5. Write yoink.md with a placeholder Top Comments section.
      6. Spawn a background thread that fetches comments and rewrites
         the comments block in place.
    Returns a dict with folder, yoink_md (current text), screenshot_count,
    title, video_slug, caption_count.
    """
    requested_long_video_mode = _normalize_long_video_mode(long_video_mode)
    output_folder.mkdir(parents=True, exist_ok=True)

    if metadata is None:
        if phase_callback:
            phase_callback("metadata")
        metadata = _fetch_metadata(url, cancel_event=cancel_event)
    if topic is None:
        topic = _classify_topic(metadata)

    title = metadata.get("title") or "Untitled"
    video_slug = slugify(title) or "video"
    log.info("Uoinking '%s' -> %s (topic=%s)", title, output_folder, topic)

    # P1-4: bound screenshot count so a 4-hour video at 5s interval doesn't
    # produce thousands of jpgs. Recompute interval upward when needed and
    # surface the change in the corpus md.
    duration = float(metadata.get("duration") or 0)
    if duration > LONG_VIDEO_SECONDS:
        log.warning("Long video: %.0f minutes -- yoink may take a while",
                    duration / 60.0)
    # Lite recovery (A-01): force sparse screenshots so a long source's frame
    # extraction stops being a bottleneck. The full transcript still lands and
    # comments are skipped below. Done before the estimate/cap math so the
    # capped-interval note reflects the real interval used.
    is_lite = requested_long_video_mode == LONG_VIDEO_MODE_LITE
    if is_lite:
        interval = max(interval, LITE_SHOT_INTERVAL_SEC)
    long_video_chunks = (
        _long_video_chunks(duration)
        if requested_long_video_mode == LONG_VIDEO_MODE_CHUNKED
        else []
    )
    if long_video_chunks:
        effective_long_video_mode = LONG_VIDEO_MODE_CHUNKED
    elif is_lite:
        effective_long_video_mode = LONG_VIDEO_MODE_LITE
    else:
        effective_long_video_mode = LONG_VIDEO_MODE_FULL
    work_durations = (
        [chunk["duration_seconds"] for chunk in long_video_chunks]
        if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED
        else [duration]
    )
    processed_media_seconds = int(sum(work_durations))
    requested_interval = interval
    notes: list[str] = []
    if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
        notes.append(
            f"Chunked mode sampled {len(long_video_chunks)} media sections "
            f"({processed_media_seconds // 60}m of {int(duration) // 60}m) "
            "while retaining the full available subtitle track."
        )
    elif requested_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
        notes.append(
            "Chunked mode was requested, but the source duration was unknown; "
            "Uoink used the full-media path."
        )
    if is_lite:
        notes.append(
            "Lite recovery mode: kept the full transcript, took a screenshot "
            f"about every {interval // 60} minutes, and skipped the comments "
            "fetch. Re-yoink in full mode for dense screenshots and comments."
        )

    estimate = _estimated_screenshot_count(work_durations, interval)
    if estimate > MAX_SCREENSHOTS:
        new_interval = interval
        while _estimated_screenshot_count(work_durations, new_interval) > MAX_SCREENSHOTS:
            new_interval += 1
        notes.append(
            f"Capped screenshots at {MAX_SCREENSHOTS}: interval raised from "
            f"{requested_interval}s to {new_interval}s for this video "
            f"(processed media {processed_media_seconds // 60}m)."
        )
        log.warning(notes[-1])
        interval = new_interval
    cap_warning = " ".join(notes) or None

    # Persist the raw metadata blob for debugging without re-downloading.
    try:
        (output_folder / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("could not write metadata.json: %s", e)

    # Thumbnail (best-effort; absence shouldn't fail the extraction).
    _download_thumbnail(metadata, output_folder, cancel_event=cancel_event)

    # Clear only helper-owned transient media from an earlier attempt in this
    # same yoink folder. The corpus/sidecar remain until the new run succeeds.
    for pattern in ("video.*", "video-chunk-*.*"):
        for stale in output_folder.glob(pattern):
            if stale.is_file():
                stale.unlink(missing_ok=True)

    # Full mode downloads one low-res media file plus subtitles. Chunked mode
    # downloads representative media sections with yt-dlp's section support,
    # then fetches the full available subtitle track separately.
    download_timeout = _ytdlp_timeout_for(processed_media_seconds or duration)
    media_cmd = [
        *YTDLP_CMD,
        # Require a video stream. Plain `worst` can pick audio-only on some
        # Shorts, which makes ffmpeg screenshot extraction fail with no packets.
        "-f", "worst*[vcodec!=none][height>=360]/worst*[vcodec!=none]/worst",
        "--concurrent-fragments", "4",
        "--retries", "10",
        "--fragment-retries", "10",
        "--socket-timeout", "30",
    ]
    if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
        for chunk in long_video_chunks:
            media_cmd.extend(["--download-sections", _chunk_section_spec(chunk)])
        media_cmd.extend([
            "-o", str(output_folder / "video-chunk-%(section_number)03d.%(ext)s"),
            url,
        ])
    else:
        media_cmd.extend([
            # Full mode still refuses a multi-GB media file. Chunked mode
            # intentionally omits this source-level check because the selected
            # sections already bound the downloaded media work.
            "--max-filesize", str(YTDLP_MAX_FILESIZE_BYTES),
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang", "en.*,en",
            "--convert-subs", "srt",
            "-o", str(output_folder / "video.%(ext)s"),
            url,
        ])

    try:
        if phase_callback:
            phase_callback("download")
        _run_subprocess(
            media_cmd,
            cancel_event=cancel_event,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=download_timeout,
        )
    except subprocess.TimeoutExpired:
        # Log the real cause (duration + the budget we actually used) so
        # helper.log has a trace -- the old path discarded this and left the
        # 2-hour failure looking like "nothing happened".
        log.error(
            "yt-dlp %s download timed out after %ds "
            "(source duration ~%.0fs, media work ~%ds): %s",
            effective_long_video_mode, download_timeout, duration,
            processed_media_seconds, url)
        mins = max(1, download_timeout // 60)
        raise ExtractionPhaseError(
            "download",
            f"Download timed out after about {mins} minutes. This is a "
            "download/network issue, not a screenshot setting -- the video "
            "may be very long, or the connection to YouTube is slow or being "
            "throttled. Try again on a faster connection, or pick a shorter "
            "video."
        )

    if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
        if phase_callback:
            phase_callback("transcript")
        try:
            _run_subprocess(
                [
                    *YTDLP_CMD,
                    "--skip-download",
                    "--write-auto-subs",
                    "--write-subs",
                    "--sub-lang", "en.*,en",
                    "--convert-subs", "srt",
                    "-o", str(output_folder / "video.%(ext)s"),
                    url,
                ],
                cancel_event=cancel_event,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=COMMENTS_TIMEOUT_SEC,
            )
        except PlaylistJobCancelled:
            raise
        except (OSError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as e:
            # Captions are optional throughout the existing pipeline. Chunked
            # media should still succeed when the source exposes none.
            log.warning("chunked subtitle fetch unavailable: %s", e)

    media_glob = (
        "video-chunk-*.*"
        if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED
        else "video.*"
    )
    video_files = [f for f in sorted(output_folder.glob(media_glob))
                   if f.suffix in (".mp4", ".webm", ".mkv")]
    srt_files = list(output_folder.glob("video*.srt"))
    if not video_files:
        if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
            raise ExtractionPhaseError(
                "download",
                "Chunked download produced no media sections. The source may "
                "be unavailable, private, region-locked, or may not support "
                "section downloads."
            )
        raise ExtractionPhaseError(
            "download",
            "yt-dlp produced no video file. The video may exceed the 2 GB "
            "download cap (set in helper config), or it may be unavailable, "
            "private, or region-locked."
        )

    shots_dir = output_folder / "screenshots"
    shots_dir.mkdir(exist_ok=True)
    for pattern in ("shot_*.jpg", "chunk_*_shot_*.jpg"):
        for stale in shots_dir.glob(pattern):
            stale.unlink(missing_ok=True)

    shot_times: list[int] = []
    if effective_long_video_mode == LONG_VIDEO_MODE_CHUNKED:
        shot_number = 1
        for i, video_file in enumerate(video_files):
            chunk = long_video_chunks[min(i, len(long_video_chunks) - 1)]
            chunk_phase = f"screenshots_chunk_{i + 1}_of_{len(video_files)}"
            try:
                if phase_callback:
                    phase_callback(chunk_phase)
                prefix = f"chunk_{i + 1:03d}_shot_"
                _run_subprocess(
                    [
                        "ffmpeg", "-loglevel", "error", "-y",
                        "-i", str(video_file),
                        "-vf", f"fps=1/{interval}",
                        "-q:v", "2",
                        str(shots_dir / f"{prefix}%04d.jpg"),
                    ],
                    cancel_event=cancel_event,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=_ffmpeg_timeout_for(chunk["duration_seconds"]),
                )
            except subprocess.TimeoutExpired:
                log.error(
                    "ffmpeg chunk %d/%d timed out (section %ss-%ss, interval %ds)",
                    i + 1, len(video_files), chunk["start_seconds"],
                    chunk["end_seconds"], interval)
                raise ExtractionPhaseError(
                    chunk_phase,
                    f"Screenshot generation timed out in chunk {i + 1} of "
                    f"{len(video_files)}. Try a longer screenshot interval "
                    f"(current: {interval}s)."
                )
            local_shots = sorted(shots_dir.glob(f"{prefix}*.jpg"))
            for local_i, local_shot in enumerate(local_shots):
                target = shots_dir / f"shot_{shot_number:04d}.jpg"
                local_shot.replace(target)
                shot_times.append(
                    int(chunk["start_seconds"] + (local_i * interval))
                )
                shot_number += 1
    else:
        video_file = video_files[0]
        try:
            if phase_callback:
                phase_callback("screenshots")
            _run_subprocess(
                [
                    "ffmpeg", "-loglevel", "error", "-y",
                    "-i", str(video_file),
                    "-vf", f"fps=1/{interval}",
                    "-q:v", "2",
                    str(shots_dir / "shot_%04d.jpg"),
                ],
                cancel_event=cancel_event,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=_ffmpeg_timeout_for(duration),
            )
        except subprocess.TimeoutExpired:
            log.error(
                "ffmpeg screenshot extraction timed out after %ds "
                "(video duration ~%.0fs, interval %ds)",
                _ffmpeg_timeout_for(duration), duration, interval)
            raise ExtractionPhaseError(
                "screenshots",
                "Screenshot generation timed out -- try a longer screenshot "
                "interval (current: %ds)." % interval
            )
    shots = sorted(shots_dir.glob("shot_*.jpg"))
    if not shot_times:
        shot_times = [i * interval for i in range(len(shots))]

    entries = list(parse_srt(srt_files[0])) if srt_files else []

    if entries:
        plain = "\n".join(text for _, _, text in entries)
        (output_folder / "transcript.txt").write_text(plain, encoding="utf-8")

    if phase_callback:
        phase_callback("write")

    # Channel context (description + recent videos). Best-effort.
    channel_url = (metadata.get("channel_url")
                   or metadata.get("uploader_url")
                   or "")
    channel_ctx = _fetch_channel_context(channel_url)

    # Build the corpus markdown.
    yoink_md = _build_yoink_md(
        metadata=metadata, url=url, entries=entries, shots=shots,
        interval=interval, channel_ctx=channel_ctx,
        yoinked_at=_now_iso(), topic=topic,
        cap_warning=cap_warning,
        shot_times=shot_times,
    )
    # Filename matches the folder's slug -- "kapathy-talk/kapathy-talk.md"
    # rather than "kapathy-talk/yoink.md" -- so the file is identifiable
    # outside its folder.
    yoink_path = _corpus_path(output_folder)
    _atomic_write_text(yoink_path, yoink_md)
    hook_type_pending = _should_start_hook_type(metadata)

    # Structured JSON sidecar (STRAT). Same data the markdown carries but
    # in a machine-shaped form: future MCP server / programmatic tooling
    # consumes this without having to parse the human-facing md. Written
    # next to the md so it travels with the folder.
    #
    # `comments` ships as `null` here and is filled in by the comments
    # worker once yt-dlp returns -- mirrors the markdown placeholder
    # behavior. Consumers see `comments_status: "pending"` until the
    # worker either succeeds (`fetched`), finds none (`disabled`), or
    # fails (`unavailable`).
    try:
        sidecar = {
            "schema_version": 2,  # bumped: structured screenshots + comments
            "url": url,
            # v3.1: platform indicator chip in dashboard. Inferred from the
            # canonical URL produced by _normalize_video_url; default
            # 'youtube' so existing rows that pre-date this field render
            # as YouTube without a migration.
            "platform": _detect_platform_from_url(url),
            "title": title,
            "topic": topic,
            "yoinked_at": _now_iso(),
            "interval_seconds": interval,
            "requested_interval_seconds": requested_interval,
            "screenshot_cap_warning": cap_warning,
            "duration_seconds": duration,
            "requested_long_video_mode": requested_long_video_mode,
            "long_video_mode": effective_long_video_mode,
            "long_video_chunks": long_video_chunks,
            "processed_media_seconds": processed_media_seconds,
            "channel": metadata.get("channel") or metadata.get("uploader"),
            "channel_url": metadata.get("channel_url") or metadata.get("uploader_url"),
            "upload_date": metadata.get("upload_date"),
            "view_count": metadata.get("view_count"),
            "like_count": metadata.get("like_count"),
            "video_id": metadata.get("id"),
            "transcript": [
                {"start": s, "end": e, "text": t} for s, e, t in entries
            ],
            # Structured shape: timestamp + relative path + bare filename so
            # consumers don't have to parse paths or recompute timestamps.
            "screenshots": [
                {
                    "timestamp": fmt_time(shot_times[i]),
                    "path": f"screenshots/{p.name}",
                    "filename": p.name,
                }
                for i, p in enumerate(shots)
            ],
            "channel_context": channel_ctx,
            "comments": None,
            # Lite recovery skips the comments fetch, so mark it skipped rather
            # than leaving it "pending" forever (no worker will resolve it).
            "comments_status": (
                "skipped"
                if effective_long_video_mode == LONG_VIDEO_MODE_LITE
                else "pending"
            ),
            # Hook Type runs inside the comments worker, so lite mode (which
            # skips comments) skips hook typing too -- mark it skipped, not
            # pending, so nothing waits on a worker that never starts.
            "hook_type_status": (
                "pending"
                if hook_type_pending
                and effective_long_video_mode != LONG_VIDEO_MODE_LITE
                else "skipped"
            ),
            "hook_type": None,
            "hook_explanation": None,
            "hook_type_confidence": None,
            "hook_type_error": None,
            "comment_intelligence": None,
            "comment_intelligence_status": "not_run",
            "comment_intelligence_error": None,
            # Sprint 16: entity extraction runs in the background once the
            # row is indexed. "pending" when a key is set, "skipped"
            # otherwise; the worker flips it to completed / failed.
            "entity_extraction_status": (
                "pending" if _saved_anthropic_key() else "skipped"
            ),
            "entity_extraction_error": None,
        }
        # A5: extraction-time health snapshot, stored on the sidecar.
        sidecar["health"] = compute_health(sidecar)
        # v2.5: stamp the per-file data-shape version. Lets v2.5+ readers tell
        # at a glance whether a sidecar predates facets/engagement. Missing =
        # treat as 1 via _upgrade_sidecar() (lazy up-convert on read).
        sidecar["schema_version"] = CURRENT_SIDECAR_SCHEMA
        sidecar_path = output_folder / f"{output_folder.name}.json"
        _atomic_write_text(sidecar_path, json.dumps(sidecar, ensure_ascii=False, indent=2))
    except (OSError, TypeError) as e:
        # Non-fatal: the markdown is the user-facing artifact. Sidecar is
        # for future tooling.
        log.warning("could not write JSON sidecar: %s", e)

    # v2.5 A1: optional local transcript reliability detection. It runs only
    # when the user has opted in and the Whisper model is already cached; the
    # dashboard's "Download model now" button is the explicit consent gate for
    # the ~150 MB model download. Run before deleting the downloaded video so
    # the automatic path does not need a second yt-dlp fetch.
    try:
        if (_read_settings().get("transcript_reliability_auto_check")
                and effective_long_video_mode == LONG_VIDEO_MODE_FULL):
            rel = _compute_transcript_reliability(
                sidecar.get("video_id") or metadata.get("id") or "",
                folder=output_folder,
                audio_path=video_files[0],
                threshold=RELIABILITY_DEFAULT_THRESHOLD,
                allow_model_download=False,
            )
            if not rel.get("ok"):
                log.info("transcript reliability skipped/failed: %s", rel.get("error"))
            _sidecar_path, sidecar = _read_sidecar_for_folder(output_folder)
    except Exception as e:
        log.warning("transcript reliability auto-check failed: %s", e)

    for video_file in video_files:
        video_file.unlink(missing_ok=True)

    # Sprint 19.6 / Fix 6: refresh _all-yoinks-index.md INCREMENTALLY
    # instead of the pre-Sprint-19.6 full-tree rescan that became O(N) on
    # large libraries. _incremental_index_update parses the existing file
    # and prepends one new entry; first-launch / parse failure spawn a
    # background full regen so the foreground yoink stays fast either way.
    try:
        rel_path = (f"{output_folder.parent.name}/"
                    f"{output_folder.name}/{yoink_path.name}")
        _incremental_index_update({
            "title": title,
            "topic": output_folder.parent.name or "uncategorised",
            "channel": (metadata.get("channel")
                        or metadata.get("uploader") or ""),
            "yoinked_at": datetime.now().date().isoformat(),
            "rel_path": rel_path,
        })
    except Exception as e:
        log.warning("incremental index call site failed: %s", e)

    # Sprint 15 (A1/A4/A5): incrementally index this yoink + its citation
    # map + health score in index.db. Best-effort -- a library-index failure
    # must never fail an otherwise-successful extraction. (This is separate
    # from _regenerate_index above, which maintains the human-readable
    # _all-yoinks-index.md file.)
    try:
        _index_yoink(output_folder, sidecar, yoink_path, sidecar_path)
    except Exception as e:
        log.warning("library index update failed for %s: %s", output_folder, e)

    # Sprint 16 (A2): extract named entities off the transcript in the
    # background, in parallel with the comments / Comment Intelligence
    # pipeline (it does not wait on either). Started after _index_yoink so
    # the yoinks row exists for the entity_mentions foreign key. Best-effort
    # -- a failure never fails an otherwise-successful extraction.
    _start_entity_extraction_thread(
        output_folder, sidecar.get("video_id"), sidecar
    )

    # Build the clipboard / paste version once we know the on-disk md is
    # final. Session adds skip this -- the session corpus is built at
    # /session/close time, so the per-video paste version would be unused
    # bytes shipped over the chrome.runtime message.
    paste_md: str | None = None
    if generate_paste:
        try:
            paste_md = _generate_paste_corpus(output_folder)
        except Exception as e:
            log.warning("paste corpus generation failed: %s", e)
            paste_md = None

    # Comments fetch in background; updates the corpus file when done. Hook
    # Type waits for this comments worker to finish so it can include the top
    # comment when one is available. Lite recovery (A-01) skips it: comments
    # are the fragile/expensive tail this mode exists to shed.
    if effective_long_video_mode == LONG_VIDEO_MODE_LITE:
        log.info("lite mode: skipping comments fetch for %s", url)
    else:
        if phase_callback:
            phase_callback("comments")
        _start_comments_thread(url, output_folder, yoink_path, metadata, entries)
    if phase_callback:
        phase_callback("done")

    if open_explorer:
        try:
            _platform.open_in_os(output_folder)
        except Exception as e:
            log.warning("startfile failed: %s", e)

    return {
        "ok": True,
        "folder": str(output_folder),
        "yoink_md": yoink_md,
        # Multimodal clipboard version: same content as yoink_md but with
        # screenshots inlined as base64 data URIs. Extension prefers this
        # over yoink_md when copying to the clipboard. None on session adds
        # or when generation fails -- caller falls back to yoink_md.
        "corpus_md_paste": paste_md,
        "screenshot_count": len(shots),
        "title": title,
        "video_slug": video_slug,
        "caption_count": len(entries),
        "topic": topic,
        "requested_long_video_mode": requested_long_video_mode,
        "long_video_mode": effective_long_video_mode,
        "long_video_chunks": long_video_chunks,
        "processed_media_seconds": processed_media_seconds,
        "source_duration_seconds": int(duration),
    }


INSTALL_HELP_URL = "https://uoink.app/install"


def _is_youtube_rate_limit(e: BaseException) -> bool:
    """True when an exception thrown out of _run_extraction is yt-dlp
    surfacing a YouTube HTTP 429. Drives the rate-limit queue (Sprint 19):
    the extract handler enqueues for retry instead of returning the
    pre-Sprint-19 friendly_error string, and the retry worker uses the
    same predicate to decide between exponential backoff and immediate
    terminal failure."""
    if not isinstance(e, subprocess.CalledProcessError):
        return False
    stderr = (e.stderr.decode("utf-8", errors="ignore")
              if isinstance(e.stderr, bytes) else (e.stderr or ""))
    return "HTTP Error 429" in stderr


# How long the /extract handler asks the user to wait before the first
# retry of a rate-limited URL. The retry worker's exponential backoff
# (60s * 2^attempts, capped at 15 minutes) takes over after that.
_RATE_LIMIT_INITIAL_BACKOFF_SEC = 60


def _legacy_friendly_error_unused(e: BaseException) -> str:
    """Translate raw exceptions into copy the user can act on."""
    if isinstance(e, FileNotFoundError):
        return ("Uoink can't find yt-dlp or ffmpeg on this machine. "
                f"Install both, then try again. See {INSTALL_HELP_URL}")

    if isinstance(e, subprocess.CalledProcessError):
        stderr = (e.stderr.decode("utf-8", errors="ignore") if isinstance(e.stderr, bytes)
                  else (e.stderr or "")).strip()
        # Match known YouTube failures so the user doesn't see a yt-dlp stack.
        if "Sign in to confirm you're not a bot" in stderr or "captcha" in stderr.lower():
            return ("YouTube wants a sign-in check. Open YouTube in this browser, "
                    "sign in once, then try again.")
        if "Video unavailable" in stderr or "This video is private" in stderr:
            return "This video isn't available (private, deleted, or region-locked)."
        if "Members-only" in stderr or "members only" in stderr.lower():
            return "Members-only video — Uoink can't reach it without an account."
        if "is live" in stderr.lower() or "premiere" in stderr.lower():
            return "Uoink can't grab livestreams or premieres yet. Try again after the broadcast ends."
        if "HTTP Error 429" in stderr:
            return "YouTube is rate-limiting. Wait a minute, then try again."

        last = stderr.splitlines()[-1] if stderr else f"exit code {e.returncode}"
        tool = Path(e.cmd[0]).name if e.cmd else "subprocess"
        # Strip yt-dlp's "ERROR:" prefix if present so the message doesn't shout.
        last = re.sub(r"^ERROR:\s*", "", last)
        return f"Uoink hit an error from {tool}: {last}"

    if isinstance(e, RuntimeError):
        return f"Uoink couldn't finish this video: {e}"

    return f"Uoink hit an unexpected error: {e}"


def _subprocess_output(e: subprocess.CalledProcessError) -> str:
    stderr = (e.stderr.decode("utf-8", errors="ignore")
              if isinstance(e.stderr, bytes) else (e.stderr or ""))
    stdout = (e.stdout.decode("utf-8", errors="ignore")
              if isinstance(e.stdout, bytes) else (e.stdout or ""))
    return "\n".join(part for part in (stderr, stdout) if part).strip()


def machine_error_detail(e: BaseException) -> str:
    """Raw-ish diagnostic detail for dashboard disclosures, not primary UI."""
    if isinstance(e, subprocess.CalledProcessError):
        pieces = []
        if e.cmd:
            try:
                pieces.append("Command: " + " ".join(str(part) for part in e.cmd))
            except TypeError:
                pieces.append(f"Command: {e.cmd}")
        pieces.append(f"Exit code: {e.returncode}")
        output = _subprocess_output(e)
        if output:
            pieces.append(output)
        return "\n".join(pieces).strip()[:6000]
    return re.sub(r"\s+", " ", str(e or "")).strip()[:3000]


def _source_name_from_error(text: str) -> str:
    lower = text.lower()
    if "youtube" in lower or "youtu.be" in lower:
        return "YouTube"
    if "x.com" in lower or "twitter" in lower:
        return "X"
    if "vimeo" in lower:
        return "Vimeo"
    return "The source"


def _plain_error_from_text(text: str) -> str:
    lower = text.lower()
    source = _source_name_from_error(text)
    if ("too many requests" in lower or "http error 429" in lower
            or "rate-limit" in lower or "rate limit" in lower):
        return "Helper's catching its breath. Retrying..."
    if ("sign in" in lower or "login" in lower or "cookies" in lower
            or "captcha" in lower or "guest token" in lower):
        return f"{source} wouldn't hand this one over without a login. Retry with cookies?"
    if "members-only" in lower or "members only" in lower:
        return f"{source} kept this one behind members-only access."
    if ("video unavailable" in lower or "this video is private" in lower
            or " private" in lower or "region" in lower):
        return f"{source} did not expose a usable video for this source."
    if "is live" in lower or "premiere" in lower:
        return f"{source} is still live. Try again once the broadcast becomes a replay."
    if "ffmpeg" in lower:
        return "The source came down, but the local media step tripped. Details are tucked below."
    if "whisperx" in lower or "whisper" in lower:
        return "The local transcript step tripped. Details are tucked below."
    if "can't find yt-dlp" in lower or "can't find ffmpeg" in lower or "no such file" in lower:
        return "Uoink can't find a local media helper. Details are tucked below."
    if "yt-dlp" in lower or "unable to download" in lower or "extractor error" in lower:
        return f"{source} would not hand this one over cleanly. Details are tucked below."
    return "Uoink couldn't finish this one. Details are tucked below."


def friendly_error(e: BaseException) -> str:
    """Translate raw exceptions into copy the user can act on."""
    if isinstance(e, ExtractionPhaseError):
        return str(e)
    if isinstance(e, FileNotFoundError):
        return ("Uoink can't find yt-dlp or ffmpeg on this machine. "
                f"Install both from {INSTALL_HELP_URL}, then try again.")
    if isinstance(e, subprocess.CalledProcessError):
        return _plain_error_from_text(machine_error_detail(e))
    if isinstance(e, RuntimeError):
        return _plain_error_from_text(str(e))
    return "Uoink couldn't finish this one. Details are tucked below."


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
# v3.1: Twitter/X video extractor (yt-dlp supports it). Hosts accepted both
# pre- and post-rename so the user can paste a link from before or after the
# x.com switch. mobile.twitter.com kept for old shares.
_TWITTER_HOSTS = {"twitter.com", "www.twitter.com", "mobile.twitter.com",
                   "x.com", "www.x.com"}
# Twitter status id is a 15-19 digit snowflake. Strict so we can't accept
# attacker-shaped paths like /status/junk.
_TWITTER_STATUS_RE = re.compile(r"^\d{15,19}$")
# Twitter usernames: 1-15 chars, A-Z 0-9 underscore (no dot, no hyphen).
_TWITTER_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")

# Platform tag persisted on the sidecar + yoink row so the dashboard can
# render a per-platform indicator chip. youtube is the default for backward
# compat with existing rows that pre-date this field.
PLATFORM_YOUTUBE = "youtube"
PLATFORM_TWITTER = "twitter"
# v3.1 universal extract: any URL yt-dlp supports that isn't a known
# host gets the generic platform tag. Dashboard renders a neutral chip.
PLATFORM_GENERIC = "generic"
_KNOWN_PLATFORMS = (PLATFORM_YOUTUBE, PLATFORM_TWITTER, PLATFORM_GENERIC)

# v3.1: per-host platform hint table for the (small) set of sites the
# dashboard renders with a custom chip. Anything not here is 'generic'
# but the sidecar still records the raw host so a future Codex/AG pass
# can expand the recognized list without a helper-side migration.
_PLATFORM_HOST_HINTS: dict[str, str] = {
    # Vimeo, Dailymotion, etc. are TBD -- left to Codex's chip work
    # so this PR stays focused on the helper-side extractor surface.
}

# ASCII-explicit so non-ASCII unicode word chars can't sneak through \w.
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,}$")
_JOB_ID_RE = re.compile(r"^job_[A-Za-z0-9_-]{1,96}$")


def _normalize_youtube_url(raw: str) -> str | None:
    """Parse the URL, verify the hostname is in the YouTube allowlist, pull
    the video ID, and return the canonical https://www.youtube.com/watch?v=
    form. Returns None for anything that isn't a real YouTube video URL --
    bare strings, attacker-shaped URLs like https://evil.com/youtube.com/x,
    non-video YouTube paths (channels, search), etc.
    """
    if not raw:
        return None
    try:
        u = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None

    video_id = None
    if host == "youtu.be":
        first = (u.path or "").lstrip("/").split("/", 1)[0]
        if _VIDEO_ID_RE.match(first):
            video_id = first
    else:
        if u.path == "/watch":
            qs = parse_qs(u.query)
            v = (qs.get("v") or [""])[0]
            if _VIDEO_ID_RE.match(v):
                video_id = v
        elif u.path.startswith("/shorts/"):
            seg = u.path.split("/", 3)[2] if len(u.path.split("/", 3)) > 2 else ""
            if _VIDEO_ID_RE.match(seg):
                video_id = seg
        elif u.path.startswith("/embed/"):
            seg = u.path.split("/", 3)[2] if len(u.path.split("/", 3)) > 2 else ""
            if _VIDEO_ID_RE.match(seg):
                video_id = seg
    if not video_id:
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def _normalize_twitter_url(raw: str) -> str | None:
    """Parse the URL, verify the hostname is in the Twitter/X allowlist,
    pull (handle, status_id) and return the canonical
    https://x.com/<handle>/status/<status_id> form. Returns None for
    anything that isn't a real tweet video URL.

    Path shape (Twitter + X are identical):
      /<handle>/status/<status_id>          -- canonical
      /<handle>/status/<status_id>/video/N  -- the video sub-page that
                                                yt-dlp also accepts
      /i/status/<status_id>                 -- the bare-status fallback
                                                (no handle in the URL)"""
    if not raw:
        return None
    try:
        u = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host not in _TWITTER_HOSTS:
        return None
    parts = (u.path or "").strip("/").split("/")
    if not parts:
        return None
    if parts[0].lower() == "i" and len(parts) >= 3 and parts[1] == "status":
        if _TWITTER_STATUS_RE.match(parts[2]):
            return f"https://x.com/i/status/{parts[2]}"
        return None
    if len(parts) >= 3 and parts[1] == "status":
        handle = parts[0]
        status_id = parts[2]
        if (_TWITTER_HANDLE_RE.match(handle)
                and _TWITTER_STATUS_RE.match(status_id)):
            return f"https://x.com/{handle}/status/{status_id}"
    return None


def _detect_platform_from_url(url: str) -> str:
    """Return the platform tag for a canonical URL. Used by the sidecar
    writer + the dashboard chip. Pre-v3.1 callers that pass a raw YouTube
    URL still get 'youtube'. v3.1 generic extract returns 'generic' for
    anything yt-dlp accepts that isn't on the known-host list."""
    if not url:
        return PLATFORM_YOUTUBE
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return PLATFORM_YOUTUBE
    if host in _YOUTUBE_HOSTS:
        return PLATFORM_YOUTUBE
    if host in _TWITTER_HOSTS:
        return PLATFORM_TWITTER
    if host in _PLATFORM_HOST_HINTS:
        return _PLATFORM_HOST_HINTS[host]
    return PLATFORM_GENERIC


# v3.1: the only relaxed-validation entry point. /extract/any uses this;
# the original /extract still goes through the strict YouTube validator.
# Why this is safe: we ONLY accept http(s) URLs with a real-looking
# hostname and hand the result straight to yt-dlp. The dispatcher does
# NOT itself fetch anything. Same posture as Twitter -- yt-dlp's site
# list does the heavy lifting; we just guard the inputs.
_GENERIC_HOST_RE = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")


def _normalize_any_url(raw: str) -> tuple[str | None, str | None]:
    """Validate an arbitrary URL for /extract/any. Returns (canonical, platform).

    Acceptance gates:
      1. Parses with urlparse (no shape errors).
      2. Scheme is http or https (no file:, ftp:, javascript:, data: ...)
      3. Hostname matches the conservative hostname regex (DNS label
         shape; rejects IP literals, bracketed IPv6, and weird unicode).
    Returns None on failure. Platform is best-effort from the host.

    This deliberately does NOT call yt-dlp -- that's the extraction step.
    The dispatcher's job is to keep attacker-shaped URLs from reaching
    yt-dlp's subprocess in the first place."""
    if not raw or not isinstance(raw, str):
        return None, None
    raw = raw.strip()
    if not raw:
        return None, None
    # Reject the obvious dangerous schemes outright even if urlparse
    # would shrug them off. Belt-and-suspenders: the scheme check below
    # would catch these too, but listing them is clearer.
    lower = raw.lower()
    for bad in ("javascript:", "data:", "vbscript:", "file:", "ftp:",
                 "mailto:", "blob:"):
        if lower.startswith(bad):
            return None, None
    # Try YouTube + Twitter normalisers first -- they give canonical
    # forms. If neither accepts, fall through to the generic gate.
    yt = _normalize_youtube_url(raw)
    if yt:
        return yt, PLATFORM_YOUTUBE
    tw = _normalize_twitter_url(raw)
    if tw:
        return tw, PLATFORM_TWITTER
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urlparse(raw)
    except ValueError:
        return None, None
    if u.scheme not in ("http", "https"):
        return None, None
    host = (u.hostname or "")
    if not host or len(host) > 253:
        return None, None
    if not _GENERIC_HOST_RE.match(host):
        return None, None
    # Canonical = scheme://host[:port]/path?query  (drops fragment + auth)
    netloc = host.lower()
    if u.port:
        netloc = f"{netloc}:{u.port}"
    query = f"?{u.query}" if u.query else ""
    canonical = f"{u.scheme}://{netloc}{u.path}{query}"
    return canonical, _detect_platform_from_url(canonical)


def _normalize_video_url(raw: str) -> tuple[str | None, str | None]:
    """v3.1: dispatch a raw URL to the appropriate platform validator and
    return (canonical_url, platform). Tries YouTube first, then Twitter/X.
    Returns (None, None) for unsupported / attacker-shaped inputs."""
    yt = _normalize_youtube_url(raw)
    if yt:
        return yt, PLATFORM_YOUTUBE
    tw = _normalize_twitter_url(raw)
    if tw:
        return tw, PLATFORM_TWITTER
    return None, None


def _normalize_playlist_url(raw: str) -> str | None:
    """Return canonical YouTube playlist URL, or None for unsupported input.

    Accepts youtube.com/playlist?list=... and watch URLs that carry a list=
    parameter. The returned URL intentionally drops any watch `v=` start
    position; Playlist Mode always processes the selected playlist from the
    first entry after the Python-side cap is applied.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        u = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return None
    qs = parse_qs(u.query)
    list_id = (qs.get("list") or [""])[0]
    if not list_id or not _PLAYLIST_ID_RE.match(list_id):
        return None
    if u.path not in ("", "/", "/playlist", "/watch"):
        return None
    return f"https://www.youtube.com/playlist?list={list_id}"


def _is_valid_job_id(s: str) -> bool:
    return bool(s) and bool(_JOB_ID_RE.match(s))


INDEX_FILENAME = "_all-uoinks-index.md"
# Pre-rename master-index filename. Still read so the incremental updater can
# pick up (and supersede) a Yoink-era index that hasn't been regenerated yet.
INDEX_FILENAME_LEGACY = "_all-yoinks-index.md"


def _index_path() -> Path:
    """Master index location -- DESKTOP_ROOT/_all-uoinks-index.md. Leading
    underscore keeps it sorted to the top in Explorer."""
    return DESKTOP_ROOT / INDEX_FILENAME


def _corpus_path(folder: Path) -> Path:
    """Canonical corpus file path: <folder>/<folder.name>.md.

    Per-video filename matches the folder's slug so the file stays
    identifiable when moved out of its folder, and so the master index can
    link to it cleanly. The legacy filename was always 'yoink.md', which
    made every corpus indistinguishable once dragged out."""
    return folder / f"{folder.name}.md"


def _resolve_corpus_path(folder: Path) -> Path | None:
    """Return the corpus md file in `folder`, falling back to the legacy
    yoink.md name if the new <slug>.md isn't there yet. Returns None if
    neither exists."""
    candidate = _corpus_path(folder)
    if candidate.exists():
        return candidate
    legacy = folder / "yoink.md"
    if legacy.exists():
        return legacy
    return None


# ---- Multimodal paste corpus (clipboard version) -------------------------
# The on-disk <slug>.md keeps local image refs (screenshots/shot_NNNN.jpg)
# so VS Code preview / Obsidian render the file straight from the folder.
# The CLIPBOARD version inlines a curated subset of screenshots as base64
# data URIs so a single Ctrl+V into Claude or ChatGPT delivers transcript +
# images without the user having to re-upload anything.
#
PASTE_SCREENSHOT_WIDTH = 800
PASTE_SCREENSHOT_QUALITY = 80
PASTE_SIZE_WARN_MB = 4

_SCREENSHOT_BLOCK_RE = re.compile(
    r"### \[([^\]]+)\]\n\n!\[Screenshot at [^\]]+\]\(screenshots/(shot_\d+\.jpg)\)\n",
)


def _select_paste_indices(n: int, target: int) -> list[int]:
    """Pick `target` evenly-distributed indices from [0, n). Always includes
    0 and n-1 (linear interpolation lands on those endpoints exactly).
    Returns sorted unique indices, so a small `n` may produce fewer than
    target points after rounding collisions are deduped."""
    if target <= 0:
        return []
    if n <= target:
        return list(range(n))
    if target == 1:
        return [0]
    return sorted({round(i * (n - 1) / (target - 1)) for i in range(target)})


def _clipboard_screenshot_cap() -> int:
    settings = _read_settings()
    try:
        cap = int(settings.get("clipboard_screenshot_cap"))
    except (TypeError, ValueError):
        cap = CLIPBOARD_SCREENSHOT_CAP_DEFAULT
    return max(0, min(CLIPBOARD_SCREENSHOT_CAP_MAX, cap))


def _encode_screenshot_b64(path: Path, *, max_width: int, quality: int) -> str:
    """Resize + JPEG-recompress + base64 a screenshot for clipboard
    embedding. Imports Pillow lazily so the rest of server.py keeps
    working in dev environments where Pillow isn't installed (the
    bundled installer always ships it)."""
    from PIL import Image  # type: ignore[import-not-found]
    import base64
    import io
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > max_width:
        new_h = max(1, int(img.height * (max_width / img.width)))
        img = img.resize((max_width, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _paste_header(size_mb: float) -> str:
    """Lead-in for the clipboard corpus. The blockquote shape lets it
    survive paste into Claude / ChatGPT without breaking the surrounding
    transcript markup."""
    lines = [
        "> This corpus includes embedded images. When pasted into Claude or",
        "> ChatGPT, the AI sees both the transcript text and the screenshots",
        "> inline.",
    ]
    if size_mb > PASTE_SIZE_WARN_MB:
        lines.append(">")
        lines.append(
            f"> Note: This corpus is large ({size_mb:.1f} MB). If pasting"
            " into the AI fails, open the .md file directly and paste"
            " manually."
        )
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _generate_paste_corpus(folder: Path) -> str:
    """Build the clipboard version of the corpus from <folder>/<slug>.md.

    Replaces local image refs (`screenshots/shot_NNNN.jpg`) with base64
    data URIs for up to the configured clipboard_screenshot_cap
    evenly-distributed shots.
    Drops the rest of the per-shot blocks (so the markdown stays readable
    instead of silently shrinking only some images).

    Returns the empty string if the corpus file isn't found, falls back
    to the unmodified file content when Pillow isn't installed (dev mode
    without the bundled distribution)."""
    corpus_path = _resolve_corpus_path(folder)
    if corpus_path is None:
        return ""
    md = corpus_path.read_text(encoding="utf-8")

    try:
        from PIL import Image  # noqa: F401  -- import probe
    except ImportError:
        log.warning(
            "Pillow not installed; clipboard corpus will keep local image"
            " references. Install Pillow or rebuild via the installer."
        )
        return md

    matches = list(_SCREENSHOT_BLOCK_RE.finditer(md))
    if not matches:
        # No screenshots to embed -- still prepend the header so the user
        # can tell the clipboard version was generated. Size is just the
        # md length.
        size_mb = len(md.encode("utf-8")) / (1024 * 1024)
        return _paste_header(size_mb) + md

    cap = _clipboard_screenshot_cap()
    selected = set(_select_paste_indices(len(matches), cap)) if cap > 0 else set()
    kept_count = len(selected)
    reduction_note = ""
    if kept_count < len(matches):
        reduction_note = (
            f"[Showing {kept_count} of {len(matches)} screenshots in clipboard; "
            "full set on disk]\n\n"
        )

    # Counter-aware substitution: we need the index of each match to know
    # whether it's in the selected set, but re.sub doesn't pass an index.
    counter = {"i": 0}

    def replacer(m: re.Match) -> str:
        idx = counter["i"]
        counter["i"] += 1
        if idx not in selected:
            return ""  # drop this block entirely
        ts = m.group(1)
        shot_name = m.group(2)
        try:
            b64 = _encode_screenshot_b64(
                folder / "screenshots" / shot_name,
                max_width=PASTE_SCREENSHOT_WIDTH,
                quality=PASTE_SCREENSHOT_QUALITY,
            )
        except (OSError, ValueError) as e:
            log.warning("paste: failed to encode %s: %s", shot_name, e)
            return m.group(0)  # leave the original block on encode failure
        return (
            f"### [{ts}]\n\n"
            f"![Screenshot at {ts}](data:image/jpeg;base64,{b64})\n"
        )

    paste_md = _SCREENSHOT_BLOCK_RE.sub(replacer, md)
    size_mb = len(paste_md.encode("utf-8")) / (1024 * 1024)
    return _paste_header(size_mb) + reduction_note + paste_md


def _scan_yoinks() -> list[dict]:
    """Walk DESKTOP_ROOT/<topic>/<slug>/ and collect index metadata for
    every per-video yoink that still exists on disk. Folders the user has
    deleted simply drop out of future regenerations -- the index reflects
    what's actually there now, not historical state.

    Dedupes by URL: if the same video URL appears in two folders (e.g.,
    user yoinked it once, renamed the title in YouTube, yoinked again),
    keep the most recent. Falls back to relative path when URL is missing.

    Skips _sessions/ and any other underscore-prefixed top-level folder
    (the index file itself lives there, plus future internal folders)."""
    if not DESKTOP_ROOT.exists():
        return []
    by_key: dict[str, dict] = {}
    for topic_dir in DESKTOP_ROOT.iterdir():
        if not topic_dir.is_dir():
            continue
        if topic_dir.name.startswith("_") or topic_dir.name.startswith("."):
            continue
        topic = topic_dir.name
        for video_dir in topic_dir.iterdir():
            if not video_dir.is_dir():
                continue
            corpus = _resolve_corpus_path(video_dir)
            if corpus is None:
                continue

            title = video_dir.name
            url = ""
            channel = ""
            meta_path = video_dir / "metadata.json"
            if meta_path.exists():
                try:
                    m = json.loads(meta_path.read_text(encoding="utf-8"))
                    title = m.get("title") or title
                    url = (m.get("webpage_url")
                           or m.get("original_url") or "")
                    channel = (m.get("channel") or m.get("uploader") or "")
                except (OSError, json.JSONDecodeError):
                    pass

            mtime = corpus.stat().st_mtime
            yoinked_at = datetime.fromtimestamp(mtime).date().isoformat()
            rel_path = f"{topic}/{video_dir.name}/{corpus.name}"
            entry = {
                "title": title,
                "topic": topic,
                "channel": channel,
                "yoinked_at": yoinked_at,
                "yoinked_at_ts": mtime,
                "rel_path": rel_path,
                "url": url,
            }

            key = url or rel_path
            existing = by_key.get(key)
            if existing is None or mtime > existing["yoinked_at_ts"]:
                by_key[key] = entry
    return list(by_key.values())


def _render_index(entries: list[dict]) -> str:
    """Markdown for _all-uoinks-index.md. Topic sections sorted A-Z; videos
    within each topic sorted most-recent first. 'Recent (last 20)' section
    at the bottom for a quick chronological view."""
    parts = [
        "# All Uoinks",
        f"_Last updated: {_now_iso()}_  ",
        f"_Total uoinks: {len(entries)}_",
        "",
    ]

    if not entries:
        parts.append("_No uoinks yet. Click the rust U under any YouTube video to start._")
        parts.append("")
        return "\n".join(parts)

    # By topic
    parts.append("## By topic")
    parts.append("")
    by_topic: dict[str, list[dict]] = {}
    for e in entries:
        by_topic.setdefault(e["topic"], []).append(e)
    for topic in sorted(by_topic.keys(), key=str.lower):
        items = sorted(by_topic[topic], key=lambda x: x["yoinked_at_ts"], reverse=True)
        plural = "" if len(items) == 1 else "s"
        parts.append(f"### {topic} ({len(items)} uoink{plural})")
        for e in items:
            byline = f" -- {e['channel']}" if e["channel"] else ""
            parts.append(
                f"- [{e['title']}]({_md_link_path(e['rel_path'])}) "
                f"-- Uoinked {e['yoinked_at']}{byline}"
            )
        parts.append("")

    # Recent (last 20)
    recent = sorted(entries, key=lambda x: x["yoinked_at_ts"], reverse=True)[:20]
    parts.append("## Recent (last 20)")
    parts.append("")
    for e in recent:
        parts.append(
            f"- [{e['title']}]({_md_link_path(e['rel_path'])}) -- {e['yoinked_at']}"
        )
    parts.append("")

    return "\n".join(parts)


def _md_link_path(rel: str) -> str:
    """Markdown links want forward slashes. On Windows our Path joins
    produce backslashes; replace so Obsidian / VS Code preview / GitHub
    render the link correctly."""
    return rel.replace("\\", "/")


def _regenerate_index() -> None:
    """Rebuild _all-uoinks-index.md from a fresh scan of DESKTOP_ROOT.

    Best-effort: failures here shouldn't fail the uoink that triggered the
    regeneration, so we log + swallow rather than raise. Sprint 19.6 /
    Fix 6 removed this from the per-uoink hot path -- it now runs on
    demand from /open-index (and as a fallback from
    _incremental_index_update for first-launch / parse failure). The scan
    is O(N) in the library size; the incremental path is the steady state."""
    try:
        entries = _scan_yoinks()
        DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
        _index_path().write_text(_render_index(entries), encoding="utf-8")
        # v2.1 rename: supersede a leftover Yoink-era index so the Desktop
        # folder doesn't show two near-identical index files.
        legacy_index = DESKTOP_ROOT / INDEX_FILENAME_LEGACY
        if legacy_index != _index_path() and legacy_index.exists():
            legacy_index.unlink(missing_ok=True)
    except Exception as e:
        log.warning("index regeneration failed: %s", e)


def _start_full_index_regen_thread() -> None:
    """Background-thread shim for _regenerate_index, so the fallback paths
    in _incremental_index_update don't make the foreground yoink wait on
    a full-tree rescan."""
    threading.Thread(
        target=_regenerate_index, name="index-md-regen", daemon=True
    ).start()


def _patch_index_md(text: str, entry: dict) -> str | None:
    """Apply one new uoink to the rendered _all-uoinks-index.md, in place.

    Returns the updated markdown, or None when the file's structure isn't
    recognised (caller falls back to a full regen). Three edits:

    * Bump the header's total count and timestamp.
    * Prepend the entry to its topic subsection (creating the subsection
      if it doesn't yet exist).
    * Prepend the entry to the Recent section, capped at 20.
    """
    total_re = re.compile(r"_Total uoinks:\s*(\d+)_")
    if not total_re.search(text):
        # A Yoink-era index (with "_Total yoinks:_") won't match; returning
        # None makes the caller fall back to a full regen, which rewrites
        # the file in the new format under the new filename.
        return None
    text = total_re.sub(
        lambda m: f"_Total uoinks: {int(m.group(1)) + 1}_", text, count=1)
    text = re.sub(
        r"_Last updated:[^_\n]*_",
        f"_Last updated: {_now_iso()}_  ", text, count=1)

    topic = entry.get("topic") or "uncategorised"
    byline = f" -- {entry['channel']}" if entry.get("channel") else ""
    topic_line = (
        f"- [{entry['title']}]({_md_link_path(entry['rel_path'])}) "
        f"-- Uoinked {entry['yoinked_at']}{byline}"
    )
    topic_header_re = re.compile(
        rf"^### {re.escape(topic)} \((\d+) uoinks?\)\n", re.MULTILINE)
    m = topic_header_re.search(text)
    if m:
        new_count = int(m.group(1)) + 1
        plural = "" if new_count == 1 else "s"
        new_header = f"### {topic} ({new_count} uoink{plural})\n"
        text = text[:m.start()] + new_header + topic_line + "\n" + text[m.end():]
    else:
        # New topic -- insert a fresh subsection just before "## Recent".
        recent_anchor = text.find("\n## Recent ")
        if recent_anchor == -1:
            return None
        new_block = f"### {topic} (1 uoink)\n{topic_line}\n\n"
        text = text[:recent_anchor + 1] + new_block + text[recent_anchor + 1:]

    recent_header_re = re.compile(
        r"^## Recent \(last 20\)\n\n", re.MULTILINE)
    rm = recent_header_re.search(text)
    if not rm:
        return None
    recent_start = rm.end()
    rest = text[recent_start:]
    nxt = re.search(r"^##\s", rest, re.MULTILINE)
    recent_end = recent_start + (nxt.start() if nxt else len(rest))
    block = text[recent_start:recent_end]
    item_lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
    new_item = (
        f"- [{entry['title']}]({_md_link_path(entry['rel_path'])}) "
        f"-- {entry['yoinked_at']}"
    )
    capped = [new_item] + item_lines[:19]
    new_recent_block = "\n".join(capped) + "\n\n"
    text = text[:recent_start] + new_recent_block + text[recent_end:]
    return text


def _incremental_index_update(entry: dict) -> None:
    """Sprint 19.6 / Fix 6: append one new yoink to _all-yoinks-index.md
    without re-walking the whole library. Falls back to a background
    full-regen on first-launch / unreadable file / structural-parse
    failure so the foreground yoink never pays the O(N) scan cost.
    Best-effort -- an update failure here never fails the underlying
    yoink."""
    try:
        path = _index_path()
        if not path.exists():
            _start_full_index_regen_thread()
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("index file unreadable, scheduling full regen: %s", e)
            _start_full_index_regen_thread()
            return
        new_text = _patch_index_md(text, entry)
        if new_text is None:
            log.info("index file structure unrecognised, scheduling full regen")
            _start_full_index_regen_thread()
            return
        _atomic_write_text(path, new_text)
    except Exception as e:
        log.warning("incremental index update failed: %s", e)


def _is_valid_session_id(s: str) -> bool:
    """Session IDs become path segments under SESSIONS_ROOT, so anything
    that isn't a strict alphanumeric+_- token would let a caller traverse
    the filesystem (../, absolute paths, drive letters)."""
    return bool(s) and bool(_SESSION_ID_RE.match(s))


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---- Update check (Tier 2; notify-only) ----------------------------------
# Polls GitHub Releases, caches the result >=24h on disk so the dashboard can
# poll freely, and NEVER downloads or self-updates -- it only reports whether a
# newer tag exists and links out. Network/parse failures degrade silently.
_UPDATE_RELEASES_API = "https://api.github.com/repos/ryanbiddy/uoink/releases/latest"
_UPDATE_CACHE_PATH = DATA_ROOT / "update_check.json"
_UPDATE_CACHE_TTL_SEC = 24 * 3600
_update_check_lock = threading.Lock()


def _semver_tuple(v: str) -> tuple:
    """'v2.2.1' / '2.2.1' -> (2,2,1) for ordering. Trailing pre-release/build
    bits are dropped; missing parts pad with 0; non-numeric parts become 0."""
    core = (v or "").strip().lstrip("vV").split("+")[0].split("-")[0]
    parts: list[int] = []
    for p in core.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _check_for_update(*, force: bool = False) -> dict:
    """Notify-only update check. Cached >=24h; failures return
    {'update_available': False, 'error': ...} and are not cached so the next
    call retries. Never downloads anything."""
    now = time.time()
    with _update_check_lock:
        if not force:
            try:
                cached = json.loads(_UPDATE_CACHE_PATH.read_text(encoding="utf-8"))
                if now - float(cached.get("_ts", 0)) < _UPDATE_CACHE_TTL_SEC:
                    cached.pop("_ts", None)
                    cached["cached"] = True
                    return cached
            except (OSError, ValueError):
                pass
        req = urllib.request.Request(
            _UPDATE_RELEASES_API,
            headers={"User-Agent": "uoink-update-check",
                     "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                rel = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network down, rate-limited, malformed -- non-fatal
            log.debug("update check: fetch failed: %s", e)
            return {"current": VERSION, "latest": None, "update_available": False,
                    "url": None, "error": "offline", "checked_at": _now_iso(),
                    "cached": False}
        latest = str(rel.get("tag_name") or "").strip().lstrip("vV")
        result = {
            "current": VERSION,
            "latest": latest or None,
            "update_available": bool(latest) and _semver_tuple(latest) > _semver_tuple(VERSION),
            "url": rel.get("html_url"),
            "published_at": rel.get("published_at"),
            "checked_at": _now_iso(),
            "cached": False,
        }
        try:
            _UPDATE_CACHE_PATH.write_text(
                json.dumps({**result, "_ts": now}), encoding="utf-8")
        except OSError as e:
            log.debug("update check: cache write failed: %s", e)
        return result


# ---- Settings extras (Tier 2 dashboard Settings tab) ---------------------
def _mask_anthropic_key(key: str) -> str | None:
    """'sk-ant-…abcd' for display; None when no key is stored."""
    key = (key or "").strip()
    if not key:
        return None
    return (key[:6] + "…" + key[-4:]) if len(key) >= 12 else "set"


# Autostart Run key reuses the same HKCU value the installer writes.
_AUTOSTART_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_VALUE = "Uoink"


def _autostart_command() -> str:
    return f'"{HERE / "python" / "pythonw.exe"}" "{HERE / "server.py"}"'


def _autostart_enabled() -> bool | None:
    """True/False on Windows; None where there's no HKCU Run key (non-Windows)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_SUBKEY, 0,
                            winreg.KEY_READ) as k:
            try:
                winreg.QueryValueEx(k, _AUTOSTART_VALUE)
                return True
            except FileNotFoundError:
                return False
    except OSError:
        return None


def _set_autostart(enabled: bool) -> bool | None:
    """Set/clear the HKCU Run\\Uoink value. Returns True on success, None when
    unsupported (non-Windows), False on a registry error."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_SUBKEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, _AUTOSTART_VALUE, 0, winreg.REG_SZ,
                                  _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_VALUE)
                except FileNotFoundError:
                    pass
        log.info("autostart %s", "enabled" if enabled else "disabled")
        return True
    except OSError as e:
        log.warning("autostart toggle failed: %s", e)
        return False


def _validate_topics(topics) -> str | None:
    """Validate a topics-editor payload: list of {name:str, keywords:[str]}.
    Returns an error string, or None if valid."""
    if not isinstance(topics, list):
        return "topics must be a list"
    if len(topics) > 200:
        return "too many topics (max 200)"
    for t in topics:
        if not isinstance(t, dict):
            return "each topic must be an object"
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            return "each topic needs a non-empty name"
        kws = t.get("keywords", [])
        if not isinstance(kws, list) or not all(isinstance(k, str) for k in kws):
            return f"topic '{name}' keywords must be a list of strings"
    return None


def _write_topics(topics: list) -> None:
    """Persist the topics editor to topics.json, preserving any other keys."""
    try:
        existing = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {}
    except (OSError, ValueError):
        existing = {}
    existing["topics"] = [
        {"name": t["name"].strip(),
         "keywords": [k.strip() for k in t.get("keywords", []) if k.strip()]}
        for t in topics
    ]
    tmp = TOPICS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp.replace(TOPICS_PATH)


def _mcp_settings_snippet() -> dict:
    """MCP server config snippet for the Settings tab's Copy button. Points at
    the bundled stdio entry (uoink_mcp.py) under the install dir. (Distinct from
    _mcp_config_payload(), which serves the /mcp/v1/config protocol endpoint.)"""
    py = str(HERE / "python" / "python.exe")
    script = str(HERE / "uoink_mcp.py")
    entry = {"command": py, "args": [script]}
    cfg = {"mcpServers": {"uoink": entry}}
    return {"claude_desktop": cfg, "cursor": cfg,
            "raw": json.dumps(cfg, indent=2)}


def _focus_youtube_window() -> bool:
    """Best-effort "Open last YouTube tab": focus a visible top-level window
    whose title contains 'YouTube' (Chromium tabs read '… - YouTube … -
    Google Chrome' when a YouTube tab is foreground). Returns True if one was
    focused. ctypes-only (no pywin32 dependency); Windows-only. This is the
    'simpler heuristic' from the build plan -- it only catches a browser whose
    active tab is already YouTube; otherwise the caller opens youtube.com."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "YouTube" in buf.value:
                found.append(hwnd)
                return False  # stop enumerating
            return True

        user32.EnumWindows(_cb, 0)
        if found:
            user32.ShowWindow(found[0], 9)        # SW_RESTORE
            user32.SetForegroundWindow(found[0])
            return True
    except Exception as e:
        log.debug("open-last-youtube: window enum failed: %s", e)
    return False


def _session_folder(slug: str) -> Path:
    return SESSIONS_ROOT / slug


def _read_session(slug: str) -> dict | None:
    path = _session_folder(slug) / "session.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to read session %s: %s", slug, e)
        return None


def _write_session(slug: str, data: dict) -> None:
    folder = _session_folder(slug)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "session.json"
    tmp = folder / "session.json.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _all_sessions() -> list[dict]:
    if not SESSIONS_ROOT.exists():
        return []
    out = []
    for sub in SESSIONS_ROOT.iterdir():
        if not sub.is_dir():
            continue
        data = _read_session(sub.name)
        if data:
            out.append(data)
    out.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return out


def _active_session() -> dict | None:
    for s in _all_sessions():
        if s.get("status") == "open":
            return s
    return None


def _demote_headings(md: str) -> str:
    """Demote H1/H2 in a video's yoink.md so they nest under the corpus's H2.

    H1 -> H3, H2 -> H3 (we want everything below the per-video heading to read
    as a sub-section, but timestamp headings can stay at the same depth).
    """
    out_lines = []
    for ln in md.splitlines():
        m = re.match(r"^(#+)(\s)", ln)
        if m:
            level = len(m.group(1))
            new_level = min(level + 2, 6)
            ln = "#" * new_level + ln[level:]
        out_lines.append(ln)
    return "\n".join(out_lines)


def _build_corpus(session: dict) -> str:
    name = session.get("name") or session.get("slug")
    created = session.get("created_at", "")
    videos = session.get("videos", [])
    folder = _session_folder(session["slug"])

    parts = [
        f"# Research Session: {name}",
        f"# Created: {created}",
        f"# Videos: {len(videos)}",
        "",
        "---",
        "",
    ]
    for i, v in enumerate(videos, 1):
        title = v.get("title", "(unknown)")
        url = v.get("url", "")
        video_slug = v.get("video_slug", "")
        rel = f"{video_slug}/"
        # Resolver handles both <slug>.md (new) and yoink.md (legacy folders
        # captured before the rename).
        yoink_path = _resolve_corpus_path(folder / video_slug)

        parts.append(f"## Video {i}: {title}")
        parts.append(f"Source: {url}")
        parts.append(f"Local folder: {rel}")
        parts.append("")

        if yoink_path is not None and yoink_path.exists():
            try:
                body = yoink_path.read_text(encoding="utf-8")
                # Strip the per-video H1 (the title) -- we already emitted Video N: title.
                body = re.sub(r"^# .+\n", "", body, count=1)
                # Strip the leading metadata lines we'd duplicate (URL/Uoinked/etc.).
                # The bold-prefixed lines come right after the title block.
                body = re.sub(r"^(\*\*[^*]+:\*\*[^\n]*\n)+", "", body)
                parts.append(_demote_headings(body.strip()))
            except OSError as e:
                parts.append(f"> _Failed to read corpus file: {e}_")
        else:
            parts.append("> _Corpus file not found -- extraction may have failed._")

        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# v2 Playlist jobs
# ---------------------------------------------------------------------------
_IMAGE_REF_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$", re.MULTILINE)


def _strip_image_refs(md: str) -> str:
    """Clipboard playlist corpora are text-only; on-disk corpora keep images."""
    return _IMAGE_REF_LINE_RE.sub("", md)


def _strip_paste_header(md: str) -> str:
    """Remove the multimodal clipboard-only notice from persisted job text."""
    lines = md.splitlines()
    if not lines or not lines[0].startswith("> This corpus includes embedded images."):
        return md
    i = 0
    while i < len(lines) and (lines[i].startswith(">") or not lines[i].strip()):
        i += 1
    return "\n".join(lines[i:]).lstrip("\n")


def _job_text_only_corpus(md: str) -> str:
    """Small `/jobs` payload: no base64/data URI or local image references."""
    if not isinstance(md, str):
        return ""
    return _strip_image_refs(_strip_paste_header(md)).strip()


def _sanitize_single_job_result(result):
    """Strip legacy multimodal payloads from single-video job records."""
    if not isinstance(result, dict):
        return result
    clean = dict(result)
    clean.pop("corpus_md_paste", None)
    text = clean.get("combined_md_text")
    if isinstance(text, str):
        clean["combined_md_text"] = _job_text_only_corpus(text)
    return clean


def _coerce_nullable_int(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _video_url_from_flat_entry(e: dict) -> str | None:
    vid = e.get("id")
    if isinstance(vid, str) and _VIDEO_ID_RE.match(vid):
        return f"https://www.youtube.com/watch?v={vid}"
    raw = e.get("webpage_url") or e.get("url")
    if isinstance(raw, str):
        if _VIDEO_ID_RE.match(raw):
            return f"https://www.youtube.com/watch?v={raw}"
        return _normalize_youtube_url(raw)
    return None


def _fetch_playlist_preview(url: str) -> tuple[dict | None, str | None, int]:
    """Return (playlist, error, status_code) for a validated playlist URL."""
    normalized = _normalize_playlist_url(url)
    if not normalized:
        return None, "playlist URL invalid", 400
    try:
        cp = _run_subprocess(
            [*YTDLP_CMD, "--dump-single-json", "--flat-playlist", normalized],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMENTS_TIMEOUT_SEC,
        )
        data = json.loads(cp.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, OSError) as e:
        log.warning("playlist preview failed: %s", e)
        return None, "yt-dlp playlist preview failed", 200

    entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
    videos = []
    for e in entries:
        video_url = _video_url_from_flat_entry(e)
        if not video_url:
            continue
        videos.append({
            "index": len(videos) + 1,
            "id": e.get("id") if isinstance(e.get("id"), str) else None,
            "url": video_url,
            "title": e.get("title") or "(untitled)",
            "channel": e.get("channel") or e.get("uploader"),
            "duration_seconds": _coerce_nullable_int(e.get("duration")),
        })

    if not videos:
        return None, "playlist has no videos", 200

    raw_count = data.get("playlist_count") or data.get("n_entries")
    video_count = _coerce_nullable_int(raw_count) or len(videos)
    truncated = video_count > PLAYLIST_VIDEO_CAP or len(videos) > PLAYLIST_VIDEO_CAP
    capped = videos[:PLAYLIST_VIDEO_CAP]
    for i, v in enumerate(capped, 1):
        v["index"] = i
    warnings = ["playlist exceeds cap"] if truncated else []
    message = (
        f"Playlist has {video_count} videos -- yoinking the first {PLAYLIST_VIDEO_CAP}."
        if truncated else
        f"Playlist has {len(capped)} video{'s' if len(capped) != 1 else ''}."
    )
    playlist = {
        "url": normalized,
        "title": data.get("title") or "YouTube Playlist",
        "uploader": data.get("uploader") or data.get("channel"),
        "video_count": video_count,
        "cap": PLAYLIST_VIDEO_CAP,
        "will_process_count": len(capped),
        "truncated": truncated,
        "message": message,
        "warnings": warnings,
        "videos": capped,
    }
    return playlist, None, 200


def _make_job_id() -> str:
    return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _public_job(job: dict) -> dict:
    kind = job.get("kind") or "playlist"
    result = job.get("result")
    if kind == "single":
        result = _sanitize_single_job_result(result)
    return {
        "id": job.get("id"),
        "kind": kind,
        "state": job.get("state") or "failed",
        "source_url": job.get("source_url"),
        "title": job.get("title"),
        "playlist_title": job.get("playlist_title"),
        "session_folder": job.get("session_folder"),
        "videos_total": int(job.get("videos_total") or 0),
        "videos_done": int(job.get("videos_done") or 0),
        "videos_failed": int(job.get("videos_failed") or 0),
        "current_video": job.get("current_video"),
        "current_video_phase": job.get("current_video_phase"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "completed_at": job.get("completed_at"),
        "error": job.get("error"),
        "error_detail": job.get("error_detail"),
        "requested_long_video_mode": job.get("requested_long_video_mode"),
        "long_video_mode": job.get("long_video_mode"),
        "processed_media_seconds": job.get("processed_media_seconds"),
        "source_duration_seconds": job.get("source_duration_seconds"),
        "result": result,
        "warnings": list(job.get("warnings") or []),
        "message": job.get("message"),
    }


def _index_job_row(job: dict) -> dict:
    """Map an in-memory job dict (or an already-public job dict) to an index
    `jobs` table row. The full public projection is stored in metadata_json
    minus any corpus text -- jobs.metadata_json must never carry
    combined_md_text (the architectural bloat the Sprint 14b audit flagged)."""
    public = _public_job(job)
    result = public.get("result")
    if isinstance(result, dict) and "combined_md_text" in result:
        result = {k: v for k, v in result.items() if k != "combined_md_text"}
        public = {**public, "result": result}
    folder = job.get("session_folder")
    return {
        "job_id": job.get("id"),
        "kind": job.get("kind") or "playlist",
        "status": job.get("state") or "failed",
        "slug": Path(folder).name if folder else None,
        "title": job.get("title") or job.get("playlist_title"),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at") or _now_iso(),
        "metadata_json": json.dumps(public, ensure_ascii=False),
    }


def _persist_jobs_locked(changed_job: dict | None = None) -> None:
    """Persist job state into the library index. Caller must hold _jobs_lock.

    With `changed_job`, upserts just that one row -- the hot path: a single
    per-row SQLite write, replacing the old rewrite-the-entire-jobs.json-file
    pattern. With no argument, upserts every in-memory job (used once at
    restore, after non-terminal jobs are flipped to failed)."""
    try:
        idx = _get_index()
        jobs = [changed_job] if changed_job is not None else list(_jobs.values())
        for job in jobs:
            idx.upsert_job(_index_job_row(job))
    except Exception as e:
        log.warning("job persistence write failed: %s", e)


def _validate_persisted_job(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    job_id = raw.get("id")
    kind = raw.get("kind")
    state = raw.get("state")
    if not isinstance(job_id, str) or not job_id:
        return None
    if kind not in ("playlist", "single"):
        return None
    if state not in ("queued", "running", "completed", "cancelled", "failed"):
        return None

    job = _public_job(raw)
    if job["state"] not in _JOB_TERMINAL_STATES:
        now = _now_iso()
        job.update({
            "state": "failed",
            "current_video": None,
            "current_video_phase": None,
            "completed_at": now,
            "updated_at": now,
            "error": "server restarted",
            "error_detail": None,
            "result": None,
            "message": "Job failed because the Uoink helper restarted.",
        })
    return job


def _start_fresh_jobs(reason: str) -> None:
    log.warning("%s; starting fresh", reason)
    with _jobs_lock:
        _jobs.clear()
        _persist_jobs_locked()


def _restore_jobs_from_disk() -> None:
    """Hydrate the in-memory _jobs dict from the library index at startup.
    Non-terminal jobs are flipped to failed (their worker thread did not
    survive the restart) and the corrected state is written back.

    Named for historical continuity; the source is now index.db, not
    jobs.json (which _migrate_jobs_json_to_index folds in once)."""
    try:
        rows = _get_index().list_jobs(limit=1000)
    except Exception as e:
        log.warning("job restore from the index failed: %s", e)
        return
    restored: dict[str, dict] = {}
    for row in rows:
        meta = row.get("metadata_json")
        try:
            public = json.loads(meta) if meta else None
        except (json.JSONDecodeError, TypeError):
            public = None
        if not isinstance(public, dict):
            continue
        job = _validate_persisted_job(public)
        if job is not None:
            restored[job["id"]] = job
    with _jobs_lock:
        _jobs.clear()
        _jobs.update(restored)
        # _validate_persisted_job flipped non-terminal jobs to failed; write
        # those corrected states back so the index matches memory.
        _persist_jobs_locked()
    log.info("Restored %d job record(s) from the library index", len(restored))


def _migrate_jobs_json_to_index() -> None:
    """One-time: import a pre-Sprint-15 jobs.json into the index `jobs`
    table, then rename it to jobs.json.migrated. A no-op once the file is
    gone. combined_md_text is dropped by _index_job_row. On any error the
    source file is left intact and the helper still boots."""
    if not JOBS_PATH.exists():
        return
    try:
        raw = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
        jobs_raw = raw.get("jobs") if isinstance(raw, dict) else None
        if not isinstance(jobs_raw, list):
            jobs_raw = []
        idx = _get_index()
        imported = 0
        for item in jobs_raw:
            if isinstance(item, dict) and item.get("id"):
                idx.upsert_job(_index_job_row(item))
                imported += 1
        JOBS_PATH.replace(JOBS_PATH.with_name(JOBS_PATH.name + ".migrated"))
        log.info("Migrated %d job(s) from jobs.json into the index", imported)
    except Exception:
        log.exception("jobs.json migration failed; leaving the file in place")


def _supersede_terminal_single_jobs_locked(source_url: str, keep_id: str) -> None:
    """Drop older terminal single-video jobs for the same source URL.

    Caller must hold _jobs_lock. Every /extract attempt mints a fresh job
    id, so re-extracting a URL (a rate-limit retry, the retry worker, or the
    user re-yoinking) used to leave a second failed `single` job in _jobs.
    Both then rendered in Activity as identical failed rows (QA #42 -- the
    OpenClaw job twice). Activity's client-side dedupe only covers
    job-vs-queue, never job-vs-job, so the coalescing has to happen here at
    the source. Running/queued jobs are never touched -- they're live."""
    if not source_url:
        return
    stale = [
        jid for jid, j in _jobs.items()
        if jid != keep_id
        and j.get("kind") == "single"
        and j.get("source_url") == source_url
        and (j.get("state") or "") in _JOB_TERMINAL_STATES
    ]
    for jid in stale:
        _jobs.pop(jid, None)
        try:
            _get_index().delete_job(jid)
        except Exception as e:  # noqa: BLE001
            log.warning("could not drop superseded job %s: %s", jid, e)


def _add_job_record(job: dict) -> dict:
    with _jobs_lock:
        _jobs[job["id"]] = job
        # A new single-video attempt supersedes any prior terminal attempt
        # for the same URL, so Activity shows one row per source (G-14).
        if job.get("kind") == "single":
            _supersede_terminal_single_jobs_locked(
                job.get("source_url") or "", job["id"])
        _persist_jobs_locked(job)
        return _public_job(job)


def _record_single_extract_job(url: str, started_at: str, *,
                               result: dict | None = None,
                               error: str | None = None,
                               error_detail: str | None = None,
                               failure_phase: str | None = None,
                               long_video_mode: str | None = None,
                               title: str | None = None,
                               folder: Path | None = None) -> dict:
    now = _now_iso()
    ok = result is not None and not error
    folder_path = Path(result["folder"]) if result and result.get("folder") else folder
    corpus_path = _resolve_corpus_path(folder_path) if folder_path else None
    job = {
        "id": _make_job_id(),
        "kind": "single",
        "state": "completed" if ok else "failed",
        "source_url": url,
        "title": (result or {}).get("title") or title,
        "playlist_title": None,
        "session_folder": str(folder_path) if folder_path else None,
        "videos_total": 1,
        "videos_done": 1 if ok else 0,
        "videos_failed": 0 if ok else 1,
        "current_video": None,
        "current_video_phase": None if ok else failure_phase,
        "started_at": started_at,
        "updated_at": now,
        "completed_at": now,
        "error": None if ok else (error or "single-video extraction failed"),
        "error_detail": None if ok else error_detail,
        "requested_long_video_mode": (
            (result or {}).get("requested_long_video_mode") or long_video_mode
        ),
        "long_video_mode": (
            (result or {}).get("long_video_mode") or long_video_mode
        ),
        "processed_media_seconds": (
            (result or {}).get("processed_media_seconds")
        ),
        "source_duration_seconds": (
            (result or {}).get("source_duration_seconds")
        ),
        "result": {
            "combined_md_path": str(corpus_path) if corpus_path else None,
            # Full corpus text is intentionally NOT persisted into the
            # jobs.json record. jobs.json is re-serialized in full on every
            # job mutation, so storing per-extract corpus text grew the file
            # linearly with lifetime yoink count. Consumers read the corpus
            # from combined_md_path / folder on demand.
            "combined_md_text": "",
            "folder": str(folder_path) if folder_path else None,
            "requested_long_video_mode": result.get(
                "requested_long_video_mode"),
            "long_video_mode": result.get("long_video_mode"),
            "long_video_chunks": result.get("long_video_chunks") or [],
            "processed_media_seconds": result.get("processed_media_seconds"),
            "source_duration_seconds": result.get("source_duration_seconds"),
        } if ok else None,
        "warnings": [],
        "message": "Single-video yoink complete." if ok else "Single-video yoink failed.",
    }
    return _add_job_record(job)


def _get_public_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return _public_job(job) if job else None


def _update_job(job_id: str, **updates) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job.get("state") in _JOB_TERMINAL_STATES:
            return _public_job(job)
        job.update(updates)
        job["updated_at"] = _now_iso()
        _persist_jobs_locked(job)
        return _public_job(job)


def _job_cancel_event(job_id: str) -> threading.Event | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return job.get("_cancel_event") if job else None


def _list_public_jobs(kind: str | None = None) -> list[dict]:
    with _jobs_lock:
        jobs = [
            _public_job(j)
            for j in _jobs.values()
            if kind is None or j.get("kind") == kind
        ]
    return sorted(jobs, key=lambda j: j.get("updated_at") or "", reverse=True)


def _create_playlist_job(playlist: dict, interval: int) -> tuple[str, dict]:
    """Create + start a playlist job from an already-previewed playlist.

    Shared by the HTTP `/playlist/start` route and the MCP `yoink_playlist`
    tool so both entry points get identical job shapes and lifecycle.
    """
    job_id = _make_job_id()
    title = playlist.get("title") or "YouTube Playlist"
    folder_slug = slugify(title) or "playlist"
    folder = _session_folder(folder_slug)
    if folder.exists():
        folder = _session_folder(f"{folder_slug}_{job_id[-6:]}")
    cancel_event = threading.Event()
    now = _now_iso()
    job = {
        "id": job_id,
        "kind": "playlist",
        "state": "queued",
        "source_url": playlist["url"],
        "playlist_title": title,
        "session_folder": str(folder),
        "videos_total": playlist["will_process_count"],
        "videos_done": 0,
        "videos_failed": 0,
        "current_video": None,
        "current_video_phase": None,
        "started_at": None,
        "updated_at": now,
        "completed_at": None,
        "error": None,
        "result": None,
        "warnings": playlist.get("warnings") or [],
        "message": playlist.get("message"),
        "per_video": [],
        "_videos": playlist["videos"],
        "_interval": interval,
        "_folder": str(folder),
        "_cancel_event": cancel_event,
    }
    worker = threading.Thread(
        target=_playlist_worker,
        args=(job_id,),
        name=f"playlist-{job_id}",
        daemon=True,
    )
    job["_thread"] = worker
    with _jobs_lock:
        _jobs[job_id] = job
        _persist_jobs_locked(job)
        public = _public_job(job)
    worker.start()
    return job_id, public


def _cancel_playlist_job(job_id: str) -> tuple[dict | None, str | None, int]:
    """Cancel a running async job. Returns (job, error, status)."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None, "job not found", 404
        if job.get("state") in _JOB_TERMINAL_STATES:
            return None, "job is already finished", 200
        event = job.get("_cancel_event")
        if not isinstance(event, threading.Event):
            return None, "job cancel failed", 200
        event.set()
        now = _now_iso()
        job.update({
            "state": "cancelled",
            "current_video": None,
            "current_video_phase": None,
            "completed_at": now,
            "error": None,
            "result": None,
            "message": "Playlist job cancelled. Partial outputs were left on disk.",
            "updated_at": now,
        })
        _persist_jobs_locked(job)
        return _public_job(job), None, 200


def _unique_child_folder(parent: Path, preferred: str, used: set[str]) -> Path:
    base = slugify(preferred) or "video"
    slug = base
    n = 2
    while slug in used or (parent / slug).exists():
        slug = f"{base}_{n}"
        n += 1
    used.add(slug)
    return parent / slug


def _build_playlist_corpus(job: dict, *, text_only: bool) -> str:
    title = job.get("playlist_title") or "YouTube Playlist"
    parts = [
        f"# Playlist Corpus: {title}",
        f"**Source:** {job.get('source_url')}",
        f"**Uoinked:** {_now_iso()}",
        f"**Videos:** {job.get('videos_done', 0)} succeeded, {job.get('videos_failed', 0)} failed",
        "",
        "---",
        "",
    ]

    for item in job.get("per_video", []):
        title = item.get("title") or "(unknown)"
        url = item.get("url") or ""
        parts.append(f"## Video {item.get('index')}: {title}")
        parts.append(f"Source: {url}")
        if item.get("folder"):
            parts.append(f"Local folder: {item.get('folder')}")
        parts.append("")

        if not item.get("ok"):
            parts.append(f"> _Failed: {item.get('error') or 'unknown error'}_")
        else:
            md_path = item.get("md_path")
            try:
                body = Path(md_path).read_text(encoding="utf-8")
                body = re.sub(r"^# .+\n", "", body, count=1)
                body = re.sub(r"^(\*\*[^*]+:\*\*[^\n]*\n)+", "", body)
                if text_only:
                    body = _strip_image_refs(body)
                parts.append(_demote_headings(body.strip()))
            except (OSError, TypeError) as e:
                parts.append(f"> _Failed to read corpus file: {e}_")

        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Authenticated file serving for extension UI thumbnails
# ---------------------------------------------------------------------------
_SERVED_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _path_has_parent_ref(raw: str) -> bool:
    parts = str(raw).replace("\\", "/").split("/")
    return any(part == ".." for part in parts)


def _magic_matches(path: Path, mime: str) -> bool:
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    if mime == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if mime == "image/webp":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def _resolve_served_file(raw_path: str) -> tuple[Path | None, str | None, int, str | None]:
    if not raw_path:
        return None, None, 400, "path required"
    if _path_has_parent_ref(raw_path):
        return None, None, 400, "path invalid"
    try:
        p = Path(raw_path)
        if not p.is_absolute():
            return None, None, 400, "path invalid"
        resolved = p.resolve()
        if any(part == ".." for part in resolved.parts):
            return None, None, 400, "path invalid"
        # Sprint 19 / Wave 1 Fix 4: accept any allowed root, not just the
        # active DESKTOP_ROOT, so a yoink saved under Desktop\Yoink stays
        # readable after a switch to the LOCALAPPDATA fallback.
        if not _path_under_any(resolved, _allowed_roots()):
            return None, None, 403, "path escapes Uoink root"
    except (OSError, ValueError):
        return None, None, 400, "path invalid"

    if not resolved.exists() or not resolved.is_file():
        return None, None, 404, "file not found"
    try:
        if resolved.stat().st_size > MAX_SERVED_FILE_BYTES:
            return None, None, 400, "file too large"
    except OSError:
        return None, None, 404, "file not found"

    mime = _SERVED_IMAGE_TYPES.get(resolved.suffix.lower())
    if not mime or not _magic_matches(resolved, mime):
        return None, None, 415, "unsupported file type"
    return resolved, mime, 200, None


# ---------------------------------------------------------------------------
# Screenshot picker + re-yoink (D-20: pick screenshots on post / refresh source)
# ---------------------------------------------------------------------------
def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    """Read (width, height) from a JPEG or PNG header without a third-party
    image library. Walks JPEG segment markers to the SOFn frame header;
    reads the PNG IHDR. Returns (None, None) on anything it can't parse so
    the picker still lists the file, just without a known aspect ratio."""
    try:
        with open(path, "rb") as f:
            head = f.read(2)
            if head == b"\xff\xd8":  # JPEG (SOI)
                while True:
                    byte = f.read(1)
                    if not byte:
                        break
                    if byte != b"\xff":
                        continue
                    marker = f.read(1)
                    while marker == b"\xff":  # skip fill bytes
                        marker = f.read(1)
                    if not marker:
                        break
                    m = marker[0]
                    # Standalone markers carry no length payload.
                    if m == 0x01 or 0xD0 <= m <= 0xD9:
                        continue
                    length_bytes = f.read(2)
                    if len(length_bytes) < 2:
                        break
                    seg_len = int.from_bytes(length_bytes, "big")
                    # SOF0..SOF15 hold the frame dimensions (skip DHT/JPG/DAC).
                    if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                        frame = f.read(5)
                        if len(frame) < 5:
                            break
                        height = int.from_bytes(frame[1:3], "big")
                        width = int.from_bytes(frame[3:5], "big")
                        return width or None, height or None
                    f.seek(seg_len - 2, 1)
                return None, None
            if head == b"\x89P":  # PNG
                rest = f.read(24)
                buf = head + rest
                if len(buf) >= 24 and buf[:8] == b"\x89PNG\r\n\x1a\n":
                    width = int.from_bytes(buf[16:20], "big")
                    height = int.from_bytes(buf[20:24], "big")
                    return width or None, height or None
    except OSError:
        return None, None
    return None, None


def _screenshot_list_for_yoink(idx, video_id: str) -> dict | None:
    """Build the picker payload for a yoink: every available screenshot with
    its absolute path, a /file URL the dashboard can render, the capture
    timestamp, and pixel dimensions. The sidecar's structured screenshot
    list is the source of truth; a filesystem glob backstops it so a fresh
    re-yoink whose sidecar hasn't been re-read still surfaces its shots.

    Returns None when the yoink id is unknown. A capture with no screenshots
    (text / page yoinks) returns an empty list, not None -- the picker shows
    a "text-only, nothing to attach" state for those."""
    from urllib.parse import quote

    row = idx.get_yoink(video_id)
    if not row:
        return None

    corpus_path = row.get("corpus_path") or ""
    sidecar_path = row.get("sidecar_path") or ""
    folder = Path(corpus_path).parent if corpus_path else None

    sidecar: dict = {}
    if sidecar_path and Path(sidecar_path).exists():
        try:
            sidecar = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sidecar = {}

    interval = sidecar.get("interval_seconds")
    try:
        interval = int(interval) if interval else None
    except (TypeError, ValueError):
        interval = None

    def _entry(name: str, index: int, ts_human, ts_secs, abs_path: Path) -> dict:
        width, height = _image_dimensions(abs_path)
        return {
            "index": index,
            "filename": name,
            "timestamp": ts_human,
            "timestamp_seconds": ts_secs,
            "rel_path": f"screenshots/{name}",
            "path": str(abs_path),
            "file_url": "/file?path=" + quote(str(abs_path)),
            "width": width,
            "height": height,
        }

    entries: list[dict] = []
    seen: set[str] = set()
    shots_dir = (folder / "screenshots") if folder else None

    for i, shot in enumerate(sidecar.get("screenshots") or []):
        if not isinstance(shot, dict):
            continue
        name = (shot.get("filename") or Path(shot.get("path") or "").name).strip()
        if not name or not shots_dir:
            continue
        abs_path = shots_dir / name
        if not abs_path.exists():
            continue  # referenced but gone; don't offer a broken thumbnail
        seen.add(name)
        ts_secs = _parse_hms(shot.get("timestamp"))
        if ts_secs is None and interval is not None:
            ts_secs = i * interval
        entries.append(_entry(name, i, shot.get("timestamp"), ts_secs, abs_path))

    # Filesystem backstop: shots on disk the sidecar didn't list (re-yoink
    # drift). Derive the timestamp from the shot number when we know the
    # interval so the picker still labels them.
    if shots_dir and shots_dir.is_dir():
        for p in sorted(shots_dir.glob("shot_*.jpg")):
            if p.name in seen:
                continue
            match = re.match(r"shot_(\d+)", p.stem)
            shot_no = int(match.group(1)) if match else (len(entries) + 1)
            ts_secs = ((shot_no - 1) * interval) if interval is not None else None
            ts_human = fmt_time(ts_secs) if ts_secs is not None else None
            entries.append(_entry(p.name, len(entries), ts_human, ts_secs, p))

    return {
        "video_id": video_id,
        "title": row.get("title"),
        "folder": str(folder) if folder else None,
        "interval_seconds": interval,
        "count": len(entries),
        "screenshots": entries,
    }


def _reyoink_source(idx, video_id: str) -> tuple[str, int | None] | None:
    """Resolve the original source URL + capture interval for a yoink so it
    can be re-captured. Returns None when the yoink is unknown; ('', None)
    when it has no saved source link (e.g. a manual import)."""
    row = idx.get_yoink(video_id)
    if not row:
        return None
    sidecar_path = row.get("sidecar_path") or ""
    url = ""
    interval = None
    if sidecar_path and Path(sidecar_path).exists():
        try:
            sidecar = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
            url = (sidecar.get("url") or "").strip()
            raw_interval = sidecar.get("interval_seconds")
            interval = int(raw_interval) if raw_interval else None
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return url, interval


# ---------------------------------------------------------------------------
# Screenshot picker v3.2.4 -- visual-diff dedup + auto-suggest (grid UI)
# ---------------------------------------------------------------------------
# A small perceptual "average hash" (aHash) is enough to spot near-duplicate
# frames (a static talking-head shot that barely changes for a minute). We
# lazy-import Pillow -- it's a bundled dependency (requirements.txt) but the
# helper must never crash the picker if a broken bundle ships without it, so
# every caller treats "no Pillow" as "dedup unavailable, return everything".
_AHASH_SIDE = 8  # 8x8 -> 64-bit hash


def _ahash_file(path: Path) -> int | None:
    """64-bit average hash of an image, or None when it can't be read.

    No third-party dep is *required*: returns None if Pillow is missing so
    the picker degrades to "show all frames" rather than erroring."""
    try:
        from PIL import Image  # lazy: bundled, but optional at runtime
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            small = im.convert("L").resize(
                (_AHASH_SIDE, _AHASH_SIDE), Image.BILINEAR)
            pixels = list(small.getdata())
    except Exception:
        return None
    if not pixels:
        return None
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, px in enumerate(pixels):
        if px >= avg:
            bits |= (1 << i)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _dedupe_screenshot_entries(entries: list[dict], *,
                               threshold: int = 5) -> tuple[list[dict], int, bool]:
    """Drop frames that are visually near-identical to the last frame we
    kept, comparing average-hashes with a Hamming-distance threshold.

    Comparing against the *last kept* frame (not the immediate predecessor)
    means a slow pan still surfaces periodic frames instead of collapsing to
    one. Returns (kept, removed_count, dedupe_available). When Pillow is
    unavailable for the very first frame we bail and return everything with
    dedupe_available=False so the transport can tell the UI."""
    if not entries:
        return entries, 0, True
    kept: list[dict] = []
    last_hash: int | None = None
    any_hash = False
    for entry in entries:
        h = _ahash_file(Path(entry["path"])) if entry.get("path") else None
        if h is None:
            # Unhashable (or no Pillow): never silently drop a frame we
            # couldn't compare. Keep it and reset the anchor.
            kept.append(entry)
            last_hash = None
            continue
        any_hash = True
        if last_hash is not None and _hamming(h, last_hash) <= threshold:
            continue  # near-duplicate of the last kept frame
        kept.append(entry)
        last_hash = h
    removed = len(entries) - len(kept)
    return kept, removed, any_hash


def _screenshot_dedupe_query(qs: dict) -> tuple[bool, int]:
    dedupe = (qs.get("dedupe") or [""])[0].strip().lower() in (
        "1", "true", "yes")
    try:
        threshold = int((qs.get("dedupe_threshold") or ["5"])[0])
    except (TypeError, ValueError):
        threshold = 5
    return dedupe, max(0, min(32, threshold))


def _apply_screenshot_dedupe(payload: dict, *, threshold: int) -> dict:
    kept, removed, available = _dedupe_screenshot_entries(
        payload.get("screenshots") or [], threshold=threshold)
    payload["screenshots"] = kept
    payload["count"] = len(kept)
    payload["deduped"] = True
    payload["dedupe_removed"] = removed
    payload["dedupe_available"] = available
    payload["dedupe_threshold"] = threshold
    return payload


def _even_indices(n: int, count: int) -> list[int]:
    """`count` indices spread evenly across range(n), endpoints included,
    de-duplicated and sorted. Used by the thread/blog auto-suggest."""
    if n <= 0 or count <= 0:
        return []
    if count == 1:
        return [n // 2]
    if count >= n:
        return list(range(n))
    out = sorted({round(i * (n - 1) / (count - 1)) for i in range(count)})
    # Rounding collisions can leave us short; backfill from the gaps.
    i = 0
    while len(out) < count and i < n:
        if i not in out:
            out.append(i)
        i += 1
    return sorted(out)[:count]


# Auto-suggest defaults. The corpus carries a *video-level* hook_type
# classification but no per-timestamp hook position (see sidecar schema), so
# "best frame for a tweet" is a documented heuristic: skip the cold-open and
# land just inside the opening zone where the hook is delivered on camera.
_HOOK_ZONE_FRACTION = 0.08   # ~8% into the timeline
_BLOG_SUGGEST_COUNT = 5      # 3-5; we aim for 5 and clamp to what's available
_THREAD_MIN, _THREAD_MAX = 3, 8


def _suggest_screenshots(payload: dict, *, mode: str,
                         thread_size: int | None = None) -> dict:
    """Pick a sensible default frame set for tweet / thread / blog.

    tweet  -> 1 frame in the hook zone (heuristic; see _HOOK_ZONE_FRACTION).
    thread -> one frame per post, evenly distributed across the timeline.
    blog   -> 3-5 frames sampled start/mid/end.

    Returns a dict with the chosen entries + the indices + the strategy used
    so the UI (and the convergence doc) can show *why* these frames."""
    entries = payload.get("screenshots") or []
    n = len(entries)
    mode = (mode or "").strip().lower()
    if mode not in ("tweet", "thread", "blog"):
        raise ValueError("mode must be one of tweet|thread|blog")

    if n == 0:
        return {"mode": mode, "strategy": "empty", "count": 0,
                "indices": [], "selected": []}

    if mode == "tweet":
        idx = max(1, round(_HOOK_ZONE_FRACTION * (n - 1))) if n > 1 else 0
        indices = [idx]
        strategy = "hook_zone_heuristic"
    elif mode == "thread":
        size = thread_size if isinstance(thread_size, int) else 5
        size = max(_THREAD_MIN, min(_THREAD_MAX, size))
        indices = _even_indices(n, size)
        strategy = "even_distribution"
    else:  # blog
        count = min(_BLOG_SUGGEST_COUNT, n)
        count = max(min(3, n), count)
        indices = _even_indices(n, count)
        strategy = "start_mid_end_zones"

    selected = [entries[i] for i in indices if 0 <= i < n]
    return {
        "mode": mode,
        "strategy": strategy,
        "thread_size": (thread_size if mode == "thread" else None),
        "count": len(selected),
        "indices": indices,
        "selected": selected,
    }


# ---------------------------------------------------------------------------
# MCP HTTP transport helpers
# ---------------------------------------------------------------------------
MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}


def _mcp_tools_module():
    import uoink_mcp_tools

    uoink_mcp_tools.bind_backend(sys.modules[__name__])
    return uoink_mcp_tools


def _mcp_request_id(body: dict):
    return body.get("id") if isinstance(body, dict) else None


def _mcp_initialize_result(body: dict) -> dict:
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    requested = params.get("protocolVersion")
    protocol = (
        requested
        if isinstance(requested, str) and requested in MCP_SUPPORTED_PROTOCOL_VERSIONS
        else MCP_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol,
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "uoink",
            "version": VERSION,
        },
        "instructions": (
            "Uoink exposes local YouTube extraction tools. Outputs are stored "
            "under the user's Uoink output folder on this machine."
        ),
    }


def _mcp_stdio_command() -> tuple[str, list[str]]:
    """Command/args for client config snippets.

    Installed builds should use the bundled console `python.exe` for stdio;
    `pythonw.exe` has no standard streams and would break JSON-RPC.
    """
    bundled = HERE / "python" / "python.exe"
    command = bundled if bundled.exists() else Path(sys.executable)
    return str(command), [str(HERE / "uoink_mcp.py")]


def _mcp_config_payload() -> dict:
    command, args = _mcp_stdio_command()
    return {
        "ok": True,
        "stdio": {
            "command": command,
            "args": args,
        },
        "http": {
            "url": f"http://{HOST}:{PORT}/mcp/v1",
            "sse_url": f"http://{HOST}:{PORT}/mcp/v1/sse",
            "auth_header": "X-Uoink-Token",
        },
    }


# ---------------------------------------------------------------------------
# Fix 4A -- one-click agent setup. Detect installed desktop AI clients and
# write Uoink's MCP server entry into their config in place (with a backup).
# Creator-facing: the dashboard turns these into "Connect Claude Desktop"
# buttons instead of dumping raw JSON. Detection is read-only; connect only
# ever edits a JSON config file -- it never installs or launches anything.
# ---------------------------------------------------------------------------
# Canonical client ids the connect endpoint accepts.
AGENT_CLIENTS = ("claude-desktop", "cursor", "cline", "continue")


def _env_dir(var: str) -> Path | None:
    val = os.environ.get(var)
    return Path(val) if val else None


def _agent_client_specs() -> list[dict]:
    """Per-client detection spec: the config file we'd edit, plus the marker
    paths whose existence means "this client is installed". Windows-first
    (the only shipped build today); falls back to ~/.<client> paths that are
    correct on macOS/Linux too so the logic is portable when the Mac build
    lands."""
    home = Path.home()
    appdata = _env_dir("APPDATA") or (home / "AppData" / "Roaming")
    local = _env_dir("LOCALAPPDATA") or (home / "AppData" / "Local")
    code_user = appdata / "Code" / "User"
    return [
        {
            "name": "claude-desktop",
            "label": "Claude Desktop",
            "config_path": appdata / "Claude" / "claude_desktop_config.json",
            "markers": [appdata / "Claude",
                        local / "AnthropicClaude",
                        local / "Programs" / "claude"],
        },
        {
            "name": "cursor",
            "label": "Cursor",
            # Cursor reads global MCP servers from ~/.cursor/mcp.json.
            "config_path": home / ".cursor" / "mcp.json",
            "markers": [home / ".cursor",
                        appdata / "Cursor",
                        local / "Programs" / "cursor"],
        },
        {
            "name": "cline",
            "label": "Cline",
            # Cline (VS Code extension) keeps its MCP servers here.
            "config_path": (code_user / "globalStorage"
                            / "saoudrizwan.claude-dev" / "settings"
                            / "cline_mcp_settings.json"),
            # Plain VS Code is not Cline. Require Cline's own extension
            # storage marker so detection does not offer a false connect.
            "markers": [code_user / "globalStorage" / "saoudrizwan.claude-dev"],
        },
        {
            "name": "continue",
            "label": "Continue",
            "config_path": home / ".continue" / "config.json",
            "markers": [home / ".continue"],
        },
    ]


def _agent_client_spec(name: str) -> dict | None:
    name = (name or "").strip().lower()
    for spec in _agent_client_specs():
        if spec["name"] == name:
            return spec
    return None


def _uoink_mcp_entry() -> dict:
    """The mcpServers entry every client gets: the bundled stdio command."""
    command, args = _mcp_stdio_command()
    return {"command": command, "args": args}


def _client_is_connected(config_path: Path) -> bool:
    """True when the client's config already lists a `uoink` mcpServers entry.
    Best-effort: an unreadable / non-JSON file reads as not-connected."""
    try:
        if not config_path.exists():
            return False
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and "uoink" in servers


def _detect_ai_clients() -> list[dict]:
    """Scan for installed desktop AI clients. Pure read; never writes."""
    out: list[dict] = []
    for spec in _agent_client_specs():
        installed = any(p.exists() for p in spec["markers"])
        cfg = spec["config_path"]
        out.append({
            "name": spec["name"],
            "label": spec["label"],
            "installed": installed,
            "config_path": str(cfg),
            "config_exists": cfg.exists(),
            "connected": _client_is_connected(cfg),
        })
    return out


def _connect_ai_client(name: str) -> dict:
    """Add Uoink's MCP server entry to a client's config file in place.

    Validates existing JSON before touching it (a malformed config is left
    untouched and reported, never clobbered), writes a `.bak` copy first, then
    atomically rewrites the file with the `uoink` entry merged into
    `mcpServers`. Returns a result dict; raises ValueError (mapped to 4xx) for
    an unknown client or a missing parent directory ("not installed")."""
    spec = _agent_client_spec(name)
    if spec is None:
        e = ValueError("That AI client is not supported.")
        e.http_status = 404
        raise e
    cfg: Path = spec["config_path"]
    installed = any(p.exists() for p in spec["markers"])
    if not installed and not cfg.parent.exists():
        e = ValueError(
            f"{spec['label']} doesn't look installed on this machine.")
        e.http_status = 409
        raise e

    existed = cfg.exists()
    data: dict = {}
    if existed:
        try:
            raw = cfg.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("agent connect: config read failed (%s)", exc)
            e = ValueError(
                f"Couldn't read the {spec['label']} settings. "
                "Nothing was changed.")
            e.http_status = 500
            raise e
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                e = ValueError(
                    f"{spec['label']} settings aren't valid JSON; "
                    "left it untouched. Open it and fix the syntax, then "
                    "try connecting again.")
                e.http_status = 422
                raise e
            if not isinstance(parsed, dict):
                e = ValueError(
                    f"{spec['label']} config isn't a JSON object; "
                    "left it untouched.")
                e.http_status = 422
                raise e
            data = parsed

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    already = "uoink" in servers
    servers["uoink"] = _uoink_mcp_entry()
    data["mcpServers"] = servers

    backup_path = cfg.with_suffix(cfg.suffix + ".bak")
    try:
        cfg.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("agent connect: settings directory unavailable (%s)", exc)
        e = ValueError(
            f"Couldn't prepare the {spec['label']} settings folder. "
            "Nothing was changed.")
        e.http_status = 500
        raise e
    if existed:
        try:
            shutil.copy2(cfg, backup_path)
        except OSError as exc:
            log.warning("agent connect: backup failed (%s)", exc)
            e = ValueError(
                f"Couldn't back up the {spec['label']} settings, so Uoink "
                "refused to change them.")
            e.http_status = 500
            raise e
    else:
        backup_path = None

    tmp = cfg.with_suffix(cfg.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(cfg)
    except OSError as exc:
        log.warning("agent connect: config write failed (%s)", exc)
        tmp.unlink(missing_ok=True)
        e = ValueError(
            f"Couldn't update the {spec['label']} settings. "
            "The original settings were left in place.")
        e.http_status = 500
        raise e
    log.info("agent connect: wrote uoink mcpServers entry to %s", cfg)
    return {
        "client": spec["name"],
        "label": spec["label"],
        "config_path": str(cfg),
        "backup_path": (str(backup_path) if backup_path else None),
        "action": "updated" if already else "added",
        "created_config": not existed,
        "entry": servers["uoink"],
    }


def _finish_job_cancelled(job_id: str):
    _update_job(
        job_id,
        state="cancelled",
        current_video=None,
        current_video_phase=None,
        completed_at=_now_iso(),
        error=None,
        result=None,
        message="Playlist job cancelled. Partial outputs were left on disk.",
    )


def _write_failed_marker(folder: Path, *, url: str | None,
                         index: int | None, reason: str) -> None:
    lines = [
        "Uoink playlist item failed",
        "",
        f"Timestamp: {_now_iso()}",
    ]
    if index is not None:
        lines.append(f"Playlist index: {index}")
    if url:
        lines.append(f"URL: {url}")
    lines.extend(["", "Reason:", reason, ""])
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(folder / "FAILED.txt", "\n".join(lines))
    except OSError as e:
        log.warning("could not write playlist failure marker: %s", e)


def _playlist_worker(job_id: str):
    public = _get_public_job(job_id)
    if not public:
        return
    cancel_event = _job_cancel_event(job_id)
    used_slugs: set[str] = set()

    with _jobs_lock:
        job = _jobs.get(job_id)
        videos = list(job.get("_videos") or []) if job else []
        interval = int(job.get("_interval") or 30) if job else 30
        folder = Path(job.get("_folder")) if job else SESSIONS_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=True)

    if cancel_event is not None and cancel_event.is_set():
        _finish_job_cancelled(job_id)
        return

    _update_job(
        job_id,
        state="running",
        started_at=_now_iso(),
        message=f"Uoinking video 1 of {len(videos)}." if videos else "Starting playlist job.",
    )

    per_video = []
    videos_done = 0
    videos_failed = 0
    rate_limit_hits = 0
    last_failure_phase = None

    try:
        for v in videos:
            _raise_if_cancelled(cancel_event)
            if per_video and PLAYLIST_SLEEP_SEC > 0:
                _update_job(
                    job_id,
                    message=(
                        f"Waiting {PLAYLIST_SLEEP_SEC:g}s before the next video "
                        "to avoid YouTube rate limits."
                    ),
                )
                _sleep_with_cancel(PLAYLIST_SLEEP_SEC, cancel_event)
            idx = int(v.get("index") or (len(per_video) + 1))
            current = {
                "index": idx,
                "title": v.get("title") or "(untitled)",
                "url": v.get("url"),
            }
            target: Path | None = None
            current_phase = "metadata"
            _update_job(
                job_id,
                current_video=current,
                current_video_phase=current_phase,
                message=f"Uoinking video {idx} of {len(videos)}.",
            )

            try:
                metadata = _fetch_metadata(v["url"], cancel_event=cancel_event)
                title = metadata.get("title") or current["title"] or "Untitled"
                current["title"] = title
                target = _unique_child_folder(folder, title, used_slugs)
                _update_job(job_id, current_video=current)

                def phase_cb(phase: str, *, _job_id=job_id):
                    nonlocal current_phase
                    current_phase = phase
                    _update_job(_job_id, current_video_phase=phase)

                with _extract_lock:
                    _raise_if_cancelled(cancel_event)
                    result = _run_extraction(
                        v["url"],
                        interval,
                        target,
                        open_explorer=False,
                        metadata=metadata,
                        topic="Playlist",
                        generate_paste=False,
                        cancel_event=cancel_event,
                        phase_callback=phase_cb,
                    )

                corpus_path = _resolve_corpus_path(target)
                item = {
                    "index": idx,
                    "title": result.get("title") or title,
                    "url": v["url"],
                    "folder": str(target),
                    "md_path": str(corpus_path) if corpus_path else None,
                    "json_path": str(target / f"{target.name}.json"),
                    "ok": True,
                    "error": None,
                }
                per_video.append(item)
                videos_done += 1
                _update_job(
                    job_id,
                    videos_done=videos_done,
                    current_video_phase="done",
                    message=f"Finished video {idx} of {len(videos)}.",
                )
            except PlaylistJobCancelled:
                raise
            except BaseException as e:
                msg = friendly_error(e)
                detail = machine_error_detail(e)
                failure_phase = _failure_phase(e, current_phase)
                last_failure_phase = failure_phase
                log.error("playlist job %s video %d failed: %s", job_id, idx, msg)
                if target is None:
                    target = _unique_child_folder(
                        folder,
                        current.get("title") or v.get("id") or f"video-{idx}",
                        used_slugs,
                    )
                _write_failed_marker(
                    target,
                    url=v.get("url"),
                    index=idx,
                    reason=msg,
                )
                per_video.append({
                    "index": idx,
                    "title": current.get("title") or "(untitled)",
                    "url": v.get("url"),
                    "folder": str(target),
                    "md_path": None,
                    "json_path": None,
                    "failed_marker_path": str(target / "FAILED.txt"),
                    "ok": False,
                    "error": msg,
                    "error_detail": detail,
                    "error_phase": failure_phase,
                })
                videos_failed += 1
                _update_job(
                    job_id,
                    videos_failed=videos_failed,
                    current_video_phase=failure_phase,
                    message=f"Video {idx} failed; continuing.",
                )
                if _is_rate_limit_error(e):
                    rate_limit_hits += 1
                    backoff = min(
                        PLAYLIST_RATE_LIMIT_BACKOFF_MAX_SEC,
                        PLAYLIST_RATE_LIMIT_BACKOFF_BASE_SEC * (2 ** (rate_limit_hits - 1)),
                    )
                    _update_job(
                        job_id,
                        message=(
                            "YouTube appears to be rate-limiting; backing off "
                            f"for {backoff:g}s before continuing."
                        ),
                    )
                    _sleep_with_cancel(backoff, cancel_event)

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["per_video"] = per_video
                job["videos_done"] = videos_done
                job["videos_failed"] = videos_failed
                _persist_jobs_locked(job)

        _raise_if_cancelled(cancel_event)
        if videos_done == 0:
            _update_job(
                job_id,
                state="failed",
                current_video=None,
                current_video_phase=last_failure_phase,
                completed_at=_now_iso(),
                error="playlist extraction failed: zero videos succeeded",
                result=None,
                message="Playlist failed: zero videos succeeded.",
            )
            return

        with _jobs_lock:
            job = dict(_jobs[job_id])
        disk_md = _build_playlist_corpus(job, text_only=False)
        clipboard_md = _build_playlist_corpus(job, text_only=True)
        corpus_path = folder / "corpus.md"
        _atomic_write_text(corpus_path, disk_md)
        _raise_if_cancelled(cancel_event)
        result = {
            "combined_md_path": str(corpus_path),
            "combined_md_text": clipboard_md,
            "per_video": per_video,
        }
        _update_job(
            job_id,
            state="completed",
            current_video=None,
            current_video_phase=None,
            completed_at=_now_iso(),
            error=None,
            result=result,
            message="Playlist complete.",
        )
    except PlaylistJobCancelled:
        log.info("playlist job %s cancelled", job_id)
        _finish_job_cancelled(job_id)
    except BaseException as e:
        msg = friendly_error(e)
        detail = machine_error_detail(e)
        failure_phase = _failure_phase(
            e, (_get_public_job(job_id) or {}).get("current_video_phase"))
        log.error("playlist job %s failed: %s", job_id, msg)
        _update_job(
            job_id,
            state="failed",
            current_video=None,
            current_video_phase=failure_phase,
            completed_at=_now_iso(),
            error=msg,
            error_detail=detail,
            result=None,
            message="Playlist failed.",
        )


# ---------------------------------------------------------------------------
# Soft delete -- _yoink-trash/ (Sprint 18 / B1)
# ---------------------------------------------------------------------------
def _trash_root() -> Path:
    """The trash folder soft-deleted yoinks are moved into."""
    return DESKTOP_ROOT / "_yoink-trash"


def _fs_safe_ts(iso: str) -> str:
    """A filesystem-safe rendering of an ISO timestamp -- drops the colons
    Windows forbids in path names. Deterministic, so a trash folder name
    can be recomputed from the stored deleted_at."""
    return (iso or "").replace(":", "")


def _trash_folder_for(row: dict) -> Path:
    """The trash destination for a soft-deleted yoink row:
    _yoink-trash/<topic-folder>/<slug>__deleted-<deleted_at>. Derived from
    corpus_path so it mirrors the on-disk topic folder exactly, and from
    deleted_at so delete / restore / purge all agree on the same path."""
    original = Path(row["corpus_path"]).parent
    topic_folder = original.parent.name
    slug = original.name
    ts = _fs_safe_ts(row.get("deleted_at") or "")
    return _trash_root() / topic_folder / f"{slug}__deleted-{ts}"


# Trash purge cadence: a pass at startup, then once a day.
_TRASH_PURGE_INTERVAL_SEC = 24 * 60 * 60


def _purge_trash() -> int:
    """One trash-purge pass: hard-delete every soft-deleted yoink past the
    30-day retention window -- both its _yoink-trash/ folder and its index
    row (the FK cascade then clears its citations, entity_mentions, and
    taxonomy_corrections). Returns the number purged."""
    try:
        idx = _get_index()
        stale = idx.prune_trash(datetime.now())
    except Exception as e:
        log.warning("trash purge: could not query the index: %s", e)
        return 0
    purged = 0
    for video_id in stale:
        row = idx.get_yoink(video_id)
        if not row:
            continue
        try:
            trash = _trash_folder_for(row)
            if trash.exists():
                shutil.rmtree(trash, ignore_errors=True)
            idx.delete_yoink(video_id)
            purged += 1
        except Exception:
            log.exception("trash purge: failed to purge %s", video_id)
    if purged:
        log.info("trash purge: hard-removed %d expired yoink(s)", purged)
    return purged


def _start_trash_purge_thread() -> None:
    """Run the trash purge once at startup, then every 24h. Daemon thread
    so it never delays the bind or blocks shutdown."""
    def _runner():
        while True:
            try:
                _purge_trash()
            except Exception:
                log.exception("trash purge pass crashed")
            time.sleep(_TRASH_PURGE_INTERVAL_SEC)

    threading.Thread(target=_runner, name="trash-purge", daemon=True).start()


# ---------------------------------------------------------------------------
# Rate-limit retry worker (Sprint 19 / C4)
# ---------------------------------------------------------------------------
# Poll the queue this often. The retry_after column is the real gate -- this
# is just how soon the worker notices a row that becomes eligible.
_RETRY_POLL_INTERVAL_SEC = 30
# Exponential backoff base; doubled on each strike, capped at the max.
_RETRY_INITIAL_BACKOFF_SEC = 60
_RETRY_MAX_BACKOFF_SEC = 15 * 60
_pending_long_video_modes: dict[int, str] = {}
_pending_long_video_modes_lock = threading.Lock()


def _remember_pending_long_video_mode(pending_id: int, mode: str) -> None:
    with _pending_long_video_modes_lock:
        _pending_long_video_modes[int(pending_id)] = _normalize_long_video_mode(mode)


def _pending_long_video_mode(pending_id: int, *, remove: bool = False) -> str:
    with _pending_long_video_modes_lock:
        if remove:
            return _pending_long_video_modes.pop(
                int(pending_id), LONG_VIDEO_MODE_FULL)
        return _pending_long_video_modes.get(
            int(pending_id), LONG_VIDEO_MODE_FULL)


def _pending_with_long_video_mode(row: dict) -> dict:
    shaped = dict(row)
    persisted = shaped.get("long_video_mode")
    if persisted:
        shaped["long_video_mode"] = _normalize_long_video_mode(persisted)
        return shaped
    pending_id = shaped.get("pending_id")
    if pending_id is not None:
        shaped["long_video_mode"] = _pending_long_video_mode(pending_id)
    return shaped


def _retry_pending_one() -> bool:
    """One pass of the retry worker: pick the oldest pending row whose
    retry_after has arrived, attempt the extract, and update the queue
    accordingly. Returns True when a row was processed (regardless of
    outcome) so the caller can loop / log."""
    idx = _get_index()
    try:
        row = idx.next_pending(_now_iso())
    except Exception as e:
        log.warning("retry worker: next_pending failed: %s", e)
        return False
    if not row:
        return False
    pending_id = row["pending_id"]
    url = row["url"]
    interval = row["interval_seconds"] or 30
    attempts_before = row["attempt_count"] or 0
    long_video_mode = _normalize_long_video_mode(
        row.get("long_video_mode") or _pending_long_video_mode(pending_id))

    try:
        idx.mark_pending_running(pending_id)
    except Exception:
        log.exception("retry worker: mark_pending_running failed")
        return False

    log.info("retry worker: attempting pending #%d (attempt %d): %s",
             pending_id, attempts_before + 1, url)
    started_at = _now_iso()
    title = None
    folder = None
    current_phase = "metadata"
    with _extract_lock:
        try:
            metadata = _fetch_metadata(url)
            title = metadata.get("title") or "Untitled"
            topic = _classify_topic(metadata)
            folder = (DESKTOP_ROOT / _topic_folder_name(topic)
                      / (slugify(title) or "video"))

            def phase_cb(phase: str):
                nonlocal current_phase
                current_phase = phase

            result = _run_extraction(url, interval, folder,
                                     metadata=metadata, topic=topic,
                                     long_video_mode=long_video_mode,
                                     phase_callback=phase_cb)
        except BaseException as e:
            if _is_youtube_rate_limit(e):
                # Still rate-limited: back off exponentially and re-queue
                # (mark_pending_failed handles the strike-out at the cap).
                attempts = attempts_before + 1
                delay = min(
                    _RETRY_INITIAL_BACKOFF_SEC * (2 ** attempts),
                    _RETRY_MAX_BACKOFF_SEC,
                )
                retry_at = (datetime.now() + timedelta(seconds=delay)).strftime(
                    "%Y-%m-%dT%H:%M:%S")
                try:
                    idx.mark_pending_failed(
                        pending_id, "youtube_rate_limit", retry_at)
                except Exception:
                    log.exception("retry worker: mark_pending_failed failed")
                log.info(
                    "retry worker: pending #%d still rate-limited; "
                    "retry at %s (backoff %ds)",
                    pending_id, retry_at, delay)
                return True
            # Non-recoverable error -- jump straight to terminal failure.
            # The user-facing job gets on-brand copy plus a disclosure detail;
            # the queue row's persisted last_error still goes through
            # _sanitize_error so paths / credentials don't leak into a
            # long-lived store (Sprint 19.6 / Fix 8).
            msg = friendly_error(e)
            detail = machine_error_detail(e)
            failure_phase = _failure_phase(e, current_phase)
            persisted = _sanitize_error(msg)
            try:
                idx.mark_pending_failed(
                    pending_id, persisted, _now_iso(), force_final=True)
            except Exception:
                log.exception("retry worker: mark_pending_failed failed")
            _record_single_extract_job(
                url, started_at, error=msg, error_detail=detail,
                failure_phase=failure_phase,
                long_video_mode=long_video_mode,
                title=title, folder=folder)
            _pending_long_video_mode(pending_id, remove=True)
            log.warning(
                "retry worker: pending #%d non-recoverable: %s",
                pending_id, persisted)
            return True

    job = _record_single_extract_job(url, started_at, result=result)
    job_id = (job or {}).get("id") or ""
    try:
        idx.mark_pending_succeeded(pending_id, job_id)
    except Exception:
        log.exception("retry worker: mark_pending_succeeded failed")
    _pending_long_video_mode(pending_id, remove=True)
    log.info("retry worker: pending #%d succeeded -> %s", pending_id, job_id)
    return True


def _start_retry_pending_thread() -> None:
    """Daemon thread: every 30s, process at most one pending URL. One row
    per pass keeps the lock window short and gives breathing room between
    attempts so we don't ourselves drive YouTube into a deeper rate-limit."""
    def _runner():
        while True:
            try:
                _retry_pending_one()
            except Exception:
                log.exception("retry worker pass crashed")
            time.sleep(_RETRY_POLL_INTERVAL_SEC)

    threading.Thread(
        target=_runner, name="retry-pending", daemon=True).start()


# ---------------------------------------------------------------------------
# /diagnose -- structured self-check (Sprint 19 / C3)
# ---------------------------------------------------------------------------
def _keyring_display_name() -> str:
    # Sprint 19.5 Stage 1: delegated to _platform so the per-platform
    # label table lives in one place.
    return _platform.keyring_display_name()


def _probe_command(cmd: list[str]) -> tuple[str, str | None]:
    """Run a short version-probe subprocess. Returns (status, detail) where
    status is 'ok' / 'error' and detail is a one-line message."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, **SUBPROCESS_KW,
        )
    except FileNotFoundError:
        return "error", "not installed or not on PATH"
    except (subprocess.TimeoutExpired, OSError) as e:
        return "error", f"probe failed: {e}"
    if out.returncode != 0:
        first_err = (out.stderr or "").strip().splitlines()
        return "error", first_err[0] if first_err else f"exit code {out.returncode}"
    first_line = (out.stdout or "").strip().splitlines()
    return "ok", first_line[0] if first_line else "ok"


def _diagnose_payload() -> dict:
    """Structured self-check (Sprint 19 / C3). Public, no-auth -- the popup
    polls this when the helper looks unhealthy to surface a specific
    recovery hint rather than a generic 'helper offline'."""
    checks: list[dict] = []
    warnings: list[str] = []

    def add(name: str, status: str, detail: str | None = None) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    # 1. helper_responsive -- we are answering this request.
    add("helper_responsive", "ok", None)

    # 2. platform (Sprint 19.5 Stage 1). The popup uses this to surface
    # platform-appropriate install / recovery hints rather than the
    # generic Windows-shaped copy the pre-Stage-1 UI showed everyone.
    add("platform", "ok", _platform.platform_detail())

    # 3. output_root_writable
    if _is_writable_dir(DESKTOP_ROOT):
        add("output_root_writable", "ok", str(DESKTOP_ROOT))
    else:
        add("output_root_writable", "error",
            f"{DESKTOP_ROOT} is not writable")
        warnings.append(
            f"Uoink can't write to {DESKTOP_ROOT}. Check folder "
            "permissions, or set the UOINK_OUTPUT_DIR environment variable.")

    # 4. anthropic_key_set + 5. anthropic_key_valid
    try:
        settings_data = _read_settings()
    except Exception:
        settings_data = {}
    key_invalid = bool(settings_data.get("anthropic_key_invalid"))
    try:
        key = (_get_saved_anthropic_key() or "").strip()
    except Exception:
        key = ""
    anthropic_key_valid = "skipped"
    if key_invalid:
        add("anthropic_key_set", "warning", "saved key failed verification")
        add("anthropic_key_valid", "error", "Your Anthropic key isn't working.")
        anthropic_key_valid = False
        warnings.append("Your Anthropic key isn't working. Update it in Settings.")
    elif key:
        add("anthropic_key_set", "ok", None)
        add("anthropic_key_valid", "ok", "saved key present")
        anthropic_key_valid = True
    else:
        add("anthropic_key_set", "warning", "no key configured")
        add("anthropic_key_valid", "skipped", "no key entered")
        anthropic_key_valid = "skipped"
        warnings.append(
            "Anthropic API key not configured. Open setup to add one if you "
            "want Comment Intelligence, Hook Type, or entity extraction "
            "(everything else still works without it).")

    # 6. index_db_writable
    if _is_writable_dir(INDEX_PATH.parent):
        add("index_db_writable", "ok", str(INDEX_PATH))
    else:
        add("index_db_writable", "error",
            f"{INDEX_PATH.parent} is not writable")
        warnings.append(
            f"Index database is not writable at {INDEX_PATH}. Search, the "
            "Memory page, and the rate-limit queue will fail.")

    # 7. yt_dlp_available
    status, detail = _probe_command([*YTDLP_CMD, "--version"])
    if status == "ok":
        add("yt_dlp_available", "ok", f"yt-dlp {detail}")
    else:
        add("yt_dlp_available", "error", detail)
        warnings.append(
            "yt-dlp is missing or broken. Reinstall with "
            "`python -m pip install -U yt-dlp`.")

    # 8. keyring_available
    err = _credential_store_error()
    if err is None:
        add("keyring_available", "ok", _keyring_display_name())
    else:
        add("keyring_available", "warning", str(err))
        warnings.append(
            "OS credential store is unreachable -- the Anthropic API key "
            "cannot be saved between sessions.")

    # 9. ffmpeg_available
    status, detail = _probe_command(["ffmpeg", "-version"])
    if status == "ok":
        add("ffmpeg_available", "ok", detail)
    else:
        add("ffmpeg_available", "error", detail)
        warnings.append(
            "ffmpeg is missing or broken. Screenshot extraction will fail.")

    if _OUTPUT_ROOT_FALLBACK:
        warnings.append(
            f"Output folder fallback in effect: uoinks are being saved to "
            f"{DESKTOP_ROOT} because the Desktop folder was not writable. The "
            "extension's /file sandbox still serves both locations.")
    # v2.1 migration signal. The extension popup polls /diagnose to decide
    # whether to offer the opt-in "Move your saved uoinks to Desktop\Uoink\?"
    # prompt (the Desktop-corpus move is user-confirmed, never automatic).
    # Also flags a failed keyring migration so the user is told to re-enter
    # their Anthropic key rather than hitting a silent empty key (design Q4 A).
    try:
        migration = migrate_install.migration_status()
    except Exception as e:
        migration = {"error": str(e)}
    if migration.get("keyring_legacy_present") and not key:
        warnings.append(
            "Your Anthropic key didn't carry over from the previous install. "
            "Re-enter it on the setup page to restore Comment Intelligence, "
            "Hook Type, and entity extraction.")
    return {
        "ok": True,
        "version": VERSION,
        "output_root_fallback": _OUTPUT_ROOT_FALLBACK,
        "migration": migration,
        "anthropic_key_valid": anthropic_key_valid,
        "checks": checks,
        "warnings": warnings,
    }


def _enrich_yoink_rows(idx, rows: list[dict]) -> list[dict]:
    """Shape a page of index yoink rows into the enriched result the popup's
    /recent list and the Memory page both consume: fresh health (Sprint
    15), entity stats (Sprint 16), hook type + confidence (Sprint 17),
    and the thumbnail path (Sprint 18). Rows missing video_id or
    corpus_path are dropped.

    Sprint 19.6 / Fix 4: the index-side enrichment (taxonomy + entity
    aggregates) is batched into Index.enrich_yoinks, so a 50-row page
    is three IN-list queries instead of 150 per-row lookups. The
    sidecar-fresh health and the filesystem-derived thumbnail check stay
    per-row -- fs I/O dominates anyway, and pushing them down into the
    Index would couple it to server-side helpers."""
    if not rows:
        return []
    try:
        rows = idx.enrich_yoinks(rows)
    except Exception:
        # Fail open: if the batch enrich raises, fall back to raw rows
        # without crashing the whole render.
        log.exception("enrich_yoinks failed; rendering bare rows")
    out: list[dict] = []
    for r in rows:
        video_id = r.get("video_id")
        corpus_path = r.get("corpus_path") or ""
        if not video_id or not corpus_path:
            continue
        folder = Path(corpus_path).parent
        sidecar_path = r.get("sidecar_path") or ""

        # Fresh health from the live sidecar -- the stored snapshot is
        # captured at extraction time, before the AI workers finish, so
        # re-computing reflects the latest hook / CI / entity status.
        health = None
        live = {}
        if sidecar_path and Path(sidecar_path).exists():
            try:
                live = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
                health = compute_health(live)
            except (OSError, json.JSONDecodeError):
                pass
        if health is None and r.get("health_score_json"):
            try:
                health = json.loads(r["health_score_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Thumbnail (Sprint 18): absolute path when thumbnail.jpg is on
        # disk so the Memory page can fetch it via the token-gated /file
        # endpoint.
        thumb = folder / "thumbnail.jpg"
        thumbnail_path = str(thumb) if thumb.exists() else None
        metadata = {}
        if r.get("metadata_json"):
            try:
                metadata = json.loads(r["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        platform = (
            live.get("platform")
            or metadata.get("platform")
            or _detect_platform_from_url(live.get("url") or metadata.get("url") or "")
        )
        duration_seconds = (
            live.get("duration_seconds")
            or metadata.get("duration_seconds")
            or metadata.get("duration")
        )
        speakers = live.get("speakers") or live.get("speaker_labels") or []
        transcript = live.get("transcript") or []
        speaker_names: set[str] = set()
        if isinstance(speakers, list):
            for i, speaker in enumerate(speakers):
                if isinstance(speaker, str):
                    speaker_names.add(speaker)
                elif isinstance(speaker, dict):
                    speaker_names.add(str(
                        speaker.get("name")
                        or speaker.get("label")
                        or speaker.get("id")
                        or f"Speaker {i + 1}"
                    ))
        if isinstance(transcript, list):
            for seg in transcript:
                if isinstance(seg, dict):
                    label = (seg.get("speaker") or seg.get("speaker_label")
                             or seg.get("speaker_id"))
                    if label:
                        speaker_names.add(str(label))

        out.append({
            "title": live.get("episode_title") or live.get("title") or r.get("title") or "",
            "topic": r.get("topic") or "",
            "folder": str(folder),
            "video_id": video_id,
            "channel": live.get("host") or live.get("channel") or r.get("channel"),
            "yoinked_at": r.get("yoinked_at"),
            "hook_type": r.get("hook_type"),
            "hook_type_confidence": r.get("hook_type_confidence"),
            "health": health,
            "entity_count": r.get("entity_count", 0),
            "top_entities": r.get("top_entities", []),
            "thumbnail_path": thumbnail_path,
            "sidecar_path": sidecar_path,
            "source_url": live.get("url") or metadata.get("url"),
            "platform": platform,
            "media_type": live.get("media_type") or metadata.get("media_type"),
            "content_type": live.get("content_type") or metadata.get("content_type"),
            "is_live": bool(live.get("is_live") or metadata.get("is_live")),
            "live_status": live.get("live_status") or metadata.get("live_status"),
            "duration_seconds": duration_seconds,
            "podcast_title": live.get("podcast_title") or metadata.get("podcast_title"),
            "episode_title": live.get("episode_title") or metadata.get("episode_title"),
            "host": live.get("host") or metadata.get("host"),
            "speaker_count": len([s for s in speaker_names if s]),
        })
    return out


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = f"Uoink/{VERSION}"
    # Per-request socket timeout. BaseHTTPRequestHandler.setup() applies this
    # to the connection, so a client that opens a socket (or sends a
    # Content-Length header) and then stalls cannot pin a worker thread
    # indefinitely. Each socket read is bounded to 30s; legitimate requests
    # -- including the largest allowed body -- complete well within that.
    timeout = 30

    def log_message(self, fmt, *args):
        return

    # ---- CORS helpers ----
    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if origin in ALLOWED_ORIGINS:
            return origin
        # Some Chromium builds send the extension origin instead of the page
        # origin for content-script fetches.
        if origin.startswith("chrome-extension://"):
            return origin
        return None

    def _send_cors(self, origin: str | None):
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            # X-Uoink-Token is the auth header the extension sends on every
            # mutating request. X-Uoink-Client is the /token gate header.
            # Browsers won't send custom headers without the OPTIONS
            # preflight allowing them explicitly. The legacy X-Yoink-* names
            # stay in the allow-list through the v2.x alias window so a
            # not-yet-updated extension build keeps working.
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, X-Uoink-Token, X-Uoink-Client, "
                             "X-Yoink-Token, X-Yoink-Client")
            self.send_header("Access-Control-Max-Age", "600")
            # Private Network Access: Chrome requires this header when a public
            # HTTPS origin (youtube.com) fetches a loopback resource. Without
            # it the preflight is rejected and fetch fails as "Failed to fetch"
            # before any visible request reaches the handler.
            self.send_header("Access-Control-Allow-Private-Network", "true")

    # ---- Auth helpers ----
    def _request_token(self) -> str:
        """Pull the auth token from the X-Uoink-Token header (legacy
        X-Yoink-Token accepted through the v2.x alias window).

        Header-only by design: the previous ?token= query-param fallback
        was unused (the extension always set the header) and would have
        leaked the token into the user's browser history, the server's
        own access logs, and any HTTP debugging tooling that captures
        URLs but redacts headers."""
        return (self.headers.get("X-Uoink-Token")
                or self.headers.get("X-Yoink-Token") or "").strip()

    def _check_token(self) -> bool:
        return secrets.compare_digest(self._request_token(), TOKEN)

    def _is_extension_origin(self) -> bool:
        """True if Origin looks like a browser extension OR is absent.
        Some Chromium forks (Comet, observed in v1 testing) issue
        same-process service-worker fetches with no Origin header at all,
        so a strict allowlist locks them out. Browser-side CSRF defense
        moves to the X-Uoink-Client header gate + the existing CORS ACAO
        allowlist; see docs/security.md."""
        origin = (self.headers.get("Origin", "") or "")
        if not origin:
            return True
        return (origin.startswith("chrome-extension://")
                or origin.startswith("moz-extension://"))

    def _has_yoink_client_header(self) -> bool:
        """Defense-in-depth header that the extension sets on /token. A
        webpage can't set custom request headers cross-origin without
        triggering a CORS preflight, and our preflight only echoes ACAO
        for chrome-extension://* + the YouTube allowlist -- so the actual
        request from a malicious origin is blocked by the browser before
        it even runs the GET.

        v2.1 alias window: accept the new X-Uoink-Client/"uoink-extension"
        pair AND the legacy X-Yoink-Client/"yoink-extension" pair so the
        gate keeps passing whether or not the extension has been updated."""
        value = (self.headers.get("X-Uoink-Client")
                 or self.headers.get("X-Yoink-Client") or "").strip()
        return value in (_UOINK_CLIENT_HEADER_VALUE, _YOINK_CLIENT_HEADER_VALUE)

    def _require_token(self) -> bool:
        """Returns True if request authenticates. Otherwise sends a 403 and
        returns False -- caller should `return` immediately."""
        if self._check_token():
            return True
        log.info("auth: rejected %s %s (token mismatch)",
                 self.command, self.path.split("?", 1)[0])
        self._send_json(403, {"ok": False, "error": "missing or invalid token"})
        return False

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors(self._cors_origin())
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int = 202):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self._send_cors(self._cors_origin())
        self.end_headers()

    def _send_file(self, path: Path, mime: str):
        try:
            body = path.read_bytes()
        except OSError:
            return self._send_json(404, {"ok": False, "error": "file not found"})
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=300")
        self._send_cors(self._cors_origin())
        self.end_headers()
        self.wfile.write(body)

    # Sentinel raised by _read_json_body when validation fails. Carries the
    # HTTP status the caller should send back. Keeps the caller code simple
    # (one try/except instead of three checks per endpoint).
    class _BodyError(Exception):
        def __init__(self, status: int, message: str):
            super().__init__(message)
            self.status = status
            self.message = message

    def _read_json_body(self) -> dict:
        # P1-3: bound everything we trust from the network. Without these
        # checks Content-Length was unbounded (memory exhaustion via large
        # POST), Content-Type was unchecked (HTML form posts could trigger
        # mutations), and a JSON array body would blow up later code that
        # called body.get(...).
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise Handler._BodyError(415, "Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Handler._BodyError(400, "Bad Content-Length")
        if length < 0:
            raise Handler._BodyError(400, "Bad Content-Length")
        if length > MAX_BODY_BYTES:
            raise Handler._BodyError(413, f"Body too large (>{MAX_BODY_BYTES} bytes)")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise Handler._BodyError(400, f"Bad JSON: {e}")
        if not isinstance(parsed, dict):
            raise Handler._BodyError(400, "Top-level JSON must be an object")
        return parsed

    # ---- Methods ----
    def do_OPTIONS(self):
        raw_origin = self.headers.get("Origin")
        origin = self._cors_origin()
        pna = self.headers.get("Access-Control-Request-Private-Network")
        log.info("OPTIONS %s origin=%r allowed=%r pna=%r -> 200",
                 self.path, raw_origin, origin, pna)
        self.send_response(200)
        self._send_cors(origin)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        # /health is a friendlier alias for the same liveness probe; both
        # paths return the same payload so existing clients keep working.
        bare = self.path.split("?", 1)[0]
        if bare == "/ping" or bare == "/health":
            # Public liveness probe -- intentionally unauthenticated.
            log.info("GET %s from %s -> ok", bare, self.client_address[0])
            settings = _read_settings() or {}
            whisper_model = whisper_runner.normalize_model(
                settings.get("whisper_model"))
            return self._send_json(200, {
                "ok": True,
                "version": VERSION,
                "whisperx_available": whisper_runner.is_whisperx_available(),
                "whisper_model": whisper_model,
                "whisperx_model_loaded": whisper_runner.is_model_downloaded(
                    DATA_ROOT, whisper_model),
                # True while a corrupt index.db is being rebuilt from disk.
                "index_recovering": _index_recovering,
                # True when the active output root has been swapped from
                # Desktop\Yoink to %LOCALAPPDATA%\Yoink\output because the
                # Desktop path was not writable at startup.
                "output_root_fallback": _OUTPUT_ROOT_FALLBACK,
            })
        if bare == "/index/backfill-status":
            # Public, read-only progress counts (same posture as /health) so
            # the popup can poll a backfill banner without the token dance.
            with _backfill_lock:
                snapshot = dict(_backfill_state)
            return self._send_json(200, {"ok": True, **snapshot})
        if bare == "/diagnose":
            # Public, no-auth (same posture as /health). Sprint 19 / C3:
            # structured self-check the popup uses to surface a specific
            # recovery hint instead of a generic "helper offline".
            return self._send_json(200, _diagnose_payload())
        if bare == "/sources/manifest":
            # Public product metadata (no user data) so the static site can
            # bake it at build time and the dashboard Sources tab can read it
            # live. Same posture as /mcp/v1/config.
            return self._handle_sources_manifest()
        if bare == "/creators/manifest":
            return self._handle_creators_manifest()
        if bare == "/developers/manifest":
            return self._handle_developers_manifest()
        if bare == "/openapi/v1/spec.json":
            # Public, like the manifests: the OpenAPI 3.1 spec for the tool
            # bridge. Lets a non-MCP agent (Gemini/Grok/Perplexity) discover
            # how to call the local tools over HTTP. /tools/<name> itself is
            # token-gated; the spec is just the map.
            return self._handle_openapi_spec()
        if bare == "/.well-known/uoink-mcp.json":
            return self._handle_well_known_mcp()
        if bare == "/dashboard" or bare == "/dashboard/":
            # Public local UI shell. The page itself performs the same token
            # handshake as the extension before reading recent yoinks or
            # opening folders, so the route can stay unauthenticated while the
            # user-data APIs remain token-gated.
            return self._handle_dashboard()
        if bare == "/splash" or bare == "/splash/":
            # Public local UI shell, same posture as /dashboard. The splash JS
            # performs the /token handshake before reading any token-gated
            # endpoint, and the failure/success variant is decided by the page
            # itself via fetch("/diagnose").
            return self._handle_splash()
        if bare == "/token":
            return self._handle_token()
        # Everything below mutates state or reveals user data -- token-gated.
        if not self._require_token():
            return
        if bare == "/session/list":
            return self._handle_session_list()
        if bare == "/session/active":
            return self._handle_session_active()
        if bare == "/settings":
            return self._handle_settings_get()
        if bare == "/settings/pricing":
            return self._handle_settings_pricing()
        if bare == "/role/emphasis":
            return self._handle_role_emphasis()
        if bare == "/live/status":
            return self._handle_live_status_get()
        if bare == "/podcasts/feeds":
            return self._handle_podcasts_feeds_list()
        if bare == "/podcasts/episodes":
            return self._handle_podcasts_episodes_list()
        if bare == "/transcribe/status":
            return self._handle_transcribe_status_get()
        if bare == "/playlists/monitored":
            return self._handle_monitored_playlists_list()
        if bare == "/playlists/monitored/events":
            return self._handle_monitored_playlist_events_list()
        if bare == "/writing/style-anchors/defaults":
            return self._handle_writing_style_anchors_defaults()
        if bare == "/writing/style-anchors":
            return self._handle_writing_style_anchors_list()
        if bare == "/writing/draft" or bare.startswith("/writing/draft/"):
            return self._handle_writing_draft_get(bare)
        if bare == "/writing/recent-ctas":
            return self._handle_writing_recent_ctas()
        if bare.startswith("/writing/") and not bare.endswith("/revise") \
                and not bare.startswith("/writing/style-anchors"):
            return self._handle_writing_piece_get(bare)
        if bare == "/extract/page/allowlist":
            return self._handle_page_allowlist_get()
        if bare == "/update/check":
            return self._handle_update_check()
        if bare == "/engagement/scores":
            return self._handle_engagement_scores()
        if bare == "/library/facets":
            return self._handle_library_facets()
        if bare == "/corpus/channels":
            return self._handle_corpus_channels()
        if bare == "/facets/taxonomy":
            return self._handle_facets_taxonomy()
        if bare == "/facets/backfill":
            return self._handle_facets_backfill()
        if bare == "/channels":
            return self._handle_channels_list()
        if bare == "/self/analysis":
            return self._handle_self_analysis()
        if bare == "/workspaces":
            return self._handle_workspaces_list()
        if bare.startswith("/workspace/") and not bare.endswith("/assemble") \
                and not bare.endswith("/critique"):
            return self._handle_workspace_get(bare)
        if bare.startswith("/claims/"):
            return self._handle_claims_get(bare)
        if bare == "/scripts":
            return self._handle_scripts_list()
        if bare.startswith("/script/") and bare.endswith("/shot-list"):
            return self._handle_script_shot_list_get(bare)
        if bare.startswith("/script/"):
            return self._handle_script_get(bare)
        if bare == "/memory/taste":
            return self._handle_memory_taste_get()
        if bare == "/memory/user":
            return self._handle_memory_user_get()
        if bare == "/settings/mcp-config":
            return self._handle_settings_mcp_config()
        if bare == "/open-last-youtube":
            return self._handle_open_last_youtube()
        if bare == "/file":
            return self._handle_file()
        if bare == "/mcp/v1/config":
            return self._send_json(200, _mcp_config_payload())
        if bare == "/mcp/v1/sse":
            return self._handle_mcp_sse()
        if bare == "/skill/system-prompt":
            return self._handle_skill_system_prompt()
        if bare == "/open-prompts":
            return self._handle_open_prompts()
        if bare == "/open-index":
            return self._handle_open_index()
        if bare == "/recent":
            return self._handle_recent()
        if bare.startswith("/yoinks/") and bare.endswith("/screenshots"):
            return self._handle_yoink_screenshots(bare)
        if bare.startswith("/yoinks/") and bare.endswith("/screenshots/suggest"):
            return self._handle_yoink_screenshots_suggest(bare)
        if bare.startswith("/yoinks/") and "/screenshots/" in bare:
            return self._handle_yoink_screenshot_file(bare)
        if bare == "/agents/detect":
            return self._handle_agents_detect()
        if bare == "/open-folder":
            return self._handle_open_folder()
        if bare == "/jobs/stream":
            return self._handle_jobs_stream()
        if bare == "/jobs":
            return self._handle_jobs_list()
        if bare.startswith("/jobs/"):
            return self._handle_job_get(bare)
        if bare == "/taxonomy":
            return self._handle_taxonomy()
        if bare == "/taxonomy/corrections":
            return self._handle_taxonomy_corrections()
        if bare == "/memory/search":
            return self._handle_memory_search()
        if bare == "/reliability/model/status":
            return self._handle_reliability_model_status()
        m = re.fullmatch(r"/reliability/([^/]+)", bare)
        if m:
            return self._handle_reliability_get(m.group(1))
        if bare == "/queue/status":
            return self._handle_queue_status()
        log.info("GET %s -> 404", self.path)
        self._send_json(404, {"ok": False, "error": "not found"})

    # ---- /token ----
    # Returns the per-install auth token. CSRF defense layered as:
    #   1. X-Uoink-Client header must equal "uoink-extension" (legacy
    #      X-Yoink-Client/"yoink-extension" still accepted). A drive-by
    #      browser request from a random site can't set this without a
    #      CORS preflight, and our preflight refuses ACAO for any origin
    #      outside the youtube + chrome-extension allowlist.
    #   2. Origin (if present) must be a browser-extension origin.
    #      Absent Origin is allowed -- some Chromium forks (Comet) issue
    #      service-worker fetches with no Origin header.
    #   3. Per-install rate limit (10/min) so a noisy attacker can't
    #      poll the endpoint indefinitely.
    # Local processes (curl, malicious scripts on the same machine) CAN
    # bypass all of this; they already run with the user's privileges and
    # could read token.txt directly. The gate exists for CSRF, not for
    # local-attacker defense.
    def _handle_token(self):
        if not self._has_yoink_client_header():
            log.info("GET /token rejected (missing X-Uoink-Client)")
            return self._send_json(403, {"ok": False, "error": "forbidden"})
        if not self._is_extension_origin():
            log.info("GET /token rejected (origin=%r)", self.headers.get("Origin"))
            return self._send_json(403, {"ok": False, "error": "forbidden"})
        if not _check_token_rate_limit():
            log.info("GET /token rate-limited")
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        self._send_json(200, {"ok": True, "token": TOKEN})

    # ---- /dashboard ----
    def _handle_dashboard(self):
        return self._send_file(
            DASHBOARD_PATH,
            "text/html; charset=utf-8",
        )

    def _handle_splash(self):
        return self._send_file(
            SPLASH_PATH,
            "text/html; charset=utf-8",
        )

    # ---- /settings ----
    def _handle_settings_get(self):
        self._send_json(200, {"ok": True, "settings": _public_settings()})

    def _handle_settings_pricing(self):
        self._send_json(200, {"ok": True, "pricing": _anthropic_pricing_payload()})

    def _handle_role_emphasis(self):
        """GET /role/emphasis -- dashboard reads this on load to bias
        the Library default sort + filter-chip order. Token-gated. Pure
        mapping from settings.role -> emphasis dict; no model, no
        outbound."""
        if not self._require_token():
            return
        role = _normalize_role((_read_settings() or {}).get("role"))
        self._send_json(200, {
            "ok": True, "role": role,
            "emphasis": _role_facet_emphasis(role),
            "supported_roles": list(_ROLE_ENUM),
        })

    def _handle_update_check(self):
        """Notify-only update check (Tier 2). Token-gated; cached >=24h on disk.
        `?force=1` bypasses the cache. Never downloads -- reports + links only."""
        if not self._require_token():
            return
        force = (parse_qs(urlparse(self.path).query).get("force") or [""])[0] == "1"
        self._send_json(200, {"ok": True, **_check_for_update(force=force)})

    # ---- v2.5 S2 engagement memory -----------------------------------------
    # Pure local instrumentation. value_score formula + decay live on the
    # index (index.py); the helper is just a thin transport layer.

    def _handle_engagement_log(self, body):
        """POST /engagement/log -- append one engagement event. Already
        token-gated by do_POST. Zero outbound. Body:
            {video_id, event_type, source, ts_utc?}"""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        video_id = (body.get("video_id") or "").strip()
        event_type = (body.get("event_type") or "").strip()
        source = (body.get("source") or "").strip()
        ts_utc = body.get("ts_utc")
        if not video_id or not event_type or not source:
            return self._send_json(
                400, {"ok": False,
                      "error": "video_id, event_type, source required"})
        try:
            row_id = _get_index().log_engagement(
                video_id, event_type, source, ts_utc=ts_utc)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/engagement/log failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "id": row_id})

    def _handle_engagement_scores(self):
        """GET /engagement/scores?limit=N -- top-N videos by value_score.
        Token-gated. Pure read; the score is computed from local events with
        time decay (see index.py _ENGAGEMENT_WEIGHTS + half-life)."""
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            limit = int((qs.get("limit") or ["20"])[0])
        except ValueError:
            limit = 20
        try:
            scores = _get_index().top_engaged(limit=limit)
        except Exception as e:
            log.exception("/engagement/scores failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "scores": scores,
                                      "count": len(scores)})

    # ---- v2.5 S1 facet endpoints -------------------------------------------
    def _handle_facets_taxonomy(self):
        """Enum lists for the dashboard filter chips. Public (read-only enums)."""
        self._send_json(200, {
            "ok": True,
            "format": list(FORMAT_ENUM),
            "performance_tier": list(PERF_TIER_ENUM),
            "length_bucket": list(LENGTH_BUCKET_ENUM),
            "hook": sorted(HOOK_TYPES.keys()) if isinstance(HOOK_TYPES, dict) else list(HOOK_TYPES),
        })

    def _handle_library_facets(self):
        """GET /library/facets -- corpus-wide filter facets (G-12 / QA #14).

        Distinct channels / formats / performance tiers / length buckets /
        topics / hook types actually present in the corpus, each with a count
        and a human `label`, plus the yoinked_at `date_bounds`. The Library
        filters populate from this, not from the cards on the current page,
        so a channel absent from the first 50 rows still filters. Token-gated
        like the rest of the private Library API."""
        if not self._require_token():
            return
        try:
            facets = _get_index().corpus_facets()
        except Exception as e:
            log.warning("/library/facets failed: %s", e)
            return self._send_json(503, {
                "ok": False, "error": "facets unavailable",
                "state": "unavailable"})
        labelled = {}
        for col in ("channel", "format", "performance_tier",
                    "length_bucket", "topic", "hook_type"):
            labelled[col] = [
                {"value": item["value"],
                 "label": _humanize_facet(col, item["value"]),
                 "count": item["count"]}
                for item in facets.get(col, [])
            ]
        self._send_json(200, {
            "ok": True,
            "facets": labelled,
            "date_bounds": facets.get("date_bounds", {"min": None, "max": None}),
        })

    def _handle_facets_classify(self, body: dict):
        """Persist an agent-classified facet set + tags for a video. Model-
        agnostic: the calling agent does the LLM work; this just validates +
        writes. The server fills performance_tier (channel percentile) and
        length_bucket (duration) if the agent didn't pass them."""
        if not self._require_token():
            return
        video_id = (body.get("video_id") or "").strip()
        if not video_id:
            return self._send_json(400, {"ok": False, "error": "video_id required"})
        clean, err = _validate_facets(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        tags = clean.pop("__tags", None)
        idx = _get_index()
        if "performance_tier" not in clean or "length_bucket" not in clean:
            row = idx._conn.execute(
                "SELECT channel, metadata_json FROM yoinks WHERE video_id=?",
                (video_id,)).fetchone()
            if row:
                try:
                    meta = json.loads(row["metadata_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                if "performance_tier" not in clean and row["channel"]:
                    tier = _perf_tier(
                        idx.channel_view_counts(row["channel"]),
                        meta.get("views") or meta.get("view_count"))
                    if tier:
                        clean["performance_tier"] = tier
                if "length_bucket" not in clean:
                    lb = _length_bucket_from_seconds(
                        meta.get("duration_seconds") or meta.get("duration"))
                    if lb:
                        clean["length_bucket"] = lb
        facets_set = idx.set_facets(video_id, **clean)
        tags_added = idx.add_tags(video_id, tags or [], source="agent") if tags else 0
        self._send_json(200, {
            "ok": True, "video_id": video_id,
            "facets_set": facets_set, "tags_added": tags_added,
            "facets": clean,
        })

    def _handle_facets_backfill(self):
        """Stub. v2.5.0 ships agent-driven per-video classification as the
        primary path (see /facets/classify and the classify_facets MCP tool).
        Server-side bulk backfill needs a BYO Anthropic worker pool + careful
        rate-limit handling -- deferred to a v2.5.x follow-up so this PR keeps
        the model-agnostic posture clean."""
        if not self._require_token():
            return
        confirm = (parse_qs(urlparse(self.path).query).get("confirm") or [""])[0] == "true"
        if not confirm:
            return self._send_json(400, {
                "ok": False,
                "error": ("backfill is opt-in; pass ?confirm=true. Note: v2.5.0 "
                          "substrate has the endpoint but no automated worker "
                          "yet -- agent-driven classify_facets is the path.")})
        self._send_json(501, {
            "ok": False,
            "error": "automated facet backfill not yet implemented",
            "next_steps": ("Call classify_facets(video_id) per video from your "
                           "agent. The classify path is fully wired; only the "
                           "bulk loop is deferred.")})

    # ---- v2.5 P3 your-channel mode -----------------------------------------
    # All channel CRUD + verification + recognition flows through
    # channels.py. These handlers are thin transport wrappers; the only
    # outbound call is verify_channel which is documented in the module.

    def _handle_channels_list(self):
        if not self._require_token():
            return
        try:
            rows = channels.list_channels(_get_index())
        except Exception as e:
            log.exception("/channels GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "channels": rows,
                                      "count": len(rows)})

    def _handle_corpus_channels(self):
        """GET /corpus/channels -- channels appearing across the captured
        corpus, for the source/channel picker (G-21). Each row is
        {channel, count, thumbnail_url}, thumbnail_url being a representative
        yoink's thumbnail (or null). Optional ?q= substring for type-ahead,
        ?limit= bounded. Distinct from /channels (the user's own registered
        channels) -- this is the corpus answering for itself.

        Topic and hook facets are NOT duplicated here; consume /library/facets
        for those (G-12)."""
        if not self._require_token():
            return
        from urllib.parse import quote
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0].strip() or None
        try:
            limit = max(1, min(500, int((qs.get("limit") or ["200"])[0])))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "limit must be an integer"})
        try:
            rows = _get_index().corpus_channels(q=q, limit=limit)
        except Exception as e:
            log.warning("/corpus/channels failed: %s", e)
            return self._send_json(503, {"ok": False,
                                          "error": "channels unavailable",
                                          "state": "unavailable"})
        out = []
        for r in rows:
            corpus_path = r.get("corpus_path") or ""
            thumb_url = None
            if corpus_path:
                thumb = Path(corpus_path).parent / "thumbnail.jpg"
                if thumb.exists():
                    thumb_url = "/file?path=" + quote(str(thumb))
            out.append({"channel": r["channel"], "count": r["count"],
                        "thumbnail_url": thumb_url})
        return self._send_json(200, {"ok": True, "channels": out,
                                      "total": len(out)})

    def _handle_writing_recent_ctas(self):
        """GET /writing/recent-ctas -- distinct CTAs used in past scripts,
        most-recent first, for the CTA picker (G-21). {text, last_used}."""
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            limit = max(1, min(100, int((qs.get("limit") or ["20"])[0])))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "limit must be an integer"})
        try:
            ctas = _get_index().recent_ctas(limit=limit)
        except Exception as e:
            log.warning("/writing/recent-ctas failed: %s", e)
            return self._send_json(503, {"ok": False,
                                          "error": "ctas unavailable",
                                          "state": "unavailable"})
        return self._send_json(200, {"ok": True, "ctas": ctas})

    def _handle_channels_add(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        handle = (body.get("handle") or "").strip()
        name = body.get("name")
        channel_id = body.get("channel_id")
        if not handle:
            return self._send_json(400, {"ok": False, "error": "handle required"})
        try:
            row = channels.add_channel(_get_index(), handle,
                                         name=name, channel_id=channel_id)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/channels POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "channel": row})

    def _handle_channels_remove(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        handle = (body.get("handle") or "").strip()
        if not handle:
            return self._send_json(400, {"ok": False, "error": "handle required"})
        try:
            removed = channels.remove_channel(_get_index(), handle)
        except Exception as e:
            log.exception("/channels/remove failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "removed": removed})

    def _handle_channels_verify(self, body):
        """Hits youtube.com/@<handle>. Documented outbound call per
        ROADMAP P3 spec (one of the explicitly-permitted external
        endpoints in the locked compute policy)."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        handle = (body.get("handle") or "").strip()
        if not handle:
            return self._send_json(400, {"ok": False, "error": "handle required"})
        try:
            result = channels.verify_channel(_get_index(), handle)
        except Exception as e:
            log.exception("/channels/verify failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_channels_recognize_now(self):
        """POST /channels/recognize-now -- backfill self-recognition tags
        across existing yoinks. Idempotent (yoink_tags PK is video_id+tag).
        Already token-gated by do_POST."""
        try:
            result = channels.recognize_now(_get_index())
        except Exception as e:
            log.exception("/channels/recognize-now failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_self_analysis(self):
        """GET /self/analysis?handle=...&limit=... -- aggregated view of
        self-tagged yoinks. Token-gated. Read-only."""
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        handle = (qs.get("handle") or [None])[0]
        try:
            limit = int((qs.get("limit") or ["10"])[0])
        except ValueError:
            limit = 10
        try:
            result = channels.self_analysis(_get_index(),
                                              handle=handle, top_n=limit)
        except Exception as e:
            log.exception("/self/analysis failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    # ---- v3 P4 build workspace ---------------------------------------------
    # Model-agnostic by default: the helper assembles a corpus slice + records
    # critique findings; the calling agent does the LLM work. BYO-key on-server
    # path is accepted by the schema but not implemented in this PR (deferred
    # to a v3.x BYO worker pool, same posture as S1's /facets/backfill).

    def _handle_workspaces_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            limit = int((qs.get("limit") or ["50"])[0])
        except ValueError:
            limit = 50
        try:
            rows = workspaces.list_workspaces(_get_index(), limit=limit)
        except Exception as e:
            log.exception("/workspaces GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "workspaces": rows,
                                      "count": len(rows)})

    def _handle_workspace_get(self, bare: str):
        """GET /workspace/<id>"""
        if not self._require_token():
            return
        workspace_id = bare[len("/workspace/"):].strip("/")
        if not workspace_id:
            return self._send_json(400, {"ok": False, "error": "id required"})
        try:
            ws = workspaces.get_workspace(_get_index(), workspace_id)
        except Exception as e:
            log.exception("/workspace/<id> failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if ws is None:
            return self._send_json(404, {"ok": False,
                                          "error": "workspace not found"})
        try:
            crit = workspaces.critique_log_for(_get_index(), workspace_id)
        except Exception as e:
            log.exception("critique_log_for failed")
            crit = []
        return self._send_json(200, {"ok": True, "workspace": ws,
                                      "critique_log": crit})

    def _handle_workspaces_create(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            ws = workspaces.create_workspace(
                _get_index(),
                format=(body.get("format") or None),
                topic=(body.get("topic") or None),
                hook_target=(body.get("hook_target") or None),
                your_channel=(body.get("your_channel") or None),
                n_examples=int(body.get("n_examples") or 10),
                notes=(body.get("notes") or None))
        except (ValueError, TypeError) as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/workspaces POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "workspace": ws})

    def _handle_workspace_assemble(self, body):
        """POST /workspace/assemble -- run the assembler. If body includes
        a `workspace_id`, the assembled list persists to that row; else the
        slice is just returned for inspection."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            result = workspaces.assemble_workspace(
                _get_index(),
                format=(body.get("format") or None),
                topic=(body.get("topic") or None),
                hook_target=(body.get("hook_target") or None),
                your_channel=(body.get("your_channel") or None),
                n_examples=int(body.get("n_examples") or 10),
                workspace_id=(body.get("workspace_id") or None))
        except (ValueError, TypeError) as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/workspace/assemble failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_workspace_critique(self, body):
        """POST /workspace/critique -- two-phase contract.

        Phase 1 (no findings): returns the assembled context the agent
        needs to produce findings.
        Phase 2 (findings present): persists the findings to the
        critique log. Mode defaults to 'agent' (the locked compute path)."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        workspace_id = (body.get("workspace_id") or "").strip()
        draft_text = body.get("draft_text") or ""
        findings = body.get("findings")
        mode = (body.get("mode") or workspaces.COMPUTE_MODE_AGENT).strip()
        if not workspace_id:
            return self._send_json(400, {"ok": False,
                                          "error": "workspace_id required"})
        if not isinstance(draft_text, str):
            return self._send_json(400, {"ok": False,
                                          "error": "draft_text must be a string"})
        try:
            result = workspaces.critique_against_corpus(
                _get_index(), workspace_id,
                draft_text=draft_text, findings=findings, mode=mode)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/workspace/critique failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    # ---- v3 A2 claim extraction + verification -----------------------------
    # LOCKED FRAMING (ROADMAP A2): assistance only. The endpoints + MCP tools
    # surface checkable claims with evidence + sources. NEVER auto-assert
    # truth verdicts; alignment_signal is restricted to supports / contradicts
    # / mixed / inconclusive at the claims.py layer.

    def _handle_claims_get(self, bare: str):
        """GET /claims/<video_id>  -- list claims for one video."""
        if not self._require_token():
            return
        video_id = bare[len("/claims/"):].strip("/")
        if not video_id:
            return self._send_json(400, {"ok": False,
                                          "error": "video_id required"})
        try:
            rows = claims.get_claims_for_video(_get_index(), video_id)
        except Exception as e:
            log.exception("/claims/<video_id> GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "video_id": video_id,
                                      "claims": rows, "count": len(rows)})

    def _handle_claims_extract(self, body):
        """POST /claims/extract -- persist agent-extracted claims for a
        video. Locked compute policy: the calling agent does the LLM
        decomposition; this endpoint validates + writes the structure."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        video_id = (body.get("video_id") or "").strip()
        claims_list = body.get("claims") or []
        mode = (body.get("mode") or claims.COMPUTE_MODE_AGENT).strip()
        if not video_id:
            return self._send_json(400, {"ok": False,
                                          "error": "video_id required"})
        try:
            result = claims.extract_claims(_get_index(), video_id,
                                             claims=claims_list, mode=mode)
        except Exception as e:
            log.exception("/claims/extract failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_claims_verify(self, bare: str, body):
        """POST /claims/<id>/verify  -- record evidence for one claim.

        Opt-in per claim: the user (or the agent acting on the user's
        behalf) explicitly verifies a claim. The /settings flag
        `claim_verification_enabled` gates batch / auto-verify flows
        upstream of this endpoint, but the endpoint itself is always
        available -- a single explicit verification is consent enough."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        # Parse /claims/<id>/verify
        try:
            claim_id = int(bare[len("/claims/"):-len("/verify")].strip("/"))
        except (ValueError, TypeError):
            return self._send_json(400, {"ok": False,
                                          "error": "claim_id must be an integer"})
        evidence = body.get("evidence") or []
        mode = (body.get("mode") or claims.COMPUTE_MODE_AGENT).strip()
        try:
            result = claims.verify_claim(_get_index(), claim_id,
                                           evidence=evidence, mode=mode)
        except Exception as e:
            log.exception("/claims/<id>/verify failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_claims_skip(self, bare: str, body):
        """POST /claims/<id>/skip  -- user marks a claim as not-attempted
        (per ROADMAP A2 status enum). No evidence written."""
        try:
            claim_id = int(bare[len("/claims/"):-len("/skip")].strip("/"))
        except (ValueError, TypeError):
            return self._send_json(400, {"ok": False,
                                          "error": "claim_id must be an integer"})
        try:
            ok = claims.mark_not_attempted(_get_index(), claim_id)
        except Exception as e:
            log.exception("/claims/<id>/skip failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if not ok:
            return self._send_json(404, {"ok": False,
                                          "error": "claim not found"})
        return self._send_json(200, {"ok": True, "claim_id": claim_id,
                                      "status": claims.STATUS_NOT_ATTEMPTED})

    # ---- v3 P5 script studio -----------------------------------------------
    # Two-phase generator + revisor (mirror of P4 critique): without
    # `script` payload the helper returns grounding context for the agent
    # to write against; with `script` payload it persists. Compute is
    # model-agnostic per the locked policy.

    def _handle_scripts_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        workspace_id = (qs.get("workspace_id") or [None])[0]
        try:
            limit = int((qs.get("limit") or ["50"])[0])
        except ValueError:
            limit = 50
        try:
            rows = p5_scripts.list_scripts(
                _get_index(), workspace_id=workspace_id, limit=limit)
        except Exception as e:
            log.exception("/scripts GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "scripts": rows,
                                      "count": len(rows)})

    def _handle_script_get(self, bare: str):
        if not self._require_token():
            return
        try:
            script_id = int(bare[len("/script/"):].strip("/"))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "script_id must be an integer"})
        try:
            row = p5_scripts.get_script(_get_index(), script_id)
        except Exception as e:
            log.exception("/script/<id> failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if row is None:
            return self._send_json(404, {"ok": False,
                                          "error": "script not found"})
        return self._send_json(200, {"ok": True, "script": row})

    def _handle_script_shot_list_get(self, bare: str):
        if not self._require_token():
            return
        try:
            script_id = int(
                bare[len("/script/"):-len("/shot-list")].strip("/"))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "script_id must be an integer"})
        try:
            result = p5_scripts.get_shot_list(_get_index(), script_id)
        except Exception as e:
            log.exception("/script/<id>/shot-list failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 404
        return self._send_json(status, result)

    def _handle_script_generate(self, body):
        """POST /script/generate -- two-phase generator.

        body: {workspace_id, script?, mode?, parent_script_id?}

        Phase 1 (no `script`): returns grounding context.
        Phase 2 (`script` present): persists the agent-produced script."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        workspace_id = (body.get("workspace_id") or "").strip()
        if not workspace_id:
            return self._send_json(400, {"ok": False,
                                          "error": "workspace_id required"})
        script = body.get("script")
        mode = (body.get("mode") or p5_scripts.COMPUTE_MODE_AGENT).strip()
        parent = body.get("parent_script_id")
        try:
            parent_id = int(parent) if parent is not None else None
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "parent_script_id must be an integer"})
        try:
            result = p5_scripts.generate_script(
                _get_index(), workspace_id, script=script, mode=mode,
                parent_script_id=parent_id)
        except Exception as e:
            log.exception("/script/generate failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_script_revise(self, body):
        """POST /script/revise -- two-phase revisor grounded in critique
        findings. body: {script_id, critique_findings?, revision_target?,
        revised_script?, mode?}"""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            script_id = int(body.get("script_id"))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "script_id (integer) required"})
        crit = body.get("critique_findings")
        target = body.get("revision_target")
        revised = body.get("revised_script")
        mode = (body.get("mode") or p5_scripts.COMPUTE_MODE_AGENT).strip()
        try:
            result = p5_scripts.revise_script(
                _get_index(), script_id,
                critique_findings=crit,
                revision_target=target,
                revised_script=revised,
                mode=mode)
        except Exception as e:
            log.exception("/script/revise failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_script_shot_list_post(self, body):
        """POST /script/shot-list -- derive a default shot list from a
        script's beats + format. body: {script_id}"""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            script_id = int(body.get("script_id"))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "script_id (integer) required"})
        try:
            result = p5_scripts.derive_shot_list(_get_index(), script_id)
        except Exception as e:
            log.exception("/script/shot-list POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 404
        return self._send_json(status, result)

    # ---- v2.5 S4 markdown memory layer -------------------------------------
    # File I/O + consolidate logic lives in memory_layer.py. These handlers
    # are thin transport wrappers that wire DATA_ROOT + the optional vault
    # path from settings + the SQLite index.

    def _memory_vault_path(self) -> str | None:
        try:
            return (_read_settings().get("obsidian_vault_path") or "") or None
        except Exception:
            return None

    def _handle_memory_taste_get(self):
        """GET /memory/taste -- consolidated TASTE.md (lazily regenerated
        if absent). Token-gated."""
        if not self._require_token():
            return
        try:
            result = memory_layer.read_taste(
                _get_index(), DATA_ROOT,
                vault_path=self._memory_vault_path())
        except Exception as e:
            log.exception("/memory/taste GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_memory_taste_post(self, body):
        """POST /memory/taste -- body {section, content}. Updates the
        anchor row in memory_layer table + re-consolidates TASTE.md. Already
        token-gated by do_POST."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        section = (body.get("section") or "").strip()
        content = body.get("content")
        if section not in memory_layer.ANCHOR_SECTIONS:
            return self._send_json(400, {
                "ok": False,
                "error": f"section must be one of "
                          f"{list(memory_layer.ANCHOR_SECTIONS)}"})
        if not isinstance(content, str):
            return self._send_json(400, {
                "ok": False, "error": "content must be a string"})
        try:
            result = memory_layer.update_user_taste(
                _get_index(), DATA_ROOT, section, content,
                vault_path=self._memory_vault_path())
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/memory/taste POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_memory_user_get(self):
        """GET /memory/user -- USER.md (skeleton seeded on first read).
        Token-gated."""
        if not self._require_token():
            return
        try:
            result = memory_layer.read_user(DATA_ROOT)
        except Exception as e:
            log.exception("/memory/user GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    def _handle_memory_user_post(self, body):
        """POST /memory/user -- body {content}. Replaces USER.md verbatim.
        Already token-gated by do_POST."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False, "error": "json object required"})
        content = body.get("content")
        if not isinstance(content, str):
            return self._send_json(400, {
                "ok": False, "error": "content must be a string"})
        try:
            result = memory_layer.write_user(
                DATA_ROOT, content, vault_path=self._memory_vault_path())
        except Exception as e:
            log.exception("/memory/user POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, result)

    # ---- v3.1 podcast RSS feeds ---------------------------------------
    # Feed registry + polling. Episode rows materialise as metadata-only
    # rows when a feed is polled; the audio download + WhisperX
    # transcription pipelines land in subsequent PRs (CC's queue track B
    # step 2 + step 3). User opts in to download per-episode by moving
    # the row from 'new' -> 'queued' via /podcasts/episodes/set-status.

    def _parse_feed_id(self, body):
        try:
            return int(body.get("feed_id")), None
        except (TypeError, ValueError):
            return None, "feed_id (integer) required"

    def _handle_podcasts_feeds_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        enabled_only = (qs.get("enabled_only") or [""])[0] == "1"
        try:
            rows = podcasts.list_feeds(_get_index(),
                                          enabled_only=enabled_only)
        except Exception as e:
            log.exception("/podcasts/feeds GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "feeds": rows,
                                      "count": len(rows)})

    def _handle_podcasts_feed_add(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        feed_url = (body.get("feed_url") or "").strip()
        interval = body.get("poll_interval_min") or 60
        try:
            row = podcasts.add_feed(_get_index(), feed_url,
                                       poll_interval_min=int(interval))
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/podcasts/feeds POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "feed": row})

    def _handle_podcasts_feed_remove(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        feed_id, err = self._parse_feed_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        try:
            removed = podcasts.remove_feed(_get_index(), feed_id)
        except Exception as e:
            log.exception("/podcasts/feeds/remove failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "removed": removed})

    def _handle_podcasts_feed_set_enabled(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        feed_id, err = self._parse_feed_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return self._send_json(400, {"ok": False,
                                          "error": "enabled (boolean) required"})
        try:
            changed = podcasts.set_feed_enabled(_get_index(),
                                                  feed_id, enabled)
        except Exception as e:
            log.exception("/podcasts/feeds/set-enabled failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "changed": changed,
                                      "enabled": enabled})

    def _handle_podcasts_feed_poll(self, body):
        """Manual poll. Body: {feed_id}. Returns the structured
        per-feed result -- used by the dashboard's "refresh" button +
        the future background poller can call the same function."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        feed_id, err = self._parse_feed_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        try:
            result = podcasts.poll_feed(_get_index(), feed_id)
        except Exception as e:
            log.exception("/podcasts/feeds/poll failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_podcasts_episodes_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        feed_id = qs.get("feed_id")
        try:
            feed_id_i = int(feed_id[0]) if feed_id else None
        except (TypeError, ValueError):
            feed_id_i = None
        status = (qs.get("status") or [None])[0]
        try:
            limit = int((qs.get("limit") or ["100"])[0])
        except ValueError:
            limit = 100
        try:
            rows = podcasts.list_episodes(_get_index(),
                                             feed_id=feed_id_i,
                                             status=status, limit=limit)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/podcasts/episodes GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "episodes": rows,
                                      "count": len(rows)})

    def _handle_podcasts_episode_set_status(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            episode_id = int(body.get("episode_id"))
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False,
                                          "error": "episode_id (integer) required"})
        status = (body.get("status") or "").strip()
        try:
            changed = podcasts.set_episode_status(_get_index(),
                                                     episode_id, status)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/podcasts/episodes/set-status failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "changed": changed,
                                      "status": status})

    def _handle_podcasts_episode_download(self, body):
        """POST /podcasts/episodes/download {episode_id} -- download
        the episode's MP3 via yt-dlp + ffmpeg. Synchronous: returns
        when the file lands or yt-dlp errors. The dashboard's queue
        view + status='queued' make the in-flight progress visible."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            episode_id = int(body.get("episode_id"))
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False, "error": "episode_id (integer) required"})
        try:
            result = podcasts.download_episode_audio(
                _get_index(), episode_id, data_root=DATA_ROOT)
        except Exception as e:
            log.exception("/podcasts/episodes/download failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    # ---- v3.1 WhisperX transcription -------------------------------
    def _handle_transcribe_status_get(self):
        """GET /transcribe/status -- whisperx runtime + model selection.
        Used by the Settings UI to render an "install whisperx" prompt
        when the runtime isn't available."""
        if not self._require_token():
            return
        settings = _read_settings() or {}
        return self._send_json(200, {
            "ok": True,
            "whisperx_available": whisper_runner.is_whisperx_available(),
            "selected_model": settings.get("whisper_model") or "base",
            "supported_models": list(whisper_runner._MODELS),
            "diarization_default": bool(settings.get("diarization_default")),
        })

    def _handle_podcasts_episode_transcribe(self, body):
        """POST /podcasts/episodes/transcribe {episode_id, model?,
        diarize?, consent_given?, language?}.

        Synchronous. Runs WhisperX (lazy) on the downloaded MP3, writes
        the transcript JSON next to it, persists the per-episode state.
        Returns 503 with install hints when whisperx isn't importable.
        Returns 412 when first-time model download needs consent."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        try:
            episode_id = int(body.get("episode_id"))
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False, "error": "episode_id (integer) required"})

        episode = podcasts.get_episode(_get_index(), episode_id)
        if episode is None:
            return self._send_json(404, {"ok": False,
                                          "error": "episode not found"})
        if not episode.get("audio_local_path"):
            return self._send_json(400, {
                "ok": False,
                "error": ("episode has no audio_local_path -- run "
                          "/podcasts/episodes/download first")})
        if not whisper_runner.is_whisperx_available():
            return self._send_json(503, {
                "ok": False,
                "whisperx_available": False,
                "error": ("whisperx runtime not installed. Install via "
                          "the Setup page (consent-gated dependency; "
                          "not bundled with the helper to keep the "
                          "install footprint small).")})

        settings = _read_settings() or {}
        model = whisper_runner.normalize_model(
            body.get("model") or settings.get("whisper_model"))
        diarize = bool(body.get("diarize")
                         if body.get("diarize") is not None
                         else settings.get("diarization_default"))
        consent_given = bool(body.get("consent_given"))
        language = body.get("language")

        # Flip the row state so the dashboard's Activity tab shows the
        # transcription as in-flight while we work.
        whisper_runner.update_episode_transcript_state(
            _get_index(), episode_id,
            status=whisper_runner.STATUS_RUNNING,
            model_used=model)

        from pathlib import Path as _P
        audio_path = _P(episode["audio_local_path"])
        try:
            transcript = whisper_runner.transcribe_audio(
                audio_path, data_root=DATA_ROOT,
                model_size=model, language=language,
                diarize=diarize, consent_given=consent_given)
        except PermissionError as e:
            whisper_runner.update_episode_transcript_state(
                _get_index(), episode_id,
                status=whisper_runner.STATUS_QUEUED,  # awaiting consent
                error=str(e))
            return self._send_json(412, {
                "ok": False, "consent_required": True,
                "model": model, "error": str(e)})
        except RuntimeError as e:
            whisper_runner.update_episode_transcript_state(
                _get_index(), episode_id,
                status=whisper_runner.STATUS_FAILED,
                error=str(e))
            return self._send_json(500, {"ok": False, "error": str(e)})
        except FileNotFoundError as e:
            whisper_runner.update_episode_transcript_state(
                _get_index(), episode_id,
                status=whisper_runner.STATUS_FAILED,
                error=str(e))
            return self._send_json(404, {"ok": False, "error": str(e)})

        out_path = whisper_runner.write_transcript(
            transcript, audio_path=audio_path)
        whisper_runner.update_episode_transcript_state(
            _get_index(), episode_id,
            status=whisper_runner.STATUS_DONE,
            transcript_path=out_path,
            model_used=model,
            diarization_ran=transcript.get("diarization_ran", False))
        return self._send_json(200, {
            "ok": True, "episode_id": episode_id,
            "transcript_path": str(out_path),
            "model": transcript["model"],
            "language": transcript["language"],
            "segments": len(transcript["segments"]),
            "diarization_ran": transcript["diarization_ran"],
        })

    # ---- v3.1 mobile playlist monitor --------------------------------
    # Track C from the v3.1 build plan. User maintains a YouTube
    # playlist on mobile; helper polls + diffs + auto-queues new videos
    # via the existing pending_yoinks retry worker. No new threadpool;
    # decoupled from the regular /extract path so the dashboard's
    # Activity tab can label mobile-queued jobs distinctly.

    def _parse_monitored_playlist_id(self, body):
        try:
            return int(body.get("playlist_id")), None
        except (TypeError, ValueError):
            return None, "playlist_id (integer) required"

    def _handle_monitored_playlists_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        enabled_only = (qs.get("enabled_only") or [""])[0] == "1"
        try:
            rows = mobile_playlists.list_playlists(
                _get_index(), enabled_only=enabled_only)
        except Exception as e:
            log.exception("/playlists/monitored GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "playlists": rows,
                                      "count": len(rows)})

    def _handle_monitored_playlist_add(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        playlist_url = (body.get("playlist_url") or "").strip()
        name = body.get("name")
        try:
            interval = int(body.get("poll_interval_min") or 5)
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False,
                "error": "poll_interval_min must be an integer"})
        try:
            row = mobile_playlists.add_playlist(
                _get_index(), playlist_url, name=name,
                poll_interval_min=interval,
                normalize_playlist_url=_normalize_playlist_url)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/playlists/monitored POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "playlist": row})

    def _handle_monitored_playlist_remove(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        playlist_id, err = self._parse_monitored_playlist_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        try:
            removed = mobile_playlists.remove_playlist(
                _get_index(), playlist_id)
        except Exception as e:
            log.exception("/playlists/monitored/remove failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "removed": removed})

    def _handle_monitored_playlist_set_enabled(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        playlist_id, err = self._parse_monitored_playlist_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return self._send_json(400, {
                "ok": False, "error": "enabled (boolean) required"})
        try:
            changed = mobile_playlists.set_playlist_enabled(
                _get_index(), playlist_id, enabled)
        except Exception as e:
            log.exception("/playlists/monitored/set-enabled failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "changed": changed,
                                      "enabled": enabled})

    def _handle_monitored_playlist_poll(self, body):
        """POST /playlists/monitored/poll {playlist_id} -- yt-dlp
        --flat-playlist + diff + auto-queue. Returns the structured
        result; the dashboard surfaces the new[] list in the Activity
        tab under a 'from mobile playlist' label."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        playlist_id, err = self._parse_monitored_playlist_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        # Map video_id -> canonical https://www.youtube.com/watch?v=ID
        # so the existing extract pipeline (which expects a canonical
        # URL, not a bare id) can consume the row directly.
        def _vid_to_url(vid: str) -> str | None:
            if not vid:
                return None
            return _normalize_youtube_url(f"https://www.youtube.com/watch?v={vid}")
        try:
            result = mobile_playlists.poll_playlist(
                _get_index(), playlist_id,
                normalize_video_to_canonical_url=_vid_to_url)
        except Exception as e:
            log.exception("/playlists/monitored/poll failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        status = 200 if result.get("ok") else 400
        return self._send_json(status, result)

    def _handle_monitored_playlist_events_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            playlist_id = (int((qs.get("playlist_id") or [None])[0])
                            if qs.get("playlist_id") else None)
        except (TypeError, ValueError):
            playlist_id = None
        status_filter = (qs.get("status") or [None])[0]
        try:
            limit = int((qs.get("limit") or ["200"])[0])
        except ValueError:
            limit = 200
        try:
            rows = mobile_playlists.list_events(
                _get_index(), playlist_id=playlist_id,
                status=status_filter, limit=limit)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/playlists/monitored/events failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "events": rows,
                                      "count": len(rows)})

    # ---- v3.2 Writing Studio --------------------------------------
    # Server is POST-only at the dispatch layer; we expose the prompt's
    # PATCH/DELETE semantics via POST action paths so the dashboard +
    # MCP tools call a uniform shape. Mapping:
    #   POST /writing/style-anchors              -> add
    #   POST /writing/style-anchors/<id>         -> patch
    #   POST /writing/style-anchors/<id>/remove  -> delete

    def _writing_url_fetcher(self):
        """Return a callable that, given a URL, returns extracted prose.
        Bridges Writing Studio's style anchor URL ingestion to whatever
        page extractor is currently shipped (Universal Site PR / Crawl4AI
        wrapper). Falls back to None when no extractor is bound -- the
        anchor still saves, just with raw_text=NULL."""
        fetcher = globals().get("_extract_page_to_prose")
        return fetcher if callable(fetcher) else None

    def _handle_writing_style_anchors_list(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        active_only = (qs.get("active_only") or [""])[0] == "1"
        try:
            rows = writing_studio.list_style_anchors(
                _get_index(), active_only=active_only)
        except Exception as e:
            log.exception("/writing/style-anchors GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {
            "ok": True, "anchors": rows, "count": len(rows),
            "cap": writing_studio.STYLE_ANCHOR_CAP,
            "active_count": writing_studio.active_style_anchor_count(_get_index()),
        })

    def _handle_writing_style_anchors_defaults(self):
        """GET /writing/style-anchors/defaults -- the curated default anchors
        (is_default=1) for the 'Browse defaults' UI. Each carries its current
        active flag so the activate toggle reflects state. v3.2.3."""
        if not self._require_token():
            return
        try:
            anchors = writing_studio.list_default_anchors(_get_index())
        except Exception as e:
            log.exception("/writing/style-anchors/defaults GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {
            "ok": True, "anchors": anchors, "count": len(anchors),
            "cap": writing_studio.STYLE_ANCHOR_CAP,
        })

    def _handle_writing_style_anchor_add(self, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        name = body.get("name")
        source_type = (body.get("source_type") or "").strip()
        source_value = body.get("source_value")
        try:
            row = writing_studio.add_style_anchor(
                _get_index(),
                name=name, source_type=source_type,
                source_value=source_value,
                url_to_prose=self._writing_url_fetcher())
        except ValueError as e:
            status = getattr(e, "http_status", 400)
            return self._send_json(status, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/writing/style-anchors POST add failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "anchor": row})

    def _handle_writing_style_anchor_modify(self, bare: str, body):
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        tail = bare[len("/writing/style-anchors/"):].strip("/")
        if tail.endswith("/remove"):
            # /writing/style-anchors/<id>/remove
            try:
                anchor_id = int(tail[:-len("/remove")])
            except ValueError:
                return self._send_json(400, {
                    "ok": False, "error": "anchor id required"})
            try:
                removed = writing_studio.remove_style_anchor(
                    _get_index(), anchor_id)
            except Exception as e:
                log.exception("/writing/style-anchors remove failed")
                return self._send_json(500, {"ok": False, "error": str(e)})
            return self._send_json(200, {"ok": True, "removed": removed,
                                          "id": anchor_id})
        # /writing/style-anchors/<id> -- patch (rename / toggle active)
        try:
            anchor_id = int(tail)
        except ValueError:
            return self._send_json(400, {
                "ok": False, "error": "anchor id required"})
        try:
            row = writing_studio.update_style_anchor(
                _get_index(), anchor_id,
                name=body.get("name"),
                active=body.get("active"))
        except ValueError as e:
            return self._send_json(getattr(e, "http_status", 400),
                                   {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/writing/style-anchors PATCH failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if row is None:
            return self._send_json(404, {"ok": False,
                                          "error": "anchor not found"})
        return self._send_json(200, {"ok": True, "anchor": row})

    def _handle_writing_piece_get(self, bare: str):
        if not self._require_token():
            return
        tail = bare[len("/writing/"):].strip("/")
        try:
            piece_id = int(tail)
        except ValueError:
            return self._send_json(400, {
                "ok": False, "error": "piece id required"})
        try:
            piece = writing_studio.get_piece(_get_index(), piece_id)
        except Exception as e:
            log.exception("/writing/<id> GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if piece is None:
            return self._send_json(404, {"ok": False,
                                          "error": "piece not found"})
        # v3.2.3: surface the persisted body at the top level so the dashboard
        # can read it directly (it's also inside `piece`). This is the actual
        # generated tweet/blog text, NOT the Path-A grounding scaffolding.
        return self._send_json(200, {"ok": True, "piece": piece,
                                      "body": piece.get("body")})

    def _handle_writing_draft_save(self, body):
        """POST /writing/draft -- persist composer state (G-03, QA #32).
        Insert when `id` is absent, update when present. Returns the stored
        draft so the dashboard can keep the id and recover it after a
        reload. Unlike POST /writing/<kind>, drafts skip the credit and
        Voice DNA gates: this is work in progress, not a shipped piece."""
        if not self._require_token():
            return
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        draft_id = body.get("id")
        if draft_id is not None:
            try:
                draft_id = int(draft_id)
            except (TypeError, ValueError):
                return self._send_json(400, {
                    "ok": False, "error": "id must be an integer"})
        try:
            draft = _get_index().save_writing_draft(
                draft_id=draft_id,
                yoink_id=(body.get("source_yoink_id")
                           or body.get("yoink_id") or "").strip() or None,
                kind=str(body.get("kind") or "tweet"),
                title=body.get("title"),
                body=body.get("body") or "",
                source_credit_line=body.get("source_credit_line"),
            )
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return self._send_json(status, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/writing/draft save failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, "draft": draft,
                                      "id": draft["id"]})

    def _handle_writing_draft_get(self, bare: str):
        """GET /writing/draft/<id> -- one stored draft."""
        if not self._require_token():
            return
        tail = bare[len("/writing/draft"):].strip("/")
        try:
            draft_id = int(tail)
        except ValueError:
            return self._send_json(400, {"ok": False,
                                          "error": "draft id required"})
        try:
            draft = _get_index().get_writing_draft(draft_id)
        except Exception as e:
            log.exception("/writing/draft/<id> GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        if draft is None:
            return self._send_json(404, {"ok": False,
                                          "error": "draft not found"})
        return self._send_json(200, {"ok": True, "draft": draft,
                                      "body": draft.get("body")})

    def _writing_two_phase(self, body: dict, *, kind: str):
        """Shared two-phase contract for tweet/blog/revise. Phase 1: no
        body field -> return grounding payload (source yoink + anchors +
        voice DNA + credit lines). Phase 2: body field present + credit
        line included -> persist + scan + return."""
        if not isinstance(body, dict):
            return 400, {"ok": False, "error": "json object required"}
        yoink_id = (body.get("source_yoink_id")
                      or body.get("yoink_id") or "").strip() or None
        style_anchor_ids = body.get("style_anchor_ids") or []
        if not isinstance(style_anchor_ids, list):
            return 400, {"ok": False,
                          "error": "style_anchor_ids must be a list"}
        # Phase 1: no agent-produced body yet
        agent_body = body.get("body")
        if agent_body is None:
            grounding = writing_studio.assemble_grounding(
                _get_index(), yoink_id,
                style_anchor_ids=style_anchor_ids)
            return 200, {
                "ok": True,
                "mode": "grounding_only",
                "kind": kind,
                "context": grounding,
                "next": ("Produce the structured " + kind +
                          " (including the source_credit_line verbatim "
                          "in the body) and POST again with `body` "
                          "(and `title` + `dek` + `tags` for blogs) to "
                          "persist."),
            }
        # Phase 2: persist
        yoink_row = _get_index().get_yoink(yoink_id) if yoink_id else None
        credit_line = body.get("source_credit_line") or \
            writing_studio.build_credit_line(yoink_row, kind=kind)
        settings = _read_settings() or {}
        try:
            piece = writing_studio.persist_piece(
                _get_index(),
                yoink_id=yoink_id,
                kind=kind,
                body=agent_body,
                title=body.get("title"),
                dek=body.get("dek"),
                tags=body.get("tags") or [],
                source_credit_line=credit_line,
                style_anchor_ids=style_anchor_ids,
                angle=body.get("angle"),
                target_length=body.get("target_length"),
                mode=(body.get("mode")
                       or writing_studio.COMPUTE_MODE_AGENT),
                parent_id=body.get("parent_id"),
                voice_dna_warnings_enabled=bool(
                    settings.get("voice_dna_warnings_enabled", True)),
                skip_voice_dna_this_time=bool(
                    body.get("skip_voice_dna_this_time")),
                suppress_credit=bool(body.get("suppress_credit")),
            )
        except ValueError as e:
            status = getattr(e, "http_status", 400)
            return status, {"ok": False, "error": str(e)}
        except Exception as e:
            log.exception("/writing/<kind> persist failed: kind=%s", kind)
            return 500, {"ok": False, "error": str(e)}
        # Override the persist_piece compute-mode (agent|byo_key) with the
        # phase indicator so the dashboard can distinguish grounding_only
        # from persisted without re-parsing.
        piece["mode"] = "persisted"
        return 200, {"ok": True, **piece}

    def _handle_writing_tweet(self, body):
        status, resp = self._writing_two_phase(
            body, kind=writing_studio.KIND_TWEET)
        return self._send_json(status, resp)

    def _handle_writing_blog(self, body):
        status, resp = self._writing_two_phase(
            body, kind=writing_studio.KIND_BLOG)
        return self._send_json(status, resp)

    def _handle_writing_compose_validate(self, body):
        """POST /writing/compose/validate -- pure pre-publish computation for
        the composer (D-19): per-tweet char counts, over-280 flags, thread
        total, and the D-18 native-attribution footer preview. No
        persistence, no LLM call; safe to call on every keystroke."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                         "error": "json object required"})
        yoink_id = (body.get("source_yoink_id")
                    or body.get("yoink_id") or "").strip() or None
        kind = (body.get("kind") or writing_studio.KIND_TWEET).strip().lower()
        tweets = body.get("tweets")
        if tweets is not None and not isinstance(tweets, list):
            return self._send_json(400, {
                "ok": False, "error": "tweets must be a list of strings"})
        attribution_enabled = body.get("attribution_enabled", True)
        if not isinstance(attribution_enabled, bool):
            return self._send_json(400, {
                "ok": False, "error": "attribution_enabled must be boolean"})
        try:
            result = writing_studio.validate_composition(
                _get_index(), yoink_id=yoink_id, kind=kind,
                tweets=tweets, attribution_enabled=attribution_enabled)
        except ValueError as e:
            return self._send_json(getattr(e, "http_status", 400),
                                   {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/writing/compose/validate failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, **result})

    def _handle_writing_revise(self, bare: str, body):
        """POST /writing/<id>/revise -- two-phase revisor. Phase 1:
        returns prior piece + grounding. Phase 2: persists revision
        with parent_id chain."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        tail = bare[len("/writing/"):-len("/revise")].strip("/")
        try:
            prev_id = int(tail)
        except ValueError:
            return self._send_json(400, {
                "ok": False, "error": "piece id required"})
        prev = writing_studio.get_piece(_get_index(), prev_id)
        if prev is None:
            return self._send_json(404, {"ok": False,
                                          "error": "piece not found"})
        revision_target = body.get("revision_target")
        agent_body = body.get("body")
        if agent_body is None:
            grounding = writing_studio.assemble_grounding(
                _get_index(), prev.get("yoink_id"),
                style_anchor_ids=prev.get("style_anchor_ids"))
            return self._send_json(200, {
                "ok": True,
                "mode": "revision_context",
                "kind": prev.get("kind"),
                "previous": prev,
                "revision_target": revision_target,
                "context": grounding,
                "next": ("Produce the revised body (with the credit "
                          "line preserved) and POST again with `body` "
                          "to persist as a new version."),
            })
        # Phase 2: persist as revision with parent chain.
        body = {**body, "parent_id": prev_id}
        body.setdefault("source_yoink_id", prev.get("yoink_id"))
        body.setdefault("style_anchor_ids",
                         prev.get("style_anchor_ids") or [])
        status, resp = self._writing_two_phase(
            body, kind=prev.get("kind") or writing_studio.KIND_TWEET)
        return self._send_json(status, resp)

    # ---- v3.2 Universal Site Uoinking --------------------------------
    def _handle_page_allowlist_get(self):
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        active_only = (qs.get("active_only") or [""])[0] == "1"
        try:
            rows = page_extractor.list_allowed(
                _get_index(), active_only=active_only)
        except Exception as e:
            log.exception("/extract/page/allowlist GET failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {
            "ok": True, "sites": rows, "count": len(rows),
            "default_seeds": list(page_extractor.DEFAULT_ALLOW_SEEDS),
        })

    def _handle_page_allowlist_modify(self, body):
        """POST /extract/page/allowlist {action: 'add'|'remove',
        url_pattern}. Per prompt spec."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        action = (body.get("action") or "").strip().lower()
        pattern = (body.get("url_pattern") or "").strip()
        if action not in ("add", "remove"):
            return self._send_json(400, {
                "ok": False,
                "error": "action must be 'add' or 'remove'"})
        if not pattern:
            return self._send_json(400, {
                "ok": False, "error": "url_pattern required"})
        try:
            if action == "add":
                row = page_extractor.add_allowed(_get_index(), pattern)
                return self._send_json(200, {"ok": True, "site": row})
            removed = page_extractor.remove_allowed(_get_index(), pattern)
            return self._send_json(200, {"ok": True, "removed": removed,
                                          "url_pattern": pattern.lower()})
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            log.exception("/extract/page/allowlist POST failed")
            return self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_extract_page(self, body):
        """POST /extract/page {url, render_mode?, include_screenshot?,
        follow_links_depth?}. Allowlist-gated by default; result lands
        in yoinks with source_type='page' (auto-persisted)."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                          "error": "json object required"})
        url = (body.get("url") or "").strip()
        render_mode = (body.get("render_mode")
                         or page_extractor.RENDER_MODE_JS).strip().lower()
        include_screenshot = bool(body.get("include_screenshot", True))
        try:
            follow_depth = int(body.get("follow_links_depth", 0))
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False,
                "error": "follow_links_depth must be an integer"})

        try:
            result = page_extractor.extract_page(
                _get_index(), url,
                render_mode=render_mode,
                include_screenshot=include_screenshot,
                follow_links_depth=follow_depth,
                enforce_allowlist=True)
        except Exception as e:
            log.exception("/extract/page failed")
            return self._send_json(500, {"ok": False, "error": str(e)})

        if not result.get("ok"):
            # Allowlist denial returns 403; other validation errors 400.
            if result.get("code") == "host_not_allowed":
                return self._send_json(403, result)
            return self._send_json(400, result)

        # Auto-persist as a yoink row -- universal site captures land in
        # the same Library as videos, distinguished by source_type.
        try:
            video_id = page_extractor.persist_page_yoink(
                _get_index(), result, data_root=DATA_ROOT)
            result["video_id"] = video_id
        except Exception as e:
            log.warning("/extract/page persist failed: %s", e)
            result["video_id"] = None

        return self._send_json(200, result)

    def _handle_settings_mcp_config(self):
        """MCP config snippet for the Settings tab Copy button. Token-gated."""
        if not self._require_token():
            return
        self._send_json(200, {"ok": True, "mcp_config": _mcp_settings_snippet()})

    def _handle_reliability_model_status(self):
        self._send_json(200, {"ok": True, "model": _reliability_model_status()})

    def _handle_reliability_model_download(self):
        try:
            status = uoink_reliability.ensure_model(
                RELIABILITY_MODEL_NAME,
                RELIABILITY_MODEL_ROOT,
            )
        except Exception as e:
            return self._send_json(200, {
                "ok": False,
                "error": _sanitize_error(str(e)),
                "model": _reliability_model_status(),
            })
        self._send_json(200, {
            "ok": True,
            "downloaded": True,
            "model": {**_reliability_model_status(), **status},
        })

    def _handle_reliability_get(self, video_id: str):
        folder, _row = _folder_for_video_id(video_id)
        if folder is None:
            return self._send_json(404, {"ok": False, "error": "yoink not found"})
        _sidecar_path, sidecar = _read_sidecar_for_folder(folder)
        reliability = sidecar.get("reliability")
        if not isinstance(reliability, dict):
            reliability = {
                "status": "not_computed",
                "spans": [],
                "span_count": 0,
            }
        self._send_json(200, {
            "ok": True,
            "video_id": video_id,
            "reliability": reliability,
            "model": _reliability_model_status(),
        })

    def _handle_reliability_compute(self, video_id: str, body: dict):
        threshold = RELIABILITY_DEFAULT_THRESHOLD
        raw_threshold = body.get("threshold") if isinstance(body, dict) else None
        if raw_threshold is not None:
            try:
                threshold = max(0.05, min(0.95, float(raw_threshold)))
            except (TypeError, ValueError):
                return self._send_json(400, {
                    "ok": False,
                    "error": "threshold must be a number",
                })
        result = _compute_transcript_reliability(
            video_id,
            threshold=threshold,
            allow_model_download=bool(body.get("allow_model_download")),
            force=bool(body.get("force")),
        )
        self._send_json(200, result)

    def _handle_open_last_youtube(self):
        """Focus an existing YouTube browser window, else open youtube.com.
        Token-gated. CTA on the Finished/Splash screens + dashboard."""
        if not self._require_token():
            return
        if _focus_youtube_window():
            return self._send_json(200, {
                "ok": True, "action": "focused_existing", "url": None})
        url = "https://www.youtube.com"
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            log.debug("open-last-youtube: webbrowser failed: %s", e)
            return self._send_json(200, {"ok": False, "error": "could not open browser"})
        self._send_json(200, {"ok": True, "action": "opened_new", "url": url})

    def _handle_helper_quit(self):
        """Graceful stop (dashboard 'Stop helper' + tray 'Quit'). Token-gated.
        Replies 200 then shuts the server down on a worker thread so
        serve_forever() unblocks and main() returns (atexit clears the PID);
        expect the connection to drop right after this response."""
        if not self._require_token():
            return
        self._send_json(200, {"ok": True, "stopping": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _handle_settings_post(self, body: dict):
        boolean_fields = (
            "comment_intelligence_enabled",
            "hook_type_enabled",
            "smart_screenshot_picker_enabled",
            "transcript_reliability_auto_check",
            "claim_verification_enabled",  # v3 A2 -- default OFF (claims
                                            # extracted on yoink only when on)
            "diarization_default",          # v3.1 track B/D -- WhisperX
                                            # speaker diarization on every
                                            # interview-format transcribe
            "voice_dna_warnings_enabled",   # v3.2 Writing Studio
            "voice_dna_show_per_generation_toggle",  # v3.2 Writing Studio
            "writing_show_screenshot_picker",  # v3.3 D-20
            "writing_default_attach_all_screenshots",  # v3.3 D-20
        )
        integer_fields = ("clipboard_screenshot_cap",)
        extra_fields = ("output_dir", "autostart", "topics",
                         "obsidian_vault_path",   # Tier 2 + v2.5 S4
                         "role",                  # v3.1 P2
                         "live_stream_behavior",  # v3.1 live
                         "whisper_model")         # v3.1 A1/podcast
        if (
            not any(f in body for f in boolean_fields)
            and not any(f in body for f in integer_fields)
            and "anthropic_key" not in body
            and not any(f in body for f in extra_fields)
        ):
            return self._send_json(400, {
                "ok": False,
                "error": "settings field required",
            })
        for field in boolean_fields:
            if field in body and not isinstance(body.get(field), bool):
                return self._send_json(400, {
                    "ok": False,
                    "error": f"{field} must be boolean",
                })
        if "clipboard_screenshot_cap" in body:
            cap = body.get("clipboard_screenshot_cap")
            if isinstance(cap, bool) or not isinstance(cap, int):
                return self._send_json(400, {
                    "ok": False,
                    "error": "clipboard_screenshot_cap must be an integer",
                })
            if cap < 0 or cap > CLIPBOARD_SCREENSHOT_CAP_MAX:
                return self._send_json(400, {
                    "ok": False,
                    "error": f"clipboard_screenshot_cap must be 0-{CLIPBOARD_SCREENSHOT_CAP_MAX}",
                })
        if "anthropic_key" in body and body.get("anthropic_key") is not None:
            if not isinstance(body.get("anthropic_key"), str):
                return self._send_json(400, {
                    "ok": False,
                    "error": "anthropic_key must be a string or null",
                })
            if len(body.get("anthropic_key")) > 4096:
                return self._send_json(400, {
                    "ok": False,
                    "error": "anthropic_key is too long",
                })

        data = _read_settings()
        for field in boolean_fields:
            if field in body:
                data[field] = body[field]
        if "clipboard_screenshot_cap" in body:
            data["clipboard_screenshot_cap"] = int(body["clipboard_screenshot_cap"])
        if "anthropic_key" in body:
            raw_key = body.get("anthropic_key")
            key = "" if raw_key is None else raw_key.strip()
            try:
                _store_saved_anthropic_key(key)
            except CredentialStoreError as e:
                log.warning("settings credential write failed: %s", e)
                return self._send_json(200, {
                    "ok": False,
                    "error": "credential store unavailable",
                })
            data["anthropic_key_invalid"] = False
        # ---- Tier 2 extras ----
        if "output_dir" in body:
            val = body.get("output_dir")
            if not isinstance(val, str) or not val.strip():
                return self._send_json(400, {
                    "ok": False, "error": "output_dir must be a non-empty string"})
            try:
                cand = Path(val).expanduser()
                cand.mkdir(parents=True, exist_ok=True)
                if not _is_writable_dir(cand):
                    raise OSError("not writable")
            except OSError:
                return self._send_json(400, {
                    "ok": False, "error": f"output_dir is not a writable folder: {val}"})
            # Persisted; _get_output_root applies it on the next start (no live
            # DESKTOP_ROOT mutation under in-flight extractions).
            data["output_dir"] = str(cand.resolve())
        if "autostart" in body:
            if not isinstance(body.get("autostart"), bool):
                return self._send_json(400, {
                    "ok": False, "error": "autostart must be boolean"})
            if _set_autostart(body["autostart"]) is False:
                return self._send_json(200, {
                    "ok": False, "error": "autostart toggle failed"})
        if "obsidian_vault_path" in body:
            val = body.get("obsidian_vault_path")
            if val is None or val == "":
                data["obsidian_vault_path"] = ""
            elif isinstance(val, str):
                # Validate the path exists + is writable. The vault dir
                # itself must exist; we create the Uoink/ subfolder lazily
                # on first mirror write.
                try:
                    cand = Path(val).expanduser()
                    if not cand.exists() or not cand.is_dir():
                        raise OSError("vault path missing or not a directory")
                    if not _is_writable_dir(cand):
                        raise OSError("vault path not writable")
                except OSError as e:
                    return self._send_json(400, {
                        "ok": False,
                        "error": f"obsidian_vault_path invalid: {e}"})
                data["obsidian_vault_path"] = str(cand.resolve())
            else:
                return self._send_json(400, {
                    "ok": False,
                    "error": "obsidian_vault_path must be a string or null"})
        if "role" in body:
            raw_role = body.get("role")
            if raw_role is None or raw_role == "":
                data["role"] = ROLE_MIXED
            elif isinstance(raw_role, str):
                norm = raw_role.strip().lower()
                if norm not in _ROLE_ENUM:
                    return self._send_json(400, {
                        "ok": False,
                        "error": f"role must be one of {list(_ROLE_ENUM)}"})
                data["role"] = norm
            else:
                return self._send_json(400, {
                    "ok": False, "error": "role must be a string"})
        if "live_stream_behavior" in body:
            raw_lsb = body.get("live_stream_behavior")
            if raw_lsb is None or raw_lsb == "":
                data["live_stream_behavior"] = LIVE_BEHAVIOR_WAIT
            elif isinstance(raw_lsb, str):
                norm = raw_lsb.strip().lower()
                if norm not in _LIVE_BEHAVIORS:
                    return self._send_json(400, {
                        "ok": False,
                        "error": (f"live_stream_behavior must be one of "
                                   f"{list(_LIVE_BEHAVIORS)}")})
                data["live_stream_behavior"] = norm
            else:
                return self._send_json(400, {
                    "ok": False,
                    "error": "live_stream_behavior must be a string"})
        if "whisper_model" in body:
            raw_model = body.get("whisper_model")
            if raw_model is None or raw_model == "":
                data["whisper_model"] = "base"
            elif isinstance(raw_model, str):
                norm = raw_model.strip().lower()
                if norm not in _WHISPER_MODELS:
                    return self._send_json(400, {
                        "ok": False,
                        "error": f"whisper_model must be one of {list(_WHISPER_MODELS)}"})
                data["whisper_model"] = norm
            else:
                return self._send_json(400, {
                    "ok": False,
                    "error": "whisper_model must be a string"})
        if "topics" in body:
            err = _validate_topics(body.get("topics"))
            if err:
                return self._send_json(400, {"ok": False, "error": err})
            try:
                _write_topics(body["topics"])
            except OSError as e:
                log.warning("topics write failed: %s", e)
                return self._send_json(200, {
                    "ok": False, "error": "topics write failed"})
        data["updated_at"] = _now_iso()
        try:
            _write_settings(data)
        except OSError as e:
            log.warning("settings write failed: %s", e)
            return self._send_json(200, {"ok": False, "error": "settings write failed"})
        self._send_json(200, {"ok": True, "settings": _public_settings(data)})

    # ---- /settings/test-key ----
    def _handle_settings_test_key(self, body: dict):
        provided = "anthropic_key" in body and body.get("anthropic_key") is not None
        if provided and not isinstance(body.get("anthropic_key"), str):
            return self._send_json(400, {
                "ok": False,
                "error": "anthropic_key must be a string or null",
            })
        if provided:
            key = body.get("anthropic_key").strip()
            using_stored_key = False
        else:
            data = _read_settings()
            key = _get_saved_anthropic_key().strip()
            using_stored_key = True

        ok, reason, status = _test_anthropic_key(key)
        if not ok and status == 401 and using_stored_key:
            _mark_anthropic_key_invalid()
        self._send_json(200, {
            "ok": True,
            "valid": ok,
            "error": None if ok else reason,
            "settings": _public_settings(),
        })

    # ---- /file?path=... ----
    # Authenticated thumbnail serving for extension UI. MV3 popups cannot
    # reliably render file:// paths, so the helper exposes a very narrow
    # image-only, Yoink-output-root-only file endpoint.
    def _handle_file(self):
        qs = parse_qs(urlparse(self.path).query)
        raw_path = (qs.get("path") or [""])[0]
        path, mime, status, error = _resolve_served_file(raw_path)
        if error:
            return self._send_json(status, {"ok": False, "error": error})
        return self._send_file(path, mime)

    # ---- MCP HTTP transport ----
    # This is a small JSON-RPC HTTP wrapper over the same tool registry used
    # by uoink_mcp.py's stdio server. It intentionally keeps state out of the
    # transport; auth remains the v1 X-Uoink-Token gate (legacy X-Yoink-Token
    # still accepted through the alias window).
    def _send_mcp_result(self, request_id, result: dict):
        return self._send_json(200, {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        })

    def _send_mcp_error(self, request_id, code: int, message: str):
        return self._send_json(200, {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        })

    def _handle_mcp_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_cors(self._cors_origin())
        self.end_headers()
        # Compatibility shim for HTTP/SSE clients: advertise the JSON-RPC
        # POST endpoint. Most desktop agents use stdio; HTTP clients can use
        # /mcp/v1 directly with the same JSON-RPC messages.
        self.wfile.write(b"event: endpoint\ndata: /mcp/v1\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _mcp_tool_call_result(self, payload: dict) -> dict:
        is_error = not bool(payload.get("ok", True))
        text = json.dumps(payload, ensure_ascii=False)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": is_error,
        }

    def _handle_mcp_post(self, bare: str, body: dict):
        request_id = _mcp_request_id(body)
        method = body.get("method") if isinstance(body.get("method"), str) else None
        # Support both a single RPC endpoint (/mcp/v1 with method in body) and
        # explicit helper paths (/mcp/v1/tools/call) because different HTTP
        # MCP clients are still converging on transport details.
        if bare == "/mcp/v1/initialize" or (bare == "/mcp/v1" and method == "initialize"):
            return self._send_mcp_result(request_id, _mcp_initialize_result(body))
        if method == "notifications/initialized":
            # JSON-RPC notifications have no response id/body. Return an
            # empty 202 so strict clients don't see a non-MCP `{ok:true}`.
            return self._send_empty(202)
        if method == "ping":
            return self._send_mcp_result(request_id, {})
        if bare == "/mcp/v1/tools/list" or (bare == "/mcp/v1" and method == "tools/list"):
            return self._send_mcp_result(request_id, {
                "tools": _mcp_tools_module().list_tools(),
            })
        if bare == "/mcp/v1/tools/call" or (bare == "/mcp/v1" and method == "tools/call"):
            params = body.get("params") if isinstance(body.get("params"), dict) else body
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(args, dict):
                return self._send_mcp_error(request_id, -32602, "invalid tool call")
            payload = _mcp_tools_module().call_tool(name, args)
            return self._send_mcp_result(request_id, self._mcp_tool_call_result(payload))
        return self._send_mcp_error(request_id, -32601, "method not found")

    # ---- /recent ----
    # Walk Desktop\Yoink\<topic>\<slug>\ and return the 3 most recent video
    # folders. A folder counts as a yoink if it has a yoink.md inside it.
    # Sessions root (_sessions/) is excluded.
    def _handle_recent(self):
        """Recent yoinks for the popup. Sprint 15.1 followups read from the
        Index instead of walking disk; Sprint 19.6 / Fix 4 enrichment is
        batched into Index.enrich_yoinks (taxonomy + entity_count +
        top_entities all in three IN-list queries) instead of the
        pre-fix N+1 per-row pattern."""
        idx = _get_index()
        try:
            rows = idx.list_recent(limit=10)
        except Exception as e:
            log.warning("recent: index unavailable: %s", e)
            rows = []
        results = _enrich_yoink_rows(idx, rows)
        self._send_json(200, {"ok": True, "recent": results})

    # ---- /memory/search ----
    def _handle_memory_search(self):
        """Filtered/paginated yoink search behind the memory page (B1).
        Token-gated, rate-limited (heavier than /recent due to FTS)."""
        if not _check_memory_search_rate_limit():
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        qs = parse_qs(urlparse(self.path).query)

        def _one(name: str) -> str | None:
            value = (qs.get(name) or [""])[0].strip()
            return value or None

        hook_type = _one("hook_type")
        if hook_type:
            hook_type = hook_type.lower()
            if hook_type not in HOOK_TYPES:
                return self._send_json(
                    400, {"ok": False, "error": "hook_type invalid"})
        date_from = _one("date_from")
        date_to = _one("date_to")
        for label, value in (("date_from", date_from), ("date_to", date_to)):
            if value and not _valid_iso_date(value):
                return self._send_json(
                    400, {"ok": False, "error": f"{label} must be YYYY-MM-DD"})
        # Reject an impossible window server-side (G-12 / QA #13). Before this
        # the from>to range fell through to an empty result that read as "no
        # uoinks," hiding the real problem (the dates are backwards).
        if date_from and date_to and date_from > date_to:
            return self._send_json(400, {
                "ok": False,
                "error": "date_from is after date_to",
                "state": "invalid_range",
            })
        try:
            limit = max(1, min(200, int(_one("limit") or "50")))
            offset = max(0, int(_one("offset") or "0"))
        except (TypeError, ValueError):
            return self._send_json(
                400, {"ok": False, "error": "limit/offset must be integers"})

        idx = _get_index()
        try:
            res = idx.search_yoinks_for_memory(
                q=_one("q"), channel=_one("channel"), topic=_one("topic"),
                hook_type=hook_type, date_from=date_from, date_to=date_to,
                limit=limit, offset=offset,
            )
            corpus_total = idx.count_corpus()
        except Exception as e:
            # The Library-unavailable state (G-11 / QA #12). The frontend must
            # render this distinctly and NEVER fall back to job records dressed
            # as uoinks. `state: "unavailable"` is the signal to do that.
            log.warning("memory search: index error: %s", e)
            return self._send_json(503, {
                "ok": False,
                "error": "search failed",
                "state": "unavailable",
            })
        results = _enrich_yoink_rows(idx, res["results"])
        # Three distinct populated-but-zero states so the frontend stops
        # collapsing them into one "0 uoinks" message (G-11 / QA #11, #12):
        #   matches      -> rows to show
        #   no_matches   -> corpus has uoinks, this query/filter set matched 0
        #   empty_corpus -> nothing saved yet; show the real onboarding CTA
        total = res["total"]
        if total > 0:
            state = "matches"
        elif corpus_total > 0:
            state = "no_matches"
        else:
            state = "empty_corpus"
        self._send_json(200, {
            "ok": True,
            "state": state,
            "total": total,
            "corpus_total": corpus_total,
            "limit": limit,
            "offset": offset,
            "results": results,
        })

    # ---- /open-folder?path=... ----
    # Pop Explorer at an arbitrary folder. Used by the "Recent yoinks" list
    # so clicking a row opens that folder. The path must be inside
    # DESKTOP_ROOT — we don't want this turning into an arbitrary-folder
    # opener.
    def _handle_open_folder(self):
        qs = parse_qs(urlparse(self.path).query)
        target = (qs.get("path") or [""])[0]
        if not target:
            return self._send_json(400, {"ok": False, "error": "path required"})
        try:
            p = Path(target).resolve()
            # Sandboxing: only allow folders inside DESKTOP_ROOT. relative_to
            # raises ValueError when p is outside the root.
            p.relative_to(DESKTOP_ROOT.resolve())
        except (ValueError, OSError):
            return self._send_json(400, {
                "ok": False, "error": "path is outside the Uoink folder",
            })
        if not p.exists() or not p.is_dir():
            return self._send_json(404, {"ok": False, "error": "folder not found"})
        try:
            _platform.open_in_os(p)
        except Exception as e:
            return self._send_json(200, {"ok": False, "error": str(e)})
        self._send_json(200, {"ok": True, "folder": str(p)})

    # ---- /open-index ----
    # Open _all-yoinks-index.md in the user's default markdown viewer
    # (typically VS Code, Obsidian, or Notepad). Regenerates the file first
    # in case it doesn't exist yet (e.g. user hasn't yoinked anything in
    # this install but is exploring the popup).
    def _handle_open_index(self):
        try:
            _regenerate_index()
            target = _index_path()
            if not target.exists():
                return self._send_json(200, {
                    "ok": False,
                    "error": "Index file couldn't be created.",
                })
            _platform.open_in_os(target)
        except Exception as e:
            return self._send_json(200, {"ok": False, "error": str(e)})
        log.info("GET /open-index -> %s", target)
        self._send_json(200, {"ok": True, "path": str(target)})

    # ---- /open-prompts ----
    # Pop Explorer at extension/prompts.json so the user can edit their custom
    # prompts without hunting through the project folder. Selected so the file
    # is highlighted (not just the parent folder opened).
    def _handle_open_prompts(self):
        prompts_path = HERE / "extension" / "prompts.json"
        if not prompts_path.exists():
            return self._send_json(200, {
                "ok": False,
                "error": f"prompts.json not found at {prompts_path}",
            })
        try:
            _platform.reveal_in_file_manager(prompts_path)
        except Exception as e:
            return self._send_json(200, {"ok": False, "error": str(e)})
        log.info("GET /open-prompts -> %s", prompts_path)
        self._send_json(200, {"ok": True, "path": str(prompts_path)})

    # ---- /skill/system-prompt ----
    # setup.html uses this to offer a copyable fallback prompt for clients
    # that do not load SKILL.md natively. Token-gated because it reveals the
    # local install layout and should follow the rest of setup's private API.
    def _handle_skill_system_prompt(self):
        # The skill folder is renamed skills/yoink -> skills/uoink by the
        # extension/skill agent (out of this PR's scope). Resolve the new
        # location first and fall back to the legacy one so this endpoint
        # works whether or not that rename has merged yet.
        skill_dir = HERE / "skills" / "uoink"
        if not skill_dir.is_dir():
            skill_dir = HERE / "skills" / "yoink"
        prompt_path = skill_dir / "system-prompt.md"
        try:
            body = prompt_path.read_text(encoding="utf-8").encode("utf-8")
        except OSError:
            return self._send_json(404, {
                "ok": False,
                "error": "skill system prompt not found",
            })
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=300")
        self._send_cors(self._cors_origin())
        self.end_headers()
        self.wfile.write(body)

    def _handle_extract_reddit(self, body: dict):
        """POST /extract/reddit {url, depth_limit?, score_threshold?} --
        capture a Reddit thread via its public .json as a yoink with
        source_type='reddit_thread'. Reuses page_extractor.persist_page_yoink
        for the corpus write + index upsert. Token gate cleared by do_POST."""
        if not isinstance(body, dict):
            return self._send_json(400, {"ok": False,
                                         "error": "json object required"})
        url = (body.get("url") or "").strip()
        if not url:
            return self._send_json(400, {"ok": False, "error": "url required"})

        def _bounded(value, default, lo, hi):
            try:
                return max(lo, min(int(value), hi))
            except (TypeError, ValueError):
                return default

        depth = _bounded(body.get("depth_limit"),
                         reddit_extractor.DEFAULT_DEPTH_LIMIT, 0, 10)
        score = _bounded(body.get("score_threshold"),
                         reddit_extractor.DEFAULT_SCORE_THRESHOLD, -100, 100000)
        result = reddit_extractor.extract_reddit_thread(
            url, depth_limit=depth, score_threshold=score)
        if not result.get("ok"):
            log.info("POST /extract/reddit -> %s", result.get("code"))
            return self._send_json(200, {
                "ok": False, "error": result.get("error"),
                "code": result.get("code")})
        try:
            video_id = page_extractor.persist_page_yoink(
                _get_index(), result, data_root=DATA_ROOT,
                source_type=reddit_extractor.SOURCE_TYPE,
                subfolder="Reddit", slug_prefix="reddit")
        except Exception:
            log.exception("/extract/reddit persist failed")
            return self._send_json(500, {
                "ok": False,
                "error": "Captured the thread but couldn't save it locally."})
        if not video_id:
            return self._send_json(500, {
                "ok": False, "error": "Couldn't save the Reddit thread."})
        log.info("POST /extract/reddit -> ok (%s, %d comments)",
                 video_id, result.get("comments_captured", 0))
        return self._send_json(200, {
            "ok": True,
            "video_id": video_id,
            "title": result["title"],
            "comments_captured": result.get("comments_captured", 0),
            "metadata": result.get("metadata", {}),
        })

    def _handle_openapi_spec(self):
        base = f"http://{HOST}:{PORT}"
        try:
            tools = _mcp_tools_module()
            spec = openapi_bridge.build_spec(
                base, tool_registry=tools.TOOL_REGISTRY, version=VERSION)
        except Exception:
            log.exception("/openapi/v1/spec.json build failed")
            return self._send_json(
                500, {"ok": False, "error": "could not build the OpenAPI spec"})
        return self._send_json(200, spec)

    def _handle_well_known_mcp(self):
        base = f"http://{HOST}:{PORT}"
        try:
            tool_count = len(_mcp_tools_module().TOOL_REGISTRY)
        except Exception:
            tool_count = 0
        return self._send_json(200, openapi_bridge.build_well_known(
            base, version=VERSION, tool_count=tool_count))

    def _handle_tools_call_http(self, bare: str, body: dict):
        """POST /tools/<name> -- HTTP transport for the MCP tools, so a
        non-MCP agent can call them after reading /openapi/v1/spec.json.
        Token gate already cleared by do_POST. Routes through the same
        uoink_mcp_tools.call_tool the MCP transport uses (one dispatch path,
        one rate limiter). Tool/validation errors come back as ok:false at
        HTTP 200 (matching the rest of the helper); only an unknown tool name
        is a 404."""
        from urllib.parse import unquote
        name = unquote(bare[len("/tools/"):]).strip("/")
        if not name or "/" in name:
            return self._send_json(400, {"ok": False,
                                         "error": "tool name required"})
        tools = _mcp_tools_module()
        aliases = getattr(tools, "MCP_TOOL_ALIASES", {})
        if name not in tools.TOOL_REGISTRY and name not in aliases:
            return self._send_json(404, {"ok": False,
                                         "error": "tool not found"})
        try:
            result = tools.call_tool(name, body if isinstance(body, dict) else {})
        except Exception:
            log.exception("/tools/%s failed", name)
            return self._send_json(500, {"ok": False,
                                         "error": "tool execution failed"})
        # call_tool returns the handler dict on success, or {ok:false,error}
        # on a tool/rate-limit error. Normalise to a uniform envelope.
        if isinstance(result, dict) and result.get("ok") is False:
            return self._send_json(200, result)
        return self._send_json(200, {"ok": True, "result": result})

    def _handle_sources_manifest(self):
        return self._send_json(
            200, {"ok": True, **source_manifest.build_sources()})

    def _handle_creators_manifest(self):
        return self._send_json(
            200, {"ok": True, **source_manifest.build_creators()})

    def _handle_developers_manifest(self):
        try:
            tool_count = len(_mcp_tools_module().TOOL_REGISTRY)
        except Exception:
            log.exception("developers manifest: tool count unavailable")
            tool_count = 0
        payload = source_manifest.build_developers(
            tool_count=tool_count,
            mcp_endpoint=f"http://{HOST}:{PORT}/mcp/v1",
            openapi_spec_path="/openapi/v1/spec.json",
        )
        return self._send_json(200, {"ok": True, **payload})

    def _handle_yoink_screenshots(self, bare: str):
        """GET /yoinks/<id>/screenshots -- list the source's screenshots for
        the Writing Studio picker (D-20). Token gate already cleared by
        do_GET. Returns 404 for an unknown id, 200 with an empty list for a
        text-only capture.

        v3.2.4: `?dedupe=true` hides visually near-duplicate frames (a static
        shot that barely changes). `?dedupe_threshold=N` tunes the Hamming
        cutoff (default 5; higher = more aggressive). When the runtime can't
        hash images (no Pillow) the full list is returned with
        `dedupe_available=false` so the grid can say so."""
        from urllib.parse import unquote
        video_id = unquote(
            bare[len("/yoinks/"):-len("/screenshots")]).strip("/")
        if not video_id:
            return self._send_json(400, {"ok": False,
                                         "error": "video_id required"})
        qs = parse_qs(urlparse(self.path).query)
        dedupe, threshold = _screenshot_dedupe_query(qs)
        try:
            payload = _screenshot_list_for_yoink(_get_index(), video_id)
        except Exception:
            log.exception("/yoinks/<id>/screenshots failed")
            return self._send_json(500, {
                "ok": False, "error": "Couldn't read this uoink's screenshots."})
        if payload is None:
            return self._send_json(404, {"ok": False,
                                         "error": "uoink not found"})
        if dedupe:
            _apply_screenshot_dedupe(payload, threshold=threshold)
        return self._send_json(200, {"ok": True, **payload})

    def _handle_yoink_screenshots_suggest(self, bare: str):
        """GET /yoinks/<id>/screenshots/suggest?mode=tweet|thread|blog&thread_size=N
        &dedupe=true -- return the auto-suggested frame set for a post type.
        With dedupe enabled, suggestions operate on the exact same reduced
        frame set as the picker. Token gate cleared by do_GET."""
        from urllib.parse import unquote
        head = bare[len("/yoinks/"):-len("/screenshots/suggest")]
        video_id = unquote(head).strip("/")
        if not video_id:
            return self._send_json(400, {"ok": False,
                                         "error": "video_id required"})
        qs = parse_qs(urlparse(self.path).query)
        mode = (qs.get("mode") or ["tweet"])[0]
        dedupe, threshold = _screenshot_dedupe_query(qs)
        thread_size = None
        raw_ts = (qs.get("thread_size") or [None])[0]
        if raw_ts is not None:
            try:
                thread_size = int(raw_ts)
            except (TypeError, ValueError):
                return self._send_json(400, {
                    "ok": False, "error": "thread_size must be an integer"})
        try:
            payload = _screenshot_list_for_yoink(_get_index(), video_id)
        except Exception:
            log.exception("/yoinks/<id>/screenshots/suggest failed")
            return self._send_json(500, {
                "ok": False, "error": "Couldn't read this uoink's screenshots."})
        if payload is None:
            return self._send_json(404, {"ok": False,
                                         "error": "uoink not found"})
        if dedupe:
            _apply_screenshot_dedupe(payload, threshold=threshold)
        try:
            suggestion = _suggest_screenshots(
                payload, mode=mode, thread_size=thread_size)
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})
        return self._send_json(200, {
            "ok": True, "video_id": video_id,
            "interval_seconds": payload.get("interval_seconds"),
            "total_available": payload.get("count"),
            "deduped": bool(payload.get("deduped")),
            "dedupe_removed": payload.get("dedupe_removed", 0),
            "dedupe_available": payload.get("dedupe_available"),
            "dedupe_threshold": payload.get("dedupe_threshold"),
            **suggestion,
        })

    def _handle_yoink_screenshot_file(self, bare: str):
        """GET /yoinks/<id>/screenshots/<n>.png -- serve the Nth screenshot
        (0-based, matching the `index` field of the list endpoint) as binary
        image bytes for an inline grid that can't use /file?path=. The `.png`
        suffix is cosmetic; the real bytes are JPEG and the Content-Type
        follows the file on disk."""
        from urllib.parse import unquote
        tail = bare[len("/yoinks/"):]
        head, _, idx_part = tail.rpartition("/screenshots/")
        video_id = unquote(head).strip("/")
        idx_str = idx_part.rsplit(".", 1)[0]  # strip an optional .png/.jpg
        if not video_id or not idx_str.isdigit():
            return self._send_json(400, {
                "ok": False, "error": "expected /yoinks/<id>/screenshots/<n>"})
        index = int(idx_str)
        try:
            payload = _screenshot_list_for_yoink(_get_index(), video_id)
        except Exception:
            log.exception("/yoinks/<id>/screenshots/<n> failed")
            return self._send_json(500, {
                "ok": False, "error": "Couldn't read this uoink's screenshots."})
        if payload is None:
            return self._send_json(404, {"ok": False,
                                         "error": "uoink not found"})
        shots = payload.get("screenshots") or []
        if index < 0 or index >= len(shots):
            return self._send_json(404, {
                "ok": False, "error": "screenshot index out of range"})
        path, mime, status, error = _resolve_served_file(shots[index]["path"])
        if error:
            return self._send_json(status, {"ok": False, "error": error})
        return self._send_file(path, mime)

    def _handle_agents_detect(self):
        """GET /agents/detect -- list desktop AI clients on this machine so
        the dashboard can offer one-click connect buttons (Fix 4A). Token gate
        cleared by do_GET. Pure read."""
        try:
            agents = _detect_ai_clients()
        except Exception:
            log.exception("/agents/detect failed")
            return self._send_json(500, {
                "ok": False, "error": "Couldn't scan for AI clients."})
        return self._send_json(200, {
            "ok": True,
            "agents": agents,
            "any_installed": any(a["installed"] for a in agents),
        })

    def _handle_agents_connect(self, bare: str):
        """POST /agents/connect/<client> -- merge Uoink's MCP server entry
        into the client's config file in place (.bak backup, JSON validated
        first). Fix 4A. Token gate cleared by do_POST."""
        from urllib.parse import unquote
        client = unquote(bare[len("/agents/connect/"):]).strip("/")
        if not client:
            return self._send_json(400, {"ok": False,
                                         "error": "client required"})
        try:
            result = _connect_ai_client(client)
        except ValueError as e:
            return self._send_json(getattr(e, "http_status", 400),
                                   {"ok": False, "error": str(e)})
        except Exception:
            log.exception("/agents/connect/%s failed", client)
            return self._send_json(500, {
                "ok": False,
                "error": "Couldn't update that AI client's settings. "
                         "Nothing was changed."})
        return self._send_json(200, {"ok": True, **result})

    def _handle_reyoink(self, bare: str):
        """POST /yoinks/<id>/reyoink -- re-capture the source so the composer
        gets a fresh transcript + screenshots (D-20 Capability A). Reuses the
        /extract path verbatim so live-detection, rate-limit queueing, and
        job recording behave identically; the composer re-fetches
        /yoinks/<id>/screenshots once this returns ok."""
        from urllib.parse import unquote
        video_id = unquote(
            bare[len("/yoinks/"):-len("/reyoink")]).strip("/")
        if not video_id:
            return self._send_json(400, {"ok": False,
                                         "error": "video_id required"})
        resolved = _reyoink_source(_get_index(), video_id)
        if resolved is None:
            return self._send_json(404, {"ok": False,
                                         "error": "uoink not found"})
        url, interval = resolved
        if not url:
            return self._send_json(400, {
                "ok": False,
                "error": ("This uoink has no saved source link to re-capture. "
                          "Grab it again from the original page.")})
        body = {"url": url}
        if isinstance(interval, int) and interval > 0:
            body["interval"] = interval
        log.info("POST /yoinks/%s/reyoink -> re-extract %s", video_id, url)
        return self._handle_extract(body)

    def do_POST(self):
        # Auth first so we don't even read the body for unauthenticated
        # callers. Public POST endpoints don't exist today, so the gate is
        # unconditional here.
        if not self._require_token():
            return
        try:
            body = self._read_json_body()
        except Handler._BodyError as e:
            return self._send_json(e.status, {"ok": False, "error": e.message})

        bare = self.path.split("?", 1)[0]
        if bare == "/settings":
            return self._handle_settings_post(body)
        if bare == "/settings/test-key":
            return self._handle_settings_test_key(body)
        if bare.startswith("/agents/connect/"):
            return self._handle_agents_connect(bare)
        if bare == "/helper/quit":
            return self._handle_helper_quit()
        if bare == "/facets/classify":
            return self._handle_facets_classify(body)
        if bare.startswith("/mcp/v1"):
            return self._handle_mcp_post(bare, body)
        if bare == "/playlist/preview":
            return self._handle_playlist_preview(body)
        if bare == "/playlist/start":
            return self._handle_playlist_start(body)
        if bare.startswith("/jobs/") and bare.endswith("/cancel"):
            return self._handle_job_cancel(bare)
        if bare == "/extract":
            return self._handle_extract(body)
        if bare == "/extract/any":
            return self._handle_extract_any(body)
        if bare.startswith("/yoinks/") and bare.endswith("/reyoink"):
            return self._handle_reyoink(bare)
        if bare == "/extract/reddit":
            return self._handle_extract_reddit(body)
        if bare.startswith("/tools/"):
            return self._handle_tools_call_http(bare, body)
        if bare == "/index/backfill-cancel":
            _backfill_cancel.set()
            return self._send_json(200, {"ok": True, "cancelled": True})
        if bare == "/taxonomy/correct":
            return self._handle_taxonomy_correct(body)
        if bare == "/memory/delete":
            return self._handle_memory_delete(body)
        if bare == "/memory/restore":
            return self._handle_memory_restore(body)
        if bare == "/reliability/model/download":
            return self._handle_reliability_model_download()
        m = re.fullmatch(r"/reliability/([^/]+)/compute", bare)
        if m:
            return self._handle_reliability_compute(m.group(1), body)
        if bare == "/queue/cancel":
            return self._handle_queue_cancel(body)
        if bare == "/queue/retry-now":
            return self._handle_queue_retry_now(body)
        if bare == "/session/start":
            return self._handle_session_start(body)
        if bare == "/session/add":
            return self._handle_session_add(body)
        if bare == "/session/close":
            return self._handle_session_close(body)
        if bare == "/session/cancel":
            return self._handle_session_cancel(body)
        if bare == "/session/open":
            return self._handle_session_open(body)
        if bare == "/migration/move-desktop-corpus":
            return self._handle_move_desktop_corpus(body)
        if bare == "/engagement/log":
            return self._handle_engagement_log(body)
        if bare == "/channels":
            return self._handle_channels_add(body)
        if bare == "/channels/remove":
            return self._handle_channels_remove(body)
        if bare == "/channels/verify":
            return self._handle_channels_verify(body)
        if bare == "/channels/recognize-now":
            return self._handle_channels_recognize_now()
        if bare == "/workspaces":
            return self._handle_workspaces_create(body)
        if bare == "/workspace/assemble":
            return self._handle_workspace_assemble(body)
        if bare == "/workspace/critique":
            return self._handle_workspace_critique(body)
        if bare == "/claims/extract":
            return self._handle_claims_extract(body)
        if bare.startswith("/claims/") and bare.endswith("/verify"):
            return self._handle_claims_verify(bare, body)
        if bare.startswith("/claims/") and bare.endswith("/skip"):
            return self._handle_claims_skip(bare, body)
        if bare == "/script/generate":
            return self._handle_script_generate(body)
        if bare == "/script/revise":
            return self._handle_script_revise(body)
        if bare == "/script/shot-list":
            return self._handle_script_shot_list_post(body)
        if bare == "/memory/taste":
            return self._handle_memory_taste_post(body)
        if bare == "/memory/user":
            return self._handle_memory_user_post(body)
        if bare == "/podcasts/feeds":
            return self._handle_podcasts_feed_add(body)
        if bare == "/podcasts/feeds/remove":
            return self._handle_podcasts_feed_remove(body)
        if bare == "/podcasts/feeds/poll":
            return self._handle_podcasts_feed_poll(body)
        if bare == "/podcasts/feeds/set-enabled":
            return self._handle_podcasts_feed_set_enabled(body)
        if bare == "/podcasts/episodes/set-status":
            return self._handle_podcasts_episode_set_status(body)
        if bare == "/podcasts/episodes/download":
            return self._handle_podcasts_episode_download(body)
        if bare == "/podcasts/episodes/transcribe":
            return self._handle_podcasts_episode_transcribe(body)
        if bare == "/playlists/monitored":
            return self._handle_monitored_playlist_add(body)
        if bare == "/playlists/monitored/remove":
            return self._handle_monitored_playlist_remove(body)
        if bare == "/playlists/monitored/set-enabled":
            return self._handle_monitored_playlist_set_enabled(body)
        if bare == "/playlists/monitored/poll":
            return self._handle_monitored_playlist_poll(body)
        if bare == "/writing/compose/validate":
            return self._handle_writing_compose_validate(body)
        if bare == "/writing/draft":
            return self._handle_writing_draft_save(body)
        if bare == "/writing/tweet":
            return self._handle_writing_tweet(body)
        if bare == "/writing/blog":
            return self._handle_writing_blog(body)
        if bare.startswith("/writing/") and bare.endswith("/revise"):
            return self._handle_writing_revise(bare, body)
        if bare == "/writing/style-anchors":
            return self._handle_writing_style_anchor_add(body)
        if bare.startswith("/writing/style-anchors/"):
            return self._handle_writing_style_anchor_modify(bare, body)
        if bare == "/extract/page":
            return self._handle_extract_page(body)
        if bare == "/extract/page/allowlist":
            return self._handle_page_allowlist_modify(body)

        log.info("POST %s -> 404", bare)
        self._send_json(404, {"ok": False, "error": "not found"})

    def _handle_move_desktop_corpus(self, body: dict):
        """v2.1 opt-in Desktop-corpus migration (design Q5 A). The extension
        popup offers "Move your saved uoinks to Desktop\\Uoink\\? [Move] [Keep
        both]"; [Move] posts mode="move", [Keep both] posts mode="copy". The
        helper performs the file operation and returns the outcome. Never runs
        automatically -- this endpoint is the user-confirmed trigger."""
        mode = body.get("mode") if isinstance(body, dict) else None
        if mode not in ("move", "copy"):
            return self._send_json(
                400, {"ok": False, "error": "mode must be 'move' or 'copy'"})
        try:
            result = migrate_install.migrate_desktop_corpus(mode=mode)
        except Exception as e:
            log.exception("desktop corpus migration failed")
            return self._send_json(500, {"ok": False, "error": str(e)})
        outcome = result.get("outcome", "")
        ok = outcome in ("moved", "copied", "no_legacy_corpus")
        return self._send_json(200 if ok else 500, {"ok": ok, **result})

    def _validate_session_id(self, body: dict):
        """Pull and validate session_id from a request body. Returns
        (session_id, None) on success or (None, error_message) on failure.
        Rejects anything that isn't strictly alphanumeric+_-, since the id
        becomes a path segment under SESSIONS_ROOT."""
        session_id = (body.get("session_id") or "").strip()
        if not session_id:
            return None, "session_id required"
        if not _is_valid_session_id(session_id):
            return None, "session_id has invalid characters"
        return session_id, None

    # ---- /extract ----
    def _validate_url_interval(self, body: dict):
        url = (body.get("url") or "").strip()
        interval = body.get("interval", 30)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            return None, None, "interval must be an integer"
        if not (5 <= interval <= 300):
            return None, None, "interval must be between 5 and 300"
        # Strict hostname allowlist. Substring checks ("youtube.com" in url)
        # accept attacker-shaped URLs like https://evil.com/youtube.com/foo,
        # which yt-dlp would happily fetch as an arbitrary URL.
        # v3.1: dispatcher accepts YouTube OR Twitter/X. Platform is
        # carried forward separately so the extraction pipeline can flag
        # it on the sidecar without re-parsing the URL.
        normalized, platform = _normalize_video_url(url)
        if not normalized:
            return None, None, ("URL must be a youtube.com, youtu.be, or "
                                  "twitter.com/x.com video link")
        # Stash the platform on the body so the downstream handler can
        # pull it without re-parsing. Backward-compatible: callers that
        # don't read body["platform"] still get the normalized URL.
        if isinstance(body, dict):
            body["__platform"] = platform
        return normalized, interval, None

    def _validate_playlist_body(self, body: dict, *, require_interval: bool = False):
        raw = body.get("url")
        if not isinstance(raw, str):
            return None, None, "playlist URL invalid", 400
        url = _normalize_playlist_url(raw.strip())
        if not url:
            return None, None, "playlist URL invalid", 400
        interval = body.get("interval", 30)
        if require_interval or "interval" in body:
            try:
                interval = int(interval)
            except (TypeError, ValueError):
                return None, None, "interval must be an integer", 400
            if not (5 <= interval <= 300):
                return None, None, "interval must be between 5 and 300", 400
        return url, interval, None, 200

    def _job_id_from_path(self, bare: str, *, cancel: bool = False):
        prefix = "/jobs/"
        suffix = "/cancel" if cancel else ""
        if not bare.startswith(prefix) or (suffix and not bare.endswith(suffix)):
            return None, "job id invalid", 400
        job_id = bare[len(prefix):]
        if suffix:
            job_id = job_id[:-len(suffix)]
        job_id = job_id.strip("/")
        if not _is_valid_job_id(job_id):
            return None, "job id invalid", 400
        return job_id, None, 200

    # ---- /playlist/preview ----
    def _handle_playlist_preview(self, body: dict):
        url, _interval, err, status = self._validate_playlist_body(body)
        if err:
            return self._send_json(status, {"ok": False, "error": err})
        playlist, err, status = _fetch_playlist_preview(url)
        if err:
            return self._send_json(status, {"ok": False, "error": err})
        self._send_json(200, {"ok": True, "playlist": playlist})

    # ---- /playlist/start ----
    def _handle_playlist_start(self, body: dict):
        url, interval, err, status = self._validate_playlist_body(body, require_interval=True)
        if err:
            return self._send_json(status, {"ok": False, "error": err})
        playlist, err, status = _fetch_playlist_preview(url)
        if err:
            return self._send_json(status, {"ok": False, "error": err})

        job_id, public = _create_playlist_job(playlist, interval)
        self._send_json(200, {"ok": True, "job_id": job_id, "job": public})

    # ---- /jobs/<id> ----
    def _handle_job_get(self, bare: str):
        job_id, err, status = self._job_id_from_path(bare)
        if err:
            return self._send_json(status, {"ok": False, "error": err})
        job = _get_public_job(job_id)
        if not job:
            return self._send_json(404, {"ok": False, "error": "job not found"})
        self._send_json(200, {"ok": True, "job": job})

    # ---- /jobs/<id>/cancel ----
    def _handle_job_cancel(self, bare: str):
        job_id, err, status = self._job_id_from_path(bare, cancel=True)
        if err:
            return self._send_json(status, {"ok": False, "error": err})
        public, error, status = _cancel_playlist_job(job_id)
        if error:
            return self._send_json(status, {"ok": False, "error": error})
        self._send_json(200, {"ok": True, "job": public})

    # ---- /jobs ----
    def _handle_jobs_list(self):
        qs = parse_qs(urlparse(self.path).query)
        kind = (qs.get("kind") or [None])[0]
        if kind not in (None, "", "playlist", "single"):
            return self._send_json(400, {
                "ok": False,
                "error": "kind must be playlist or single",
            })
        self._send_json(200, {
            "ok": True,
            "jobs": _list_public_jobs(kind or None),
        })

    # ---- /jobs/stream (Tier 2 SSE) ----
    def _queue_snapshot(self) -> dict:
        """Rate-limit queue counts for an SSE `queue` event. Tolerant of index
        errors (returns zeros) so a transient DB hiccup never kills the stream."""
        try:
            overview = _get_index().pending_counts()
        except Exception:
            overview = {}
        counts = overview.get("counts", {}) if isinstance(overview, dict) else {}
        return {
            "pending": int(counts.get("pending", 0)),
            "running": int(counts.get("running", 0)),
            "failed": int(counts.get("failed", 0)),
            "succeeded": int(counts.get("succeeded", 0)),
            "cancelled": int(counts.get("cancelled", 0)),
            "next_retry_at": overview.get("next_retry_at") if isinstance(overview, dict) else None,
        }

    def _jobs_map(self) -> dict:
        """{id: _public_job} for every current job (same shape /jobs returns)."""
        return {j["id"]: j for j in _list_public_jobs() if j.get("id")}

    def _jobs_snapshot(self) -> dict:
        jobs = _list_public_jobs()
        active = [j for j in jobs
                  if (j.get("state") or "").lower() not in _JOB_TERMINAL_STATES]
        recent = [j for j in jobs
                  if (j.get("state") or "").lower() in _JOB_TERMINAL_STATES][:10]
        return {"active": active, "recent": recent, "queue": self._queue_snapshot()}

    def _sse_emit(self, event: str, obj) -> None:
        frame = "event: %s\ndata: %s\n\n" % (event, json.dumps(obj, default=str))
        self.wfile.write(frame.encode("utf-8"))
        self.wfile.flush()

    def _handle_jobs_stream(self):
        """Server-sent job/queue stream (Tier 2). Header-gated; consume via
        fetch()+ReadableStream, NOT EventSource, so the token rides the
        X-Uoink-Token header rather than a URL (see _request_token). Emits one
        `snapshot`, then `job`/`queue` deltas on a 1s poll, plus a `: heartbeat`
        comment every 15s. One thread per connection (ThreadingHTTPServer);
        exits when the client disconnects (write raises) -- and dies with the
        process on shutdown, since worker threads are daemonic."""
        if not self._require_token():
            return
        with _sse_count_lock:
            if _sse_active[0] >= _SSE_MAX_STREAMS:
                return self._send_json(503, {"ok": False, "error": "too many streams"})
            _sse_active[0] += 1
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            # Defeat any proxy buffering so events arrive promptly.
            self.send_header("X-Accel-Buffering", "no")
            self._send_cors(self._cors_origin())
            self.end_headers()
            self.close_connection = True  # don't reuse the socket after we return

            self._sse_emit("snapshot", self._jobs_snapshot())
            last_jobs = self._jobs_map()
            last_queue = self._queue_snapshot()
            last_beat = time.monotonic()
            while True:
                time.sleep(_SSE_TICK_SEC)
                cur = self._jobs_map()
                for jid, jobj in cur.items():
                    if last_jobs.get(jid) != jobj:
                        self._sse_emit("job", jobj)
                last_jobs = cur
                queue = self._queue_snapshot()
                if queue != last_queue:
                    self._sse_emit("queue", queue)
                    last_queue = queue
                now = time.monotonic()
                if now - last_beat >= _SSE_HEARTBEAT_SEC:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    last_beat = now
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client went away -- reap this stream
        finally:
            with _sse_count_lock:
                _sse_active[0] -= 1

    # ---- /taxonomy ----
    def _handle_taxonomy(self):
        qs = parse_qs(urlparse(self.path).query)
        channel = (qs.get("channel") or [None])[0]
        hook_type = (qs.get("hook_type") or [None])[0]
        if hook_type:
            hook_type = hook_type.strip().lower()
            if hook_type not in HOOK_TYPES:
                return self._send_json(400, {
                    "ok": False,
                    "error": "hook_type invalid",
                })
        limit_raw = (qs.get("limit") or ["50"])[0]
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False,
                "error": "limit invalid",
            })
        limit = max(1, min(500, limit))
        self._send_json(200, {
            "ok": True,
            "taxonomy": _query_taxonomy(
                channel=channel,
                hook_type=hook_type,
                limit=limit,
            ),
        })

    # ---- /taxonomy/corrections ----
    def _handle_taxonomy_corrections(self):
        """List recent Hook Type corrections (Sprint 17 / A3 follow-up).
        Feeds the setup.html "Hook Type calibration" review surface.
        Read-only sibling of POST /taxonomy/correct."""
        qs = parse_qs(urlparse(self.path).query)
        channel = (qs.get("channel") or [None])[0]
        topic = (qs.get("topic") or [None])[0]
        limit_raw = (qs.get("limit") or ["50"])[0]
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False,
                "error": "limit invalid",
            })
        limit = max(1, min(200, limit))
        idx = _get_index()
        try:
            corrections = idx.list_corrections(
                limit=limit,
                channel=channel,
                topic=topic,
            )
        except Exception as e:
            log.warning("taxonomy corrections: index read failed: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "index unavailable"})
        self._send_json(200, {
            "ok": True,
            "corrections": corrections,
        })

    # ---- /taxonomy/correct ----
    def _handle_taxonomy_correct(self, body: dict):
        """Record a user's Hook Type correction (Sprint 17 / A3). The
        corrected value becomes the canonical classification and feeds back
        into future classifications as a few-shot anchor."""
        if not _check_taxonomy_correct_rate_limit():
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        video_id = (body.get("video_id") or "").strip()
        corrected = (body.get("corrected_hook_type") or "").strip().lower()
        user_reason = body.get("user_reason")
        if not video_id:
            return self._send_json(400, {"ok": False, "error": "video_id required"})
        if corrected not in HOOK_TYPES:
            return self._send_json(
                400, {"ok": False, "error": "corrected_hook_type invalid"})
        if user_reason is not None and not isinstance(user_reason, str):
            return self._send_json(
                400, {"ok": False, "error": "user_reason must be a string"})
        user_reason = (user_reason or "").strip() or None

        idx = _get_index()
        try:
            yoink = idx.get_yoink(video_id)
        except Exception as e:
            log.warning("taxonomy correct: index read failed: %s", e)
            return self._send_json(500, {"ok": False, "error": "index unavailable"})
        if not yoink:
            return self._send_json(404, {"ok": False, "error": "video not found"})

        # The original (pre-correction) hook type is read from the sidecar,
        # which the Hook Type worker keeps current; it is also the file this
        # endpoint updates.
        sidecar_path = Path(yoink.get("sidecar_path") or "")
        original = None
        try:
            sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
            original = (sc.get("hook_type") or "").strip() or None
        except (OSError, json.JSONDecodeError):
            original = None
        if not original:
            return self._send_json(409, {
                "ok": False,
                "error": "video has no hook classification to correct",
            })

        try:
            correction_id = idx.upsert_taxonomy_correction(
                video_id, original, corrected,
                user_reason=user_reason,
                channel=yoink.get("channel"),
                topic=yoink.get("topic"),
            )
        except Exception as e:
            log.warning("taxonomy correct: write failed: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "could not store correction"})

        # Sidecar update is best-effort -- the index row is authoritative.
        _record_correction_in_sidecar(sidecar_path, original, corrected)
        log.info("taxonomy correction: %s %s -> %s (#%s)",
                 video_id, original, corrected, correction_id)
        self._send_json(200, {"ok": True, "correction_id": correction_id})

    # ---- /memory/delete ----
    def _handle_memory_delete(self, body: dict):
        """Soft-delete a yoink: move its folder into _yoink-trash/ and set
        the index row's deleted_at. Reversible via /memory/restore until the
        30-day purge runs."""
        video_id = (body.get("video_id") or "").strip()
        if not video_id:
            return self._send_json(400, {"ok": False, "error": "video_id required"})
        idx = _get_index()
        row = idx.get_yoink(video_id)
        if not row:
            return self._send_json(404, {"ok": False, "error": "yoink not found"})
        if row.get("deleted_at"):
            return self._send_json(409, {"ok": False, "error": "already deleted"})

        src = Path(row.get("corpus_path") or "").parent
        if not src.exists() or not src.is_dir():
            return self._send_json(
                409, {"ok": False, "error": "yoink folder missing on disk"})

        # Mark deleted first so the trash folder name derives from the same
        # deleted_at the index stores; roll the row back if the move fails.
        updated = idx.soft_delete_yoink(video_id)
        dst = _trash_folder_for(updated)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as e:
            idx.restore_yoink(video_id)
            log.warning("memory delete: move to trash failed: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "could not move folder to trash"})
        log.info("memory delete: %s -> %s", video_id, dst)
        self._send_json(200, {
            "ok": True,
            "restored_at": None,
            "deleted_at": updated.get("deleted_at"),
        })

    # ---- /memory/restore ----
    def _handle_memory_restore(self, body: dict):
        """Restore a soft-deleted yoink: move its folder back from
        _yoink-trash/ and clear the index row's deleted_at."""
        video_id = (body.get("video_id") or "").strip()
        if not video_id:
            return self._send_json(400, {"ok": False, "error": "video_id required"})
        idx = _get_index()
        row = idx.get_yoink(video_id)
        if not row:
            return self._send_json(404, {"ok": False, "error": "yoink not found"})
        if not row.get("deleted_at"):
            return self._send_json(409, {"ok": False, "error": "yoink is not deleted"})

        trash = _trash_folder_for(row)
        dst = Path(row.get("corpus_path") or "").parent
        if not trash.exists():
            return self._send_json(
                409, {"ok": False, "error": "trash folder not found"})
        if dst.exists():
            return self._send_json(
                409, {"ok": False, "error": "original location is occupied"})
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trash), str(dst))
        except (OSError, shutil.Error) as e:
            log.warning("memory restore: move from trash failed: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "could not restore folder"})
        idx.restore_yoink(video_id)
        log.info("memory restore: %s <- %s", video_id, trash)
        self._send_json(200, {"ok": True, "restored_at": _now_iso()})

    # ---- /queue/status ----
    def _handle_queue_status(self):
        """Snapshot of the rate-limit retry queue (Sprint 19 / C4):
        per-status counts, the earliest retry_after, and the live
        (non-terminal) rows for a status banner. Token-gated, 60/min."""
        if not _check_queue_status_rate_limit():
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        idx = _get_index()
        try:
            overview = idx.pending_counts()
            pending = [
                _pending_with_long_video_mode(row)
                for row in idx.list_pending(limit=50, include_terminal=False)
            ]
        except Exception as e:
            log.warning("queue status: index error: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "queue unavailable"})
        counts = overview.get("counts", {})
        self._send_json(200, {
            "ok": True,
            "pending_count": int(counts.get("pending", 0)),
            "running_count": int(counts.get("running", 0)),
            "failed_count": int(counts.get("failed", 0)),
            "succeeded_count": int(counts.get("succeeded", 0)),
            "cancelled_count": int(counts.get("cancelled", 0)),
            "next_retry_at": overview.get("next_retry_at"),
            "pending": pending,
        })

    def _validate_pending_id(self, body: dict):
        raw = body.get("pending_id")
        try:
            pending_id = int(raw)
        except (TypeError, ValueError):
            return None, "pending_id required"
        if pending_id <= 0:
            return None, "pending_id invalid"
        return pending_id, None

    # ---- /queue/cancel ----
    def _handle_queue_cancel(self, body: dict):
        """Cancel a queued URL. 30/min."""
        if not _check_queue_mutate_rate_limit():
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        pending_id, err = self._validate_pending_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        try:
            changed = _get_index().cancel_pending(pending_id)
        except Exception as e:
            log.warning("queue cancel: index error: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "queue unavailable"})
        if not changed:
            return self._send_json(404, {
                "ok": False,
                "error": "pending row not found or already terminal",
            })
        _pending_long_video_mode(pending_id, remove=True)
        log.info("queue cancel: pending_id=%d", pending_id)
        self._send_json(200, {"ok": True})

    # ---- /queue/retry-now ----
    def _handle_queue_retry_now(self, body: dict):
        """Bump a queued URL's retry_after to now so the worker picks it up
        on the next poll. Resurrects 'failed' rows too; no-op for
        'succeeded' or 'cancelled'. 30/min."""
        if not _check_queue_mutate_rate_limit():
            return self._send_json(429, {"ok": False, "error": "too many requests"})
        pending_id, err = self._validate_pending_id(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        try:
            changed = _get_index().retry_pending_now(pending_id)
        except Exception as e:
            log.warning("queue retry-now: index error: %s", e)
            return self._send_json(
                500, {"ok": False, "error": "queue unavailable"})
        if not changed:
            return self._send_json(404, {
                "ok": False,
                "error": "pending row not found or already terminal",
            })
        log.info("queue retry-now: pending_id=%d", pending_id)
        self._send_json(200, {"ok": True})

    def _handle_extract_any(self, body: dict):
        """v3.1 universal extractor entry point.

        Accepts any URL yt-dlp supports (1,800+ sites). Routing:
          - YouTube canonical -> delegates to _handle_extract (full
            pipeline with screenshots + transcript + comments + hook).
          - Twitter canonical -> delegates to _handle_extract too (yt-dlp
            handles it; URL validation already accepted it via the
            Twitter normaliser).
          - Generic (anything else valid) -> slim metadata-only path:
            calls yt-dlp --dump-single-json --no-download, writes a
            sidecar + a basic corpus.md (title + uploader + description
            + transcript if available + thumbnail URL). NO screenshots,
            NO comment fetch, NO hook classification -- those rely on
            YouTube structure.

        The slim path is the prompt's `transcript + thumbnail only`
        graceful fallback. A later PR can deepen it with optional
        ffmpeg screenshots once we know which sites benefit."""
        raw = (body.get("url") or "").strip()
        canonical, platform = _normalize_any_url(raw)
        if not canonical:
            return self._send_json(400, {
                "ok": False,
                "error": ("URL must be http(s) with a valid hostname "
                          "(yt-dlp accepts 1,800+ sites; the helper "
                          "filters attacker-shaped inputs)")})
        # If it's a known platform we already have a full pipeline for,
        # delegate. The downstream handler runs its own validation; we
        # pass the canonical so we don't double-normalise.
        if platform in (PLATFORM_YOUTUBE, PLATFORM_TWITTER):
            body = dict(body)
            body["url"] = canonical
            return self._handle_extract(body)

        # Generic path: metadata-only extraction. Best-effort -- if
        # yt-dlp doesn't support the URL we surface its error verbatim
        # so the user gets a useful message rather than a generic 500.
        log.info("POST /extract/any (generic) url=%s -> running", canonical)
        DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
        with _extract_lock:
            try:
                metadata = _fetch_metadata(canonical)
            except subprocess.CalledProcessError as e:
                detail = friendly_error(e) if callable(globals().get(
                    "friendly_error")) else str(e)
                return self._send_json(400, {
                    "ok": False, "error": f"yt-dlp could not extract: {detail}",
                    "url": canonical, "platform": platform})
            except Exception as e:
                log.exception("/extract/any (generic) metadata failed")
                return self._send_json(500, {
                    "ok": False, "error": str(e),
                    "url": canonical, "platform": platform})

        title = metadata.get("title") or "Untitled"
        topic = _classify_topic(metadata)
        folder = (DESKTOP_ROOT / _topic_folder_name(topic)
                   / (slugify(title) or "video"))
        folder.mkdir(parents=True, exist_ok=True)

        # Best-effort transcript reconstruction from yt-dlp's
        # subtitles/automatic_captions map (when present).
        transcript_entries = _extract_generic_transcript(metadata)

        # Slim sidecar -- structurally compatible with the v2.5 reader,
        # all v3-only fields tagged.
        sidecar = {
            "schema_version": CURRENT_SIDECAR_SCHEMA,
            "url": canonical,
            "platform": platform,
            "extraction_mode": "generic",   # v3.1 marker
            "title": title,
            "topic": topic,
            "yoinked_at": _now_iso(),
            "duration_seconds": metadata.get("duration"),
            "channel": (metadata.get("channel") or metadata.get("uploader")
                          or metadata.get("creator")),
            "channel_url": (metadata.get("channel_url")
                               or metadata.get("uploader_url")),
            "upload_date": metadata.get("upload_date"),
            "view_count": metadata.get("view_count"),
            "video_id": metadata.get("id"),
            "transcript": transcript_entries,
            # Comments/screenshots/hook are explicit nulls so the
            # dashboard knows they're unavailable rather than missing.
            "comments_status": "skipped_generic",
            "screenshots": [],
            "thumbnail_url": (metadata.get("thumbnail") or None),
            "host": (urlparse(canonical).hostname or "").lower(),
        }
        sidecar_path = folder / f"{folder.name}.json"
        _atomic_write_text(sidecar_path,
                            json.dumps(sidecar, indent=2, ensure_ascii=False))

        # Slim corpus markdown -- enough for an agent to do useful work.
        corpus_lines = [
            f"# {title}",
            "",
            f"**Source:** {canonical}",
            f"**Platform:** {platform} ({sidecar['host']})",
        ]
        if sidecar["channel"]:
            corpus_lines.append(f"**Channel/Creator:** {sidecar['channel']}")
        if sidecar["duration_seconds"]:
            corpus_lines.append(
                f"**Duration:** {fmt_time(int(sidecar['duration_seconds']))}")
        if sidecar["upload_date"]:
            corpus_lines.append(f"**Uploaded:** {sidecar['upload_date']}")
        corpus_lines.append("")
        desc = (metadata.get("description") or "").strip()
        if desc:
            corpus_lines += ["## Description", "", desc, ""]
        if transcript_entries:
            corpus_lines += ["## Transcript", ""]
            for ent in transcript_entries:
                corpus_lines.append(
                    f"- [{fmt_time(int(ent.get('start') or 0))}] "
                    f"{ent.get('text') or ''}")
            corpus_lines.append("")
        else:
            corpus_lines += ["## Transcript",
                              "",
                              "_No transcript available (site did not "
                              "expose subtitles / yt-dlp could not parse)._",
                              ""]
        corpus_path = folder / "corpus.md"
        _atomic_write_text(corpus_path, "\n".join(corpus_lines))

        # Persist as a yoink row so it appears in Library + MCP search.
        try:
            _get_index().upsert_yoink({
                "video_id": (metadata.get("id")
                                or f"generic_{abs(hash(canonical)) & 0xFFFFFF:06x}"),
                "slug": folder.name,
                "channel": sidecar["channel"],
                "title": title,
                "topic": topic,
                "yoinked_at": sidecar["yoinked_at"],
                "corpus_path": str(corpus_path),
                "sidecar_path": str(sidecar_path),
                "metadata_json": json.dumps({
                    "platform": platform,
                    "duration_seconds": sidecar["duration_seconds"],
                    "host": sidecar["host"],
                }),
            }, content=("\n".join(corpus_lines)[:65000]))
        except Exception as e:
            log.warning("/extract/any generic upsert_yoink failed: %s", e)

        return self._send_json(200, {
            "ok": True,
            "mode": "generic",
            "platform": platform,
            "host": sidecar["host"],
            "url": canonical,
            "title": title,
            "folder": str(folder),
            "transcript_segments": len(transcript_entries),
            "has_thumbnail": bool(sidecar["thumbnail_url"]),
        })

    def _handle_live_extract_dispatch(self, url, interval, live_state,
                                      metadata, long_video_mode):
        """v3.1 live stream branch. Returns a Response dict (and the
        caller short-circuits) when we want to defer the extraction;
        returns None when the caller should proceed with the normal
        download (post_live with a recording exposed).

        Wait-for-end mode: enqueue into pending_yoinks with a future
        retry_after so the existing rate-limit retry worker (which polls
        on schedule) re-attempts when the broadcast ends. We piggyback
        on the existing infra rather than spinning a dedicated live
        worker -- the worker doesn't care WHY a row is pending, only
        whether retry_after has passed.

        extract_when_recorded mode: for is_live + upcoming we 409 with
        a useful message. For post_live we try anyway (yt-dlp will
        return a recording when one is exposed).

        Returns None iff the caller should fall through to the normal
        _run_extraction pipeline."""
        settings = (_read_settings() or {})
        behavior = _normalize_live_behavior(
            settings.get("live_stream_behavior"))
        live_title = (metadata or {}).get("title") or url

        # When mode == NOW + state == POST_LIVE we let the extraction
        # proceed (the recording may already be downloadable).
        if (behavior == LIVE_BEHAVIOR_NOW
                and live_state == LIVE_STATE_POST_LIVE):
            return None  # fall through

        # When mode == NOW + state in (LIVE, UPCOMING) we surface the
        # live status as a 409. The dashboard can offer a "retry now"
        # button later.
        if behavior == LIVE_BEHAVIOR_NOW and live_state in (
                LIVE_STATE_LIVE, LIVE_STATE_UPCOMING):
            return self._send_json(409, {
                "ok": False,
                "live_state": live_state,
                "behavior": behavior,
                "title": live_title,
                "error": ("URL is currently a live broadcast; "
                           "your setting requests immediate extraction "
                           "only when a recording is exposed. Try "
                           "again after the broadcast ends, or change "
                           "the setting to wait_for_end to enqueue "
                           "automatically."),
            })

        # Default (wait_for_end + any live-ish state): enqueue. The
        # retry worker will re-fetch metadata; once live_state moves to
        # was_live, the existing extraction pipeline proceeds.
        retry_after = (datetime.now() + timedelta(
            seconds=_LIVE_RETRY_INTERVAL_SEC
        )).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            pending_id = _get_index().enqueue_pending(
                url, interval, retry_after, long_video_mode)
        except Exception as e:
            log.warning("live: enqueue failed (%s); proceeding inline", e)
            return None  # fall through -- best-effort
        _remember_pending_long_video_mode(pending_id, long_video_mode)
        log.info("POST /extract -> queued (live state=%s) pending_id=%d",
                  live_state, pending_id)
        return self._send_json(200, {
            "ok": True,
            "queued": True,
            "pending_id": pending_id,
            "retry_after": retry_after,
            "reason": "live_stream",
            "live_state": live_state,
            "behavior": behavior,
            "title": live_title,
            "long_video_mode": long_video_mode,
        })

    def _handle_live_status_get(self):
        """GET /live/status?url=... -- check whether a URL is currently
        a live broadcast without extracting. Used by the dashboard +
        the popup to render a 'live' chip before queueing."""
        if not self._require_token():
            return
        qs = parse_qs(urlparse(self.path).query)
        raw = (qs.get("url") or [""])[0]
        canonical, _platform = _normalize_video_url(raw)
        if not canonical:
            # /extract/any landed; fall back to the relaxed validator so
            # we can probe live state on generic URLs too.
            canonical, _platform = _normalize_any_url(raw)
        if not canonical:
            return self._send_json(400, {
                "ok": False, "error": "url query param required"})
        try:
            metadata = _fetch_metadata(canonical)
        except Exception as e:
            return self._send_json(400, {
                "ok": False, "error": f"yt-dlp could not fetch: {e}",
                "url": canonical})
        state = _detect_live_state(metadata)
        return self._send_json(200, {
            "ok": True, "url": canonical, "live_state": state,
            "title": metadata.get("title"),
            "supported_states": list(_LIVE_STATES),
        })

    def _handle_extract(self, body: dict):
        url, interval, err = self._validate_url_interval(body)
        if err:
            log.info("POST /extract -> 400 (%s)", err)
            return self._send_json(400, {"ok": False, "error": err})
        try:
            long_video_mode = _normalize_long_video_mode(
                body.get("long_video_mode"))
        except ValueError as e:
            return self._send_json(400, {"ok": False, "error": str(e)})

        log.info("POST /extract url=%s interval=%d long_video_mode=%s -> running",
                 url, interval, long_video_mode)
        DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
        started_at = _now_iso()
        title = None
        folder = None
        current_phase = "metadata"
        with _extract_lock:
            try:
                # One metadata fetch up front — used both to derive the folder
                # slug here and re-used by _run_extraction (avoids a 2nd call).
                metadata = _fetch_metadata(url)
                # v3.1 live stream handoff: route currently-broadcasting
                # / scheduled URLs through the live branch BEFORE
                # _run_extraction tries to download a half-stream.
                live_state = _detect_live_state(metadata)
                if live_state in (LIVE_STATE_LIVE, LIVE_STATE_UPCOMING,
                                    LIVE_STATE_POST_LIVE):
                    response = self._handle_live_extract_dispatch(
                        url, interval, live_state, metadata, long_video_mode)
                    if response is not None:
                        return response
                title = metadata.get("title") or "Untitled"
                topic = _classify_topic(metadata)
                folder = DESKTOP_ROOT / _topic_folder_name(topic) / (slugify(title) or "video")

                def phase_cb(phase: str):
                    nonlocal current_phase
                    current_phase = phase

                result = _run_extraction(url, interval, folder,
                                          metadata=metadata, topic=topic,
                                          long_video_mode=long_video_mode,
                                          phase_callback=phase_cb)
            except BaseException as e:
                # Sprint 19 / C4: YouTube 429 -> queue for retry instead of
                # surfacing an error. The retry worker takes over from here.
                if _is_youtube_rate_limit(e):
                    retry_after = (datetime.now() + timedelta(
                        seconds=_RATE_LIMIT_INITIAL_BACKOFF_SEC
                    )).strftime("%Y-%m-%dT%H:%M:%S")
                    try:
                        pending_id = _get_index().enqueue_pending(
                            url, interval, retry_after, long_video_mode)
                    except Exception as enqueue_err:
                        # Index unavailable; fall through to the pre-Sprint-19
                        # error path so the user still gets a useful message.
                        log.warning("POST /extract -> could not enqueue "
                                    "rate-limited URL: %s", enqueue_err)
                    else:
                        _remember_pending_long_video_mode(
                            pending_id, long_video_mode)
                        log.info(
                            "POST /extract -> queued (rate-limit) pending_id=%d",
                            pending_id)
                        return self._send_json(200, {
                            "ok": True,
                            "queued": True,
                            "pending_id": pending_id,
                            "retry_after": retry_after,
                            "reason": "youtube_rate_limit",
                            "long_video_mode": long_video_mode,
                        })
                msg = friendly_error(e)
                detail = machine_error_detail(e)
                failure_phase = _failure_phase(e, current_phase)
                log.error("POST /extract -> error: %s", msg)
                _record_single_extract_job(
                    url,
                    started_at,
                    error=msg,
                    error_detail=detail,
                    failure_phase=failure_phase,
                    long_video_mode=long_video_mode,
                    title=title,
                    folder=folder,
                )
                return self._send_json(200, {
                    "ok": False,
                    "error": msg,
                    "error_detail": detail,
                    "failure_phase": failure_phase,
                })

        _record_single_extract_job(url, started_at, result=result)
        log.info("POST /extract -> ok (%d shots, %s)",
                 result["screenshot_count"], result["folder"])
        self._send_json(200, result)

    # ---- /session/start ----
    def _handle_session_start(self, body: dict):
        name = (body.get("name") or "").strip()
        with _session_lock:
            existing = _active_session()
            if existing:
                msg = (f"A session is already open: '{existing.get('name')}'. "
                       "Close or cancel it before starting a new one.")
                log.info("POST /session/start -> 409 (active=%s)", existing.get("slug"))
                return self._send_json(409, {"ok": False, "error": msg, "active_session": {
                    "id": existing["slug"], "name": existing.get("name"),
                    "video_count": len(existing.get("videos", [])),
                }})

            slug_base = slugify(name) if name else datetime.now().strftime("session_%Y%m%d_%H%M%S")
            slug = slug_base or datetime.now().strftime("session_%Y%m%d_%H%M%S")
            # Disambiguate if a folder with that slug already exists.
            if _session_folder(slug).exists():
                slug = f"{slug}_{uuid.uuid4().hex[:6]}"

            session = {
                "name": name or slug,
                "slug": slug,
                "created_at": _now_iso(),
                "status": "open",
                "videos": [],
            }
            _write_session(slug, session)

        folder = _session_folder(slug)
        log.info("POST /session/start -> created %s", folder)
        self._send_json(200, {
            "ok": True,
            "session_id": slug,
            "name": session["name"],
            "folder": str(folder),
        })

    # ---- /session/add ----
    def _handle_session_add(self, body: dict):
        session_id, sid_err = self._validate_session_id(body)
        if sid_err:
            return self._send_json(400, {"ok": False, "error": sid_err})
        url, interval, err = self._validate_url_interval(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})

        session = _read_session(session_id)
        if not session:
            return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
        if session.get("status") != "open":
            return self._send_json(409, {
                "ok": False,
                "error": f"session '{session_id}' is {session.get('status')}, not open",
            })

        log.info("POST /session/add session=%s url=%s -> running", session_id, url)
        sess_folder = _session_folder(session_id)
        # Disambiguate the per-video subfolder by title — fetch metadata once
        # and re-use it inside _run_extraction.
        with _extract_lock:
            try:
                metadata = _fetch_metadata(url)
                title = metadata.get("title") or "Untitled"
                topic = _classify_topic(metadata)
                video_slug = slugify(title) or "video"
                target = sess_folder / video_slug
                # Disambiguate if same-named video already added.
                if target.exists():
                    video_slug = f"{video_slug}_{uuid.uuid4().hex[:6]}"
                    target = sess_folder / video_slug

                # Session adds don't go to the clipboard one-by-one (the
                # whole session is concatenated and copied at /session/close),
                # so skip the per-video paste-corpus generation -- it would
                # just inflate the runtime message payload for nothing.
                result = _run_extraction(url, interval, target,
                                          open_explorer=False,
                                          metadata=metadata, topic=topic,
                                          generate_paste=False)
            except BaseException as e:
                msg = friendly_error(e)
                detail = machine_error_detail(e)
                log.error("POST /session/add -> error: %s", msg)
                return self._send_json(200, {
                    "ok": False,
                    "error": msg,
                    "error_detail": detail,
                    "session_id": session_id,
                })

        with _session_lock:
            session = _read_session(session_id) or session
            session.setdefault("videos", []).append({
                "url": url,
                "title": result["title"],
                "video_slug": result["video_slug"],
                "screenshot_count": result["screenshot_count"],
                "caption_count": result.get("caption_count", 0),
                "added_at": _now_iso(),
            })
            _write_session(session_id, session)

        log.info("POST /session/add -> ok (%d shots, total videos=%d)",
                 result["screenshot_count"], len(session["videos"]))
        result.update({"session_id": session_id, "video_count": len(session["videos"])})
        self._send_json(200, result)

    # ---- /session/close ----
    def _handle_session_close(self, body: dict):
        session_id, sid_err = self._validate_session_id(body)
        if sid_err:
            return self._send_json(400, {"ok": False, "error": sid_err})

        with _session_lock:
            session = _read_session(session_id)
            if not session:
                return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
            if session.get("status") != "open":
                return self._send_json(409, {
                    "ok": False,
                    "error": f"session is {session.get('status')}, cannot close",
                })

            corpus_md = _build_corpus(session)
            corpus_path = _session_folder(session_id) / "corpus.md"
            _atomic_write_text(corpus_path, corpus_md)

            session["status"] = "closed"
            session["closed_at"] = _now_iso()
            _write_session(session_id, session)

        sess_folder = _session_folder(session_id)
        try:
            _platform.open_in_os(sess_folder)
        except Exception as e:
            log.warning("startfile failed: %s", e)

        total_captions = sum(v.get("caption_count", 0) for v in session.get("videos", []))
        log.info("POST /session/close -> ok (%d videos, %d chars)",
                 len(session.get("videos", [])), len(corpus_md))
        self._send_json(200, {
            "ok": True,
            "corpus_path": str(corpus_path),
            "corpus_md": corpus_md,
            "video_count": len(session.get("videos", [])),
            "caption_count": total_captions,
            "session_folder": str(sess_folder),
            "name": session.get("name"),
        })

    # ---- /session/cancel ----
    def _handle_session_cancel(self, body: dict):
        session_id, sid_err = self._validate_session_id(body)
        if sid_err:
            return self._send_json(400, {"ok": False, "error": sid_err})

        with _session_lock:
            session = _read_session(session_id)
            if not session:
                return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
            if session.get("status") not in ("open",):
                return self._send_json(409, {
                    "ok": False,
                    "error": f"session is {session.get('status')}, cannot cancel",
                })
            session["status"] = "cancelled"
            session["cancelled_at"] = _now_iso()
            _write_session(session_id, session)

        log.info("POST /session/cancel -> ok (%s)", session_id)
        self._send_json(200, {"ok": True, "session_id": session_id})

    # ---- /session/open ----
    def _handle_session_open(self, body: dict):
        session_id, sid_err = self._validate_session_id(body)
        if sid_err:
            return self._send_json(400, {"ok": False, "error": sid_err})
        folder = _session_folder(session_id)
        if not folder.exists():
            return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
        try:
            _platform.open_in_os(folder)
        except Exception as e:
            return self._send_json(200, {"ok": False, "error": str(e)})
        log.info("POST /session/open -> %s", folder)
        self._send_json(200, {"ok": True, "folder": str(folder)})

    # ---- /session/list ----
    def _handle_session_list(self):
        sessions = _all_sessions()
        summaries = [{
            "session_id": s["slug"],
            "name": s.get("name"),
            "status": s.get("status"),
            "video_count": len(s.get("videos", [])),
            "created_at": s.get("created_at"),
            "closed_at": s.get("closed_at"),
            "cancelled_at": s.get("cancelled_at"),
            "folder": str(_session_folder(s["slug"])),
        } for s in sessions]
        log.info("GET /session/list -> %d sessions", len(summaries))
        self._send_json(200, {"ok": True, "sessions": summaries})

    # ---- /session/active ----
    def _handle_session_active(self):
        s = _active_session()
        if not s:
            return self._send_json(200, {"ok": True, "session": None})
        recent = list(reversed(s.get("videos", [])))[:3]
        self._send_json(200, {
            "ok": True,
            "session": {
                "session_id": s["slug"],
                "name": s.get("name"),
                "status": s.get("status"),
                "video_count": len(s.get("videos", [])),
                "created_at": s.get("created_at"),
                "folder": str(_session_folder(s["slug"])),
                "recent": [{"title": v.get("title"), "url": v.get("url")} for v in recent],
            },
        })


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def _bundled_icon_path() -> str | None:
    """Path to the bundled uoink.ico if it ships next to server.py (it does
    in the installed product; absent in the dev repo). Used to brand the
    Windows startup / migration toast with the rust U instead of the generic
    blue OS information icon."""
    candidate = HERE / "uoink.ico"
    return str(candidate) if candidate.is_file() else None


def maybe_toast(title: str, body: str, icon_path: str | None = None):
    """Best-effort transient notification when the helper finishes booting.

    Sprint 19.5 Stage 1: now delegated to _platform.show_toast. Windows
    uses System.Windows.Forms.NotifyIcon via PowerShell, macOS uses
    osascript ``display notification``, Linux uses notify-send. All
    fire-and-forget; failures are debug-logged and swallowed so a
    missing tray icon never blocks startup.

    v2.1: ``icon_path`` (Windows only) points the balloon at the bundled
    uoink.ico so the notification carries the brand mark; defaults to the
    bundled icon when one is present."""
    if icon_path is None:
        icon_path = _bundled_icon_path()
    _platform.show_toast(title, body, icon_path=icon_path)


def _maybe_post_migration_toast() -> bool:
    """Fire the one-time post-migration toast if a legacy install
    migration just ran and the toast hasn't been shown yet. Returns True if
    it fired (so the caller skips the regular ready toast this boot).

    Gated on the ``post_migration_toast_shown`` settings flag AND the
    migrate_install ``.migrated-from-yoink`` marker, so a fresh install (no
    migration) never sees it and an upgraded install sees it exactly once."""
    try:
        settings = _read_settings()
    except Exception:
        return False
    if settings.get("post_migration_toast_shown"):
        return False
    try:
        import migrate_install
        if not migrate_install.migration_marker_present(DATA_ROOT):
            return False
    except Exception:
        return False
    maybe_toast(
        "Uoink upgrade complete",
        "Your videos, settings, and API key moved to the new Uoink folder. "
        "Nothing lost -- the magnet was always a U. uoink.app",
        icon_path=_bundled_icon_path(),
    )
    try:
        settings["post_migration_toast_shown"] = True
        settings["updated_at"] = _now_iso()
        _write_settings(settings)
    except Exception as e:
        log.warning("could not persist post_migration_toast_shown flag: %s", e)
    return True


def _existing_server_responds() -> bool:
    """Probe /health on the loopback port. True if another Yoink is already
    running here -- used to short-circuit a duplicate launch from the
    Start Menu / autostart key without writing a stale PID file."""
    try:
        with urllib.request.urlopen(
            f"http://{HOST}:{PORT}/health", timeout=0.5
        ) as r:
            return r.status == 200
    except Exception:
        return False


def _spawn_dashboard_window(*, reason: str) -> bool:
    """Open the local dashboard window without making the helper re-bind."""
    try:
        script = HERE / "uoink_dashboard.py"
        if script.exists():
            bundled = HERE / "python" / "pythonw.exe"
            exe = bundled if bundled.exists() else Path(sys.executable)
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            subprocess.Popen(
                [str(exe), str(script)],
                cwd=str(HERE),
                creationflags=creationflags,
            )
            log.info("dashboard: spawned (%s)", reason)
            return True
    except Exception as e:
        log.warning("dashboard: window spawn failed (%s): %s", reason, e)

    try:
        webbrowser.open(f"http://{HOST}:{PORT}/dashboard")
        log.info("dashboard: opened browser fallback (%s)", reason)
        return True
    except Exception as e:
        log.warning("dashboard: browser fallback failed (%s): %s", reason, e)
        return False


class _YoinkHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a bounded listen() backlog so a burst of
    connections is refused at the OS layer instead of piling up unbounded
    accept()s. Worker threads stay daemonic (inherited from ThreadingHTTPServer)
    so Ctrl+C still exits promptly."""
    request_queue_size = 16


def main(*, show_dashboard: bool = False):
    # Output directories are created lazily by the write paths themselves
    # (_run_extraction, _atomic_write_text, and the jobs/taxonomy/settings
    # writers all mkdir(parents=True, exist_ok=True) their own parents).
    # Creating them here would touch a possibly-locked OneDrive Desktop
    # before the server can even bind and answer /health.

    # Single-instance guard. The Start Menu shortcut + the HKCU\Run autostart
    # entry can both fire on a fresh login, and a user clicking the shortcut
    # twice would otherwise spawn parallel pythonw.exe processes that all
    # try to bind 5179. Probe the canonical /health endpoint first.
    if _existing_server_responds():
        if show_dashboard:
            _spawn_dashboard_window(reason="existing-server")
        log.info("Uoink server already running on http://%s:%d -- exiting", HOST, PORT)
        sys.exit(0)

    # v2.1: one-time Yoink->Uoink install migration. Copy-not-move and fully
    # idempotent, so this is a near-no-op on every boot after the first. Runs
    # before _get_index() so the copied index.db / settings are in place under
    # the new \Uoink\ DATA_ROOT before anything reads them. Never fatal.
    try:
        _mig = migrate_install.run_migration(app_dir=HERE)
        log.info("install migration: %s", _mig.get("outcome"))
    except Exception as e:
        log.warning("install migration raised (non-fatal): %s", e)

    # Sprint 19 / Wave 1 Fix 4: if Desktop\Yoink isn't writable, swap the
    # active output root to %LOCALAPPDATA%\Uoink\output before the first
    # /extract would try to write to it.
    _apply_output_root_fallback()

    # Bind FIRST. Writing the PID file before the bind would create stale
    # files when another instance still owns the port (and would also have
    # the wrong PID -- ours, not the live one).
    try:
        server = _YoinkHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        # Port held by something we couldn't probe via /health (different
        # app, half-open socket, etc). Exit 0 so the Windows autostart
        # mechanism doesn't surface an error dialog to the user.
        log.error("Failed to bind %s:%d -- %s", HOST, PORT, e)
        sys.exit(0)

    _migrate_plaintext_anthropic_key()
    # Sprint 15: open the library index (quarantining + rebuilding a corrupt
    # index.db if needed) before anything reads from or migrates into it.
    _get_index()
    # One-time: fold any pre-index jobs.json / taxonomy.json into index.db.
    _migrate_jobs_json_to_index()
    _migrate_taxonomy_json_to_index()
    # v3.2.3: seed curated default style anchors on first run (no-op once the
    # user has any anchor). Runs after the index is open (migration 0016 added
    # the is_default column).
    _seed_default_style_anchors()
    # Hydrate the in-memory job dict from the index.
    _restore_jobs_from_disk()
    # Backfill the index from disk in the background so a missing index
    # never delays the bind or /health.
    _start_backfill_thread()
    # Sprint 18: hard-delete _yoink-trash/ entries past the 30-day window,
    # once at startup and every 24h after.
    _start_trash_purge_thread()
    # Sprint 19 (C4): rate-limit retry queue. Reset any rows stuck 'running'
    # from a previous crash before starting the worker, so a mid-retry
    # crash doesn't strand them.
    try:
        reset = _get_index().reset_running_pending()
        if reset:
            log.info("retry worker: reset %d stale 'running' row(s) at boot",
                     reset)
    except Exception as e:
        log.warning("retry worker: reset_running_pending failed: %s", e)
    _start_retry_pending_thread()

    # Bind succeeded -- now safe to claim the PID file.
    pid_file = HERE / "server.pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    import atexit
    atexit.register(lambda: pid_file.unlink(missing_ok=True))

    # Tier 1 (v2.1.1): ambient system-tray presence on installed Windows
    # builds. Guarded by the installed-layout check (bundled pythonw next to
    # server.py, same guard migrate uses) so a dev run from the repo never
    # spawns a tray. Runs in a daemon thread; any failure (no pystray, no
    # system tray) degrades to "no tray, server still runs" -- the boot balloon
    # below is the fallback "it's running" affordance.
    if (HERE / "python" / "pythonw.exe").exists():
        try:
            import uoink_tray

            def _tray_stop():
                # Called from the tray's daemon thread; shut the server down on
                # a separate thread so serve_forever() unblocks and main()
                # returns (atexit then clears the PID file).
                threading.Thread(target=server.shutdown, daemon=True).start()

            uoink_tray.start(
                host=HOST, port=PORT, version=VERSION,
                token_path=TOKEN_PATH, output_dir=DESKTOP_ROOT,
                dashboard_url=f"http://{HOST}:{PORT}/dashboard",
                stop_callback=_tray_stop,
            )
        except Exception as e:
            log.warning("tray: failed to start (non-fatal): %s", e)

        # Tier 2 GUI: spawn the pywebview splash window once per installed
        # version. %LOCALAPPDATA%\Uoink\.first-run-done stores the last version
        # shown (uoink_splash.py writes it on dismiss / after its 8 s linger).
        # Subprocess so pywebview's GUI loop doesn't fight serve_forever() for
        # the main thread; pythonw.exe so the launch doesn't flash a console.
        # Non-fatal -- if pywebview / WebView2 isn't available the boot toast is
        # the fallback.
        try:
            _splash_sentinel = DATA_ROOT / ".first-run-done"
            if _splash_should_spawn(_splash_sentinel):
                _splash_script = str(HERE / "uoink_splash.py")
                _splash_pyw = str(HERE / "python" / "pythonw.exe")
                subprocess.Popen([_splash_pyw, _splash_script],
                                 creationflags=0x08000000)  # CREATE_NO_WINDOW
                log.info("splash: spawned (version %s)", VERSION)
        except Exception as e:
            log.warning("splash: failed to spawn (non-fatal): %s", e)

    if show_dashboard:
        _spawn_dashboard_window(reason="launch-flag")

    log.info("Uoink server v%s running on http://%s:%d", VERSION, HOST, PORT)
    log.info("Ready to uoink. Click any YouTube video's Uoink button.")
    log.info("Output: %s", DESKTOP_ROOT)
    log.info("Log file: %s", LOG_PATH)
    # Only fires here -- the single-instance / bind-failure paths above
    # exit() before reaching this line, so a duplicate launch doesn't
    # double-notify. If the install migration just ran, fire the one-time
    # post-migration toast instead of the regular ready toast, gated on
    # a settings flag so it never repeats.
    if not _maybe_post_migration_toast():
        maybe_toast(
            "Uoink is Active & Ready ✓",
            "Click the rust U under any YouTube video to pull context. "
            "Open the dashboard anytime from the magnet-U in your system tray.",
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


def doctor_payload() -> dict:
    """`uoink doctor`: the /diagnose self-check plus the install-migration
    status, for support triage from the console without the popup."""
    return {
        "diagnose": _diagnose_payload(),
        "migration": migrate_install.migration_status(),
    }


def run_cli(argv: list[str]) -> int:
    """Tiny CLI dispatcher for the helper. Returns a process exit code.

    - --migrate-dry-run : print exactly what the Yoink->Uoink migration would
      copy / move / delete and the keyring entry it'd rewrite, changing
      nothing. De-risks the clean-VM upgrade test.
    - --doctor          : print the /diagnose payload + migration status.
    - --show-dashboard  : run the server, then open the dashboard window.
    (no flag)           : run the server.
    """
    if "--migrate-dry-run" in argv:
        _print_json(migrate_install.run_migration(dry_run=True, app_dir=HERE))
        return 0
    if "--doctor" in argv:
        _print_json(doctor_payload())
        return 0
    main(show_dashboard="--show-dashboard" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
