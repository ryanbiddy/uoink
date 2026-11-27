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
  The size the installer bundles (3.12+: base) needs no download: a
  downloaded copy of that size still wins, else the bundled one runs.

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

import asr_worker
import asr_models
import uoink_reliability as reliability
import json
import importlib.util
import logging
import os
import inspect
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("uoink.whisper_runner")


def _register_packaged_decoder_dlls():
    """Keep Windows' loader on the app-owned FFmpeg runtime for TorchCodec."""
    if sys.platform != "win32":
        return None
    app = Path(__file__).resolve().parent
    directory = app / "bin" / "torchcodec"
    if not directory.exists():
        return None  # Source checkouts do not carry the installed native runtime.
    if directory.resolve() != directory or not directory.is_dir():
        raise RuntimeError("Packaged decoder directory must stay inside the application")
    names = ("avcodec-61.dll", "avdevice-61.dll", "avfilter-10.dll",
             "avformat-61.dll", "avutil-59.dll", "swresample-5.dll", "swscale-8.dll")
    for name in names:
        path = directory / name
        if not path.is_file() or path.resolve() != path:
            raise RuntimeError(f"Missing or redirected packaged decoder library: {name}")
    return os.add_dll_directory(str(directory))


# server.py imports this module before probing WhisperX. Direct transcription
# entry points also pass here. The handle must outlive all lazy native imports.
_PACKAGED_DECODER_DLL_HANDLE = _register_packaged_decoder_dlls()

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
MODEL_LARGE_V3_TURBO = "large-v3-turbo"
_MODELS = (
    MODEL_TINY, MODEL_BASE, MODEL_SMALL, MODEL_MEDIUM, MODEL_LARGE,
    MODEL_LARGE_V3_TURBO, "distil-small.en", "distil-large-v3.5",
)


def normalize_model(value) -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _MODELS:
            return v
    return MODEL_BASE


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ---- runtime probe -----------------------------------------------------
# Check package presence without initializing torch or its native libraries.
def _probe_whisperx() -> bool:
    import _platform
    if not _platform.media_capability()["available"]:
        return False
    if sys.platform == "darwin" and not _platform.alignment_capability()["available"]:
        return False
    try:
        return importlib.util.find_spec("whisperx") is not None
    except (ImportError, ValueError, OSError) as e:
        log.warning("whisperx unavailable: %s: %s", type(e).__name__, e)
        return False


_WHISPERX_AVAILABLE = _probe_whisperx()


def is_whisperx_available() -> bool:
    """Return the cached package-presence check used by health and settings."""
    return _WHISPERX_AVAILABLE


def transcription_engine() -> Literal["whisperx", "faster-whisper"] | None:
    """Select a podcast runtime without importing faster-whisper."""
    if is_whisperx_available():
        return "whisperx"
    if sys.platform.startswith("linux"):
        import _platform
        if (_platform.media_capability()["available"]
                and importlib.util.find_spec("faster_whisper") is not None):
            return "faster-whisper"
    return None


def is_transcription_available() -> bool:
    return transcription_engine() is not None


# Repository identities from the pinned faster-whisper 1.2.1 mapping.
_MODEL_REPOSITORIES = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": asr_models.get(MODEL_LARGE_V3_TURBO)["repo"],
    **{name: asr_models.get(name)["repo"] for name in reliability.ENGLISH_ONLY_MODELS},
}
_ASR_CACHE_FILES = ("model.bin", "config.json", "tokenizer.json")


def _model_cache_root(data_root: Path, model_size: str) -> Path:
    """Return the private ASR cache root without creating it."""
    root = Path(data_root).resolve()
    cache = root / "whisper_models" / normalize_model(model_size)
    if cache.resolve() != cache:
        raise RuntimeError("Whisper cache directories must not be redirected")
    return cache


def _model_repo_root(data_root: Path, model_size: str, *, legacy=False) -> Path:
    model_size = normalize_model(model_size)
    repo_id = asr_models.LEGACY_TURBO_REPO if legacy else _MODEL_REPOSITORIES[model_size]
    repo = _model_cache_root(data_root, model_size) / (
        "models--" + repo_id.replace("/", "--"))
    for directory in (repo, repo / "refs", repo / "snapshots", repo / "blobs"):
        if directory.resolve() != directory:
            raise RuntimeError("Whisper repository cache must not be redirected")
    return repo


