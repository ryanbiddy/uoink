"""Platform captions: YouTube escapes become text, and cues stay inside the video."""
from __future__ import annotations

from pathlib import Path

import yt_extract
import pytest

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


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("lines", [
    ["we will rock you", "we will rock you"],
    ["yes.", "yes.", "yes."],
    ["I have a dream", "I have a dream that one day"],
])
def test_contiguous_repetition_and_lyrics_keep_every_word_and_time(tmp_path, automatic, lines):
    path = _srt(tmp_path, [(f"00:00:0{i},000", f"00:00:0{i+1},000", line)
                           for i, line in enumerate(lines)])
    parsed = yt_extract.parse_srt(path, automatic=True) if automatic else yt_extract.parse_srt(path)
    assert list(parsed) == [
        (i, i + 1, line) for i, line in enumerate(lines)]


def test_overlapping_lyrics_and_anaphora_need_more_than_a_shared_opening(tmp_path):
    path = _srt(tmp_path, [
        ("00:00:00,000", "00:00:02,000", "sing it again"),
        ("00:00:01,990", "00:00:04,000", "sing it again"),
        ("00:00:03,990", "00:00:06,000", "I have a dream"),
        ("00:00:05,990", "00:00:07,000", "I have a dream that one day"),
    ])
    assert list(yt_extract.parse_srt(path, automatic=True)) == list(yt_extract.parse_srt(path))


def test_vtt_rollup_ghost_and_inline_timings_are_auto_only(tmp_path):
    path = tmp_path / "video.en.vtt"
    path.write_text("""WEBVTT
Kind: captions
Language: en

00:00:00.500 --> 00:00:02.000 align:start position:0%
blue<00:00:01.000><c> sky</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
blue sky

00:00:02.010 --> 00:00:04.000 align:start position:0%
blue sky
red<00:00:03.020><c> sun</c>

00:00:04.000 --> 00:00:06.000 align:start position:0%
red sun
gold leaf
""", encoding="utf-8")
    assert list(yt_extract.parse_srt(path, automatic=True)) == [
        (0.5, 2, "blue sky"), (2.01, 4, "red sun"), (4, 6, "gold leaf")]
    assert list(yt_extract.parse_srt(path)) == [
        (0.5, 2, "blue sky"), (2, 2.01, "blue sky"),
        (2.01, 4, "blue sky red sun"), (4, 6, "red sun gold leaf")]


def test_json3_replayed_window_preserves_separately_spoken_repeats(tmp_path):
    import json
    path = tmp_path / "video.en-orig.json3"
    path.write_text(json.dumps({"wireMagic": "pb3", "events": [
        {"tStartMs": 0, "wWinId": 1},
        {"tStartMs": 500, "dDurationMs": 2000, "segs": [
            {"utf8": "yes."}, {"utf8": " yes.", "tOffsetMs": 800}]},
        {"tStartMs": 1300, "dDurationMs": 1200, "segs": [
            {"utf8": "yes."}, {"utf8": " yes.", "tOffsetMs": 700}]},
        {"tStartMs": 2500, "aAppend": 1, "segs": [{"utf8": "\n"}]}
    ]}), encoding="utf-8")
    assert list(yt_extract.parse_srt(path, duration=2.3, automatic=True)) == [
        (.5, 1.3, "yes."), (1.3, 2, "yes."), (2, 2.3, "yes.")]


