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
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "tiny"
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
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
_RELIABILITY_CACHE_FILES = ("model.bin", "config.json", "tokenizer.json")

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
}


def _import_faster_whisper():
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ReliabilityUnavailableError(
            "faster-whisper is not installed; install requirements and "
            "download the local Whisper model before computing reliability"
        ) from e
    return WhisperModel


# faster-whisper's compute_type: int8 keeps the tiny model tiny on CPU and
# needs no CUDA. The reliability model is deliberately the smallest one --
# it's a confidence probe, not the primary transcript.
_COMPUTE_TYPE = "int8"


def _load_model(model_name: str, model_root: str | Path | None, *,
                local_files_only: bool = True):
    """Construct WhisperModel. Ordinary callers stay local-only.

    ``ensure_model`` is the only acquisition path and must pass
    ``local_files_only=False``.
    """
    WhisperModel = _import_faster_whisper()
    kwargs: dict[str, Any] = {
        "device": "cpu",
        "compute_type": _COMPUTE_TYPE,
        "local_files_only": bool(local_files_only),
    }
    if model_root:
        root = Path(model_root)
        if not local_files_only:
            root.mkdir(parents=True, exist_ok=True)
        kwargs["download_root"] = str(root)
    return WhisperModel(model_name, **kwargs)


def ensure_model(model_name: str = DEFAULT_MODEL,
                 model_root: str | Path | None = None) -> dict[str, Any]:
    """Load the model once so faster-whisper downloads it if missing."""
    _load_model(model_name, model_root, local_files_only=False)
    ready_marker: Path | None = None
    if model_root:
        # The model itself is a Hugging Face snapshot directory managed by
        # faster-whisper. This tiny sentinel is the explicit-consent signal
        # consumed by readiness checks; it is written only after the
        # user-triggered model load succeeds. A marker without the Hub
        # snapshot files is not a ready cache.
        ready_marker = Path(model_root) / f"{model_name}.pt"
        ready_marker.write_text(
            "Uoink faster-whisper model ready\n",
            encoding="utf-8",
        )
    return {
        "ok": True,
        "model": model_name,
        "model_root": str(model_root) if model_root else None,
        "ready_marker": str(ready_marker) if ready_marker else None,
    }


def _supported_model_name(model_name: object) -> str | None:
    name = str(model_name or "").strip().lower()
    return name if name in _MODEL_REPOSITORIES else None


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


def _reliability_repo_root(model_root: str | Path, model_name: str) -> Path:
    name = _supported_model_name(model_name)
    if name is None:
        raise ValueError(f"unsupported reliability model: {model_name!r}")
    repo_id = _MODEL_REPOSITORIES[name]
    repo = _reliability_cache_root(model_root) / (
        "models--" + repo_id.replace("/", "--")
    )
    for directory in (repo, repo / "refs", repo / "snapshots", repo / "blobs"):
        if directory.resolve() != directory:
            raise RuntimeError("Reliability repository cache must not be redirected")
    return repo


def _checked_reliability_snapshot(
        model_root: str | Path, model_name: str, snapshot: Path) -> Path | None:
    """Check minimum ASR cache structure, not model integrity or safety."""
    try:
        repo = _reliability_repo_root(model_root, model_name)
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
    """Read the Hub cache layout under the reliability root; never fetch or write."""
    try:
        repo = _reliability_repo_root(model_root, model_name)
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
            model_root, model_name, repo / "snapshots" / revision)
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


def reliability_model_status(model_name: object,
                             model_root: str | Path) -> dict[str, Any]:
    """Selected-model status used by the helper settings payload."""
    selected = str(model_name or "").strip().lower()
    root = Path(model_root)
    return {
        "model": selected,
        "model_root": str(root),
        "cached": is_model_ready(selected, root),
        "estimated_download_mb": estimated_download_mb(selected),
    }


def _transcript_entries_from_segments(
        segments) -> list[tuple[float, float, str]]:
    """Normalize faster-whisper segments into Uoink transcript entries."""
    entries: list[tuple[float, float, str]] = []
    for segment in segments:
        if isinstance(segment, dict):
            start = segment.get("start")
            end = segment.get("end")
            text = segment.get("text")
        else:
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            text = getattr(segment, "text", None)
        clean_text = str(text or "").strip()
        if not clean_text:
            continue
        try:
            start_value = max(0.0, float(start or 0.0))
            end_value = max(start_value, float(end or start_value))
        except (TypeError, ValueError):
            continue
        entries.append((start_value, end_value, clean_text))
    return entries


