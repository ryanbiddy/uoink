"""Transcript quality (3.18): loop filter, word timings, English-only guard.

Fake segments and fake models only; nothing loads or runs a real model.
Run through safe.sh.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uoink_reliability as rel  # noqa: E402


def seg(start, end, text, *, words=None, ratio=1.2, no_speech=0.05):
    return SimpleNamespace(start=start, end=end, text=text, words=words,
                           compression_ratio=ratio, no_speech_prob=no_speech)


def word(text, start, end, p=0.9):
    return SimpleNamespace(word=text, start=start, end=end, probability=p)


class FakeModel:
    def __init__(self, name, *, language="en", probability=0.97, segments=None):
        self.name, self.language, self.probability = name, language, probability
        self.segments = segments or [seg(0.0, 2.0, f"spoken words from {name}")]
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        info = SimpleNamespace(language=kwargs.get("language") or self.language,
                               language_probability=self.probability, duration=10.0)
        return iter(self.segments), info


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "clip.wav"
    path.write_bytes(b"not audio; never decoded")
    return path


def models(monkeypatch, **by_name):
    monkeypatch.setattr(rel, "_language_samples", lambda *_: [b"fake decoded window"], raising=False)
    loads = []

    def load(name, root, *, local_files_only=True):
        assert local_files_only is True
        loads.append(name)
        return by_name[name]

    monkeypatch.setattr(rel, "_load_model", load)
    return loads


# ---- loop filter -----------------------------------------------------------
def test_repetition_without_acoustic_evidence_is_preserved():
    rows = [(0.0, 9.0, "Thank you. " * 5)] + [(i, i + 1, "Yeah.") for i in range(10, 15)]
    assert rel.drop_repetition_loops(rows) == rows


def test_repetitive_text_over_likely_silence_is_dropped():
    rows = rel.drop_repetition_loops(
        [(0.0, 30.0, "Thank you for watching. " * 8), (30.0, 32.0, "Welcome back.")],
        [(3.1, 0.8), (1.1, 0.02)])
    assert rows == [(30.0, 32.0, "Welcome back.")]


def test_normal_speech_passes_unchanged():
    lines = [(0.0, 2.0, "We tried three times."), (2.0, 4.0, "It worked on the third.")]
    assert rel.drop_repetition_loops(lines, [(1.3, 0.01), (1.2, 0.02)]) == lines


def test_transcribe_media_applies_the_filter_and_decode_options(monkeypatch, media):
    looping = FakeModel("base", segments=[
        seg(0.0, 2.0, "Intro music."), seg(2.0, 4.0, "Thanks for watching."),
        seg(4.0, 6.0, "Thanks for watching."), seg(6.0, 8.0, "Thanks for watching."),
        seg(8.0, 30.0, "Thanks for watching. " * 6, ratio=3.0, no_speech=0.9)])
    models(monkeypatch, base=looping)
    rows = rel.transcribe_media(media, model_name="base")
    assert [text for _s, _e, text in rows] == [
        "Intro music.", "Thanks for watching.", "Thanks for watching.", "Thanks for watching.",
        ("Thanks for watching. " * 6).strip()]
    assert [r.held_reason for r in rows] == [None, None, None, None, "repetition"]
    options = looping.calls[0]
    assert options["vad_filter"] is True
    assert options["condition_on_previous_text"] is False
    assert options["compression_ratio_threshold"] == 2.4
    assert options["no_speech_threshold"] == 0.6
    assert options["log_prob_threshold"] == -1.0
    assert options["word_timestamps"] is True


# ---- word timings ----------------------------------------------------------
def test_word_timings_are_kept_on_entries(monkeypatch, media):
    model = FakeModel("base", segments=[
        seg(0.0, 1.2, " Hello there.", words=[word(" Hello", 0.0, 0.5, 0.91), word(" there.", 0.5, 1.2, 0.88)]),
        seg(1.2, 2.0, " Plain line.")])
    models(monkeypatch, base=model)
    rows = rel.transcribe_media(media, model_name="base")
    assert rows[0] == (0.0, 1.2, "Hello there.")
    assert rows[0].words == [{"word": "Hello", "start": 0.0, "end": 0.5},
                             {"word": "there.", "start": 0.5, "end": 1.2}]
    assert getattr(rows[1], "words", None) is None
    # They survive the trip between processes.
    back = rel.entry_from_json(rel.entry_to_json(rows[0]))
    assert back == rows[0] and back.words == rows[0].words


def test_video_sidecar_rows_carry_words_only_when_present():
    import server
    words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
    rows = server._transcript_entries_with_links(
        {"url": "https://example.com/watch/abc", "source_url": "https://example.com/watch/abc"},
        [rel.TranscriptEntry(0.0, 1.2, "Hello there.", words), (1.2, 2.0, "Plain line.")])
    assert rows[0]["words"] == words
    assert "words" not in rows[1]
    assert rows[1]["text"] == "Plain line."


def test_podcast_transcripts_keep_words_and_old_ones_still_read():
    import json
    import podcasts
    new = json.dumps({"segments": [
        {"start": 0.0, "end": 1.0, "text": "Hi.", "words": [
            {"word": "Hi.", "start": 0.0, "end": 0.4}, {"word": "", "start": 0.4, "end": 0.5},
            {"word": "bad", "start": "x", "end": 1}, "junk"]},
        {"start": 1.0, "end": 2.0, "text": "No words here."}]}).encode()
    _raw, shaped = podcasts._transcript_from_bytes(new)
    assert shaped[0]["words"] == [{"word": "Hi.", "start": 0.0, "end": 0.4}]
    assert "words" not in shaped[1]
    old = json.dumps({"segments": [{"start": 0.0, "end": 1.0, "text": "Old item."}]}).encode()
    _raw, shaped = podcasts._transcript_from_bytes(old)
    assert shaped == [{"start": 0.0, "end": 1.0, "text": "Old item."}]


def test_stored_word_timings_cost_under_half_a_megabyte_per_hour():
    import json
    # 150 words a minute for an hour, in the stored shape.
    words = [{"word": "example", "start": round(i * 0.4, 2), "end": round(i * 0.4 + 0.3, 2)}
             for i in range(9000)]
    size = len(json.dumps(words, ensure_ascii=False).encode("utf-8"))
    assert size < 500_000, size


# ---- English-only models ---------------------------------------------------
def test_english_audio_runs_the_english_model(monkeypatch, media):
    checker, english = FakeModel("base", language="en", probability=0.96), FakeModel("distil-small.en")
    loads = models(monkeypatch, **{"base": checker, "distil-small.en": english})
    info = {}
    rows = rel.transcribe_media(media, model_name="distil-small.en", info=info)
    assert loads == ["base", "distil-small.en"]
    assert english.calls[0]["language"] == "en"
    assert rows[0][2] == "spoken words from distil-small.en"
    assert "english_fallback" not in info


def test_non_english_audio_falls_back_to_the_multilingual_model(monkeypatch, media):
    checker = FakeModel("base", language="es", probability=0.97,
                        segments=[seg(0.0, 2.0, "Hola a todos.")])
    english = FakeModel("distil-large-v3.5")
    loads = models(monkeypatch, **{"base": checker, "distil-large-v3.5": english})
    info = {}
    rows = rel.transcribe_media(media, model_name="distil-large-v3.5", info=info)
    assert loads == ["base", "base"]
    assert english.calls == []          # the English-only model never ran
    assert checker.calls[-1]["language"] == "es"
    assert rows == [(0.0, 2.0, "Hola a todos.")]
    assert info["model"] == "base"
    assert info["english_fallback"] == {
        "requested_model": "distil-large-v3.5", "used_model": "base",
        "detected_language": "es", "language_probability": 0.97}


def test_unsure_english_falls_back_and_lets_whisper_pick(monkeypatch, media):
    checker = FakeModel("base", language="en", probability=0.31)
    models(monkeypatch, **{"base": checker, "distil-small.en": FakeModel("distil-small.en")})
    info = {}
    rel.transcribe_media(media, model_name="distil-small.en", info=info)
    assert info["english_fallback"]["used_model"] == "base"
    assert "language" not in checker.calls[-1]


def test_a_named_language_skips_detection(monkeypatch, media):
    base, english = FakeModel("base"), FakeModel("distil-small.en")
    loads = models(monkeypatch, **{"base": base, "distil-small.en": english})
    info = {}
    rel.transcribe_media(media, model_name="distil-small.en", language="fr", info=info)
    assert loads == ["base"] and base.calls[0]["language"] == "fr"
    assert info["english_fallback"]["detected_language"] == "fr"
    loads.clear()
    rel.transcribe_media(media, model_name="distil-small.en", language="en")
    assert loads == ["distil-small.en"]


def test_multilingual_models_never_run_the_check(monkeypatch, media):
    small = FakeModel("small", language="de")
    loads = models(monkeypatch, small=small)
    rel.transcribe_media(media, model_name="small")
    assert loads == ["small"] and "language" not in small.calls[0]


def test_capture_records_the_fallback(monkeypatch, tmp_path):
    import server
    media = tmp_path / "video.mp4"
    media.write_bytes(b"fake")
    monkeypatch.setattr(server, "_reliability_model_status", lambda name: {"cached": True})
    monkeypatch.setattr(server, "_media_has_audio", lambda path, cancel=None: True)

    def fake(path, **kwargs):
        kwargs["info"].update({"model": "base", "english_fallback": {
            "requested_model": "distil-small.en", "used_model": "base",
            "detected_language": "es", "language_probability": 0.97}})
        return [(0.0, 1.0, "Hola.")]

    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", fake)
    entries, source, meta = server._resolve_video_transcript(
        [], media, 60, settings={"whisper_model": "distil-small.en", "asr_fallback_enabled": True})
    assert source == "asr" and entries == [(0.0, 1.0, "Hola.")]
    assert meta["model"] == "base"
    assert meta["requested_model"] == "distil-small.en"
    assert meta["detected_language"] == "es"


@pytest.mark.parametrize("line", ["No no no no!", "one two one two one two one two",
                                  "0 0 0 0", "We will rock you " * 4, "Go team! " * 4])
def test_real_repeated_speech_keeps_words_and_timings(line):
    row = rel.TranscriptEntry(0, 4, line.strip(), [{"word": "first", "start": 0, "end": 1}])
    rows = rel.drop_repetition_loops([row] * 5, [(1.1, 0.01)] * 5)
    assert rows == [row] * 5 and all(r.words == row.words for r in rows)
    if line.startswith(("No ", "one ", "0 ")):
        assert rel.drop_repetition_loops([row], [(3.1, 0.95)]) == [row]
    assert "vad_parameters" not in rel.DECODE_OPTIONS


def test_invalid_word_times_never_reach_json():
    import json
    import podcasts
    raw = [{"word": "bad", "start": x, "end": 2} for x in (float("nan"), float("inf"), -1, True)]
    raw += [{"word": "bad", "start": 2, "end": float("inf")}, {"word": "ok", "start": 2, "end": 1}]
    import whisper_runner
    aligned = whisper_runner._shape_segments([{"start": 0, "end": 2, "text": "ok", "words": raw}])
    for rows in (rel._segment_words({"words": raw}), podcasts._valid_words(raw), aligned[0]["words"]):
        assert rows == [{"word": "ok", "start": 2, "end": 2}]
        json.dumps(rows, allow_nan=False)


def test_language_probe_uses_window_vad_and_reliability_uses_multilingual(monkeypatch, media):
    base = FakeModel("base", language="es")
    english = FakeModel("distil-small.en")
    models(monkeypatch, **{"base": base, "distil-small.en": english})
    rel.detect_unreliable_spans("", media, model_name="distil-small.en")
    assert not english.calls and base.calls[-1]["language"] == "es"
    assert base.calls[0]["vad_filter"]
    rel.transcribe_media(media, model_name="distil-small.en", language="en-US")
    assert english.calls[-1]["language"] == "en"


def test_bundled_base_checks_mixed_podcast_and_capture(monkeypatch, tmp_path, media):
    import whisper_runner as runner
    from tests.test_bundled_whisper_model import stage_bundled, seed_user_cache
    app = tmp_path / "bundle"
    base = stage_bundled(app)
    data = tmp_path / "data"
    root = data / "models" / "whisper"
    seed_user_cache(root, "distil-small.en")
    monkeypatch.setattr(rel, "bundled_model_root", lambda: app)
    monkeypatch.setattr(rel, "_language_samples", lambda *_: ["intro", "middle", "tail"], raising=False)
    calls = []
    class Multilingual:
        def __init__(self, path, **kw):
            assert path == str(base) and kw["local_files_only"]
        def transcribe(self, path, **kw):
            calls.append((path, kw))
            lang = "en" if path == "intro" else "es"
            return [seg(0, 2, "Buenos dias.")], SimpleNamespace(language=lang, language_probability=0.99)
    monkeypatch.setattr(rel, "_import_faster_whisper", lambda: Multilingual)
    monkeypatch.setattr(runner.asr_worker, "in_child", lambda: True)
    monkeypatch.setattr(runner, "plain_engine_for", lambda _: True)
    for run in ("capture", "podcast"):
        calls.clear()
        info = {}
        if run == "capture":
            rel.transcribe_media(media, model_name="distil-small.en", model_root=root, info=info)
        else:
            info = runner.transcribe_audio(media, model_size="distil-small.en", data_root=data)
        assert info["model"] == "base" and info["english_fallback"]["detected_language"] == "mixed"
        assert [kw["vad_filter"] for _, kw in calls] == [True, True, True, True]
        assert "language" not in calls[-1][1]


def test_mixed_sections_keep_separate_provenance(tmp_path, monkeypatch):
    import server
    paths = [tmp_path / name for name in ("one", "two")]
    monkeypatch.setattr(server, "_reliability_model_status", lambda *_: {"cached": True})
    monkeypatch.setattr(server, "_media_has_audio", lambda *_: True)
    def transcribe(path, **kw):
        if path == paths[0]:
            kw["info"]["english_fallback"] = {"used_model": "base", "detected_language": "es"}
        return [(0, 1, "sample")]
    monkeypatch.setattr(rel, "transcribe_media", transcribe)
    _, _, meta = server._resolve_video_transcript([], paths[0], 10, settings={"whisper_model": "distil-small.en"},
        media_chunks=[(paths[0], 0, 2), (paths[1], 8, 2)])
    assert meta["model"] == "distil-small.en" and "detected_language" not in meta
    assert meta["section_fallbacks"] == [{"used_model": "base", "detected_language": "es"}, None]


def test_thank_you_over_silence_with_word_times():
    words = [word(t, i * .45, i * .45 + .22) for i, t in
             enumerate(("Thank you. " * 9 + "Thank").split())]
    entries = rel._transcript_entries_from_segments([
        seg(0, 9, "Thank you. Thank you, " + "Thank you. " * 7 + "Thank", words=words)])
    rows = rel.drop_repetition_loops(entries, [(1.9, .94)])
    assert rows == [(0.0, 9.0, "Thank you.")]
    assert not getattr(rows[0], "words", None) or len(rows[0].words) == 2


def test_identical_segments_over_silence():
    lines = ["Yeah.", "yeah", "Yeah!", "Yeah.", "Yeah.", "So the launch moved.", "Yeah."]
    rows = rel.drop_repetition_loops([(i, i+1, line) for i, line in enumerate(lines)],
                                     [(1.9, .92)] * len(lines))
    assert [text for _s, _e, text in rows] == ["Yeah.", "yeah", "So the launch moved.", "Yeah."]


def test_whisperx_segment_times_survive_persistence(tmp_path):
    import whisper_runner as runner
    import json
    rows = runner._shape_segments([{"start": a, "end": b, "text": "ok"} for a, b in
        [(float("nan"), 1), (0, float("inf")), (True, 2), (-1, 1), (2, 1)]])
    path = runner.write_transcript({"segments": rows}, audio_path=tmp_path / "clip.wav")
    assert [(row["start"], row["end"]) for row in json.loads(path.read_bytes())["segments"]] == [(0, 1), (2, 2)]


@pytest.mark.parametrize("intro_vad_seconds", [0, 1])
def test_language_probe_music_speech_and_silence(tmp_path, monkeypatch, intro_vad_seconds):
    import wave
    import struct
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", ""))
        for level in (500, 5000, 0):
            out.writeframes(struct.pack("<h", level) * (16000 * 20))
    class Checker:
        def transcribe(self, audio, **kw):
            speech = audio.max() > 0.1
            return [], SimpleNamespace(language="en" if speech else "fr",
                language_probability=.98 if speech else .3,
                duration_after_vad=20 if speech else (intro_vad_seconds if audio.max() else 0))
    monkeypatch.setattr(rel, "_load_model", lambda *a, **kw: Checker())
    assert rel._english_guard(path, "distil-small.en", None, None) == ("distil-small.en", "en", None)


@pytest.mark.parametrize(("speech", "expected"), [
    ("en", "distil-small.en"), ("es", "base"),
])
def test_english_only_model_after_forty_seconds_of_music(media, monkeypatch, speech, expected):
    # Three consecutive 20-second windows. VAD finds music in the first two.
    english = FakeModel("distil-small.en")
    class Checker(FakeModel):
        def transcribe(self, audio, **kwargs):
            if isinstance(audio, int):
                assert kwargs["vad_filter"]
                return [], SimpleNamespace(language="fr" if audio < 40 else speech,
                    language_probability=.99, duration_after_vad=0 if audio < 40 else 19)
            return super().transcribe(audio, **kwargs)
    loads = models(monkeypatch, base=Checker("base", language=speech), **{"distil-small.en": english})
    monkeypatch.setattr(rel, "_language_samples", lambda *_: iter((0, 20, 40)))
    info = {}
    phases = []
    monkeypatch.setattr(rel.asr_worker, "_phase_callback", phases.append)
    rows = rel.transcribe_media(media, model_name="distil-small.en", info=info)
    assert phases == ["language check", "model load", "decode"]
    assert loads == ["base", expected] and info["language"] == speech
    assert rows[0][2] == f"spoken words from {expected}"
    assert bool(english.calls) == (speech == "en")


@pytest.mark.parametrize("empty", [True, False])
def test_language_probe_unreadable_stream_falls_back(empty, monkeypatch, media):
    pytest.importorskip("numpy")  # the probe decodes samples with numpy
    import contextlib
    class Container:
        streams = SimpleNamespace(audio=[] if empty else [SimpleNamespace(duration=100, time_base=1)])
        def decode(self, stream):
            return iter([])
        def seek(self, *a, **kw):
            # Some PyAV builds raise an FFmpegError without an OSError base.
            raise RuntimeError("input is unseekable")
    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(
        open=lambda _: contextlib.nullcontext(Container()), AudioResampler=lambda **kw: None))
    monkeypatch.setattr(rel, "_load_model", lambda *a, **kw: FakeModel("base"))
    assert rel._english_guard(media, "distil-small.en", None, None)[:2] == ("base", None)


def test_chunked_provenance_keeps_silent_section_and_ignores_confidence(tmp_path, monkeypatch):
    import server
    paths = [tmp_path / str(i) for i in range(3)]
    monkeypatch.setattr(server, "_reliability_model_status", lambda *_: {"cached": True})
    monkeypatch.setattr(server, "_media_has_audio", lambda *_: True)
    def decode(path, **kwargs):
        i = paths.index(path)
        if i == 1:
            return []
        kwargs["info"]["english_fallback"] = {"used_model": "base", "detected_language": "es",
                                               "language_probability": .91 + .01 * i}
        return [(0, 1, "hola")]
    monkeypatch.setattr(rel, "transcribe_media", decode)
    _, _, meta = server._resolve_video_transcript([], paths[0], 30, settings={"whisper_model": "distil-small.en"},
        media_chunks=[(path, i*10, 2) for i, path in enumerate(paths)])
    assert meta["model"] == "base" and meta["detected_language"] == "es"
    assert [f and f["used_model"] for f in meta["section_fallbacks"]] == ["base", None, "base"]



def test_song_refrain_with_distinct_timings_and_speech_evidence():
    segments = [seg(i, i + 1, "La la la.", words=[
        word("La", i, i+.2), word("la", i+.3, i+.5), word("la.", i+.6, i+.9)],
        ratio=2.8, no_speech=.02) for i in range(0, 24, 3)]
    scores = []
    rows = rel._transcript_entries_from_segments(segments, scores)
    filtered = rel.drop_repetition_loops(rows, scores)
    assert filtered == rows and all(a.words == b.words for a, b in zip(filtered, rows))
