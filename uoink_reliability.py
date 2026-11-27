"""Local faster-whisper support for Uoink transcripts.

The module owns two bounded jobs: surface low-confidence word spans in a
saved transcript, and produce a local transcript when a captured video has
no platform captions. Diarization and cloud transcription remain out of
scope.

C-02 (CRIT-2, license compliance): the confidence source is now
faster-whisper's per-word ``probability`` (faster-whisper is MIT, and
already in the bundle as a whisperx dependency). This replaces the prior
AGPL word-confidence library (which pulled openai-whisper + dtw-python and
made the shipped product's "MIT" claim false). The public interface
(detect_unreliable_spans / ensure_model / Span) is unchanged, so nothing
downstream moves.

3.12: every installer ships one model (see ``bundled_model_dir``), so a
fresh install transcribes without a download step. A model the user
downloaded still wins over the bundled copy.
"""

from __future__ import annotations

import asr_worker
import asr_models
import transcript_review
import math
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# The settings default (server._normalize_settings) and the bundled model.
DEFAULT_MODEL = "base"
DEFAULT_THRESHOLD = 0.5


class ReliabilityUnavailableError(RuntimeError):
    """Raised when the optional local Whisper stack is unavailable."""


@dataclass
class Span:
    start_word_idx: int
    end_word_idx: int
    confidence: float
    reason: str
    text: str
    start: float | None = None
    end: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_HOMOPHONE_HINTS = {
    "accept", "except", "affect", "effect", "bare", "bear", "break",
    "brake", "buy", "by", "bye", "capital", "capitol", "cite", "sight",
    "site", "for", "four", "fore", "hear", "here", "its", "it's",
    "knew", "new", "know", "no", "one", "won", "right", "write",
    "their", "there", "they're", "to", "too", "two", "weather",
    "whether", "your", "you're",
}


# Repository identities from the pinned faster-whisper 1.2.1 mapping.
# Do not change production provider/repository mapping here.
_MODEL_REPOSITORIES = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
    # 3.18: distilled English models, the same names faster-whisper 1.2.1
    # maps (utils._MODELS). English only: see ENGLISH_ONLY_MODELS.
    "distil-small.en": "Systran/faster-distil-whisper-small.en",
    "distil-large-v3.5": "distil-whisper/distil-large-v3.5-ct2",
}
_RELIABILITY_CACHE_FILES = ("model.bin", "config.json", "tokenizer.json")
# Models trained on English only. They never run on other languages: the
# multilingual model detects the language first and takes over if needed.
ENGLISH_ONLY_MODELS = frozenset({"distil-small.en", "distil-large-v3.5"})
LANGUAGE_CHECK_MODEL = "base"   # bundled, multilingual, works offline
ENGLISH_MIN_PROBABILITY = 0.8

# Conservative rounded decimal MB estimates of advertised Hub file totals
# captured 2026-09-13. These are advertised logical bytes of the current
# helper's model/config/tokenizer/vocabulary/preprocessor files, not
# observed network transfers or an approved model manifest.
_ESTIMATED_DOWNLOAD_MB = {
    "tiny": 80,
    "base": 150,
    "small": 490,
    "medium": 1540,
    "large": 3100,
    "large-v3-turbo": 1630,
    "distil-small.en": 340,      # 335,542,354 bytes at the pinned revision
    "distil-large-v3.5": 1520,   # 1,516,479,656 bytes at the pinned revision
}

# Decode settings for every local transcription (3.18). Whisper can loop on
# silence or music, repeating one phrase. Not feeding the previous text back
# breaks the loop; the thresholds are Whisper's own retry/skip limits made
# explicit; voice detection stays on. Word timings are kept, and they let
# faster-whisper skip hallucinated stretches inside long silences.
DECODE_OPTIONS = {
    "condition_on_previous_text": False,
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "word_timestamps": True,
    "hallucination_silence_threshold": 2.0,
}


def is_english_only(model_name: object) -> bool:
    return str(model_name or "").strip().lower() in ENGLISH_ONLY_MODELS


def _offload_active() -> bool:
    """True in long-lived processes that send model work to a child process
    (asr_worker.enable_offload). Never true inside that child or in tests."""
    try:
        import asr_worker
    except ImportError:  # pragma: no cover - the module always ships
        return False
    return asr_worker.offload_active()


def _cancelled_error():
    import asr_worker
    return asr_worker.TranscriptionCancelled("transcription cancelled")


