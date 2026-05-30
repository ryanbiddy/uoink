"""v3.1 WhisperX transcription runner.

Per PROMPT-V3.1 track B step 3 (podcast transcription) + track D
(A1 re-transcription). Both share the WhisperX runtime + the same
model + the same lazy-download UX -- one worker, two entry points.

Locked compute policy (LOCAL-FIRST):
- Whisper inference runs on the user's machine. No cloud API call.
- WhisperX is imported LAZILY so the helper boots fast, but the Windows
  installer bundles the runtime. The /transcribe endpoints still surface
  a structured 503 if an install is damaged or a dependency is missing.
- Model files (200 MB - 2 GB) are downloaded on first use under
  <data_root>/whisper_models/<model_size>/. Consent dialog lives in
  the dashboard; this module just respects an explicit
  `consent_given=True` flag and refuses without it on first download.

Output shape (transcript JSON written to
<data_root>/Podcasts/<feed>/<episode>.transcript.json):

    {
      "model": "base" | "small" | ...,
      "language": "en",
      "diarization_ran": true | false,
      "segments": [
        {"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00",
          "text": "Welcome to the show."},
        ...
      ],
      "generated_at": "ISO timestamp"
    }

Compute budget per ROADMAP: 10-15 minutes per hour of audio on a
typical laptop with the `base` model. Long episodes are fire-and-
forget background processing -- the worker runs synchronously here
but the endpoint can be wrapped in a thread by server.py."""

from __future__ import annotations

import json
import logging
import os
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("uoink.whisper_runner")

# Bounded enum for the per-row transcription state. The dashboard reads
# this directly. 'queued' is set when the user opts in; 'running' once
# the worker picks it up; 'done' / 'failed' on completion.
STATUS_NONE = "none"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
_STATUSES = (STATUS_NONE, STATUS_QUEUED, STATUS_RUNNING,
              STATUS_DONE, STATUS_FAILED)

# Bounded model enum. Larger = slower but more accurate. base is the
# pragmatic default. tiny is for testing / low-spec hardware.
MODEL_TINY = "tiny"
MODEL_BASE = "base"
MODEL_SMALL = "small"
MODEL_MEDIUM = "medium"
MODEL_LARGE = "large"
_MODELS = (MODEL_TINY, MODEL_BASE, MODEL_SMALL, MODEL_MEDIUM, MODEL_LARGE)


def normalize_model(value) -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _MODELS:
            return v
    return MODEL_BASE


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ---- runtime probe -----------------------------------------------------
def is_whisperx_available() -> bool:
    """Cheap import probe. Used by /diagnose + the endpoints' 503 path."""
    try:
        import whisperx  # noqa: F401
        return True
    except ImportError:
        return False


def is_model_downloaded(data_root: Path, model_size: str = MODEL_BASE) -> bool:
    """Return true once the local Whisper model cache has any payload.

    The first transcription still requires explicit user consent before
    WhisperX downloads the model. /health uses this as a read-only status
    bit, so it must not create the model directory as a side effect.
    """
    model_size = normalize_model(model_size)
    model_path = Path(data_root) / "whisper_models" / model_size
    if not model_path.exists() or not model_path.is_dir():
        return False
    try:
        return any(model_path.iterdir())
    except OSError:
        return False


def _model_dir(data_root: Path, model_size: str) -> Path:
    p = Path(data_root) / "whisper_models" / model_size
    p.mkdir(parents=True, exist_ok=True)
    return p


def _runtime_device() -> str:
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _compute_type(device: str) -> str:
    return "float16" if device == "cuda" else "int8"


def _hf_token() -> str | None:
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    )


def _diarization_pipeline(whisperx, *, device: str, data_root: Path):
    """Create a WhisperX diarizer across old/new constructor signatures."""
    kwargs: dict[str, Any] = {}
    try:
        params = inspect.signature(whisperx.DiarizationPipeline).parameters
    except (TypeError, ValueError):
        params = {}
    if "model_name" in params:
        # Current WhisperX defaults here too, but pinning it avoids falling
        # back to older pyannote 3.1 behavior when dependency resolution drifts.
        kwargs["model_name"] = "pyannote/speaker-diarization-community-1"
    token = _hf_token()
    if token:
        if "token" in params:
            kwargs["token"] = token
        elif "use_auth_token" in params:
            kwargs["use_auth_token"] = token
    if "cache_dir" in params:
        kwargs["cache_dir"] = str(Path(data_root) / "diarization_models")
    kwargs["device"] = device
    return whisperx.DiarizationPipeline(**kwargs)


# ---- transcript helper -------------------------------------------------
def _shape_segments(segments) -> list[dict]:
    """Normalise whisperx's per-segment dicts to our schema. WhisperX
    returns dicts with start/end/text and optional speaker after the
    diarization step. We drop everything else (logprobs, timings) --
    the dashboard never reads them."""
    out: list[dict] = []
    for s in segments or []:
        if not isinstance(s, dict):
            continue
        row: dict[str, Any] = {
            "start": float(s.get("start") or 0.0),
            "end": float(s.get("end") or 0.0),
            "text": (s.get("text") or "").strip(),
        }
        spk = s.get("speaker")
        if spk:
            row["speaker"] = str(spk)
        out.append(row)
    return out


