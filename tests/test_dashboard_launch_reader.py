"""Launch regressions: dark frames, reader chronology, and copied Markdown."""
import builtins
import json
import os
from pathlib import Path
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
    assert second.hits >= first.hits + 3
    assert second.misses == first.misses + 2  # unreadable and disk-only frames
    dark = folder / "screenshots" / "dark.png"
    old = dark.stat()
    _png(dark, (200, 200, 200))
    os.utime(dark, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000_000))
    payload = server._screenshot_list_for_yoink(idx, "synthetic")
    assert payload["screenshots"][0]["filename"] == "dark.png"


def test_missing_pillow_is_reported_and_retried(capture, monkeypatch, caplog):
    folder, _, _, idx, handler = capture
    server._screenshot_mean_luma.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, "PIL", None)
            assert server._screenshot_list_for_yoink(idx, "synthetic")["count"] == 5
            status, data = handler._handle_yoink_details("/yoinks/synthetic/details")
            assert status == 200 and len(data["details"]["screenshots"]) == 4
        assert "Pillow" in caplog.text and "dark screenshots" in caplog.text
        assert server._screenshot_is_near_black(folder / "screenshots" / "dark.png", folder)
    finally:
        server._screenshot_mean_luma.cache_clear()


def test_luma_retries_a_transient_read_failure_without_a_file_change(capture, monkeypatch):
    folder, _, _, _, _ = capture
    path = folder / "screenshots" / "dark.png"
    original_open = builtins.open
    reads = []

    def flaky_open(file, *args, **kwargs):
        if Path(file) == path:
            reads.append(file)
            if len(reads) == 1:
                raise PermissionError("synthetic sharing violation")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    assert not server._screenshot_is_near_black(path, folder)
    assert server._screenshot_is_near_black(path, folder)
    assert len(reads) == 2


@pytest.mark.parametrize("aliased", ["frame", "folder"])
def test_luma_compares_resolved_capture_and_frame_paths(capture, monkeypatch, aliased):
    folder, _, _, _, _ = capture
    alias = folder.parent / "alias"
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        # Model /tmp -> /private/tmp on every test platform.
        if path.is_relative_to(alias):
            path = folder / path.relative_to(alias)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    path = (alias if aliased == "frame" else folder) / "screenshots" / "dark.png"
    assert server._screenshot_is_near_black(path, alias if aliased == "folder" else folder)


@pytest.mark.parametrize("relative, absolute", [
    ("path", "absolute_path"), ("path", "file_path"),
    ("filename", "absolute_path"), ("filename", "file_path"), ("filename", "path"),
])
def test_reader_prefers_current_capture_paths_over_stale_absolute_paths(capture, relative, absolute):
    folder, sidecar, data, idx, handler = capture
    data["screenshots"] = [{
        absolute: str(folder.parent / "old-location" / "dark.png"),
        relative: "screenshots/dark.png" if relative == "path" else "dark.png",
    }]
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    status, details = handler._handle_yoink_details("/yoinks/synthetic/details")
    assert status == 200 and details["details"]["screenshots"] == []
    assert server._screenshot_list_for_yoink(idx, "synthetic")["count"] == 0
    assert json.loads(sidecar.read_text(encoding="utf-8")) == data


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


@pytest.mark.parametrize("start", [0, 30, 60])
def test_equal_time_frames_precede_a_whole_paragraph(start):
    result = run_js(r'''(() => {
      const start = %s;
      const sidecar = {
        transcript: [
          ...(start ? [{start: start - 2, end: start, text: "Before frame."}] : []),
          {start, end: start + 2, text: "Opening."},
          {start: start + 2, text: "Next cue."},
        ],
        screenshots: [{timestamp_seconds: start, path: "frame.png"}],
      };
      return {html: readerTranscriptHtml({source_type: "video", folder: "/synthetic"}, sidecar),
        paragraphs: readerParagraphs(sidecar)};
    })()''' % start)
    assert result["paragraphs"][-1]["parts"] == ["Opening.", "Next cue."]
    html = result["html"]
    assert html.index('alt="Screenshot at ') < html.index("Opening. Next cue.")
    if start:
        assert html.index("Before frame.") < html.index('alt="Screenshot at ')


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
    assert "No tags" not in copied and "## Tags" not in copied
    assert copied.index("## Transcript") < copied.index("## Description")
    assert "**URL:** https://example.com/video" in copied
    assert "[00:00:02] These are the useful words." in copied
    assert result["saved"] == MARKDOWN
    if prefix:
        assert f"![Thumbnail]({prefix}thumbnail.jpg)" in copied
        assert f"({prefix}screenshots/shot_0002.jpg)" in copied
    else:
        assert "![Thumbnail](thumbnail.jpg)" in copied
        assert "![Screenshot at 00:00:30](screenshots/shot_0002.jpg)" in copied


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


