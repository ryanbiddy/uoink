"""Launch regressions: dark frames, reader chronology, and copied Markdown."""
import json
import os
import re
import struct
import sys
from types import SimpleNamespace
import zlib

import pytest

import server
from tests.test_dashboard_theme_reader import run_js


def _png(path, rgb):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    pixels = (b"\0" + bytes(rgb) * 32) * 24
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 24, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


@pytest.fixture
def capture(tmp_path, monkeypatch):
    folder = tmp_path / "output" / "synthetic"
    shots = folder / "screenshots"
    shots.mkdir(parents=True)
    for name, rgb in (("dark.png", (7, 7, 7)), ("edge.png", (8, 8, 8)),
                      ("bright.png", (0, 128, 0)), ("shot_0006.jpg", (0, 0, 0))):
        _png(shots / name, rgb)
    (shots / "unknown.png").write_bytes(b"unreadable image")
    sidecar = folder / "synthetic.json"
    data = {"interval_seconds": 30, "screenshots": [
        {"filename": name, "path": "screenshots/" + name, "timestamp": f"0:{i * 10:02d}"}
        for i, name in enumerate(("dark.png", "edge.png", "bright.png", "unknown.png"))
    ]}
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    row = {"video_id": "synthetic", "title": "Synthetic capture",
           "corpus_path": str(folder / "synthetic.md"), "sidecar_path": str(sidecar)}
    idx = SimpleNamespace(get_yoink=lambda video_id: row if video_id == "synthetic" else None)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "output")
    monkeypatch.setattr(server, "_allowed_roots", lambda: [tmp_path / "output"])
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = lambda status, payload: (status, payload)
    return folder, sidecar, data, idx, handler


def test_reader_and_generate_skip_dark_frames_but_keep_unknowns(capture):
    folder, sidecar, data, idx, handler = capture
    status, details = handler._handle_yoink_details("/yoinks/synthetic/details")
    assert status == 200
    assert [shot["filename"] for shot in details["details"]["screenshots"]] == [
        "edge.png", "bright.png", "unknown.png"]
    for dedupe in ("false", "true"):
        handler.path = f"/yoinks/synthetic/screenshots?dedupe={dedupe}"
        status, picker = handler._handle_yoink_screenshots("/yoinks/synthetic/screenshots")
        assert status == 200
        assert "dark.png" not in [shot["filename"] for shot in picker["screenshots"]]
        assert "shot_0006.jpg" not in [shot["filename"] for shot in picker["screenshots"]]
        assert "unknown.png" in [shot["filename"] for shot in picker["screenshots"]]
    assert json.loads(sidecar.read_text(encoding="utf-8")) == data
    assert (folder / "screenshots" / "dark.png").exists()


def test_suggestions_and_image_routes_keep_original_ids_after_filtering(capture):
    folder, _, _, idx, handler = capture
    payload = server._screenshot_list_for_yoink(idx, "synthetic")
    assert [shot["index"] for shot in payload["screenshots"]] == [1, 2, 3]
    handler.path = "/yoinks/synthetic/screenshots/suggest?mode=blog"
    status, suggested = handler._handle_yoink_screenshots_suggest("/yoinks/synthetic/screenshots/suggest")
    assert status == 200 and suggested["total_available"] == 3
    assert [shot["index"] for shot in suggested["selected"]] == [1, 2, 3]
    handler._send_file = lambda path, mime: (path, mime)
    assert handler._handle_yoink_screenshot_file("/yoinks/synthetic/screenshots/1.png") == (
        folder / "screenshots" / "edge.png", "image/png")
    assert handler._handle_yoink_screenshot_file("/yoinks/synthetic/screenshots/0.png")[0] == 404


def test_luma_is_cached_across_reader_and_picker_and_refreshes_changed_files(capture):
    folder, _, _, idx, handler = capture
    server._screenshot_mean_luma.cache_clear()
    handler._handle_yoink_details("/yoinks/synthetic/details")
    first = server._screenshot_mean_luma.cache_info()
    server._screenshot_list_for_yoink(idx, "synthetic")
    second = server._screenshot_mean_luma.cache_info()
    assert second.hits >= first.hits + 4
    assert second.misses == first.misses + 1  # disk-only frame
    dark = folder / "screenshots" / "dark.png"
    old = dark.stat()
    _png(dark, (200, 200, 200))
    os.utime(dark, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000_000))
    payload = server._screenshot_list_for_yoink(idx, "synthetic")
    assert payload["screenshots"][0]["filename"] == "dark.png"


def test_missing_pillow_keeps_frames(capture, monkeypatch):
    _, _, _, idx, handler = capture
    server._screenshot_mean_luma.cache_clear()
    monkeypatch.setitem(sys.modules, "PIL", None)
    try:
        assert server._screenshot_list_for_yoink(idx, "synthetic")["count"] == 5
        status, data = handler._handle_yoink_details("/yoinks/synthetic/details")
        assert status == 200 and len(data["details"]["screenshots"]) == 4
    finally:
        server._screenshot_mean_luma.cache_clear()


def test_reader_luma_never_reads_paths_outside_the_capture(capture, monkeypatch):
    folder, sidecar, data, _, handler = capture
    outside = folder.parent / "outside.png"
    _png(outside, (0, 0, 0))
    data["screenshots"] = [{"absolute_path": str(outside)}, {"path": "../outside.png"}]
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    reads = []
    monkeypatch.setattr(server, "_screenshot_mean_luma", lambda *args: reads.append(args) or 0)
    status, result = handler._handle_yoink_details("/yoinks/synthetic/details")
    assert status == 200 and len(result["details"]["screenshots"]) == 2
    assert reads == []


