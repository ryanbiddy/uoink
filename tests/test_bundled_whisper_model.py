"""3.12 bundled Whisper model: lookup order, read-only loads, honest status.

Placeholder files and a fake WhisperModel only: no model, no network, no
Hugging Face cache. The real-weights load lives in
test_bundled_whisper_real.py and skips when no staged model exists.

Lookup for the selected size:
  1. the user's downloaded cache (ready marker + Hub snapshot) wins;
  2. else the bundled copy, when the selected size is the bundled size;
  3. else unavailable, as before 3.12.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import uoink_install_isolation
import uoink_reliability as rel
import whisper_runner

PLACEHOLDERS = {
    "config.json": b"{}",
    "model.bin": b"synthetic weights; never loaded",
    "tokenizer.json": b"{}",
    "vocabulary.txt": b"a\nb\n",
}


def stage_bundled(root: Path, model: str = "base", *, files=None, manifest_overrides=None) -> Path:
    """Write <root>/<model>/ the way scripts/stage_whisper_model.py does."""
    files = dict(PLACEHOLDERS if files is None else files)
    directory = root / model
    directory.mkdir(parents=True)
    for name, payload in files.items():
        (directory / name).write_bytes(payload)
    manifest = {
        "schema_version": 1, "model": model, "repo": rel._MODEL_REPOSITORIES[model],
        "revision": "e" * 40, "license": "MIT",
        "files": {name: {"size": len(payload), "sha256": "0" * 64} for name, payload in files.items()},
        **(manifest_overrides or {}),
    }
    (directory / rel.BUNDLED_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def seed_user_cache(root: Path, model: str = "base") -> Path:
    """A ready user download: Hub snapshot plus ensure_model's marker."""
    repo = root / ("models--" + rel._MODEL_REPOSITORIES[model].replace("/", "--"))
    snapshot = repo / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text("a" * 40, encoding="ascii")
    for name in rel._RELIABILITY_CACHE_FILES:
        (snapshot / name).write_bytes(b"synthetic placeholder")
    (root / f"{model}.pt").write_text("Uoink faster-whisper model ready\n", encoding="utf-8")
    return snapshot


