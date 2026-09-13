"""Independent review regressions; temporary cache bytes and existing inert UI VM."""
from pathlib import Path
from unittest.mock import patch

import uoink_reliability as rel
from test_reliability_settings_ui import _run


def test_redirected_root_with_complete_physical_cache_is_unready(tmp_path):
    physical = tmp_path / "physical"
    alias = tmp_path / "alias"
    repo = physical / "models--Systran--faster-whisper-tiny"
    revision = "a" * 40
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text(revision, encoding="ascii")
    (physical / "tiny.pt").write_text("consent marker", encoding="ascii")
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (snapshot / name).write_bytes(b"synthetic placeholder; never loaded")

    # Positive control: the physical destination is complete. An alias must
    # remain rejected even when resolving it would find a ready cache.
    assert rel.is_model_ready("tiny", physical)
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == alias:
            return physical
        return original_resolve(path, *args, **kwargs)

    with patch.object(Path, "resolve", resolve):
        assert not rel.is_model_ready("tiny", alias)


def test_unknown_unsaved_model_does_not_borrow_saved_model_size():
    result = _run({
        "action": "status",
        "selected": "mystery",
        "relModel": {"model": "tiny", "cached": False,
                     "estimated_download_mb": 80},
    })["result"]
    assert "size unknown" in result
    assert "80 MB" not in result