class TranscriptEntry(tuple):
    """One transcript row, ``(start, end, text)``, that may also carry the
    model's word timings in ``words``. It unpacks as three values and equals
    the plain tuple, so every caller that reads rows is unchanged."""

    def __new__(cls, start: float, end: float, text: str, words: list | None = None,
                scores=None, held_reason=None):
        entry = super().__new__(cls, (start, end, text))
        entry.words = words or None
        entry.scores = scores or {}
        entry.held_reason = held_reason
        return entry


def entry_to_json(entry) -> list:
    row = [entry[0], entry[1], entry[2]]
    words = getattr(entry, "words", None)
    metadata = dict(getattr(entry, "scores", {}))
    if getattr(entry, "held_reason", None):
        metadata["held_reason"] = entry.held_reason
    if metadata:
        row.extend((words, metadata))
    elif words:
        row.append(words)
    return row


def entry_from_json(row) -> TranscriptEntry:
    words = row[3] if len(row) > 3 and isinstance(row[3], list) else None
    metadata = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
    return TranscriptEntry(float(row[0]), float(row[1]), str(row[2]), words,
                           transcript_review.scores(metadata), metadata.get("held_reason"))


def segment_dict(entry):
    return {"start": entry[0], "end": entry[1], "text": entry[2],
            **getattr(entry, "scores", {}),
            **({"held_reason": entry.held_reason} if getattr(entry, "held_reason", None) else {}),
            **({"words": entry.words} if getattr(entry, "words", None) else {})}


def _import_faster_whisper():
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ReliabilityUnavailableError(
            "faster-whisper is not installed; install requirements and "
            "download the local Whisper model before computing reliability"
        ) from e
    return WhisperModel


# faster-whisper's compute_type: int8 keeps the model small on CPU and needs
# no CUDA.
_COMPUTE_TYPE = "int8"


def _load_model(model_name: str, model_root: str | Path | None, *,
                local_files_only: bool = True):
    """Construct WhisperModel. Ordinary callers stay local-only.

    A local load uses the user's downloaded
    cache when it is ready, else the bundled copy of the same size.
    """
    WhisperModel = _import_faster_whisper()
    kwargs: dict[str, Any] = {
        "device": "cpu",
        "cpu_threads": asr_models.cpu_threads(),
        "compute_type": _COMPUTE_TYPE,
        "local_files_only": bool(local_files_only),
    }
    if local_files_only:
        source, bundled = resolve_model(model_name, model_root)
        if source == SOURCE_BUNDLED:
            # Read-only app data: load the snapshot directory by path and
            # pass no download_root, so nothing is created or written there.
            return WhisperModel(str(bundled), **kwargs)
    if model_name in ("large-v3-turbo", "distil-large-v3.5"):
        lookup_root = model_root
        if model_name == "large-v3-turbo" and local_files_only and lookup_root is None:
            try:
                from huggingface_hub.constants import HF_HUB_CACHE
                lookup_root = HF_HUB_CACHE
            except ImportError:
                pass
        snapshot = _cached_reliability_snapshot(lookup_root, model_name) if lookup_root and local_files_only else None
        model_name = str(snapshot) if snapshot else _MODEL_REPOSITORIES[model_name]
    if model_root:
        root = Path(model_root)
        if not local_files_only:
            root.mkdir(parents=True, exist_ok=True)
        kwargs["download_root"] = str(root)
    return WhisperModel(model_name, **kwargs)


def ensure_model(model_name: str = DEFAULT_MODEL,
                 model_root: str | Path | None = None, *, cancel_event=None) -> dict[str, Any]:
    """Explicit acquisition uses the chooser's verified downloader and cache layout."""
    if model_root is None:
        from huggingface_hub.constants import HF_HUB_CACHE
        root = Path(HF_HUB_CACHE)
    else:
        root = Path(model_root)
    model = asr_models.get(model_name)["id"]
    asr_models.download(model, root, cancel_event=cancel_event,
                        progress=asr_worker.report_download_bytes)
    return {"ok": True, "model": model, "model_root": str(model_root) if model_root else None,
            "ready_marker": str(root / (model + ".pt")) if model_root else None}


def _supported_model_name(model_name: object) -> str | None:
    name = str(model_name or "").strip().lower()
    # Return our own key, not the caller's string: model folders are built
    # from this name, so only the fixed repository names can reach a path.
    for known in _MODEL_REPOSITORIES:
        if known == name:
            return known
    return None


def estimated_download_mb(model_name: object) -> int | None:
    """Return the per-choice rounded advertised size, or None if unknown."""
    name = _supported_model_name(model_name)
    if name is None:
        return None
    return _ESTIMATED_DOWNLOAD_MB.get(name)