def _checked_model_snapshot(data_root: Path, model_size: str,
                            snapshot: Path, *, legacy=False) -> Path | None:
    """Check minimum ASR cache structure, not model integrity or safety."""
    try:
        repo = _model_repo_root(data_root, model_size, legacy=legacy)
        snapshot = Path(snapshot).absolute()
        if (snapshot.parent != repo / "snapshots"
                or re.fullmatch(r"[0-9a-f]{40}", snapshot.name) is None
                or snapshot.resolve(strict=True) != snapshot
                or not snapshot.is_dir()):
            return None
        for name in _ASR_CACHE_FILES:
            asset = (snapshot / name).resolve(strict=True)
            # Hub may link snapshot files to this repository's blob store.
            if (not asset.is_relative_to(repo) or not asset.is_file()
                    or asset.stat().st_size == 0):
                return None
        return snapshot
    except (OSError, RuntimeError, ValueError):
        return None


def _cached_model_snapshot(data_root: Path, model_size: str) -> Path | None:
    shared_root = Path(data_root) / "models" / "whisper"
    if reliability.is_model_ready(model_size, shared_root):
        return reliability._cached_reliability_snapshot(shared_root, model_size)
    snapshot = _read_model_snapshot(data_root, model_size)
    if snapshot is None and model_size == "large-v3-turbo":
        snapshot = _read_model_snapshot(data_root, model_size, legacy=True)
    return snapshot


def _read_model_snapshot(data_root: Path, model_size: str, *, legacy=False) -> Path | None:
    """Read the pinned helper's default Hub cache layout; never fetch or write."""
    try:
        repo = _model_repo_root(data_root, model_size, legacy=legacy)
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
        return _checked_model_snapshot(
            data_root, model_size, repo / "snapshots" / revision, legacy=legacy)
    except (OSError, RuntimeError, ValueError):
        return None


def _bundled_snapshot(model_size: str) -> Path | None:
    """The installer-bundled snapshot of this size, or None.

    3.12 installers ship one model under the app folder; capture ASR and
    podcast jobs share it (see uoink_reliability.bundled_model_dir). It is
    read-only app data, loaded by path, so it needs no download consent.
    """
    try:
        import uoink_reliability
    except Exception:  # pragma: no cover - the module always ships
        return None
    return uoink_reliability.bundled_model_dir(normalize_model(model_size))


def is_model_downloaded(data_root: Path, model_size: str = MODEL_BASE) -> bool:
    """Report the model available locally, without importing a runtime or writing.

    True for minimum ASR files in the user's cache, or for the installer's
    bundled copy of the same size. This is structural readiness for
    consent/preflight, not artifact validation or a claim that the model has
    loaded. Execution rechecks the snapshot.
    """
    model_size = normalize_model(model_size)
    return (_cached_model_snapshot(data_root, model_size) is not None
            or _bundled_snapshot(model_size) is not None)


def _model_dir(data_root: Path, model_size: str) -> Path:
    p = _model_cache_root(data_root, model_size)
    _model_repo_root(data_root, model_size)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _download_model_snapshot(model_size: str, cache_root: Path, *, cancel_event=None) -> Path:
    """Use the chooser's pinned downloader within the podcast cache after consent."""
    entry = asr_models.get(model_size)
    try:
        asr_models.download(model_size, cache_root, cancel_event=cancel_event,
                            progress=asr_worker.report_download_bytes)
    except asr_models.DownloadCancelled as exc:
        raise asr_worker.TranscriptionCancelled("Transcription cancelled.") from exc
    return asr_models._snapshot_dir(cache_root, entry)


def _prepare_model_snapshot(data_root: Path, model_size: str, *,
                            consent_given: bool, cancel_event=None) -> Path:
    model_size = normalize_model(model_size)
    snapshot = _cached_model_snapshot(data_root, model_size)
    if snapshot is not None:
        return snapshot
    bundled = _bundled_snapshot(model_size)
    if bundled is not None:
        return bundled
    if not consent_given:
        raise PermissionError(
            f"Whisper model '{model_size}' is not fully cached; "
            "explicit download consent is required.")
    cache_root = _model_dir(data_root, model_size)
    snapshot = _download_model_snapshot(model_size, cache_root,
                                        **({"cancel_event": cancel_event} if cancel_event else {}))
    checked = _checked_model_snapshot(data_root, model_size, snapshot)
    if checked is None:
        raise RuntimeError(
            f"Whisper model '{model_size}' download did not provide the required "
            "local ASR files (model.bin, config.json and tokenizer.json).")
    return checked