@pytest.mark.parametrize("interrupt_commit", [False, True])
def test_saved_caption_repair_republishes_once_and_preserves_edits(tmp_path, monkeypatch, interrupt_commit):
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
            "transcript_source": "captions", "caption_track_kind": "auto_captions", "yoinked_at": "2026-01-01T00:00:00Z",
            "duration_seconds": 9, "source_chapters": []}
    side["transcript"] = server._transcript_entries_with_links(side, [
        (0, 2, "the blue sky"), (1, 3, "blue sky blue sky red sun"), (2, 4, "red sun gold leaf")])
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
    for preview in (True, False):
        with pytest.raises(ValueError, match="edits were kept"):
            server.repair_rolling_captions(vid, preview=preview)
    assert capture.sidecar_path.read_bytes() == original
    plain.write_text("the blue sky\nblue sky blue sky red sun\nred sun gold leaf", encoding="utf-8")
    for key, value, reason in [("media_depth", None, "predates"), ("caption_track_kind", None, "identified as automatic"),
                               ("caption_track_kind", "captions", "identified as automatic")]:
        capture.sidecar_path.write_text(json.dumps(dict(json.loads(original), **{key: value})), encoding="utf-8")
        for preview in (True, False):
            with pytest.raises(ValueError, match=reason):
                server.repair_rolling_captions(vid, preview=preview)
    ambiguous = dict(json.loads(original), transcript=server._transcript_entries_with_links(
        side, [(i, i + 1, "yes.") for i in range(3)]))
    capture.sidecar_path.write_text(json.dumps(ambiguous), encoding="utf-8")
    for preview in (True, False):
        with pytest.raises(ValueError, match="no identifiable rolling"):
            server.repair_rolling_captions(vid, preview=preview)
    capture.sidecar_path.write_text(json.dumps(dict(json.loads(original), caption_windows_cleaned=True)), encoding="utf-8")
    for preview in (True, False):
        assert server.repair_rolling_captions(vid, preview=preview)["removed_words"] == 0
    capture.sidecar_path.write_bytes(original)
    preview = server.repair_rolling_captions(vid, preview=True)
    assert preview["removed_words"] == 4
    backup = Path(preview["original_sidecar"])
    assert not backup.exists() and capture.sidecar_path.read_bytes() == original
    import library_media as media
    import sqlite3
    publish = idx.publish_media_snapshot
    with monkeypatch.context() as racing:
        def change_track_kind(*args, **kwargs):
            capture.sidecar_path.write_text(json.dumps(dict(json.loads(original), caption_track_kind="captions")), encoding="utf-8")
            return publish(*args, **kwargs)
        racing.setattr(idx, "publish_media_snapshot", change_track_kind)
        with pytest.raises(ValueError, match="repair could not finish"):
            server.repair_rolling_captions(vid)
        assert not backup.exists()
    capture.sidecar_path.write_bytes(original)
    with monkeypatch.context() as racing:
        def edit_during_repair(*args, **kwargs):
            with capture.corpus_path.open("a", encoding="utf-8") as handle:
                handle.write("Another note.\n")
            return publish(*args, **kwargs)
        racing.setattr(idx, "publish_media_snapshot", edit_during_repair)
        with pytest.raises(ValueError, match="repair could not finish"):
            server.repair_rolling_captions(vid)
    assert capture.sidecar_path.read_bytes() == original
    if interrupt_commit:
        with monkeypatch.context() as interrupted:
            def stop_before_commit(*args):
                raise sqlite3.OperationalError("fixture interruption")
            interrupted.setattr(media, "_write_clips", stop_before_commit)
            with pytest.raises(ValueError, match="repair could not finish"):
                server.repair_rolling_captions(vid)
    else:
        assert server.repair_rolling_captions(vid) == {**preview, "preview": False}
    assert server.repair_rolling_captions(vid)["removed_words"] == 0
    assert backup.read_bytes() == original
    assert plain.read_text() == "the blue sky\nblue sky red sun\ngold leaf"
    assert len(json.loads(capture.sidecar_path.read_bytes())["transcript"]) == 3
    assert capture.corpus_path.read_text(encoding="utf-8").count("blue sky") == 2
    assert capture.corpus_path.read_text(encoding="utf-8").startswith("Personal note")
    assert capture.corpus_path.read_text(encoding="utf-8").endswith("A note added after saving.\nAnother note.\n")
    assert [c["text"] for c in idx.get_citations(vid) if c["kind"] == "transcript_chunk"] == [
        "the blue sky", "blue sky red sun", "gold leaf"]
    with idx.detached_snapshot() as conn:
        assert conn.execute("SELECT content FROM yoinks_fts WHERE video_id=?", (vid,)).fetchone()[0].count("blue sky") == 2
    idx.close()
