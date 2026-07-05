"""Transcript reliability detection for Uoink.

Scope is detection only: surface low-confidence word spans in a saved
transcript so the reader knows where the ASR was unsure. Re-transcription
and diarization are out of scope here.

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


def _load_model(model_name: str, model_root: str | Path | None):
    WhisperModel = _import_faster_whisper()
    kwargs: dict[str, Any] = {"device": "cpu", "compute_type": _COMPUTE_TYPE}
    if model_root:
        Path(model_root).mkdir(parents=True, exist_ok=True)
        kwargs["download_root"] = str(model_root)
    return WhisperModel(model_name, **kwargs)


def ensure_model(model_name: str = DEFAULT_MODEL,
                 model_root: str | Path | None = None) -> dict[str, Any]:
    """Load the model once so faster-whisper downloads it if missing."""
    _load_model(model_name, model_root)
    return {
        "ok": True,
        "model": model_name,
        "model_root": str(model_root) if model_root else None,
    }


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
                            _transcribe=None) -> list[Span]:
    """Return clustered low-confidence word spans for an audio file.

    ``transcript_text`` is accepted for the public interface and future
    alignment work; the confidence source is faster-whisper's per-word
    probability over the ASR stream. ``_transcribe`` is a test seam: a
    callable (audio_path) -> iterable of segments, so the clustering can be
    exercised without the model.
    """
    _ = transcript_text  # reserved for future YouTube-vs-ASR alignment
    threshold = max(0.05, min(0.95, float(threshold)))
    audio = Path(audio_path)
    if not audio.is_file():
        raise FileNotFoundError(f"audio file not found: {audio}")

    if _transcribe is not None:
        segments = _transcribe(str(audio))
    else:
        model = _load_model(model_name, model_root)
        segments, _info = model.transcribe(
            str(audio), language="en", word_timestamps=True,
            beam_size=1, best_of=1)

    word_rows = _words_from_segments(segments)
    return _cluster_low_words(word_rows, threshold)