def _reliability_cache_root(model_root: str | Path) -> Path:
    """Return the reliability download root without creating it."""
    root = Path(model_root).absolute()
    if root.resolve() != root:
        raise RuntimeError("Reliability cache directories must not be redirected")
    return root


def _reliability_repo_root(model_root: str | Path, model_name: str, *, legacy=False) -> Path:
    name = _supported_model_name(model_name)
    if name is None:
        raise ValueError(f"unsupported reliability model: {model_name!r}")
    repo_id = asr_models.LEGACY_TURBO_REPO if legacy else _MODEL_REPOSITORIES[name]
    repo = _reliability_cache_root(model_root) / (
        "models--" + repo_id.replace("/", "--")
    )
    for directory in (repo, repo / "refs", repo / "snapshots", repo / "blobs"):
        if directory.resolve() != directory:
            raise RuntimeError("Reliability repository cache must not be redirected")
    return repo


def _checked_reliability_snapshot(
        model_root: str | Path, model_name: str, snapshot: Path, *, legacy=False) -> Path | None:
    """Check minimum ASR cache structure, not model integrity or safety."""
    try:
        repo = _reliability_repo_root(model_root, model_name, legacy=legacy)
        snapshot = Path(snapshot).absolute()
        if (snapshot.parent != repo / "snapshots"
                or re.fullmatch(r"[0-9a-f]{40}", snapshot.name) is None
                or snapshot.resolve(strict=True) != snapshot
                or not snapshot.is_dir()):
            return None
        for name in _RELIABILITY_CACHE_FILES:
            asset = (snapshot / name).resolve(strict=True)
            # Hub may link snapshot files to this repository's blob store.
            if (not asset.is_relative_to(repo) or not asset.is_file()
                    or asset.stat().st_size == 0):
                return None
        return snapshot
    except (OSError, RuntimeError, ValueError):
        return None


def _cached_reliability_snapshot(
        model_root: str | Path, model_name: str) -> Path | None:
    snapshot = _read_reliability_snapshot(model_root, model_name)
    if snapshot is None and model_name == "large-v3-turbo":
        snapshot = _read_reliability_snapshot(model_root, model_name, legacy=True)
    return snapshot


def _read_reliability_snapshot(
        model_root: str | Path, model_name: str, *, legacy=False) -> Path | None:
    """Read the Hub cache layout under the reliability root; never fetch or write."""
    try:
        repo = _reliability_repo_root(model_root, model_name, legacy=legacy)
        reference = repo / "refs" / "main"
        if reference.resolve(strict=True) != reference or not reference.is_file():
            return None
        with reference.open("rb") as stream:
            raw_revision = stream.read(65)
        if len(raw_revision) > 64:
            return None
        revision = raw_revision.decode("ascii").strip()
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            return None
        return _checked_reliability_snapshot(
            model_root, model_name, repo / "snapshots" / revision, legacy=legacy)
    except (OSError, RuntimeError, ValueError):
        return None


def is_model_ready(model_name: object,
                   model_root: str | Path | None) -> bool:
    """Consent marker plus minimum Hub snapshot files.

    Structural readiness for settings/preflight: no runtime import, no
    constructor, no writes, and no authenticity claim.
    """
    if model_root is None:
        return False
    name = _supported_model_name(model_name)
    if name is None:
        return False
    try:
        root = _reliability_cache_root(model_root)
        marker = root / f"{name}.pt"
        if not marker.is_file():
            return False
        resolved_marker = marker.resolve(strict=True)
        if (not resolved_marker.is_relative_to(root.resolve())
                or not resolved_marker.is_file()):
            return False
        return _cached_reliability_snapshot(root, name) is not None
    except (OSError, RuntimeError, ValueError):
        return False


# ---- Bundled model (3.12) ---------------------------------------------------
# Installers stage one pinned faster-whisper snapshot
# (scripts/whisper_model_pin.json, scripts/stage_whisper_model.py) at
# <app>/models/whisper-bundled/<size>/: {app} on Windows and
# Contents/Resources in the macOS bundle, the folder this module ships in.
# It is read-only app data. Lookup for the selected size:
#   1. the user's downloaded cache (ensure_model + ready marker) wins;
#   2. otherwise the bundled copy, when the selected size is the bundled one;
#   3. otherwise unavailable, as before (capture records model_not_downloaded).
BUNDLED_MODEL_DIRNAME = "whisper-bundled"
BUNDLED_MANIFEST = "uoink-model.json"
SOURCE_DOWNLOADED = "downloaded"
SOURCE_BUNDLED = "bundled"


