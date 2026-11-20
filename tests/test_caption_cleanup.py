"""Platform captions: YouTube escapes become text, and cues stay inside the video."""
from __future__ import annotations

from pathlib import Path

import yt_extract
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _srt(tmp_path, cues):
    body = "\n\n".join(f"{i}\n{start} --> {end}\n{text}" for i, (start, end, text) in enumerate(cues, 1))
    path = tmp_path / "video.en.srt"
    path.write_text(body + "\n", encoding="utf-8")
    return path


def test_hard_spaces_and_the_censor_marker_become_readable(tmp_path):
    path = _srt(tmp_path, [
        ("00:00:01,000", "00:00:03,000", "what\\hthe [\\h__\\h] is that"),
        ("00:00:10,000", "00:00:12,000", "<c>so</c>\\h\\hgood"),
    ])
    assert [text for _, _, text in yt_extract.parse_srt(path)] == ["what the [__] is that", "so good"]


def test_cues_past_the_video_are_dropped_and_ends_clamped(tmp_path, caplog):
    # Verified on 0d2LAs-WL_4: a 4:03 video whose captions run to 6:47.
    path = _srt(tmp_path, [
        ("00:00:05,000", "00:00:08,000", "opening line"),
        ("00:04:01,000", "00:04:06,000", "last line runs over"),
        ("00:04:20,000", "00:04:25,000", "from a longer cut"),
        ("00:06:44,000", "00:06:47,000", "the end of that cut"),
    ])
    with caplog.at_level("INFO", logger="yt_extract"):
        entries = list(yt_extract.parse_srt(path, duration=243.0))
    assert entries == [(5.0, 8.0, "opening line"), (241.0, 243.0, "last line runs over")]
    assert "dropped 2 caption cue(s) past the 243s video" in caplog.text


def test_unknown_duration_keeps_every_cue(tmp_path):
    path = _srt(tmp_path, [("00:06:44,000", "00:06:47,000", "kept")])
    for duration in (None, 0, -1):
        assert list(yt_extract.parse_srt(path, duration=duration)) == [(404.0, 407.0, "kept")]


def test_the_helper_passes_the_video_duration():
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "entries = list(parse_srt(srt_files[0], duration=duration)) if srt_files else []" in source


# Input boundary after yt-dlp's --convert-subs srt. These cover the three
# rolling display shapes, independent of the source timed-text encoding.
@pytest.mark.parametrize("raw,wanted", [
    (["blue sky", "blue sky\nred sun", "red sun\ngold leaf"], ["blue sky", "red sun", "gold leaf"]),
    (["blue sky", "blue sky turns", "blue sky turns red"], ["blue sky", "turns", "red"]),
    (["blue sky", "blue sky", "blue sky"], ["blue sky"]),
])
def test_rolling_display_windows_keep_first_appearance(tmp_path, raw, wanted):
    path = _srt(tmp_path, [(f"00:00:0{i*3},000", f"00:00:0{i*3+3},000", line)
                           for i, line in enumerate(raw)])
    assert [(s, t) for s, _, t in yt_extract.parse_srt(path)] == list(zip(range(0, 9, 3), wanted))


def test_disjoint_repeated_words_are_speech():
    entries = [(0, 1, "we go"), (4, 5, "we go"), (6, 8, "go again")]
    assert yt_extract._dedupe_srt_entries(entries) == entries


def test_saved_caption_repair_republishes_once_and_preserves_edits(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import index
    import server
    from tests.phase4_fixtures import seed_yoink_item

    idx = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    vid = "talk0000001"
    item = seed_yoink_item(idx, tmp_path, video_id=vid, slug=vid, title="Daylight")
    side = {"video_id": vid, "url": "https://www.youtube.com/watch?v=" + vid,
            "transcript_source": "captions", "yoinked_at": "2026-01-01T00:00:00Z",
            "duration_seconds": 9, "source_chapters": []}
    side["transcript"] = server._transcript_entries_with_links(side, [(i, i+1, "blue sky") for i in range(3)])
    capture = SimpleNamespace(folder=tmp_path, corpus_path=Path(item["corpus_path"]),
                              sidecar_path=Path(item["sidecar_path"]), sidecar=side)
    section = server._capture_media_plan(side, tmp_path)["markdown"]
    capture.corpus_path.write_text("Personal note\n" + section, encoding="utf-8")
    capture.sidecar_path.write_text(json.dumps(capture.sidecar), encoding="utf-8")
    server._publish_capture_media(idx, tmp_path, side, capture.corpus_path, capture.sidecar_path)
    plain = capture.folder / "transcript.txt"
    original = capture.sidecar_path.read_bytes()
    with capture.corpus_path.open("a", encoding="utf-8") as handle:
        handle.write("\nA note added after saving.\n")
    plain.write_text("My edit", encoding="utf-8")
    assert server.repair_rolling_captions(vid, preview=True)["removed_words"] == 4
    with pytest.raises(ValueError, match="edits were kept"):
        server.repair_rolling_captions(vid)
    assert capture.sidecar_path.read_bytes() == original
    plain.write_text("blue sky\nblue sky\nblue sky", encoding="utf-8")
    import library_media as media
    import sqlite3
    publish = idx.publish_media_snapshot
    with monkeypatch.context() as racing:
        def edit_during_repair(*args, **kwargs):
            with capture.corpus_path.open("a", encoding="utf-8") as handle:
                handle.write("Another note.\n")
            return publish(*args, **kwargs)
        racing.setattr(idx, "publish_media_snapshot", edit_during_repair)
        with pytest.raises(ValueError, match="repair could not finish"):
            server.repair_rolling_captions(vid)
    assert capture.sidecar_path.read_bytes() == original
    with monkeypatch.context() as interrupted:
        def stop_before_commit(*args):
            raise sqlite3.OperationalError("fixture interruption")
        interrupted.setattr(media, "_write_clips", stop_before_commit)
        with pytest.raises(ValueError, match="repair could not finish"):
            server.repair_rolling_captions(vid)
    assert server.repair_rolling_captions(vid)["removed_words"] == 0
    assert plain.read_text() == "blue sky"
    assert len(json.loads(capture.sidecar_path.read_bytes())["transcript"]) == 1
    assert capture.corpus_path.read_text(encoding="utf-8").count("blue sky") == 1
    assert capture.corpus_path.read_text(encoding="utf-8").startswith("Personal note")
    assert capture.corpus_path.read_text(encoding="utf-8").endswith("A note added after saving.\nAnother note.\n")
    assert sum(c["kind"] == "transcript_chunk" for c in idx.get_citations(vid)) == 1
    with idx.detached_snapshot() as conn:
        assert conn.execute("SELECT content FROM yoinks_fts WHERE video_id=?", (vid,)).fetchone()[0].count("blue sky") == 1
    idx.close()