@pytest.mark.parametrize("footer", ["", "\n\n---\n\n## Screenshots\n\n![Frame](frame.png)\n"])
def test_copy_moves_the_whole_transcript_including_headings_and_code(footer):
    transcript = ("## Transcript\n\nOpening words.\n\n## Another idea\n\nMore words.\n\n"
                  "## Tags\n\nNo tags\n\n```markdown\n---\n\n## Screenshots\n```\n\n"
                  "## Final idea\n\nClosing words.")
    markdown = "# Saved\n\n## Description\n\nContext.\n\n" + transcript + footer
    copied = run_js("readerClipboardMarkdown(%s, {source_type: 'video'})" % json.dumps(markdown))
    assert transcript in copied
    assert copied.index("Closing words.") < copied.index("## Description")
    if footer:
        assert copied.index("## Description") < copied.rindex("## Screenshots")


@pytest.mark.parametrize("source_type", ["page", "image", "x_thread", "reddit_thread"])
def test_copy_cleans_images_and_empty_tags_on_non_timed_captures(source_type):
    row = {"source_type": source_type, "folder": "/synthetic"}
    copied = run_js("readerClipboardMarkdown(%s, %s)" % (json.dumps(MARKDOWN), json.dumps(row)))
    assert "![Thumbnail](file:///synthetic/thumbnail.jpg)" in copied
    assert "No tags" not in copied and "## Tags" not in copied
    assert copied.index("## Description") < copied.index("## Transcript")


@pytest.mark.parametrize("folder, target, expected", [
    ("/synthetic/clip", "./screenshots/first%20frame.png", "file:///synthetic/clip/screenshots/first%20frame.png"),
    ("C:\\Saved clips\\clip", "./screenshots/../first%20frame.png", "file:///C:/Saved%20clips/clip/first%20frame.png"),
    ("/synthetic/100%20literal", "./shot%20%231.png", "file:///synthetic/100%2520literal/shot%20%231.png"),
    ("", "/synthetic/./shot%20one.png", "file:///synthetic/shot%20one.png"),
    ("", "C:/Saved%20clips/./shot.png", "file:///C:/Saved%20clips/shot.png"),
    ("\\\\server\\share\\Saved clips", "./shot%20one.png", "file://server/share/Saved%20clips/shot%20one.png"),
    ("/synthetic", "./100%done.png", "file:///synthetic/100%25done.png"),
])
def test_copy_normalizes_encoded_image_paths(folder, target, expected):
    markdown = f"![Frame]({target})"
    row = {"source_type": "video", "folder": folder}
    copied = run_js("readerClipboardMarkdown(%s, %s)" % (json.dumps(markdown), json.dumps(row)))
    assert copied == f"![Frame]({expected})"


def test_copy_uses_sidecar_data_that_arrives_while_loading_markdown():
    copied = run_js("""(async () => {
      state.selectedYoink = {video_id: "synthetic", source_type: "x_thread", folder: "/synthetic"};
      state.selectedYoinkMarkdown = "";
      state.selectedYoinkSidecar = null;
      loadYoinkMarkdown = async () => {
        state.selectedYoinkSidecar = {transcript_source: "captions"};
        return %s;
      };
      let copied;
      navigator.clipboard.writeText = async (text) => { copied = text; };
      await copySelectedMarkdown();
      return copied;
    })()""" % json.dumps(MARKDOWN))
    assert copied.index("## Transcript") < copied.index("## Description")


def test_copy_uses_the_original_item_when_loading_markdown():
    copied = run_js("""(async () => {
      state.selectedYoink = {video_id: "first", source_type: "x_thread", folder: "/synthetic/first"};
      state.selectedYoinkMarkdown = "";
      state.selectedYoinkSidecar = {transcript_source: "captions"};
      let finish;
      loadYoinkMarkdown = () => new Promise((resolve) => { finish = resolve; });
      let copied;
      navigator.clipboard.writeText = async (text) => { copied = text; };
      const pending = copySelectedMarkdown();
      state.selectedYoink = {video_id: "second", source_type: "video", folder: "/synthetic/second"};
      state.selectedYoinkSidecar = {source_type: "note"};
      finish(%s);
      await pending;
      return copied;
    })()""" % json.dumps(MARKDOWN))
    assert "file:///synthetic/first/thumbnail.jpg" in copied
    assert "synthetic/second" not in copied
    assert copied.index("## Transcript") < copied.index("## Description")
