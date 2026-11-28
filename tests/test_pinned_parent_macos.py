"""pinned_parent on macOS: /dev/fd is not traversable there, so the held
directory's real path is used after an identity check (F_GETPATH)."""
import os

import pytest

from uoink_core import storage

pytestmark = pytest.mark.skipif(storage._F_GETPATH is None, reason="macOS F_GETPATH only")


def test_yields_a_writable_path_for_the_held_folder(tmp_path):
    target = tmp_path / "client" / "mcp.json"
    with storage.pinned_parent(tmp_path, target, create=True) as directory:
        (directory / "mcp.json").write_text("{}")
        assert os.path.samestat(os.stat(directory), os.stat(target.parent))
    assert target.read_text() == "{}"


def test_refuses_when_the_folder_was_swapped(tmp_path, monkeypatch):
    target = tmp_path / "client" / "mcp.json"
    target.parent.mkdir()
    real_open = os.open

    def swap_then_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if os.fsdecode(path) == "client":
            # The held folder moves away and a new one takes its name.
            os.rename(tmp_path / "client", tmp_path / "moved")
            (tmp_path / "client").mkdir()
        return fd

    monkeypatch.setattr(storage.os, "open", swap_then_open)
    with pytest.raises(storage.LibraryPathError):
        with storage.pinned_parent(tmp_path, target):
            pass
    assert not (tmp_path / "client" / "mcp.json").exists()


def test_case_variant_spelling_is_the_same_folder(tmp_path):
    (tmp_path / "Client").mkdir()
    probe = tmp_path / "client"
    if not probe.exists():
        pytest.skip("case-sensitive volume")
    with storage.pinned_parent(tmp_path, probe / "mcp.json") as directory:
        (directory / "mcp.json").write_text("{}")
    assert (tmp_path / "Client" / "mcp.json").read_text() == "{}"
