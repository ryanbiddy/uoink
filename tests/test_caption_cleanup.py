"""Offline YouTube caption fixtures exercise dialogue, display windows and word clocks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import yt_extract

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "captions"
SPEECH = ("At first light we crossed reeds beside the mill. The upper wheel still turned slowly. "
          "Below the bridge small fish waited for the shade.")


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


@pytest.mark.parametrize("fmt", ["vtt", "json3"])
def test_rolling_talk_preserves_every_spoken_word_in_order(fmt):
    path = FIXTURES / f"rolling.en.{fmt}"
    if fmt == "json3":
        rows = yt_extract.parse_json3(path)
        assert len(rows) == 3
        assert [row[:2] for row in rows] == [(0, 3), (3, 5), (5, 8)]
        assert all(row[2].endswith(".") for row in rows)
    else:
        raw = list(yt_extract.parse_srt(path))
        assert sum(text.split().count("wheel") for _, _, text in raw) == 3
        rows = list(yt_extract.parse_srt(path, automatic=True))
        assert len(rows) == len(raw)
    assert " ".join(row[2] for row in rows).split() == SPEECH.split()


@pytest.mark.parametrize(("name", "auto", "expected"), [
    ("manual.en-CA.srt", False, ["We listened  first.\nBy the river.", "By the river.", "By the river."]),
    ("auto.ja.vtt", True, ["朝の川\n水面に光が差す", "水面に光が差す\n鳥が鳴く", "鳥が鳴く\n橋を渡る"]),
    ("manual.ar.srt", False, ["\u200fصوت الماء\nعند  الجسر", "عند  الجسر\n\u200fصوت الماء"]),
    ("manual.ar.srt", True, ["\u200fصوت الماء\nعند  الجسر", "عند  الجسر\n\u200fصوت الماء"]),
    ("chorus.en.vtt", True, ["Carry me home."] * 3),
    ("no.en.srt", True, ["no no", "no", "no"]),
])
def test_keep_repeated_speech_and_native_caption_bytes(name, auto, expected):
    rows = yt_extract.parse_srt(FIXTURES / name, automatic=auto)
    assert [text.encode("utf-8") for _, _, text in rows] == [t.encode("utf-8") for t in expected]


@pytest.mark.parametrize("lines", [
    ["yes."] * 3,
    ["I hear", "I hear the water", "I hear the water running", "I hear the water running again"],
    ["past the river", "the river past", "river past the", "past the river", "the river past"],
    ["we sing now", "now ! we sing", "we sing now", "now ! we sing"],
])
def test_substantial_display_time_overlap_alone_cannot_delete_speech(tmp_path, lines):
    path = _srt(tmp_path, [(f"00:00:0{i},000", f"00:00:0{i + 1},600", line)
                           for i, line in enumerate(lines)])
    assert [row[2] for row in yt_extract.parse_srt(path, automatic=True)] == lines


def test_space_only_display_row_metadata_and_numeric_dialogue(tmp_path):
    path = tmp_path / "edge.vtt"
    path.write_text("WEBVTT\n\nNOTE private\n00:01.000 --> 00:02.000\nIGNORE\n\n"
                    "STYLE\n00:01.000 --> 00:02.000\nIGNORE\n\n"
                    "REGION\n00:01.000 --> 00:02.000\nIGNORE\n\n"
                    "first\n00:00.000 --> 00:01.000\n \nfirst words\n\n"
                    "00:08.000 --> 00:09.000\n42\n\n"
                    "00:10.000 --> 00:11.000\n \nlast words\n", encoding="utf-8")
    assert [(s, e, t.strip()) for s, e, t in yt_extract.parse_srt(path, automatic=True)] == [
        (0, 1, "first words"), (8, 9, "42"), (10, 11, "last words")]


def _event(start, words, duration=1000, **fields):
    return {"tStartMs": start, "dDurationMs": duration, "segs": [
        {"utf8": word, "tOffsetMs": offset} for offset, word in words], **fields}


def _json_rows(tmp_path, events, **kwargs):
    path = tmp_path / "video.en.json3"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")
    return yt_extract.parse_json3(path, **kwargs)


@pytest.mark.parametrize("bad_event", [
    None, {}, {"segs": None}, {"segs": []},
    _event(1000, [(0, "\n")], aAppend=1),
    {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "last"}]},
    _event(1000, [(500, "late"), (100, " early")]),
    _event(1000, [(None, "unknown")]), _event(1000, [(False, "unknown")]),
    _event(1000, [(0, "later")], duration=None), _event(0, [(0, "conflicting word")]),
    _event(1000, [(0, "odd")], aAppend="yes"),
    _event(1000, [(0, "مرحبا"), (300, " بكم")]),
    _event(1000, [(0, "朝"), (300, "です")]),
])
def test_ambiguous_json3_rejects_whole_track_including_any_good_prefix(tmp_path, bad_event):
    assert _json_rows(tmp_path, [_event(0, [(0, "opening")]), bad_event]) == []


def test_json3_one_word_replay_fresh_chorus_and_event_separators(tmp_path):
    rows = _json_rows(tmp_path, [
        _event(0, [(0, "café")]),
        _event(0, [(0, "café"), (300, " lights.")]),
        _event(1000, [(0, "café"), (300, " lights.")]),
        _event(2000, [(0, "no"), (200, " no")]),
        _event(2400, [(0, "no"), (200, " no")]),
        _event(2700, [(0, "[Music]"), (200, " rises")]),
    ])
    assert [r[2] for r in rows] == ["café lights.", "café lights.", "no no no no [Music] rises"]
    assert rows[0].words == [{"word": "café", "start": 0, "end": .3},
                             {"word": "lights.", "start": .3, "end": 1}]


@pytest.mark.parametrize("lines", [["yes."] * 3, ["I hear", "I hear the river", "I hear it too"]])
def test_json3_distinct_clocks_preserve_real_repeats(tmp_path, lines):
    events = [_event(n * 1000, [(i * 150, (" " if i else "") + word)
                                for i, word in enumerate(line.split())])
              for n, line in enumerate(lines)]
    assert " ".join(r[2] for r in _json_rows(tmp_path, events)) == " ".join(lines)


def test_json3_groups_at_pause_append_line_break_and_budget(tmp_path):
    events = [
        _event(0, [(0, "a"), (200, " b"), (1100, " c")], duration=1500),
        _event(1500, [(0, "d"), (200, "\ne"), (400, " f\n")], aAppend=1),
        _event(2100, [(i * 150, " g") for i in range(13)], duration=2200),
    ]
    rows = _json_rows(tmp_path, events)
    assert [r[2] for r in rows] == ["a b", "c", "d", "e f", " ".join(["g"] * 12), "g"]
    assert rows[-1][1] == 4.3
    assert all(r[0] == r.words[0]["start"] and r[1] == r.words[-1]["end"] for r in rows)


def test_json3_clamps_word_times_together_with_text(tmp_path):
    rows = _json_rows(tmp_path, [_event(59000, [(0, "near"), (600, " end"),
                                                (1000, " past")], duration=2000)], duration=60)
    assert rows == [(59, 60, "near end")]
    assert rows[0].words[-1] == {"word": "end", "start": 59.6, "end": 60}


def test_contiguous_slow_words_share_a_cue_until_six_seconds(tmp_path):
    # Each event supplies its end. A one-second word and a one-second pause
    # look identical if we compare starts alone.
    rows = _json_rows(tmp_path, [_event(i * 1000, [(0, word)]) for i, word in enumerate(
        "One bell rang until the wheel stopped".split())] + [_event(7900, [(0, "again")])])
    assert rows == [(0, 6, "One bell rang until the wheel"), (6, 7, "stopped"), (7.9, 8.9, "again")]


def test_auto_rtl_json3_uses_the_same_tracks_native_text(tmp_path):
    events = [_event(0, [(0, "صوت"), (400, " الماء")]),
              _event(1000, [(0, "عند"), (400, " الجسر")])]
    requests = []

    def fetch(track, prefix, text_only):
        requests.append((track["kind"], track["key"], text_only))
        if text_only:
            (tmp_path / f"{prefix}.ar.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n\u200fصوت الماء\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nعند  الجسر\n", encoding="utf-8")
        else:
            (tmp_path / f"{prefix}.ar.json3").write_text(json.dumps({"events": events}), encoding="utf-8")

    track = {"kind": "auto_captions", "key": "ar"}
    rows, reason = yt_extract.read_caption_track(tmp_path, "video.auto", track, None, fetch)
    assert reason is None
    assert requests == [("auto_captions", "ar", False), ("auto_captions", "ar", True)]
    assert [r[2].encode() for r in rows] == ["\u200fصوت الماء".encode(), "عند  الجسر".encode()]


def test_srt_space_only_separators_split_cues_without_losing_dialogue(tmp_path):
    path = tmp_path / "captions.srt"
    path.write_text("1\n00:00:00,100 --> 00:00:01,000\n \n"
                    "2 < 7  and  9 > 6\n \t \n"
                    "2\n00:00:02,000 --> 00:00:03,000\n"
                    "42\ncontinued\n\t\n00:00:03,200 --> 00:00:04,000\nlast",
                    encoding="utf-8")
    assert list(yt_extract.parse_srt(path)) == [
        (.1, 1, " \n2 < 7  and  9 > 6"), (2, 3, "42\ncontinued"), (3.2, 4, "last")]


def test_timed_roll_keeps_whole_bridges_and_both_performances_of_a_lyric():
    rows = [(0, 1, "red<00:00.500> sky"),
            (1, 1.01, "red sky"),
            (1.01, 2, "red sky\nred<00:01.500> sky"),
            (2, 2.01, "red sky\nred sky"),
            (2.01, 3, "red sky\ncedar<00:02.500> shade"),
            (3, 3.01, "cedar shade"),
            (3.01, 4, "cedar shade\nfrost<00:03.500> lifted")]
    assert yt_extract.clean_caption_windows(rows) == [
        (0, 1, "red sky"), (1, 1.01, "red sky"), (1.01, 2, "red sky"),
        (2, 2.01, "red sky\nred sky"), (2.01, 3, "cedar shade"),
        (3, 3.01, "cedar shade"), (3.01, 4, "frost lifted")]


def test_new_clocks_on_both_display_lines_keep_repeated_speech():
    lines = ["bells ring", "frost lifted", "birds return", "ice melts", "day begins"]
    rows = []
    for i, (first, second) in enumerate(zip(lines, lines[1:])):
        # Both lines were sung in THIS interval. One fresh clock on the
        # would-be carried line rules out trimming even after three shifts.
        cue = (first.replace(" ", f"<00:0{i}.200> ")
               + "\n" + second.replace(" ", f"<00:0{i}.700> "))
        rows.append((i, i + 1.5, cue))
    assert [r[2] for r in yt_extract.clean_caption_windows(rows)] == [
        first + "\n" + second for first, second in zip(lines, lines[1:])]


def test_one_word_display_history_is_kept_across_a_whole_timed_run():
    rows = [(0, 1, "Hello<00:00.500>"), (1, 1.01, "Hello"),
            (1.01, 2, "Hello\ncome<00:01.500>"), (2, 3, "come\nback<00:02.500>"),
            (3, 4, "back\nsoon<00:03.500>")]
    assert [r[2] for r in yt_extract.clean_caption_windows(rows)] == [
        "Hello", "Hello", "Hello\ncome", "come\nback", "back\nsoon"]


@pytest.mark.parametrize("protected", ["\U0002000b", "\u2067", "\uff76"])
def test_mixed_track_with_ideographs_or_direction_controls_keeps_every_row(protected):
    rows = [(0, 3, "birds return home"), (1, 4, "return home from"),
            (2, 5, "home from warmer"), (3, 6, "from warmer climes"), (6, 7, protected)]
    assert yt_extract.clean_caption_windows(rows, stored=True) == rows


@pytest.mark.parametrize("lines", [
    ["listen to the river.", "the river. has a voice",
     "a voice can make music", "make music ring out loud"],
    ["the old bell was silent", "bell was silent over water",
     "silent over water all winter", "over water all winter long"],
    ["past the river", "the river past", "river past the", "past the river"],
])
def test_flat_spoken_echoes_retain_varying_window_widths_shifts_and_cycles(lines):
    rows = [(i, i + 2.5, text) for i, text in enumerate(lines)]
    assert yt_extract.clean_caption_windows(rows, stored=True) == rows


def test_vtt_keeps_explicit_word_clocks_on_freshly_retained_lines(tmp_path):
    path = tmp_path / "clocked.vtt"
    path.write_text("WEBVTT\n\n00:00.000 --> 00:03.000\n"
                    "High<00:01.100><c> tide.</c>\n\n"
                    "00:01.000 --> 00:04.000\nHigh tide.\n"
                    "<00:03.200>Red<00:03.700><c> sky.</c>\n\n"
                    "00:02.000 --> 00:05.000\nRed sky.\n"
                    "Night<00:04.500> falls.\n\n"
                    "00:03.000 --> 00:06.000\nNight falls.\n"
                    "<00:05.250>Stars<00:05.600> rise.\n", encoding="utf-8")
    rows = list(yt_extract.parse_srt(path, automatic=True))
    assert [row[:3] for row in rows] == [
        (0, 3, "High tide."), (1, 4, "Red sky."), (2, 5, "Night falls."), (3, 6, "Stars rise.")]
    assert rows[0].words == [{"word": "High", "start": 0, "end": 1.1},
                             {"word": "tide.", "start": 1.1, "end": 3}]
    assert rows[1].words == [{"word": "Red", "start": 3.2, "end": 3.7},
                             {"word": "sky.", "start": 3.7, "end": 4}]
    assert getattr(rows[2], "words", None) is None
    assert rows[3].words[0] == {"word": "Stars", "start": 5.25, "end": 5.6}
    assert all(getattr(row, "words", None) is None for row in yt_extract.parse_srt(path))


@pytest.mark.parametrize("raw", [
    "walk<00:00.200>ing<00:00.600> home",
    "two words<00:00.300> later",
    "<00:00.600>late<00:00.200> then",
    "<00:00.500>空<00:00.800> 海",
])
def test_vtt_ambiguous_or_protected_word_clocks_stay_unset(tmp_path, raw):
    path = tmp_path / "ambiguous.vtt"
    path.write_text(f"WEBVTT\n\n00:00.000 --> 00:01.000\n{raw}\n", encoding="utf-8")
    row, = yt_extract.parse_srt(path, automatic=True)
    assert row[0:2] == (0, 1)
    assert getattr(row, "words", None) is None