def _runtime_device() -> str:
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _compute_type(device: str) -> str:
    return "float16" if device == "cuda" else "int8"


def set_current_thread_below_normal() -> bool:
    """Lower only the transcription worker on Windows.

    The server, dashboard, and search request threads retain normal priority.
    Other platforms keep their default scheduling priority.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        thread = kernel32.GetCurrentThread()
        return bool(kernel32.SetThreadPriority(thread, -1))
    except (AttributeError, OSError):
        return False


def _hf_token() -> str | None:
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    )


# The diarization model identifier recorded in Phase 6 run provenance. This
# is the pyannote pipeline, not Whisper's transcription model size.
DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"


def _diarizer_class(whisperx):
    pipeline = getattr(whisperx, "DiarizationPipeline", None)
    if pipeline is None:
        from whisperx.diarize import DiarizationPipeline
        return DiarizationPipeline
    return pipeline


def _diarization_model_name(whisperx) -> str | None:
    """The diarization model this runtime will actually load, or None when
    the installed WhisperX does not accept an explicit model name (unknown
    values are recorded as null, never guessed)."""
    try:
        params = inspect.signature(_diarizer_class(whisperx)).parameters
    except (ImportError, TypeError, ValueError):
        return None
    return DIARIZATION_MODEL if "model_name" in params else None


def _package_version(name: str) -> str | None:
    try:
        from importlib import metadata as _metadata
        return _metadata.version(name)
    except Exception:  # noqa: BLE001 -- provenance is best effort, never fatal
        return None


def _file_sha256(path: Path) -> str | None:
    """SHA-256 of the input audio, recorded at execution (never duplicated)."""
    import hashlib
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _diarization_pipeline(whisperx, *, device: str, data_root: Path):
    """Create a WhisperX diarizer across old/new constructor signatures."""
    kwargs: dict[str, Any] = {}
    try:
        params = inspect.signature(_diarizer_class(whisperx)).parameters
    except (TypeError, ValueError):
        params = {}
    if "model_name" in params:
        # Current WhisperX defaults here too, but pinning it avoids falling
        # back to older pyannote 3.1 behavior when dependency resolution drifts.
        kwargs["model_name"] = DIARIZATION_MODEL
    token = _hf_token()
    if token:
        if "token" in params:
            kwargs["token"] = token
        elif "use_auth_token" in params:
            kwargs["use_auth_token"] = token
    if "cache_dir" in params:
        kwargs["cache_dir"] = str(Path(data_root) / "diarization_models")
    kwargs["device"] = device
    return _diarizer_class(whisperx)(**kwargs)


# ---- transcript helper -------------------------------------------------
def _shape_segments(segments) -> list[dict]:
    """Normalise whisperx's per-segment dicts to our schema. WhisperX
    returns start/end/text and may also supply aligned words and a speaker."""
    out: list[dict] = []
    for s in segments or []:
        if not isinstance(s, dict):
            continue
        entries = reliability._transcript_entries_from_segments([s])
        if not entries:
            continue
        row = reliability.segment_dict(entries[0])
        spk = s.get("speaker")
        if spk:
            row["speaker"] = str(spk)
        out.append(row)
    return out


def _asr_offload_active() -> bool:
    try:
        import asr_worker
    except ImportError:  # pragma: no cover - the module always ships
        return False
    return asr_worker.offload_active()


def plain_engine_for(diarize: bool) -> bool:
    """True when a job should skip WhisperX and run on faster-whisper alone.

    WhisperX adds exactly one thing Uoink keeps: speaker labels (forced
    alignment plus pyannote diarization). Without them its output is the same
    faster-whisper text, but loading it pulls in torch, Lightning and a
    pyannote voice-detection checkpoint (gigabytes of memory). faster-whisper
    has its own Silero voice detection, so a transcript-only job uses it.
    The gate is unchanged: some engine must be available, as before.
    """
    if sys.platform == "darwin" or diarize or transcription_engine() is None:
        return False
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


def _transcribe_audio_plain(audio_path: Path, *, data_root: Path, model_size: str,
                            language: str | None, consent_given: bool,
                            initial_prompt: str | None, cancel_event=None, checkpoint=None, progress=None) -> dict:
    """Transcript-only faster-whisper run on this cache/consent/bundle policy."""
    import _platform
    import transcript_review
    import uoink_reliability
    _platform.require_media()
    model_path = _prepare_model_snapshot(
        data_root, model_size, consent_given=consent_given, cancel_event=cancel_event)
    if (model_path != _bundled_snapshot(model_size)
            and _cached_model_snapshot(data_root, model_size) != model_path):
        raise RuntimeError("Local ASR snapshot changed before model construction")
    info: dict[str, Any] = {}
    entries = uoink_reliability.transcribe_media(
        audio_path, model_name=str(model_path), language=language, info=info,
        initial_prompt=initial_prompt,
        **({"cancel_event": cancel_event} if cancel_event is not None else {}),
        **({"checkpoint": checkpoint} if checkpoint else {}),
        **({"progress": progress} if progress else {}))
    return {
        "model": model_size,
        "language": info.get("language") or language or "en",
        "diarization_ran": False,
        # Word timings ride along when the model gave them (3.18).
        **transcript_review.reviewed_fields([reliability.segment_dict(e) for e in entries],
                                            whisper=True, field="segments"),
        "generated_at": _now_iso(),
        "engine": "faster-whisper",
    }


def transcribe_audio(audio_path: Path, *,
                      data_root: Path,
                      model_size: str = MODEL_BASE,
                      language: str | None = None,
                      diarize: bool = False,
                      consent_given: bool = False,
                      initial_prompt: str | None = None, cancel_event=None, checkpoint=None,
                      duration_seconds=None, progress=None) -> dict:
    """End-to-end transcription. Synchronous. Returns the structured
    transcript dict.

    Raises RuntimeError when whisperx is not importable -- the caller
    surfaces a 503 with install hints.

    Missing or incomplete ASR caches require explicit download consent.
    Resolution and minimum-file checks precede model construction. The
    execution call receives a local snapshot and local_files_only=True;
    this does not qualify the separate VAD loader or artifact integrity."""
    import _platform
    import transcript_review
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file missing: {audio_path}")
    if _asr_offload_active():
        # The helper never loads a model: the transcription child does, and
        # exits when idle so the OS gets the memory back (asr_worker).
        return asr_worker.call("transcribe_audio", {
            "audio_path": str(audio_path), "data_root": str(Path(data_root)),
            "model_size": model_size, "language": language, "diarize": bool(diarize),
            "consent_given": bool(consent_given), "initial_prompt": initial_prompt,
            "duration_seconds": duration_seconds},
            cancel_event=cancel_event, checkpoint=checkpoint, progress=progress, background=True)
    model_size = normalize_model(model_size)
    fallback = None
    if reliability.is_english_only(model_size):
        _platform.require_media()
        checker = _cached_model_snapshot(data_root, MODEL_BASE) or _bundled_snapshot(MODEL_BASE)
        checker_name = MODEL_BASE
        if checker is None:
            for name in _MODELS:
                if not reliability.is_english_only(name):
                    checker = _cached_model_snapshot(data_root, name)
                    if checker:
                        checker_name = name
                        break
        model_size, language, fallback = reliability._english_guard(
            audio_path, model_size, Path(data_root) / "models" / "whisper", language,
            checker_path=checker, checker_name=checker_name, cancel_event=cancel_event)
    asr_worker.report_phase("model load")
    if asr_worker.in_child() and plain_engine_for(diarize):
        result = _transcribe_audio_plain(
            audio_path, data_root=data_root, model_size=normalize_model(model_size),
            language=language, consent_given=consent_given, initial_prompt=initial_prompt,
            cancel_event=cancel_event, checkpoint=checkpoint, progress=progress)
        if fallback:
            result["english_fallback"] = fallback
        return result
    _platform.require_media()
    if sys.platform == "darwin":
        alignment = _platform.alignment_capability()
        if not alignment["available"]:
            raise RuntimeError(f"{alignment['code']}: {alignment['reason']}")

    global _WHISPERX_AVAILABLE
    engine = transcription_engine()
    if engine == "whisperx":
        if not consent_given:
            _prepare_model_snapshot(data_root, model_size, consent_given=False)
        try:
            import whisperx  # type: ignore
        except Exception as exc:
            log.warning("WhisperX import failed: %s: %s", type(exc).__name__, exc)
            _WHISPERX_AVAILABLE = False
            engine = transcription_engine()
            if engine != "faster-whisper":
                raise RuntimeError(f"whisperx import failed at transcribe time: {exc}") from exc
    if engine == "faster-whisper":
        import uoink_reliability
        model_path = _prepare_model_snapshot(
            data_root, model_size, consent_given=consent_given, cancel_event=cancel_event)
        if (model_path != _bundled_snapshot(model_size)
                and _cached_model_snapshot(data_root, model_size) != model_path):
            raise RuntimeError("Local ASR snapshot changed before model construction")
        if diarize:
            log.warning("Diarization needs install.sh --with-whisperx; "
                        "continuing with transcript-only faster-whisper.")
        info: dict[str, Any] = {}
        # model_root is a Hub cache, not a snapshot. Passing the resolved path
        # as the model source preserves podcast cache/consent precedence and
        # reuses reliability's local-only CPU/int8 loader without a cache write.
        entries = uoink_reliability.transcribe_media(
            audio_path, model_name=str(model_path), language=language, info=info,
            initial_prompt=initial_prompt,
            **({"cancel_event": cancel_event} if cancel_event is not None else {}),
            **({"checkpoint": checkpoint} if checkpoint else {}),
            **({"progress": progress} if progress else {}))
        return {
            **({"english_fallback": fallback} if fallback else {}),
            "model": model_size,
            "language": info.get("language") or language or "en",
            "diarization_ran": False,
            **transcript_review.reviewed_fields([reliability.segment_dict(e) for e in entries],
                                                whisper=True, duration=duration_seconds, field="segments"),
            "generated_at": _now_iso(),
            "engine": "faster-whisper",
        }

    if engine is None:
        raise RuntimeError(
            "whisperx is not installed or its runtime is broken. "
            "Reinstall Uoink so the bundled WhisperX runtime is restored. "
            "See the helper log for the underlying import error.")
    model_path = _prepare_model_snapshot(
        data_root, model_size, consent_given=consent_given, cancel_event=cancel_event)
    try:
        import whisperx  # type: ignore
    except BaseException as e:  # noqa: BLE001 -- matches _probe_whisperx
        raise RuntimeError(
            f"whisperx import failed at transcribe time: "
            f"{type(e).__name__}: {e}"
        ) from e

    # whisperx exposes a load_model + transcribe + align + diarize chain.
    # Keep the call site narrow so a future WhisperX API rev doesn't
    # require touching every caller -- just this module.
    device = _runtime_device()
    diarization_succeeded = False
    # Phase 6 (phase6-v1): one fresh run identity per executed diarization
    # attempt, generated once and persisted with the transcript. A retry or
    # rebuild reuses it; a genuinely new execution gets a new one.
    diarization_run: dict[str, Any] | None = None
    try:
        if (model_path != _bundled_snapshot(model_size)
                and _cached_model_snapshot(data_root, model_size) != model_path):
            raise RuntimeError('Local ASR snapshot changed before model construction')
        # A previous transcript-only job may have left a faster-whisper model
        # resident in this child. Release it before constructing the WhisperX model.
        clear_cache = getattr(reliability._load_model, "cache_clear", None)
        if asr_worker.in_child() and clear_cache:
            clear_cache()
        model = whisperx.load_model(str(model_path), device=device,
                                      compute_type=_compute_type(device),
                                      **({"threads": asr_models.cpu_threads()} if device == "cpu" else {}),
                                      download_root=str(_model_cache_root(data_root, model_size)),
                                      local_files_only=True,
                                      **({"asr_options": {"initial_prompt": initial_prompt}}
                                         if initial_prompt else {}))
        audio_input = str(audio_path)
        offloaded = asr_worker.in_child()
        if offloaded or (sys.platform == "darwin" and _platform.mac_bundle_contents() is not None):
            # WhisperX's string loader invokes bare `ffmpeg`. Supply samples so
            # transcription, alignment and diarization all use our resolver.
            import numpy as np
            import subprocess
            asr_worker.report_phase("ffmpeg")
            decoded = subprocess.run([
                _platform.media_binary("ffmpeg"), "-nostdin", "-v", "error",
                "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"],
                check=True, capture_output=True, timeout=None if offloaded else 600,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if offloaded and os.name == "nt" else {}))
            audio_input = np.frombuffer(decoded.stdout, dtype=np.float32).copy()
            del decoded
            duration_seconds = len(audio_input) / 16000

        last_percent = None

        def segment_progress(percent):
            nonlocal last_percent
            if cancel_event is not None and cancel_event.is_set():
                raise reliability._cancelled_error()
            if percent is not None and last_percent is not None and percent <= last_percent:
                return
            last_percent = percent
            if progress is not None and percent is not None:
                progress(percent, 100)
            if checkpoint is not None:
                checkpoint({"percent": percent})

        def callbacks(fn):
            if checkpoint or progress or cancel_event:
                try:
                    if "progress_callback" in inspect.signature(fn).parameters:
                        return {"progress_callback": segment_progress}
                except (ValueError, TypeError):
                    pass
            return {}

        decode_callbacks = callbacks(model.transcribe)
        asr_worker.report_phase("batch transcription", duration_seconds=duration_seconds)
        result = model.transcribe(audio_input, language=language, **decode_callbacks)
        segment_progress(None)
        segments = result.get("segments") or []
        detected_lang = result.get("language") or language or "en"

        # Optional alignment + diarization. Errors here degrade
        # gracefully -- we still return the un-aligned transcript, with an
        # explicit failed run record instead of a claimed success.
        if diarize:
            import uuid
            diarization_run = {
                "run_id": uuid.uuid4().hex,
                "status": "failed",
                "producer": "whisperx",
                "producer_version": _package_version("whisperx"),
                "model": _diarization_model_name(whisperx),
                "generated_at": None,
                "input_media_sha256": _file_sha256(audio_path),
                "artifact_sha256": None,
                "parameters": {"language": detected_lang, "alignment_model": None},
            }
            try:
                asr_worker.report_phase("alignment")
                align_model, align_meta = whisperx.load_align_model(
                    language_code=detected_lang, device=device)
                aligned = whisperx.align(
                    segments, align_model, align_meta,
                    audio_input, device=device, **callbacks(whisperx.align))
                segment_progress(None)
                asr_worker.report_phase("diarization")
                diarize_pipeline = _diarization_pipeline(
                    whisperx, device=device, data_root=data_root)
                diarize_segments = diarize_pipeline(audio_input, **callbacks(diarize_pipeline))
                segment_progress(None)
                aligned = whisperx.assign_word_speakers(
                    diarize_segments, aligned)
                segments = aligned.get("segments") or segments
                diarization_succeeded = True
                diarization_run["status"] = "succeeded"
            except asr_worker.TranscriptionCancelled:
                raise
            except Exception as diar_err:
                log.warning("diarization failed (degrading to "
                              "transcript-only): %s", diar_err)
            diarization_run["generated_at"] = _now_iso()
    except asr_worker.TranscriptionCancelled:
        raise
    except Exception as e:
        raise RuntimeError(f"whisperx transcribe failed: {e}") from e

    transcript: dict[str, Any] = {
        "model": model_size,
        "language": detected_lang,
        **({"english_fallback": fallback} if fallback else {}),
        "diarization_ran": diarization_succeeded,
        **transcript_review.reviewed_fields(_shape_segments(segments), whisper=True,
                                            duration=duration_seconds, field="segments"),
        "generated_at": _now_iso(),
    }
    if diarization_run is not None:
        transcript["diarization_run"] = diarization_run
        transcript["diarization_run_id"] = diarization_run["run_id"]
    return transcript


# ---- persistence helpers (used by the endpoints to record state) -------
def transcript_output_path(audio_path: Path) -> Path:
    """Sibling of the MP3 with .transcript.json suffix."""
    audio_path = Path(audio_path)
    return audio_path.with_suffix(".transcript.json")


def write_transcript(transcript: dict, *, audio_path: Path) -> Path:
    """Persist the transcript JSON. Phase 6 (phase6-v1): when the transcript
    carries a ``diarization_run`` record, the output artifact digest is
    computed over the transcript *without* its run/provenance members
    (``library_media.transcript_artifact_bytes``) and stored in the record,
    so the archived artifact never hashes itself."""
    out = transcript_output_path(audio_path)
    run = transcript.get("diarization_run")
    if isinstance(run, dict):
        import hashlib
        import library_media  # offline validator; no model, no helper import
        run["artifact_sha256"] = hashlib.sha256(
            library_media.transcript_artifact_bytes(transcript)).hexdigest()
    out.write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False, allow_nan=False),
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
    with idx.write_transaction() as conn:
        conn.execute(
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
