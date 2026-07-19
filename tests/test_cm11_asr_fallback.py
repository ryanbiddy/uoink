"""CM-11: local ASR fallback for video captures without captions.

The fallback is deliberately caption-first and local-only. A platform
subtitle track wins whenever one exists. When it does not, Uoink may use an
already-downloaded faster-whisper model; it must never turn capture into an
implicit model download. The setting defaults on but is reversible, and an
ASR failure must not discard the otherwise valid capture.

Run: python -m pytest tests/test_cm11_asr_fallback.py -q

Red before CM-11:
  - no ASR fallback setting or resolver exists;
  - ensure_model does not leave the readiness marker the server checks;
  - caption-less X video sidecars have no transcript or source provenance;
  - the dashboard has no opt-out control or duration-scaled compute copy.
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402
import uoink_reliability as reliability  # noqa: E402


def _assert(condition, message="assertion failed"):
    if not condition:
        raise AssertionError(message)


def test_asr_fallback_setting_defaults_on_and_is_public():
    _assert(server._default_settings().get("asr_fallback_enabled") is True,
            "caption-less video fallback must default ON but remain opt-outable")
    _assert(server._normalize_settings(
        {"asr_fallback_enabled": 0})["asr_fallback_enabled"] is False,
        "normalization must preserve an explicit opt-out")
    _assert(server._public_settings(
        {"asr_fallback_enabled": False}).get("asr_fallback_enabled") is False,
        "the dashboard must receive the user's opt-out")


def test_duration_expectation_scales_with_source_length():
    one_hour = server._asr_duration_expectation(3600)
    two_hours = server._asr_duration_expectation(7200)
    _assert(one_hour["estimated_minutes_min"] == 10.0
            and one_hour["estimated_minutes_max"] == 15.0,
            f"one-hour estimate must document 10-15 minutes: {one_hour}")
    _assert(two_hours["estimated_minutes_min"] == 20.0
            and two_hours["estimated_minutes_max"] == 30.0,
            f"estimate must scale with duration: {two_hours}")
    unknown = server._asr_duration_expectation(0)
    _assert(unknown["estimated_minutes_min"] is None
            and unknown["estimated_minutes_max"] is None,
            f"unknown duration must not claim zero compute time: {unknown}")
    _assert("typical laptop" in one_hour["basis"],
            f"estimate needs an honest hardware qualifier: {one_hour}")


def test_captions_win_without_loading_asr(monkeypatch, tmp_path):
    entries = [(0.0, 2.0, "platform words")]

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("ASR must not run when captions exist")

    monkeypatch.setattr(reliability, "transcribe_media", _must_not_run,
                        raising=False)
    resolved, source, fallback = server._resolve_video_transcript(
        entries, tmp_path / "video.mp4", 120,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})

    _assert(resolved == entries, f"captions changed: {resolved}")
    _assert(source == "captions", f"wrong provenance: {source}")
    _assert(fallback["status"] == "not_needed", f"wrong status: {fallback}")


def test_opt_out_and_missing_model_do_not_transcribe(monkeypatch, tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    calls = []
    monkeypatch.setattr(
        reliability, "transcribe_media",
        lambda *_args, **_kwargs: calls.append(True) or [],
        raising=False,
    )

    entries, source, fallback = server._resolve_video_transcript(
        [], media, 3600,
        settings={"asr_fallback_enabled": False, "whisper_model": "tiny"})
    _assert(entries == [] and source is None,
            f"opt-out must leave the transcript empty: {entries}, {source}")
    _assert(fallback["status"] == "disabled", f"opt-out status: {fallback}")

    monkeypatch.setattr(
        server, "_reliability_model_status",
        lambda _model=None: {"model": "tiny", "cached": False},
    )
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 3600,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})
    _assert(entries == [] and source is None and not calls,
            "a missing model must never trigger an implicit download")
    _assert(fallback["status"] == "model_not_downloaded",
            f"missing-model status: {fallback}")
    _assert(fallback["estimated_minutes_min"] == 10.0
            and fallback["estimated_minutes_max"] == 15.0,
            f"skip metadata must retain the duration estimate: {fallback}")


def test_asr_failure_is_nonfatal_and_sanitized(monkeypatch, tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(
        server, "_reliability_model_status",
        lambda _model=None: {"model": "tiny", "cached": True},
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("decoder failed at C:\\Users\\Ryan\\secret.mp4")

    monkeypatch.setattr(reliability, "transcribe_media", _boom, raising=False)
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 30,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})

    _assert(entries == [] and source is None,
            "ASR failure must leave a valid caption-less capture")
    _assert(fallback["status"] == "failed", f"failure status: {fallback}")
    _assert("C:\\Users" not in fallback.get("error", ""),
            f"sidecar error leaked a local path: {fallback}")


def test_transcribe_media_uses_cached_model_only(tmp_path, monkeypatch):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    seen = {}

    class FakeModel:
        def transcribe(self, path, **kwargs):
            seen["path"] = path
            seen["transcribe_kwargs"] = kwargs
            return iter([
                {"start": 0.0, "end": 1.25, "text": " hello "},
                {"start": 1.25, "end": 2.5, "text": ""},
                types.SimpleNamespace(start=2.5, end=4.0, text="world"),
            ]), {"language": "en"}

    def _fake_load(model_name, model_root, *, local_files_only=False):
        seen["load"] = (model_name, Path(model_root), local_files_only)
        return FakeModel()

    monkeypatch.setattr(reliability, "_load_model", _fake_load)
    entries = reliability.transcribe_media(
        media, model_name="tiny", model_root=tmp_path / "models")

    _assert(seen["load"][2] is True,
            f"fallback model load must be cache-only: {seen['load']}")
    _assert(entries == [(0.0, 1.25, "hello"), (2.5, 4.0, "world")],
            f"segment normalization failed: {entries}")
    _assert(seen["transcribe_kwargs"]["beam_size"] == 1,
            f"CPU fallback should use bounded decoding: {seen}")


def test_explicit_model_download_writes_readiness_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(reliability, "_load_model",
                        lambda *_args, **_kwargs: object())
    result = reliability.ensure_model("tiny", tmp_path)
    marker = tmp_path / "tiny.pt"
    _assert(marker.is_file(),
            "successful explicit download must leave the marker server checks")
    _assert(result.get("ready_marker") == str(marker),
            f"download response must identify the marker: {result}")


def test_failed_model_download_never_writes_readiness_marker(
        tmp_path, monkeypatch):
    def _fail(*_args, **_kwargs):
        raise RuntimeError("download failed")

    monkeypatch.setattr(reliability, "_load_model", _fail)
    try:
        reliability.ensure_model("tiny", tmp_path)
        raise AssertionError("failed model load must propagate")
    except RuntimeError:
        pass
    _assert(not (tmp_path / "tiny.pt").exists(),
            "failed download must not leave a false ready marker")


def _fake_no_caption_subprocess(cmd, **_kwargs):
    """Mock yt-dlp + ffmpeg. It emits media and a screenshot, never an SRT."""
    parts = [str(part) for part in cmd]
    is_ffmpeg = parts and parts[0].endswith("ffmpeg")
    out = None
    if "-o" in parts:
        out = parts[parts.index("-o") + 1]
    elif is_ffmpeg:
        out = parts[-1]
    if is_ffmpeg and out:
        shot = Path(out.replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\xff\xd8\xff\xe0jpg")
    elif out:
        base_dir = Path(out).parent
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4")
    return types.SimpleNamespace(returncode=0, stdout="", stderr=b"")


def test_captionless_x_capture_persists_asr_and_provenance(
        monkeypatch, tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    idx = index_mod.Index.open(tmp_path / "index.db")
    calls = []
    try:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_run_subprocess",
                            _fake_no_caption_subprocess)
        monkeypatch.setattr(server, "_download_thumbnail",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(server, "_fetch_channel_context",
                            lambda *_args, **_kwargs: {})
        monkeypatch.setattr(server, "_start_comments_thread",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(server, "_start_entity_extraction_thread",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            server, "_read_settings",
            lambda: {
                "asr_fallback_enabled": True,
                "whisper_model": "tiny",
                "transcript_reliability_auto_check": False,
            },
        )
        monkeypatch.setattr(
            server, "_reliability_model_status",
            lambda _model=None: {"model": "tiny", "cached": True},
        )

        def _asr(media_path, **kwargs):
            calls.append((Path(media_path), kwargs))
            return [
                (0.0, 2.0, "x video words"),
                (2.0, 4.0, "now queryable locally"),
            ]

        monkeypatch.setattr(reliability, "transcribe_media", _asr,
                            raising=False)

        url = "https://x.com/replayryan/status/1812345678901234567"
        metadata = {
            "id": "1812345678901234567",
            "title": "Captionless X clip",
            "description": "an X video without platform captions",
            "uploader": "ReplayRyan",
            "duration": 60,
            "thumbnails": [],
            "webpage_url": url,
        }
        folder = root / "AI" / "captionless-x-clip"
        result = server._run_extraction(
            url, 30, folder, open_explorer=False, metadata=metadata,
            generate_paste=False)

        sidecar = json.loads(
            (folder / f"{folder.name}.json").read_text(encoding="utf-8"))
        _assert(result["ok"] is True and calls,
                f"X fallback did not run: result={result}, calls={calls}")
        _assert(sidecar.get("transcript_source") == "asr",
                f"sidecar provenance missing: {sidecar}")
        _assert(sidecar.get("asr_fallback", {}).get("status") == "completed",
                f"sidecar fallback status missing: {sidecar}")
        _assert(len(sidecar.get("transcript") or []) == 2,
                f"ASR segments not persisted: {sidecar.get('transcript')}")
        _assert("x video words" in (
            folder / "transcript.txt").read_text(encoding="utf-8"),
            "plain transcript did not use ASR output")
        _assert("x video words" in (
            folder / f"{folder.name}.md").read_text(encoding="utf-8"),
            "corpus markdown did not use ASR output")
        _assert(result.get("transcript_source") == "asr",
                f"caller response lacks provenance: {result}")
    finally:
        idx.close()


def test_dashboard_exposes_opt_out_and_compute_copy():
    html = (Path(__file__).resolve().parent.parent
            / "assets" / "dashboard" / "index.html").read_text(
                encoding="utf-8")
    for needle in (
        'id="asrFallbackEnabled"',
        "asr_fallback_enabled",
        "10–15 minutes per hour",
        "Runs locally",
        "captions are missing",
    ):
        _assert(needle in html, f"dashboard ASR disclosure missing: {needle}")
