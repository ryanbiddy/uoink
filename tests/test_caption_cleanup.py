"""Platform captions: YouTube escapes become text, and cues stay inside the video."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import yt_extract


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


@pytest.mark.parametrize("lines", [
    ["we should go", "go right now"], ["oh we will rock you", "we will rock you"],
    ["yes.", "yes.", "yes."], ["clap\nwe will rock you", "we will rock you\nwe will rock you"],
    ["I have a dream", "I have a dream that one day", "I have a dream that one day this nation"],
    ["we call your name", "your name remains"], ["星月\n星光", "星光\n海洋"],
    ["שיר\n\u200fאותו שיר", "\u200fאותו שיר\nעוד שיר"],
])
@pytest.mark.parametrize("stored", [True, False])
def test_overlapping_spoken_lines_survive(lines, stored):
    entries = [(i, i + 1.01, line) for i, line in enumerate(lines)]
    assert list(yt_extract.caption_window_text(entries, automatic=True, stored=stored)) == [
        (i, line if stored or not line.isascii() else " ".join(line.splitlines())) for i, line in enumerate(lines)]


@pytest.mark.parametrize("duration", [0, .01])
def test_two_line_bridge_is_display_only(duration):
    entries = [(0, 2, "blue sky\nred sun"), (2, 2 + duration, "blue sky\nred sun")]
    assert list(yt_extract.caption_window_text(entries, automatic=True)) == [(0, "blue sky red sun")]


def test_bridge_can_repeat_just_the_last_display_line():
    entries = [(0, 2, "blue sky\nred sun"), (2, 2.01, "red sun"),
               (2.01, 4, "red sun\ngold leaf")]
    assert list(yt_extract.caption_window_text(entries, automatic=True)) == [
        (0, "blue sky red sun"), (2, "gold leaf")]


def test_new_word_clocks_keep_a_repeated_lyric_line():
    entries = [(0, 2, "look up\nblue<00:01.500> sky"),
               (2, 4, "blue<00:02.500> sky\nred<00:03.000> sun")]
    assert list(yt_extract.caption_window_text(entries, automatic=True)) == [
        (0, "look up blue sky"), (1, "blue sky red sun")]


@pytest.mark.parametrize("marker", ["NOTE", "NOTE comment", "STYLE", "REGION", "WEBVTT"])
def test_vtt_metadata_cannot_be_spoken(tmp_path, marker):
    path = tmp_path / "captions.vtt"
    path.write_text(f"{marker}\n00:01.000 --> 00:02.000\nhidden\n\n00:03.000 --> 00:04.000\nspoken")
    assert list(yt_extract.parse_srt(path)) == [(3, 4, "spoken")]


@pytest.mark.parametrize("text", ["星光\n月光", "\u200fأهلا  بكم\n\u200fأهلا  بكم", "encore une fois"])
def test_manual_multilingual_cues_keep_native_spacing(tmp_path, text):
    path = _srt(tmp_path, [("00:00:00,000", "00:00:01,200", text),
                           ("00:00:01,000", "00:00:02,000", text)])
    assert list(yt_extract.parse_srt(path)) == [(0, 1.2, text), (1, 2, text)]


def test_regional_manual_track_wins():
    meta = {"subtitles": {"en-CA": [1]}, "automatic_captions": {"en": [1]}}
    assert yt_extract.english_caption_track(meta, True) == {"key": "en-CA", "kind": "captions"}


@pytest.mark.parametrize("bad", ["not json", "[]", '{"events":null}', '{"events":[null]}',
    '{"events":[{"tStartMs":0,"segs":[{"utf8":"partial"},null]}]}',
    '{"events":[{"tStartMs":null,"segs":[{"utf8":"lost"}]}]}'])
def test_bad_json_uses_whole_alternate_track(tmp_path, bad):
    path = _srt(tmp_path, [("00:00:00,000", "00:00:02,000", "whole fallback")]).with_suffix(".json3")
    path.write_text(bad)
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(0, 2, "whole fallback")]


def test_bad_json_tries_srt_after_an_empty_vtt(tmp_path):
    path = _srt(tmp_path, [("00:00:00,000", "00:00:02,000", "whole fallback")]).with_suffix(".json3")
    path.write_text("null")
    path.with_suffix(".vtt").write_text("WEBVTT\n")
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(0, 2, "whole fallback")]


def test_json_keeps_explicit_rtl_word_separator_across_events(tmp_path):
    path = tmp_path / "words.json3"
    path.write_text(json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 500, "segs": [{"utf8": "שלום "}]},
        {"tStartMs": 500, "dDurationMs": 500, "segs": [{"utf8": "עולם"}]},
    ]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(0, 1, "שלום עולם")]


def test_json_append_missing_offset_and_native_spacing(tmp_path):
    path = tmp_path / "video.json3"
    path.write_text(json.dumps({"events": [
        {"tStartMs": 0, "segs": None},
        {"tStartMs": 100, "segs": [{"utf8":"one"}, {"utf8":" two", "tOffsetMs":200},
                                  {"utf8":"\\h[ __ ]"}]},
        {"tStartMs": 800, "aAppend":1, "segs":[{"utf8":"星"}, {"utf8":"光"}]},
        {"tStartMs": 1600, "segs":[{"utf8":"\n"}]},
    ]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [
        (.1, .8, "one two [__]"), (.8, 1.6, "星光")]


@pytest.mark.parametrize("lines", [
    ["oh we will rock you", "we will rock you", "we will rock you"],
    ["yes.", "yes.", "yes."],
    ["I have a dream", "I have a dream that one day", "I have a dream that one day this nation"],
    ["clap\nwe will rock you", "we will rock you\nwe will rock you"],
    ["星光", "星光"], ["\u200fنعم", "\u200fنعم"],
])
def test_json_spoken_repetition_survives_append_events(tmp_path, lines):
    path = tmp_path / "repeat.json3"
    path.write_text(json.dumps({"events": [
        {"aAppend":1, "tStartMs":1000*i, "dDurationMs":1010, "segs":[{"utf8":line}]}
        for i, line in enumerate(lines)]}))
    assert [text for _, _, text in yt_extract.parse_srt(path, automatic=True)] == [
        part for line in lines for part in line.splitlines()]


def test_json_one_shared_clock_keeps_ambiguous_speech(tmp_path):
    path = tmp_path / "track.json3"
    path.write_text(json.dumps({"events": [
        {"tStartMs":0, "dDurationMs":1200, "segs":[{"utf8":"a"}, {"utf8":" yes", "tOffsetMs":400}]},
        {"tStartMs":400, "dDurationMs":800, "segs":[{"utf8":"yes"}, {"utf8":" indeed", "tOffsetMs":200}]},
    ]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(0, 1.2, "a yes yes indeed")]


def test_json_one_word_and_punctuation_are_not_two_matching_words(tmp_path):
    path = _srt(tmp_path, [("00:00:00,000", "00:00:02,000", "yes! yes! again")]).with_suffix(".json3")
    word = [{"utf8": "yes"}, {"utf8": "!", "tOffsetMs": 100}]
    path.write_text(json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 1000, "segs": word},
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [*word, {"utf8": " again", "tOffsetMs": 500}]},
    ]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(0, 2, "yes! yes! again")]


def test_final_append_with_no_end_keeps_the_last_known_word_clock(tmp_path):
    path = tmp_path / "words.json3"
    path.write_text(json.dumps({"events":[{"tStartMs":1000, "aAppend":1,
        "segs":[{"utf8":"last"}, {"utf8":" words", "tOffsetMs":200}]}]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [(1, 1.2, "last words")]


def test_contiguous_slow_words_stay_together_and_empty_append_flushes(tmp_path):
    events = [{"tStartMs":start, "dDurationMs":1000, "segs":[{"utf8":word}]}
              for start, word in [(0, "slow"), (1000, "clear"), (2000, "words"),
                                  (3800, "new"), (4800, "line")]]
    events.insert(-1, {"tStartMs":4800, "aAppend":1, "segs":None})
    path = tmp_path / "track.json3"
    path.write_text(json.dumps({"events":events}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [
        (0, 3, "slow clear words"), (3.8, 4.8, "new"), (4.8, 5.8, "line")]


@pytest.mark.parametrize("automatic", [True, False])
def test_json_native_word_pieces_and_punctuation(tmp_path, automatic):
    path = tmp_path / "words.json3"
    path.write_text(json.dumps({"events":[{"tStartMs":0, "dDurationMs":700,
        "segs":[{"utf8":"Walk"}, {"utf8":"ing", "tOffsetMs":50}, {"utf8":" home", "tOffsetMs":300},
                {"utf8":"."}, {"utf8":" Again", "tOffsetMs":550}]}]}))
    expected = [(0, .55, "Walking home."), (.55, .7, "Again")] if automatic else [(0, .7, "Walking home. Again")]
    assert list(yt_extract.parse_srt(path, automatic=automatic)) == expected


def test_json_phrase_boundaries_and_final_flush(tmp_path):
    path = tmp_path / "track.json3"
    segs = [{"utf8":" word", "tOffsetMs":100*i} for i in range(13)]
    segs.extend([{"utf8":" after", "tOffsetMs":2400}, {"utf8":" pause.\nlast", "tOffsetMs":2600}])
    path.write_text(json.dumps({"events":[{"tStartMs":100, "dDurationMs":3000, "segs":segs}]}))
    assert list(yt_extract.parse_srt(path, automatic=True)) == [
        (.1, 1.3, " ".join(["word"]*12)), (1.3, 2.5, "word"),
        (2.5, 2.7, "after pause."), (2.7, 3.1, "last")]


def test_json3_replayed_window_preserves_separately_spoken_repeats(tmp_path):
    path = tmp_path / "video.en-orig.json3"
    path.write_text(json.dumps({"wireMagic": "pb3", "events": [
        {"tStartMs": 0, "wWinId": 1},
        {"tStartMs": 500, "dDurationMs": 2000, "segs": [
            {"utf8": "yes."}, {"utf8": " yes.", "tOffsetMs": 800}]},
        {"tStartMs": 500, "dDurationMs": 2000, "segs": [
            {"utf8": "yes."}, {"utf8": " yes.", "tOffsetMs": 800}, {"utf8": " yes.", "tOffsetMs": 1500}]},
        {"tStartMs": 2500, "aAppend": 1, "segs": [{"utf8": "\n"}]}
    ]}), encoding="utf-8")
    assert list(yt_extract.parse_srt(path, duration=2.3, automatic=True)) == [
        (.5, 1.3, "yes."), (1.3, 2, "yes."), (2, 2.3, "yes.")]


@pytest.fixture
def saved_caption_track(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import index
    import server
    from tests.phase4_fixtures import seed_yoink_item

    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        def publish(entries):
            vid = "talk0000001"
            item = seed_yoink_item(idx, tmp_path, video_id=vid, slug=vid, title="Daylight")
            side = {"video_id": vid, "url": "https://www.youtube.com/watch?v=" + vid,
                    "transcript_source": "captions", "yoinked_at": "2026-01-01T00:00:00Z",
                    "duration_seconds": 9, "source_chapters": []}
            side["transcript"] = server._transcript_entries_with_links(side, entries)
            capture = SimpleNamespace(folder=tmp_path, corpus_path=Path(item["corpus_path"]),
                                      sidecar_path=Path(item["sidecar_path"]), sidecar=side)
            section = server._capture_media_plan(side, tmp_path)["markdown"]
            capture.corpus_path.write_text("Personal note\n" + section, encoding="utf-8")
            capture.sidecar_path.write_text(json.dumps(side), encoding="utf-8")
            server._publish_capture_media(idx, tmp_path, side, capture.corpus_path, capture.sidecar_path)
            return capture
        yield idx, publish


_ROLLING = [(0, 2, "the blue sky"), (1, 3, "blue sky blue sky red sun"),
            (2, 4, "red sun gold leaf"), (3, 5, "gold leaf white cloud")]


@pytest.mark.parametrize("weak", [
    [(0, 2, "we should go"), (1.99, 4, "go right now")],
    _ROLLING[:3], _ROLLING + [(6, 9, "unrelated " * 100)],
], ids=["single-word-repeat", "too-few-shifts", "small-share"])
def test_weak_legacy_capture_refused_before_any_write(saved_caption_track, weak):
    import server
    _, publish = saved_caption_track
    capture = publish(weak)
    plain = capture.folder / "transcript.txt"
    plain.write_text("\n".join(text for _, _, text in weak), encoding="utf-8")
    originals = {p: p.read_bytes() for p in (plain, capture.corpus_path, capture.sidecar_path)}
    for preview in (True, False):
        with pytest.raises(ValueError, match="no identifiable rolling"):
            server.repair_rolling_captions(capture.sidecar["video_id"], preview=preview)
        assert all(p.read_bytes() == data for p, data in originals.items())
        assert not list(capture.folder.rglob("caption-original-*.json"))


@pytest.mark.parametrize("interrupt_commit", [False, True])
def test_saved_caption_repair_republishes_once_and_preserves_edits(saved_caption_track, monkeypatch, interrupt_commit):
    import server
    idx, publish_track = saved_caption_track
    capture = publish_track(_ROLLING)
    side = capture.sidecar
    vid = side["video_id"]
    plain = capture.folder / "transcript.txt"
    original = capture.sidecar_path.read_bytes()
    with capture.corpus_path.open("a", encoding="utf-8") as handle:
        handle.write("\nA note added after saving.\n")
    plain.write_text("My edit", encoding="utf-8")
    for preview in (True, False):
        with pytest.raises(ValueError, match="edits were kept"):
            server.repair_rolling_captions(vid, preview=preview)
    assert capture.sidecar_path.read_bytes() == original
    plain.write_text("the blue sky\nblue sky blue sky red sun\nred sun gold leaf\ngold leaf white cloud", encoding="utf-8")
    for key, value, reason in [("media_depth", None, "predates"),
                               ("caption_track_kind", "captions", "automatic or unlabelled")]:
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
    assert preview["removed_words"] == 6
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
            replace = media._atomic_replace
            def check_backup_first(path, data):
                if path in (capture.corpus_path, plain, capture.sidecar_path):
                    assert backup.read_bytes() == original
                return replace(path, data)
            interrupted.setattr(media, "_atomic_replace", check_backup_first)
            interrupted.setattr(media, "_write_clips", stop_before_commit)
            with pytest.raises(ValueError, match="repair could not finish"):
                server.repair_rolling_captions(vid)
        with monkeypatch.context() as settling:
            def stale(*args, **kwargs):
                raise media.MediaError("revision_unavailable")
            settling.setattr(idx, "begin_media_publication", stale)
            with pytest.raises(ValueError, match="repair could not finish"):
                server.repair_rolling_captions(vid)
    else:
        assert server.repair_rolling_captions(vid) == {**preview, "preview": False}
    assert server.repair_rolling_captions(vid)["removed_words"] == 0
    assert backup.read_bytes() == original
    assert plain.read_text() == "the blue sky\nblue sky red sun\ngold leaf\nwhite cloud"
    assert len(json.loads(capture.sidecar_path.read_bytes())["transcript"]) == 4
    assert capture.corpus_path.read_text(encoding="utf-8").count("blue sky") == 2
    assert capture.corpus_path.read_text(encoding="utf-8").startswith("Personal note")
    assert capture.corpus_path.read_text(encoding="utf-8").endswith("A note added after saving.\nAnother note.\n")
    assert [c["text"] for c in idx.get_citations(vid) if c["kind"] == "transcript_chunk"] == [
        "the blue sky", "blue sky red sun", "gold leaf", "white cloud"]
    with idx.detached_snapshot() as conn:
        assert conn.execute("SELECT content FROM yoinks_fts WHERE video_id=?", (vid,)).fetchone()[0].count("blue sky") == 2