def bundled_model_root() -> Path:
    """This install's bundled-model folder. It may not exist (source checkout).

    An isolated install names its app folder (UOINK_ISOLATED_APP_DIR, through
    uoink_install_isolation); otherwise the app folder is this module's own.
    """
    app_dir: Path | None = None
    try:
        import uoink_install_isolation
        binding = uoink_install_isolation.current_binding()
        if binding is not None and binding.app_dir is not None:
            app_dir = Path(binding.app_dir)
    except Exception:  # pragma: no cover - the isolation module always ships
        app_dir = None
    if app_dir is None:
        app_dir = Path(__file__).resolve().parent
    elif app_dir.suffix == ".app":
        # A macOS bundle path: its app files live in Contents/Resources.
        app_dir = app_dir / "Contents" / "Resources"
    return app_dir / "models" / BUNDLED_MODEL_DIRNAME


def _bundled_manifest(directory: Path) -> dict | None:
    try:
        with (directory / BUNDLED_MANIFEST).open("rb") as stream:
            raw = stream.read(65536)
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def bundled_model_dir(model_name: object,
                      bundled_root: str | Path | None = None) -> Path | None:
    """The bundled snapshot directory for this size, or None.

    A structural check, cheap enough for every status call: the manifest
    names this size, its repository and a full revision; each listed file is
    a regular file of the pinned size; the files faster-whisper needs are
    there. The build verified every SHA-256 before packaging. Never writes.
    """
    name = _supported_model_name(model_name)
    if name is None:
        return None
    root = Path(bundled_root) if bundled_root is not None else bundled_model_root()
    directory = root.absolute() / name
    try:
        if directory.is_symlink() or not directory.is_dir():
            return None
        manifest = _bundled_manifest(directory)
        if (manifest is None or manifest.get("model") != name
                or manifest.get("repo") != _MODEL_REPOSITORIES[name]
                or re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("revision") or "")) is None):
            return None
        files = manifest.get("files")
        if not isinstance(files, dict) or not set(_RELIABILITY_CACHE_FILES) <= set(files):
            return None
        for file_name, meta in files.items():
            if (not isinstance(file_name, str) or file_name in {".", ".."}
                    or re.fullmatch(r"[\w.-]+", file_name) is None
                    or not isinstance(meta, dict)):
                return None
            path = directory / file_name
            if path.is_symlink() or not path.is_file():
                return None
            size = path.stat().st_size
            if size == 0 or size != meta.get("size"):
                return None
        return directory
    except (OSError, ValueError, TypeError):
        return None


def bundled_model_info(bundled_root: str | Path | None = None) -> dict[str, Any] | None:
    """{model, revision, path} for the size this install ships, or None."""
    root = Path(bundled_root) if bundled_root is not None else bundled_model_root()
    for name in _MODEL_REPOSITORIES:
        directory = bundled_model_dir(name, root)
        if directory is not None:
            manifest = _bundled_manifest(directory) or {}
            return {"model": name, "revision": manifest.get("revision"),
                    "path": str(directory)}
    return None


def resolve_model(model_name: object, model_root: str | Path | None, *,
                  bundled_root: str | Path | None = None) -> tuple[str | None, Path | None]:
    """Choose the local copy of a selected size: (source, bundled_dir).

    ("downloaded", None) when the user's ready cache exists, which wins;
    ("bundled", <dir>) when this install ships that size; else (None, None).
    """
    if is_model_ready(model_name, model_root):
        return SOURCE_DOWNLOADED, None
    directory = bundled_model_dir(model_name, bundled_root)
    if directory is not None:
        return SOURCE_BUNDLED, directory
    return None, None


def reliability_model_status(model_name: object,
                             model_root: str | Path, *,
                             bundled_root: str | Path | None = None) -> dict[str, Any]:
    """Selected-model status used by the helper settings payload.

    ``cached`` means the selected size can run now; ``source`` says which
    copy ("downloaded" or "bundled"). ``bundled_model`` names the size this
    install ships whatever is selected, so the dashboard can say an unsaved
    choice is already on the device. ``estimated_download_mb`` is None for
    the bundled copy, which is never downloaded.
    """
    selected = str(model_name or "").strip().lower()
    root = Path(model_root)
    source, _bundled = resolve_model(selected, root, bundled_root=bundled_root)
    shipped = bundled_model_info(bundled_root)
    return {
        "model": selected,
        "model_root": str(root),
        "cached": source is not None,
        "source": source,
        "downloaded": source == SOURCE_DOWNLOADED,
        "bundled_model": shipped["model"] if shipped else None,
        "bundled_revision": shipped["revision"] if shipped else None,
        "bundled_path": shipped["path"] if shipped else None,
        "estimated_download_mb": (None if source == SOURCE_BUNDLED
                                  else estimated_download_mb(selected)),
    }


