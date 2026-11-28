"""Verify the held directory descriptor and entry identity check on macOS."""
import os
import sys

import pytest

from uoink_core import storage

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


def _write_config(dir_fd):
    fd = os.open("mcp.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(b"{}")


def test_yields_a_writable_path_for_the_held_folder(tmp_path):
    target = tmp_path / "client" / "mcp.json"
    with storage.pinned_parent(tmp_path, target, create=True) as (directory, dir_fd):
        _write_config(dir_fd)
        assert os.path.samestat(os.stat(directory), os.stat(target.parent))
        assert os.path.samestat(os.fstat(dir_fd), os.stat(target.parent))
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
    with storage.pinned_parent(tmp_path, probe / "mcp.json") as (_, dir_fd):
        _write_config(dir_fd)
    assert (tmp_path / "Client" / "mcp.json").read_text() == "{}"