@pytest.mark.parametrize("rgb, dark", [((0, 0, 50), True), ((50, 0, 0), False)])
def test_frame_filter_uses_luma_instead_of_rgb_average(tmp_path, rgb, dark):
    path = tmp_path / "color.png"
    _png(path, rgb)
    assert server._screenshot_is_near_black(path, tmp_path) is dark


def test_reader_merges_frames_and_paragraphs_chronologically():
    html = run_js(r'''readerTranscriptHtml({source_type: "video", folder: "/synthetic"}, {
      transcript: [
        {start: 40, text: "Later."}, {start: 2, end: 5, text: "Intro."},
        {start: 6, end: 8, text: "After frame."}, {text: "Untimed."},
      ],
      screenshots: [
        {timestamp_seconds: 30, path: "thirty.png"},
        {timestamp_seconds: 0, path: "zero.png"},
        {timestamp_seconds: 3, path: "three.png"}, {path: "loose.png"},
      ],
    })''')
    order = ['alt="Screenshot at 0:00"', "Intro.", 'alt="Screenshot at 0:03"',
             "After frame.", 'alt="Screenshot at 0:30"', "Later.", "Untimed.", 'alt="Screenshot"']
    positions = [html.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert html.count('class="reader-row reader-para"') == 4
    assert "time not stored" in html


def test_equal_times_keep_text_then_frame_before_the_next_cue():
    html = run_js(r'''readerTranscriptHtml({source_type: "video", folder: "/synthetic"}, {
      transcript: [{start: 0, end: 2, text: "Opening."}, {start: 2, text: "Next cue."}],
      screenshots: [{timestamp_seconds: 0, path: "zero.png"}],
    })''')
    assert html.index("Opening.") < html.index('alt="Screenshot at 0:00"') < html.index("Next cue.")


MARKDOWN = """# Synthetic capture

**URL:** https://example.com/video

## Thumbnail

![Thumbnail](thumbnail.jpg)

## Description

Long description before the useful words.

## Tags

No tags

---

## Transcript

[00:00:02] These are the useful words.

---

## Screenshots

![Screenshot at 00:00:30](screenshots/shot_0002.jpg)
"""


@pytest.mark.parametrize("folder, prefix", [
    ("C:\\Synthetic saves\\clip #1", "file:///C:/Synthetic%20saves/clip%20%231/"),
    ("/Users/synthetic/Saved clips/clip #1", "file:///Users/synthetic/Saved%20clips/clip%20%231/"),
    ("", ""),
])
def test_copy_markdown_is_portable_and_puts_transcript_first(folder, prefix):
    result = run_js("""(async () => {
      state.selectedYoink = {video_id: "synthetic", source_type: "video", folder: %s};
      state.selectedYoinkMarkdown = %s;
      const copied = [];
      navigator.clipboard.writeText = async (text) => copied.push(text);
      await copySelectedMarkdown();
      return {copied: copied[0], saved: state.selectedYoinkMarkdown};
    })()""" % (json.dumps(folder), json.dumps(MARKDOWN)))
    copied = result["copied"]
    assert "![Thumbnail](thumbnail.jpg)" not in copied
    assert "No tags" not in copied and "## Tags" not in copied
    assert copied.index("## Transcript") < copied.index("## Description")
    assert "**URL:** https://example.com/video" in copied
    assert "[00:00:02] These are the useful words." in copied
    assert result["saved"] == MARKDOWN
    if prefix:
        assert f"![Thumbnail]({prefix}thumbnail.jpg)" in copied
        assert f"({prefix}screenshots/shot_0002.jpg)" in copied
    else:
        assert not re.search(r"!\[[^]]*\]\((?:thumbnail|screenshots/)", copied)


def test_copy_preserves_real_tags_and_literal_note_text():
    markdown = MARKDOWN.replace("No tags", "space, engineering")
    result = run_js("""(async () => {
      const copied = [];
      navigator.clipboard.writeText = async (text) => copied.push(text);
      state.selectedYoinkMarkdown = %s;
      state.selectedYoink = {video_id: "synthetic", source_type: "video"};
      await copySelectedMarkdown();
      state.selectedYoink = {video_id: "note", source_type: "note"};
      state.selectedYoinkMarkdown = %s;
      await copySelectedMarkdown();
      return copied;
    })()""" % (json.dumps(markdown), json.dumps(MARKDOWN)))
    assert "## Tags\n\nspace, engineering" in result[0]
    assert result[1] == MARKDOWN


def test_copy_keeps_section_breaks_when_transcript_ends_the_file():
    markdown = "# Saved\n\n## Description\n\nContext.\n\n## Transcript\n\nLast words."
    copied = run_js("readerClipboardMarkdown(%s, {source_type: 'video'})" % json.dumps(markdown))
    assert "## Transcript\n\nLast words.\n\n## Description" in copied


def test_copy_uses_the_original_item_when_loading_markdown():
    copied = run_js("""(async () => {
      state.selectedYoink = {video_id: "first", source_type: "video", folder: "/synthetic/first"};
      state.selectedYoinkMarkdown = "";
      let finish;
      loadYoinkMarkdown = () => new Promise((resolve) => { finish = resolve; });
      let copied;
      navigator.clipboard.writeText = async (text) => { copied = text; };
      const pending = copySelectedMarkdown();
      state.selectedYoink = {video_id: "second", source_type: "video", folder: "/synthetic/second"};
      finish(%s);
      await pending;
      return copied;
    })()""" % json.dumps(MARKDOWN))
    assert "file:///synthetic/first/thumbnail.jpg" in copied
    assert "synthetic/second" not in copied