def _transcript_entries_from_segments(
        segments, scores: list | None = None) -> list[tuple[float, float, str]]:
    """Normalize faster-whisper segments into Uoink transcript entries.

    Pass a list as ``scores`` to collect (compression_ratio, no_speech_prob)
    for each kept entry, for ``drop_repetition_loops``.
    """
    entries: list[tuple[float, float, str]] = []
    for segment in segments:
        get = segment.get if isinstance(segment, dict) else (
            lambda key, s=segment: getattr(s, key, None))
        clean_text = str(get("text") or "").strip()
        if not clean_text:
            continue
        if isinstance(get("start"), bool) or isinstance(get("end"), bool):
            continue
        try:
            start_value = float(get("start") or 0.0)
            end_value = float(get("end") or start_value)
            if not math.isfinite(start_value) or not math.isfinite(end_value):
                continue
            start_value = max(0.0, start_value)
            end_value = max(start_value, end_value)
        except (TypeError, ValueError):
            continue
        words = _segment_words(segment)
        metrics = transcript_review.scores({key: get(key) for key in transcript_review.SCORES})
        entries.append(TranscriptEntry(start_value, end_value, clean_text, words, metrics))
        if scores is not None:
            scores.append((get("compression_ratio"), get("no_speech_prob")))
    return entries


def _segment_words(segment) -> list[dict] | None:
    """Word timings from one segment, when the model gave them."""
    raw = segment.get("words") if isinstance(segment, dict) else getattr(segment, "words", None)
    if not raw:
        return None
    words = []
    for word in raw:
        get = word.get if isinstance(word, dict) else (lambda key, w=word: getattr(w, key, None))
        text = str(get("word") or "").strip()
        if isinstance(get("start"), bool) or isinstance(get("end"), bool):
            continue
        try:
            start, end = float(get("start")), float(get("end"))
        except (TypeError, ValueError):
            continue
        if text and math.isfinite(start) and math.isfinite(end) and min(start, end) >= 0:
            end = max(start, end)
            # Stored as is in the sidecar: centisecond times, no scores,
            # about 40 bytes a word (roughly 0.4 MB per hour of speech).
            words.append({"word": text, "start": round(start, 2), "end": round(end, 2)})
    return words or None


def drop_repetition_loops(entries: list, scores: list | None = None) -> list:
    """Keep ordinary repeats. Over likely silence, keep at most two consecutive
    identical segments. Collapse four or more cycles of a short phrase covering
    nearly the entire segment to one copy, or drop it for excessive compression.
    Numeric counts and short emphatic speech are preserved regardless of timing.
    """
    kept = []
    previous, run = None, 0
    counting = set("zero one two three four five six seven eight nine ten".split())
    for i, entry in enumerate(entries):
        ratio, silence = scores[i] if scores and i < len(scores) else (None, None)
        tokens = re.findall(r"\w+", entry[2].casefold())
        suspect = isinstance(silence, (float, int)) and silence > DECODE_OPTIONS["no_speech_threshold"]
        if (not suspect or not tokens or all(t.isdecimal() or t in counting for t in tokens)
                or (len(tokens) > 1 and len(set(tokens)) == 1)):
            previous, run = None, 0
            kept.append(entry)
            continue
        run = run + 1 if previous == tokens else 1
        previous = tokens
        if run > 2:
            continue
        phrase = transcript_review.repeated_phrase(tokens)
        if phrase:
            if isinstance(ratio, (int, float)) and ratio > DECODE_OPTIONS["compression_ratio_threshold"]:
                continue
            start, width = phrase
            words = list(re.finditer(r"\w+[^\w\s]*", entry[2]))
            text = entry[2][words[start].start():words[start + width - 1].end()]
            entry = (entry[0], entry[1], text)
        kept.append(entry)
    return kept


INITIAL_PROMPT_MAX_CHARS = 200


