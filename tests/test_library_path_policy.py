"""Library operations use the configured root and refuse redirected directories."""
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

import corpus_provider
import images
import notes
import page_extractor
import server
import shelf_router
import uoink_mcp_tools
from uoink_core.storage import _atomic_write_text


@pytest.fixture
def directories(tmp_path):
    root = tmp_path / "Library"
    root.mkdir()
    storage = tmp_path / "Other"
    storage.mkdir()
    def alias(name, target=None):
        destination = target or storage
        path = root / name
        if os.name == "nt":
            subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(path), str(destination)],
                           check=True, capture_output=True)
        else:
            path.symlink_to(destination, target_is_directory=True)
        return path
    return root, storage, alias


@pytest.mark.parametrize("operation", ["note", "image", "page", "shelf", "export", "session", "atomic"])
def test_writers_refuse_linked_directory(directories, monkeypatch, operation):
    root, other, alias = directories
    index = Mock()
    index.export_payload.return_value = {"tables": {}}
    if operation == "note":
        alias("Notes")
        write = lambda: notes.persist_note(index, notes.build_note("Sample note"), data_root=root)
    elif operation == "page":
        alias("Pages")
        result = {"ok": True, "url": "https://example.com/story", "markdown": "Sample story"}
        write = lambda: page_extractor.persist_page_yoink(index, result, data_root=root)
    elif operation == "image":
        alias("Images")
        data = b"\x89PNG\r\n\x1a\n" + bytes(32)
        write = lambda: images.persist_image(index, images.build_image(data), data, data_root=root)
    elif operation == "shelf":
        path = alias("Shelf") / "sample.md"
        (other / "sample.md").write_text("**Topic:** Before")
        write = lambda: shelf_router.sync_files(None, path, "After")
    elif operation == "session":
        monkeypatch.setattr(server, "SESSIONS_ROOT", alias("_sessions"))
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        write = lambda: server._write_session("sample", {"name": "Sample"})
    elif operation == "export":
        alias("_exports")
        monkeypatch.setattr(server, "_get_index", lambda: index)
        write = lambda: server.export_corpus_data(output_root=root)
    else:
        path = alias("Notes") / "sample.md"
        write = lambda: _atomic_write_text(path, "Sample")
    with pytest.raises(OSError):
        write()
    if operation == "shelf":
        assert (other / "sample.md").read_text() == "**Topic:** Before"
    else:
        assert list(other.iterdir()) == []


def test_attachment_resolver_refuses_redirected_item(directories):
    root, other, alias = directories
    folder = alias("sample")
    (other / "thumbnail.jpg").touch()
    provider = corpus_provider.UoinkCorpusProvider(Mock(), root)
    assert provider._safe_file(folder, "thumbnail.jpg") is None


def test_mcp_corpus_lookup_checks_index_path(directories, monkeypatch):
    root, other, alias = directories
    folder = alias("sample")
    (other / "sample.md").write_text("Sample text")
    backend = Mock(DESKTOP_ROOT=root)
    backend._get_index.return_value.get_by_slug.return_value = {"corpus_path": str(folder / "sample.md")}
    monkeypatch.setattr(uoink_mcp_tools, "_backend", backend)
    result = uoink_mcp_tools.get_uoink_corpus({"slug": "sample"})
    assert not result["ok"]


def test_open_markdown_refuses_linked_item(directories, monkeypatch):
    root, other, alias = directories
    target = root / "another"
    target.mkdir()
    folder = alias("sample", target)
    (target / "sample.md").write_text("Sample")
    index = Mock()
    index.get_yoink.return_value = {"corpus_path": str(folder / "sample.md")}
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    monkeypatch.setattr(server, "_get_index", lambda: index)
    path, error = server.Handler._yoink_markdown_path(None, "sample")
    assert path is None and error