def transcribe_media(media_path: str | Path, *,
                     model_name: str = DEFAULT_MODEL,
                     model_root: str | Path | None = None,
                     _transcribe=None) -> list[tuple[float, float, str]]:
    """Transcribe local media with an already-cached faster-whisper model.

    This path is used only as a fallback when a video source exposes no
    captions. ``local_files_only=True`` is intentional: capture must not
    become an implicit model download. ``ensure_model`` remains the explicit
    user-triggered download path.
    """
    media = Path(media_path)
    if not media.is_file():
        raise FileNotFoundError(f"media file not found: {media}")

    if _transcribe is not None:
        segments = _transcribe(str(media))
    else:
        model = _load_model(
            model_name,
            model_root,
            local_files_only=True,
        )
        segments, _info = model.transcribe(
            str(media),
            beam_size=1,
            best_of=1,
            vad_filter=True,
        )
    return _transcript_entries_from_segments(segments)


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


# Private reviewed-bootstrap dependency, deliberately absent. It may only look
# up a decoder-issued ticket already registered to the exact live facade/session.
# It must not grant media authority from a filename, inspect a model cache, fetch,
# or release worker-owned media on return. The worker/session owns that lifetime.
# There is no public setter, caller-supplied ticket, or real implementation here.
_RELIABILITY_MEDIA_TICKETS = None


def _require_reliability_media_tickets():
    source = _RELIABILITY_MEDIA_TICKETS
    if source is None:
        raise ReliabilityUnavailableError(
            "Owned reliability media admission is unavailable")
    return source


def _request_reliability_words(audio: Path, model_name: str,
                               model_root: str | Path | None, *,
                               local_files_only: bool = True):
    """Consume passive words inside the owned adapter and cursor lifetimes.

    The private ticket source must bind its result to the supplied exact facade.
    The existing operation port separately validates issuance and its permit.
    This helper neither decodes a file nor issues a media ticket itself.
    """
    if local_files_only is not True:
        raise ReliabilityUnavailableError(
            "Reliability requests cannot authorize model acquisition")
    ticket_source = _require_reliability_media_tickets()
    import asr_loading_adapter
    from snapshot_lifecycle import OperationFacade, SegmentStream, TranscribeRequest

    with asr_loading_adapter.faster_whisper_session(
            model_name, model_root=model_root, usage="reliability") as operations:
        if type(operations) is not OperationFacade:
            raise ReliabilityUnavailableError("Exact owned operation facade required")
        ticket = ticket_source.ticket_for_session(operations, str(audio))
        if ticket is None or isinstance(ticket, (str, bytes, bytearray, Path)):
            raise ReliabilityUnavailableError("Decoder-issued media ticket required")
        request = TranscribeRequest(
            media_ticket=ticket, language="en", word_timestamps=True,
            vad_filter=False, beam_size=1, best_of=1)
        stream = operations.transcribe(request)
        if (type(stream) is not SegmentStream
                or stream._session is not operations._session):
            raise ReliabilityUnavailableError("Exact session-bound segment stream required")
        primary_error = None
        try:
            return _words_from_segments(stream)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                stream.close()
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                BaseException.add_note(
                    primary_error, "Owned reliability stream cleanup remains unconfirmed: "
                    + type(cleanup_error).__name__)


def detect_unreliable_spans(transcript_text: str, audio_path: str | Path,
                            threshold: float = DEFAULT_THRESHOLD,
                            *,
                            model_name: str = DEFAULT_MODEL,
                            model_root: str | Path | None = None,
                            _transcribe=None) -> list[Span]:
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
    if _transcribe is None:
        _require_reliability_media_tickets()
    audio = Path(audio_path)
    if not audio.is_file():
        raise FileNotFoundError(f"audio file not found: {audio}")

    if _transcribe is not None:
        segments = _transcribe(str(audio))
    else:
        word_rows = _request_reliability_words(
            audio, model_name, model_root, local_files_only=True)
        return _cluster_low_words(word_rows, threshold)

    word_rows = _words_from_segments(segments)
    return _cluster_low_words(word_rows, threshold)