def build_initial_prompt(*titles) -> str | None:
    """A short vocabulary hint for Whisper from titles only (feed, episode,
    channel, video). Plain text, de-duplicated, capped at a word boundary."""
    seen, parts = set(), []
    for title in titles:
        text = " ".join(str(title or "").split())
        text = "".join(ch for ch in text if ch.isprintable()).strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            parts.append(text.rstrip(".!?"))
    prompt = ". ".join(parts)
    if len(prompt) > INITIAL_PROMPT_MAX_CHARS:
        prompt = prompt[:INITIAL_PROMPT_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return prompt or None


def _watched_segments(segments, cancel_event=None, progress=None, total=None):
    """Yield segments; stop between them on cancel and report how far along."""
    if progress is not None and total:
        asr_worker.report_phase("decode", duration_seconds=total)
        progress(0, total)
    for segment in segments:
        if cancel_event is not None and cancel_event.is_set():
            raise _cancelled_error()
        yield segment
        if progress is not None:
            end = segment.get("end") if isinstance(segment, dict) else getattr(segment, "end", None)
            try:
                progress(end, total)
            except Exception:  # noqa: BLE001 - a progress display never fails a job
                pass


def transcribe_media(media_path: str | Path, *,
                     model_name: str = DEFAULT_MODEL,
                     model_root: str | Path | None = None,
                     _transcribe=None,
                     info: dict | None = None,
                     language: str | None = None,
                     initial_prompt: str | None = None,
                     cancel_event=None,
                     progress=None,
                     checkpoint=None, duration_seconds=None) -> list[tuple[float, float, str]]:
    """Transcribe local media with a local faster-whisper model.

    Whisper detects the spoken language. Pass ``info`` (a dict) to receive it
    as ``language`` and ``language_probability``; the return value is the
    same either way.

    Used for caption-less video and lean Linux podcast transcription.
    The model is the user's downloaded copy or the bundled one
    (``resolve_model``). ``local_files_only=True`` is intentional: capture
    must not become an implicit model download. ``ensure_model`` remains the
    explicit user-triggered download path.

    ``initial_prompt`` is a short plain-text vocabulary hint (titles) that
    steers Whisper toward niche spellings; it is never written to the output.

    In the helper (``asr_worker.enable_offload``) the work runs in the
    transcription child process; the return value and errors are the same.
    ``cancel_event`` stops the job (``asr_worker.TranscriptionCancelled``);
    ``progress(done_seconds, total_seconds)`` reports how far along it is.

    ``checkpoint(segment)`` runs after each decoded segment, before the next
    one is decoded. Backfill raises here to pause an item and release its engine.
    """
    media = Path(media_path)
    if not media.is_file():
        raise FileNotFoundError(f"media file not found: {media}")

    if _transcribe is None and _offload_active():
        result = asr_worker.call("transcribe_media", {
            "media_path": str(media), "model_name": str(model_name),
            "model_root": str(model_root) if model_root is not None else None,
            "language": language, "initial_prompt": initial_prompt, "duration_seconds": duration_seconds,
        }, cancel_event=cancel_event, progress=progress, checkpoint=checkpoint,
            background=checkpoint is not None)
        if info is not None:
            info.update(result.get("info") or {})
        return [entry_from_json(row) for row in result.get("entries") or []]

    if _transcribe is not None:
        segments = _transcribe(str(media))
    else:
        run_model, language, fallback = _english_guard(media, model_name, model_root, language,
                                                       cancel_event=cancel_event)
        asr_worker.report_phase("model load")
        model = _load_model(
            run_model,
            model_root,
            local_files_only=True,
        )
        asr_worker.report_phase("decode")
        segments, detected = model.transcribe(
            str(media),
            beam_size=1,
            best_of=1,
            vad_filter=True,
            **DECODE_OPTIONS,
            **({"language": language} if language is not None else {}),
            **({"initial_prompt": initial_prompt} if initial_prompt else {}),
        )
        if info is not None:
            info["language"] = getattr(detected, "language", None)
            info["language_probability"] = getattr(
                detected, "language_probability", None)
            if fallback:
                info["model"] = run_model
                info["english_fallback"] = fallback
        duration_seconds = getattr(detected, "duration", None) or duration_seconds
        segments = _watched_segments(
            segments, cancel_event, progress, getattr(detected, "duration", None))
    if checkpoint is not None:
        segments = _with_checkpoint(segments, checkpoint)
    entries = _transcript_entries_from_segments(segments)
    decisions = transcript_review.reasons([segment_dict(e) for e in entries],
                                          whisper=True, duration=duration_seconds)
    for entry, reason in zip(entries, decisions):
        entry.held_reason = reason
    return entries


def _language_samples(media, cancel_event=None):
    """Decode at most three 20-second mono windows, including the middle and end."""
    import av
    import numpy as np
    rate = 16000
    with av.open(str(media)) as container:
        stream = container.streams.audio[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else (
            float(container.duration) / av.time_base if container.duration else 0)
        last = max(0, duration - 20)
        for offset in sorted({0, last / 2, last}):
            if offset:
                try:
                    container.seek(int(offset / stream.time_base), stream=stream)
                except Exception as exc:
                    # PyAV uses different exception types for unsupported seeks.
                    raise OSError("Cannot seek to a language sample.") from exc
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
            parts, count = [], 0
            for number, frame in enumerate(container.decode(stream)):
                if cancel_event is not None and cancel_event.is_set():
                    raise _cancelled_error()
                if number >= 4096:  # a seek without a usable index landed too far back
                    break
                if frame.time is not None and frame.time < offset - 0.1:
                    continue
                for out in resampler.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1))
                    count += out.samples
                if count >= rate * 20:
                    break
            if parts:
                yield np.concatenate(parts)[:rate * 20]