def tree(root: Path) -> list[tuple[str, int, int]]:
    return sorted((p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in root.rglob("*"))


@pytest.fixture
def roots(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    bundled = tmp_path / "app" / "models" / "whisper-bundled"
    user = tmp_path / "profile" / "models" / "whisper"
    monkeypatch.setattr(rel, "bundled_model_root", lambda: bundled)
    return SimpleNamespace(bundled=bundled, user=user, tmp=tmp_path)


class FakeWhisperModel:
    calls: list = []

    def __init__(self, model_size_or_path, **kwargs):
        FakeWhisperModel.calls.append((model_size_or_path, kwargs))

    def transcribe(self, media, **kwargs):
        return [SimpleNamespace(start=0.0, end=1.5, text=" Hello from the bundle.")], None


@pytest.fixture
def fake_model(monkeypatch):
    FakeWhisperModel.calls = []
    monkeypatch.setattr(rel, "_import_faster_whisper", lambda: FakeWhisperModel)
    return FakeWhisperModel


# ---- lookup order -----------------------------------------------------------

def test_bundled_copy_is_used_when_the_selected_size_matches(roots):
    directory = stage_bundled(roots.bundled)
    assert rel.resolve_model("base", roots.user) == ("bundled", directory)
    status = rel.reliability_model_status("base", roots.user)
    assert status["cached"] is True and status["source"] == "bundled"
    assert status["downloaded"] is False
    assert status["bundled_model"] == "base" and status["bundled_revision"] == "e" * 40
    assert status["bundled_path"] == str(directory)
    assert status["model_root"] == str(roots.user)
    assert not roots.user.exists(), "status must not create the user cache"


def test_user_download_of_the_selected_size_wins(roots):
    stage_bundled(roots.bundled)
    seed_user_cache(roots.user)
    assert rel.resolve_model("base", roots.user) == ("downloaded", None)
    status = rel.reliability_model_status("base", roots.user)
    assert status["cached"] is True and status["source"] == "downloaded"
    assert status["downloaded"] is True and status["bundled_model"] == "base"


def test_size_mismatch_is_unavailable_as_before(roots):
    stage_bundled(roots.bundled)
    assert rel.resolve_model("small", roots.user) == (None, None)
    status = rel.reliability_model_status("small", roots.user)
    assert status["cached"] is False and status["source"] is None
    # The dashboard still learns which size ships, so it can say so.
    assert status["bundled_model"] == "base"
    assert status["estimated_download_mb"] == 490


def test_download_size_shows_only_when_the_bundle_is_not_running(roots):
    # The bundled copy is never downloaded, so it has no download size.
    stage_bundled(roots.bundled)
    assert rel.reliability_model_status("base", roots.user)["estimated_download_mb"] is None
    # Another size still names its download, and so does the user's own copy.
    assert rel.reliability_model_status("small", roots.user)["estimated_download_mb"] == 490
    seed_user_cache(roots.user)
    status = rel.reliability_model_status("base", roots.user)
    assert status["source"] == "downloaded" and status["estimated_download_mb"] == 150


def test_no_bundle_keeps_pre_312_behavior(roots):
    status = rel.reliability_model_status("base", roots.user)
    assert status["cached"] is False and status["source"] is None
    assert status["bundled_model"] is None and status["bundled_path"] is None
    assert status["estimated_download_mb"] == 150


@pytest.mark.parametrize("damage", ["missing_tokenizer", "short_model", "wrong_repo", "wrong_model",
                                    "branch_revision", "no_manifest", "path_name", "empty_file"])
def test_damaged_bundle_is_not_used(roots, damage):
    files = dict(PLACEHOLDERS)
    overrides = {}
    if damage == "missing_tokenizer":
        files.pop("tokenizer.json")
    elif damage == "wrong_repo":
        overrides["repo"] = "someone/else"
    elif damage == "wrong_model":
        overrides["model"] = "small"
    elif damage == "branch_revision":
        overrides["revision"] = "main"
    elif damage == "empty_file":
        files["config.json"] = b""
    directory = stage_bundled(roots.bundled, files=files, manifest_overrides=overrides)
    if damage == "short_model":
        (directory / "model.bin").write_bytes(b"truncated")
    elif damage == "no_manifest":
        (directory / rel.BUNDLED_MANIFEST).unlink()
    elif damage == "path_name":
        manifest = json.loads((directory / rel.BUNDLED_MANIFEST).read_text(encoding="utf-8"))
        manifest["files"]["../escape.bin"] = {"size": 1, "sha256": "0" * 64}
        (directory / rel.BUNDLED_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert rel.bundled_model_dir("base") is None
    assert rel.reliability_model_status("base", roots.user)["cached"] is False


# ---- loads: by directory, local-only, nothing written --------------------------

def test_bundled_load_passes_the_snapshot_directory_and_writes_nothing(roots, fake_model):
    directory = stage_bundled(roots.bundled)
    before = tree(roots.bundled)
    rel._load_model("base", roots.user)
    (target, kwargs), = fake_model.calls
    assert target == str(directory)
    assert kwargs["local_files_only"] is True
    assert "download_root" not in kwargs, "no download root may point at app data"
    assert tree(roots.bundled) == before
    assert not roots.user.exists()


def test_user_cache_load_keeps_name_and_download_root(roots, fake_model):
    stage_bundled(roots.bundled)
    seed_user_cache(roots.user)
    rel._load_model("base", roots.user)
    (target, kwargs), = fake_model.calls
    assert target == "base" and kwargs["download_root"] == str(roots.user)
    assert kwargs["local_files_only"] is True


def test_explicit_download_never_targets_the_bundle(roots, fake_model):
    stage_bundled(roots.bundled)
    before = tree(roots.bundled)
    result = rel.ensure_model("base", roots.user)
    (target, kwargs), = fake_model.calls
    assert target == "base" and kwargs["local_files_only"] is False
    assert kwargs["download_root"] == str(roots.user)
    assert Path(result["ready_marker"]).parent == roots.user
    assert tree(roots.bundled) == before


def test_transcribe_media_runs_on_the_bundled_copy(roots, fake_model):
    directory = stage_bundled(roots.bundled)
    media = roots.tmp / "clip.wav"
    media.write_bytes(b"RIFF placeholder")
    entries = rel.transcribe_media(media, model_name="base", model_root=roots.user)
    assert entries == [(0.0, 1.5, "Hello from the bundle.")]
    assert fake_model.calls[0][0] == str(directory)


# ---- where the bundle lives ------------------------------------------------------

def test_default_root_is_the_app_folder_beside_this_module(monkeypatch):
    monkeypatch.setattr(uoink_install_isolation, "current_binding", lambda: None)
    expected = Path(rel.__file__).resolve().parent / "models" / "whisper-bundled"
    assert rel.bundled_model_root() == expected


def test_isolated_install_uses_its_declared_app_folder(monkeypatch, tmp_path):
    binding = SimpleNamespace(app_dir=tmp_path / "isolated-app")
    monkeypatch.setattr(uoink_install_isolation, "current_binding", lambda: binding)
    assert rel.bundled_model_root() == tmp_path / "isolated-app" / "models" / "whisper-bundled"
    binding.app_dir = tmp_path / "Uoink.app"
    assert rel.bundled_model_root() == (
        tmp_path / "Uoink.app" / "Contents" / "Resources" / "models" / "whisper-bundled")


def test_bundled_model_matches_the_settings_default():
    import server
    pin = json.loads((Path(rel.__file__).parent / "scripts" / "whisper_model_pin.json").read_text())
    assert server._default_settings()["whisper_model"] == pin["model"] == "base"
    assert server.RELIABILITY_MODEL_NAME == rel.DEFAULT_MODEL == pin["model"]
    assert server._normalize_reliability_model("bogus") == pin["model"]


# ---- server: capture ASR and the status endpoint ---------------------------------

def test_server_status_reports_the_bundled_source(roots, monkeypatch):
    import server
    stage_bundled(roots.bundled)
    monkeypatch.setattr(server, "RELIABILITY_MODEL_ROOT", roots.user)
    status = server._reliability_model_status("base")
    assert status["cached"] is True and status["source"] == "bundled"
    assert server._reliability_model_status("small")["cached"] is False


def test_caption_less_capture_transcribes_with_the_bundle(roots, fake_model, monkeypatch):
    import server
    directory = stage_bundled(roots.bundled)
    monkeypatch.setattr(server, "RELIABILITY_MODEL_ROOT", roots.user)
    monkeypatch.setattr(server, "_media_has_audio", lambda *a, **k: True)
    media = roots.tmp / "capture" / "video.mp4"
    media.parent.mkdir()
    media.write_bytes(b"placeholder video")
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 90, settings={"asr_fallback_enabled": True, "whisper_model": "base"})
    assert source == "asr" and fallback["status"] == "completed"
    assert entries == [(0.0, 1.5, "Hello from the bundle.")]
    assert fake_model.calls[0][0] == str(directory)
    # A size the install does not ship still reports the missing model.
    _entries, source, fallback = server._resolve_video_transcript(
        [], media, 90, settings={"asr_fallback_enabled": True, "whisper_model": "small"})
    assert source is None and fallback["status"] == "model_not_downloaded"


# ---- podcast jobs (whisper_runner) share the bundle --------------------------------

def seed_runner_cache(data_root: Path, model: str = "base") -> Path:
    repo = whisper_runner._model_repo_root(data_root, model)
    snapshot = repo / "snapshots" / ("b" * 40)
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text("b" * 40, encoding="ascii")
    for name in whisper_runner._ASR_CACHE_FILES:
        (snapshot / name).write_bytes(b"synthetic placeholder")
    return snapshot


def test_podcast_jobs_use_the_bundle_without_download_consent(roots, monkeypatch):
    directory = stage_bundled(roots.bundled)
    data_root = roots.tmp / "data"
    data_root.mkdir()
    monkeypatch.setattr(whisper_runner, "_download_model_snapshot",
                        lambda *a: pytest.fail("bundled size must not download"))
    assert whisper_runner.is_model_downloaded(data_root, "base") is True
    assert whisper_runner._prepare_model_snapshot(data_root, "base", consent_given=False) == directory
    assert not (data_root / "whisper_models").exists()
    # Another size still needs consent.
    assert whisper_runner.is_model_downloaded(data_root, "small") is False
    with pytest.raises(PermissionError):
        whisper_runner._prepare_model_snapshot(data_root, "small", consent_given=False)


def test_podcast_user_download_wins_over_the_bundle(roots):
    stage_bundled(roots.bundled)
    data_root = roots.tmp / "data"
    data_root.mkdir()
    snapshot = seed_runner_cache(data_root)
    assert whisper_runner._prepare_model_snapshot(data_root, "base", consent_given=False) == snapshot
