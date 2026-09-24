"""Reliability readiness is consent plus a bounded Hub snapshot.

Uses temporary placeholder files only. Does not import server, whisper_runner,
or a model package. Run: python tests/test_reliability_model_readiness.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uoink_reliability as rel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _seed_snapshot(root: Path, model="tiny", *, missing=(), empty=(),
                   revision=None, repo_id=None):
    revision = revision or ("a" * 40)
    repo_id = repo_id or rel._MODEL_REPOSITORIES[model]
    repo = Path(root) / ("models--" + repo_id.replace("/", "--"))
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    (repo / "refs").mkdir(exist_ok=True)
    (repo / "refs" / "main").write_text(revision, encoding="ascii")
    for name in rel._RELIABILITY_CACHE_FILES:
        if name in missing:
            continue
        payload = b"" if name in empty else b"synthetic placeholder; never loaded"
        (snapshot / name).write_bytes(payload)
    return snapshot


def _seed_marker(root: Path, model="tiny") -> Path:
    marker = Path(root) / f"{model}.pt"
    marker.write_text("Uoink faster-whisper model ready\n", encoding="utf-8")
    return marker


def _seed_ready(root: Path, model="tiny"):
    _seed_snapshot(root, model)
    _seed_marker(root, model)


def test_readiness_does_not_create_a_cache():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "models"
        _assert(not rel.is_model_ready("tiny", root), "missing cache must be unready")
        _assert(not root.exists(), "readiness must not create the download root")
    print("ok  readiness is read-only")


def test_marker_alone_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _seed_marker(root)
        status = rel.reliability_model_status("tiny", root)
        _assert(status["cached"] is False, f"marker-only must be unready: {status}")
        _assert(rel.estimated_download_mb("tiny") == 80, status)
    print("ok  consent marker alone is not a ready model")


def test_snapshot_alone_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _seed_snapshot(root)
        _assert(not rel.is_model_ready("tiny", root),
                "snapshot without consent marker must be unready")
    print("ok  snapshot without marker is unready")


def test_complete_marker_and_snapshot_is_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _seed_ready(root)
        status = rel.reliability_model_status("tiny", root)
        _assert(status["cached"] is True, status)
        _assert(status["model"] == "tiny", status)
        _assert(status["estimated_download_mb"] == 80, status)
    print("ok  marker plus complete snapshot is ready")


def test_each_missing_required_file_is_unready():
    for name in rel._RELIABILITY_CACHE_FILES:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _seed_marker(root)
            _seed_snapshot(root, missing=(name,))
            _assert(not rel.is_model_ready("tiny", root),
                    f"missing {name} must be unready")
    print("ok  each required snapshot file is required")


def test_empty_tokenizer_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _seed_marker(root)
        _seed_snapshot(root, empty=("tokenizer.json",))
        _assert(not rel.is_model_ready("tiny", root),
                "empty tokenizer.json must be unready")
    print("ok  empty tokenizer is unready")


def test_wrong_repository_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _seed_marker(root, "tiny")
        _seed_snapshot(root, "tiny", repo_id="Systran/faster-whisper-base")
        _assert(not rel.is_model_ready("tiny", root),
                "files under another repository must not ready tiny")
    print("ok  wrong repository is unready")


def test_unknown_or_path_shaped_reference_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        snapshot = _seed_snapshot(root)
        _seed_marker(root)
        reference = snapshot.parent.parent / "refs" / "main"
        for text in ("../outside", "a" * 39, "g" * 40, "a" * 100):
            reference.write_text(text, encoding="ascii")
            _assert(not rel.is_model_ready("tiny", root),
                    f"bad ref {text!r} must be unready")
    print("ok  bad refs stay unready")


def test_resolved_blob_inside_repo_is_allowed_but_outside_file_is_not():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        snapshot = _seed_snapshot(root)
        _seed_marker(root)
        repo = snapshot.parent.parent
        blob = repo / "blobs" / "synthetic-tokenizer"
        blob.parent.mkdir()
        blob.write_bytes(b"synthetic blob")
        outside = Path(raw) / "outside-tokenizer.json"
        outside.write_bytes(b"synthetic outside")
        actual_resolve = Path.resolve
        resolved_target = blob

        def resolve(path, *args, **kwargs):
            if path == snapshot / "tokenizer.json":
                return resolved_target
            return actual_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            _assert(rel.is_model_ready("tiny", root),
                    "internal Hub blob links must remain ready")
            resolved_target = outside
            _assert(not rel.is_model_ready("tiny", root),
                    "outside links must stay unready")
    print("ok  internal Hub links allowed; outside links refused")


def test_redirected_root_is_not_ready():
    with tempfile.TemporaryDirectory() as raw:
        root = (Path(raw) / "models").resolve()
        root.mkdir()
        _seed_ready(root)
        actual_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            current = path if isinstance(path, Path) else Path(path)
            if current == root or current.absolute() == root:
                return Path(raw).resolve() / "elsewhere"
            return actual_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            _assert(not rel.is_model_ready("tiny", root),
                    "redirected cache root must be unready")
    print("ok  redirected root is unready")


def test_all_six_models_have_sizes_and_can_be_ready():
    expected = {
        "tiny": 80,
        "base": 150,
        "small": 490,
        "medium": 1540,
        "large": 3100,
        "large-v3-turbo": 1630,
    }
    _assert(set(rel._MODEL_REPOSITORIES) == set(expected),
            rel._MODEL_REPOSITORIES)
    _assert(rel._MODEL_REPOSITORIES["large-v3-turbo"]
            == "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
            "production turbo mapping must not switch providers")
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for model, size in expected.items():
            _seed_ready(root, model)
            status = rel.reliability_model_status(model, root)
            _assert(status["cached"] is True, f"{model} should be ready: {status}")
            _assert(status["estimated_download_mb"] == size,
                    f"{model} size: {status}")
    _assert(rel.estimated_download_mb("not-a-model") is None,
            "unknown choices must not borrow 150 MB")
    print("ok  six models have per-choice sizes and independent readiness")


def test_server_status_delegates_without_marker_only_or_fixed_size():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    start = src.index("def _reliability_model_status")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    _assert("uoink_reliability.reliability_model_status" in body,
            "server status must use the structural helper")
    _assert(".pt" not in body, "server must not treat the marker as the cache")
    _assert("150" not in body, "server must not hardcode 150 MB")
    print("ok  server status delegates to structural readiness")


def main() -> int:
    test_readiness_does_not_create_a_cache()
    test_marker_alone_is_not_ready()
    test_snapshot_alone_is_not_ready()
    test_complete_marker_and_snapshot_is_ready()
    test_each_missing_required_file_is_unready()
    test_empty_tokenizer_is_not_ready()
    test_wrong_repository_is_not_ready()
    test_unknown_or_path_shaped_reference_is_not_ready()
    test_resolved_blob_inside_repo_is_allowed_but_outside_file_is_not()
    test_redirected_root_is_not_ready()
    test_all_six_models_have_sizes_and_can_be_ready()
    test_server_status_delegates_without_marker_only_or_fixed_size()
    print("\nall green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