def _english_guard(media: Path, model_name: str, model_root, language, *, checker_path=None,
                   checker_name=LANGUAGE_CHECK_MODEL, cancel_event=None):
    """Never run an English-only model on other languages.

    Returns (model to run, language to pass, fallback note or None). The
    bundled multilingual model detects the language first: transcribe()
    detects before it decodes anything, and its segments are never read.
    Anything but confident English runs on that multilingual model instead.
    """
    if not is_english_only(model_name):
        return model_name, language, None
    if language is not None and str(language).lower().split("-", 1)[0] == "en":
        return model_name, "en", None
    asr_worker.report_phase("language check")
    check_model = checker_name
    if not checker_path and model_root and not any(resolve_model(check_model, model_root)):
        check_model = next((name for name in _MODEL_REPOSITORIES if not is_english_only(name)
                            and is_model_ready(name, model_root)), LANGUAGE_CHECK_MODEL)
    probability = None
    if language is not None:
        detected = str(language).lower().split("-", 1)[0]
    else:
        try:
            checker = _load_model(str(checker_path) if checker_path else check_model,
                                  None if checker_path else model_root, local_files_only=True)
        except (RuntimeError, ValueError, OSError) as exc:
            raise ReliabilityUnavailableError("A local multilingual model is needed to check the language.") from exc
        seen = []
        try:
            for sample in _language_samples(media, cancel_event):
                if cancel_event is not None and cancel_event.is_set():
                    raise _cancelled_error()
                try:
                    _, found = checker.transcribe(sample, beam_size=1, best_of=1, vad_filter=True)
                except (IndexError, ValueError):
                    continue  # some runtimes cannot identify an empty VAD result
                voiced = getattr(found, "duration_after_vad", 20)
                tag = str(found.language or "").lower().split("-", 1)[0]
                confidence = float(found.language_probability or 0)
                if voiced < .25 or (voiced < 2 and confidence < ENGLISH_MIN_PROBABILITY):
                    continue  # a weak guess over a brief sound is not evidence of another language
                seen.append((tag, confidence if math.isfinite(confidence) else 0))
        except (OSError, IndexError, TypeError, ValueError, EOFError):
            seen.clear()  # no reliable probe for this stream
        if seen and all(tag == "en" and p >= ENGLISH_MIN_PROBABILITY for tag, p in seen):
            return model_name, "en", None
        detected, probability = min(seen, key=lambda pair: pair[1]) if seen else ("", 0)
        if len({tag for tag, _ in seen}) > 1:
            detected, probability = "mixed", 0
    sure = probability is None or (isinstance(probability, (int, float))
                                   and probability >= ENGLISH_MIN_PROBABILITY)
    return check_model, (detected if sure and detected else None), {
        "requested_model": str(model_name), "used_model": check_model,
        "detected_language": detected or None,
        "language_probability": (round(float(probability), 3)
                                 if isinstance(probability, (int, float)) else None),
    }


def _with_checkpoint(segments, checkpoint):
    # faster-whisper decodes lazily, so blocking here holds the next segment.
    for segment in segments:
        checkpoint(segment)
        yield segment


def _with_checkpoint(segments, checkpoint):
    # faster-whisper decodes lazily, so blocking here holds the next segment.
    for segment in segments:
        checkpoint(segment)
        yield segment


def _words_from_segments(segments) -> list[dict[str, Any]]:
    """Flatten faster-whisper segments into the internal word-row shape
    ({confidence, text, start, end}). faster-whisper yields Word objects
    with .word/.start/.end/.probability when word_timestamps=True; we also
    accept plain dicts so a test can inject fixtures without the library."""
    rows: list[dict[str, Any]] = []
    for segment in segments:
        words = (segment.get("words") if isinstance(segment, dict)
                 else getattr(segment, "words", None)) or []
        for word in words:
            if isinstance(word, dict):
                text = word.get("word") or word.get("text") or ""
                prob = word.get("probability")
                start = word.get("start")
                end = word.get("end")
            else:
                text = getattr(word, "word", "") or getattr(word, "text", "")
                prob = getattr(word, "probability", None)
                start = getattr(word, "start", None)
                end = getattr(word, "end", None)
            rows.append({
                "text": text,
                "confidence": prob,
                "start": start,
                "end": end,
            })
    return rows