def transcribe_audio(audio_path: Path, *,
                      data_root: Path,
                      model_size: str = MODEL_BASE,
                      language: str | None = None,
                      diarize: bool = False,
                      consent_given: bool = False) -> dict:
    """End-to-end transcription. Synchronous. Returns the structured
    transcript dict.

    Raises RuntimeError when whisperx is not importable -- the caller
    surfaces a 503 with install hints.

    `consent_given` must be True for first-time model downloads. The
    flag is verified before the load_model call -- on first use the
    model dir is empty, and we refuse without consent. The dashboard
    consent dialog records the user's opt-in and re-issues the call."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file missing: {audio_path}")
    model_size = normalize_model(model_size)

    # Lazy import. Surfaces ImportError as a clean RuntimeError so the
    # endpoint can produce a 503 with actionable text.
    try:
        import whisperx  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "whisperx is not installed. Reinstall Uoink so the bundled "
            "WhisperX runtime is restored."
        ) from e

    model_path = _model_dir(data_root, model_size)
    # If the model dir has no checkpoint files yet, this is a first
    # download. Verify the user consented before WhisperX hits the
    # internet for 200 MB - 2 GB.
    has_existing_checkpoint = any(model_path.iterdir())
    if not has_existing_checkpoint and not consent_given:
        raise PermissionError(
            f"Whisper model '{model_size}' has not been downloaded yet "
            f"and consent_given=False. The dashboard should prompt the "
            f"user before re-issuing the transcribe call with consent_given=True.")

    # whisperx exposes a load_model + transcribe + align + diarize chain.
    # Keep the call site narrow so a future WhisperX API rev doesn't
    # require touching every caller -- just this module.
    device = _runtime_device()
    diarization_succeeded = False
    try:
        model = whisperx.load_model(model_size, device=device,
                                      compute_type=_compute_type(device),
                                      download_root=str(model_path))
        result = model.transcribe(str(audio_path),
                                    language=language)
        segments = result.get("segments") or []
        detected_lang = result.get("language") or language or "en"

        # Optional alignment + diarization. Errors here degrade
        # gracefully -- we still return the un-aligned transcript.
        if diarize:
            try:
                align_model, align_meta = whisperx.load_align_model(
                    language_code=detected_lang, device=device)
                aligned = whisperx.align(
                    segments, align_model, align_meta,
                    str(audio_path), device=device)
                diarize_pipeline = _diarization_pipeline(
                    whisperx, device=device, data_root=data_root)
                diarize_segments = diarize_pipeline(str(audio_path))
                aligned = whisperx.assign_word_speakers(
                    diarize_segments, aligned)
                segments = aligned.get("segments") or segments
                diarization_succeeded = True
            except Exception as diar_err:
                log.warning("diarization failed (degrading to "
                              "transcript-only): %s", diar_err)
    except Exception as e:
        raise RuntimeError(f"whisperx transcribe failed: {e}") from e

    return {
        "model": model_size,
        "language": detected_lang,
        "diarization_ran": diarization_succeeded,
        "segments": _shape_segments(segments),
        "generated_at": _now_iso(),
    }


# ---- persistence helpers (used by the endpoints to record state) -------
def transcript_output_path(audio_path: Path) -> Path:
    """Sibling of the MP3 with .transcript.json suffix."""
    audio_path = Path(audio_path)
    return audio_path.with_suffix(".transcript.json")


def write_transcript(transcript: dict, *, audio_path: Path) -> Path:
    out = transcript_output_path(audio_path)
    out.write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return out


def update_episode_transcript_state(idx, episode_id: int, *,
                                      status: str,
                                      transcript_path: Path | None = None,
                                      model_used: str | None = None,
                                      diarization_ran: bool = False,
                                      error: str | None = None) -> None:
    """Single UPDATE that lands all transcript_* fields atomically."""
    if status not in _STATUSES:
        raise ValueError(f"status must be one of {list(_STATUSES)}")
    with idx._lock:
        idx._conn.execute(
            "UPDATE podcast_episodes SET "
            "  transcript_status = ?, "
            "  transcript_local_path = COALESCE(?, transcript_local_path), "
            "  transcript_model_used = COALESCE(?, transcript_model_used), "
            "  diarization_ran = ?, "
            "  transcript_finished_at = ?, "
            "  transcript_error = ? "
            "WHERE id = ?",
            (status,
             str(transcript_path) if transcript_path else None,
             model_used,
             1 if diarization_ran else 0,
             _now_iso() if status in (STATUS_DONE, STATUS_FAILED) else None,
             error,
             episode_id))
