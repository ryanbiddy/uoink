"""Offline regressions for the saved yt-dlp metadata cache."""
from __future__ import annotations

import copy
import json
import subprocess
from unittest.mock import Mock

import pytest

from test_caption_429_decouple import URL, extraction, server  # noqa: F401


BULKY_KEYS = {"formats", "requested_formats", "automatic_captions", "subtitles"}


@pytest.fixture
def metadata_capture(extraction):
    large_url = "https://example.invalid/" + "x" * 2_600_000
    extraction.metadata.update({
        "title": "Metadata café", "webpage_url": URL, "original_url": URL,
        "description": "A description worth keeping.", "uploader": "Example",
        "upload_date": "20261015", "view_count": 100, "like_count": 5,
        "tags": ["test"], "categories": ["Education"],
        "thumbnail": "https://example.invalid/thumbnail.jpg",
        "chapters": [{"start_time": 0, "end_time": 60, "title": "Opening"}],
        "comments": [{"text": "Existing comment", "like_count": 1}],
        "requested_subtitles": {"en": {"ext": "srt"}},
        "extra": {"formats": ["nested data stays"], "subtitles": None},
        "formats": [{"format_id": "18", "url": large_url}],
        "requested_formats": [{"format_id": "18", "url": large_url}],
        "automatic_captions": {"en": [{"ext": "vtt", "url": large_url}]},
        "subtitles": {"en": [{"ext": "srt", "url": large_url}]},
    })
    return extraction


@pytest.mark.parametrize("mode", ["full", "chunked", "lite"])
def test_metadata_cache_strips_only_bulky_tables(metadata_capture, mode):
    original = copy.deepcopy(metadata_capture.metadata)

    result = metadata_capture.run(mode)

    assert result["ok"] is True
    cache = metadata_capture.folder / "metadata.json"
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved == {key: value for key, value in original.items() if key not in BULKY_KEYS}
    assert len(json.dumps(original).encode("utf-8")) > 10_000_000
    assert cache.stat().st_size < 10_000
    assert metadata_capture.metadata == original
    if mode == "lite":
        metadata_capture.comments.assert_not_called()
    else:
        metadata_capture.comments.assert_called_once()
        assert metadata_capture.comments.call_args.args[3] is metadata_capture.metadata


@pytest.mark.parametrize("tables", [{}, {
    "formats": [], "requested_formats": None, "automatic_captions": {}, "subtitles": {},
}], ids=["absent", "empty"])
def test_metadata_cache_handles_missing_or_empty_tables(extraction, tables):
    extraction.metadata.update(tables)
    original = copy.deepcopy(extraction.metadata)

    assert extraction.run()["ok"] is True

    saved = json.loads((extraction.folder / "metadata.json").read_text(encoding="utf-8"))
    assert saved == {key: value for key, value in original.items() if key not in BULKY_KEYS}
    assert extraction.metadata == original


def test_comments_still_fetch_with_slim_metadata_cache(metadata_capture, monkeypatch):
    metadata_capture.run()
    folder = metadata_capture.folder
    yoink_path = folder / f"{folder.name}.md"
    comments = [{"author": "Example", "text": "Fetched comment", "like_count": 3}]

    def fetch_comments(cmd, **kwargs):
        assert "--write-comments" in cmd
        assert cmd[-1] == URL
        saved = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        assert BULKY_KEYS.isdisjoint(saved)
        (folder / "abcdef12345_yoink_comments.info.json").write_text(
            json.dumps({"comments": comments}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    run = Mock(side_effect=fetch_comments)
    monkeypatch.setattr(server, "_run_subprocess", run)
    for name in ("_update_sidecar_comments", "_start_hook_type_thread",
                 "_start_comment_intelligence_thread"):
        monkeypatch.setattr(server, name, Mock())

    server._comments_worker(URL, folder, yoink_path, metadata_capture.metadata, [])

    run.assert_called_once()
    assert "Fetched comment" in yoink_path.read_text(encoding="utf-8")
    server._update_sidecar_comments.assert_called_once()
    assert server._update_sidecar_comments.call_args.args[2] == "fetched"
    server._start_hook_type_thread.assert_called_once()
    assert server._start_hook_type_thread.call_args.args[2] is metadata_capture.metadata
