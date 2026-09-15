"""AW-4 ownership and packaging counterexamples, using disposable fixtures."""
import hashlib
from pathlib import Path
import subprocess
import uuid

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env, export, item_file


def test_aw4_missing_binding_does_not_readopt_an_empty_replacement_vault(env):
    export(env)
    binding = env.mirror._dest_binding_path()
    assert binding.is_file()
    binding.unlink()
    old_vault = env.root / "prior-vault"
    assert env.vault.resolve().is_relative_to(env.root.resolve())
    assert old_vault.resolve().is_relative_to(env.root.resolve())
    env.vault.rename(old_vault)
    env.vault.mkdir()
    result = env.mirror.resync()
    assert not result["ok"], "Missing prior binding granted initialization of a replacement vault"
    assert not item_file(env).exists()


def test_aw4_failed_atomic_binding_write_preserves_previous_binding(env, monkeypatch):
    export(env)
    binding = env.mirror._dest_binding_path()
    before = binding.read_bytes()
    original = env.mirror._atomic_local

    def fail_binding(path, data):
        if Path(path) == binding:
            raise OSError("injected atomic binding persistence failure")
        return original(path, data)

    monkeypatch.setattr(env.mirror, "_atomic_local", fail_binding)
    with pytest.raises(OSError):
        env.mirror._write_dest_binding(str(env.root / "different-destination"), "different-volume", True)
    assert binding.read_bytes() == before, "A direct write changed binding bytes before atomic persistence failed"


def test_aw4_temp_cleanup_preserves_same_content_replacement_file(env):
    export(env)
    uoink = env.vault / mirror.MIRROR_ROOT
    allocated = uoink / "Library" / "recorded-allocation.tmp"
    allocated.write_bytes(b"content is not file identity")
    digest = hashlib.sha256(allocated.read_bytes()).hexdigest()
    env.mirror._start_vault_io(str(env.vault))
    try:
        env.mirror._record_allocated_temp(mirror.item_key("a"), str(allocated.relative_to(uoink)), digest)
        original_file_id = allocated.stat().st_ino
        moved = allocated.with_name("original-allocation-retained.tmp")
        assert allocated.resolve().is_relative_to(env.root.resolve())
        assert moved.resolve().is_relative_to(env.root.resolve())
        allocated.rename(moved)
        allocated.write_bytes(moved.read_bytes())
        assert allocated.stat().st_ino != original_file_id
        env.mirror._cleanup_owned_temps(uoink, {}, {})
        assert allocated.is_file(), "Recorded content hash authorized deletion of another file at the same path"
        assert allocated.read_bytes() == b"content is not file identity"
    finally:
        env.mirror._stop_vault_io()


def test_aw4_source_stage_contains_the_isolated_vault_writer():
    root = Path(mirror.__file__).resolve().parent
    stage = root / "_scratch" / ("aw4-stage-" + uuid.uuid4().hex[:10])
    assert stage.resolve().is_relative_to(root)
    assert not stage.exists()
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(root / "build.ps1"),
         "-StageSourceOnly", "-SourceStagePath", str(stage)],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    worker = stage / "library_mirror_vault_io.py"
    assert worker.is_file(), "Source/installer staging omits the new required vault writer"
    assert worker.read_bytes() == (root / "library_mirror_vault_io.py").read_bytes()
