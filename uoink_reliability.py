"""Transcript reliability detection for Uoink.

v2.5 scope is detection only: use whisper-timestamped word confidence to flag
low-confidence spans in the existing YouTube transcript. Re-transcription and
speaker diarization are intentionally deferred to v3.
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


def _import_whisper_timestamped():
    try:
        import whisper_timestamped as whisper  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ReliabilityUnavailableError(
            "whisper-timestamped is not installed; install requirements and "
            "download the local Whisper model before computing reliability"
        ) from e
    return whisper


def ensure_model(model_name: str = DEFAULT_MODEL,
                 model_root: str | Path | None = None) -> dict[str, Any]:
    """Load the model once so whisper/openai-whisper downloads it if missing."""
    whisper = _import_whisper_timestamped()
    kwargs: dict[str, Any] = {}
    if model_root:
        Path(model_root).mkdir(parents=True, exist_ok=True)
        kwargs["download_root"] = str(model_root)
    whisper.load_model(model_name, device="cpu", **kwargs)
    return {
        "ok": True,
        "model": model_name,
        "model_root": str(model_root) if model_root else None,
    }


def _word_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in result.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            if isinstance(word, dict):
                rows.append(word)
    return rows


def _clean_word(text: str) -> str:
    return re.sub(r"(^[^\w']+|[^\w']+$)", "", str(text or "")).strip()


def _reason_for(words: list[dict[str, Any]], avg_conf: float,
                threshold: float) -> str:
    text = " ".join(str(w.get("text") or w.get("word") or "") for w in words)
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
        _clean_word(str(w.get("text") or w.get("word") or ""))
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


def detect_unreliable_spans(transcript_text: str, audio_path: str | Path,
                            threshold: float = DEFAULT_THRESHOLD,
                            *,
                            model_name: str = DEFAULT_MODEL,
                            model_root: str | Path | None = None) -> list[Span]:
    """Return clustered low-confidence word spans for an audio file.

    ``transcript_text`` is accepted for the public interface and future
    alignment work; v2.5 uses whisper-timestamped's ASR word stream as the
    confidence source and reports word indices in that stream.
    """
    _ = transcript_text  # reserved for future YouTube-vs-ASR alignment
    threshold = max(0.05, min(0.95, float(threshold)))
    audio = Path(audio_path)
    if not audio.is_file():
        raise FileNotFoundError(f"audio file not found: {audio}")

    whisper = _import_whisper_timestamped()
    kwargs: dict[str, Any] = {}
    if model_root:
        Path(model_root).mkdir(parents=True, exist_ok=True)
        kwargs["download_root"] = str(model_root)
    model = whisper.load_model(model_name, device="cpu", **kwargs)
    result = whisper.transcribe(
        model,
        str(audio),
        language="en",
        verbose=False,
        beam_size=1,
        best_of=1,
    )

    low: list[tuple[int, dict[str, Any]]] = []
    for i, word in enumerate(_word_rows(result)):
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