def _clean_word(text: str) -> str:
    return re.sub(r"(^[^\w']+|[^\w']+$)", "", str(text or "")).strip()


def _reason_for(words: list[dict[str, Any]], avg_conf: float,
                threshold: float) -> str:
    text = " ".join(str(w.get("text") or "") for w in words)
    tokens = [_clean_word(t).lower() for t in text.split()]
    if any(t in _HOMOPHONE_HINTS for t in tokens):
        return "homophone_likely"
    if any(_clean_word(t)[:1].isupper() for t in text.split()):
        return "proper_noun_suspect"
    if avg_conf < max(0.05, threshold * 0.55):
        return "accent_garble"
    return "low_confidence"


def _span_from_cluster(cluster: list[tuple[int, dict[str, Any]]],
                       threshold: float) -> Span:
    indices = [i for i, _ in cluster]
    words = [w for _, w in cluster]
    confidences = [
        float(w.get("confidence"))
        for w in words
        if isinstance(w.get("confidence"), (int, float))
    ]
    avg_conf = sum(confidences) / len(confidences) if confidences else threshold
    text = " ".join(
        _clean_word(str(w.get("text") or ""))
        for w in words
    ).strip()
    starts = [float(w.get("start")) for w in words
              if isinstance(w.get("start"), (int, float))]
    ends = [float(w.get("end")) for w in words
            if isinstance(w.get("end"), (int, float))]
    return Span(
        start_word_idx=min(indices),
        end_word_idx=max(indices),
        confidence=round(avg_conf, 4),
        reason=_reason_for(words, avg_conf, threshold),
        text=text,
        start=round(min(starts), 3) if starts else None,
        end=round(max(ends), 3) if ends else None,
    )


def _cluster_low_words(word_rows: list[dict[str, Any]],
                       threshold: float) -> list[Span]:
    low: list[tuple[int, dict[str, Any]]] = []
    for i, word in enumerate(word_rows):
        conf = word.get("confidence")
        if isinstance(conf, (int, float)) and float(conf) < threshold:
            low.append((i, word))
    clusters: list[list[tuple[int, dict[str, Any]]]] = []
    for item in low:
        if not clusters or item[0] > clusters[-1][-1][0] + 1:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    return [_span_from_cluster(cluster, threshold) for cluster in clusters]


def detect_unreliable_spans(transcript_text: str, audio_path: str | Path,
                            threshold: float = DEFAULT_THRESHOLD,
                            *,
                            model_name: str = DEFAULT_MODEL,
                            model_root: str | Path | None = None,
                            _transcribe=None, cancel_event=None, progress=None) -> list[Span]:
    """Return clustered low-confidence word spans for an audio file.

    ``transcript_text`` is accepted for the public interface and future
    alignment work; the confidence source is faster-whisper's per-word
    probability over the ASR stream. Ordinary execution is local-only;
    ``ensure_model`` remains the explicit download path. ``_transcribe`` is
    a test seam: a callable (audio_path) -> iterable of segments, so the
    clustering can be exercised without the model.
    """
    _ = transcript_text  # reserved for future YouTube-vs-ASR alignment
    threshold = max(0.05, min(0.95, float(threshold)))
    audio = Path(audio_path)
    if not audio.is_file():
        raise FileNotFoundError(f"audio file not found: {audio}")

    if _transcribe is None and _offload_active():
        rows = asr_worker.call("detect_unreliable_spans", {
            "transcript_text": transcript_text, "audio_path": str(audio),
            "threshold": threshold, "model_name": str(model_name),
            "model_root": str(model_root) if model_root is not None else None},
            cancel_event=cancel_event, progress=progress)
        return [Span(**row) for row in rows or []]

    if _transcribe is not None:
        segments = _transcribe(str(audio))
    else:
        model_name, language, _ = _english_guard(audio, model_name, model_root,
                                                  None if is_english_only(model_name) else "en",
                                                  cancel_event=cancel_event)
        asr_worker.report_phase("model load")
        model = _load_model(model_name, model_root, local_files_only=True)
        asr_worker.report_phase("decode")
        segments, _info = model.transcribe(
            str(audio), language=language, word_timestamps=True,
            beam_size=1, best_of=1)

        segments = _watched_segments(segments, cancel_event, progress, getattr(_info, "duration", None))
    word_rows = _words_from_segments(segments)
    return _cluster_low_words(word_rows, threshold)
