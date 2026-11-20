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
    loads = []

    def load(name, root, *, local_files_only=True):
        assert local_files_only is True
        loads.append(name)
        return by_name[name]

    monkeypatch.setattr(rel, "_load_model", load)
    return loads


# ---- loop filter -----------------------------------------------------------
def test_a_phrase_looping_inside_one_segment_collapses_to_one():
    rows = rel.drop_repetition_loops([(0.0, 9.0, "Thank you. Thank you. Thank you. Thank you. Thank you.")])
    assert rows == [(0.0, 9.0, "Thank you.")]


def test_identical_segments_after_two_in_a_row_are_dropped():
    rows = rel.drop_repetition_loops([
        (0.0, 1.0, "Yeah."), (1.0, 2.0, "yeah"), (2.0, 3.0, "Yeah."), (3.0, 4.0, "Yeah."),
        (4.0, 5.0, "So the launch moved."), (5.0, 6.0, "Yeah."),
    ])
    assert [text for _s, _e, text in rows] == ["Yeah.", "yeah", "So the launch moved.", "Yeah."]


def test_repetitive_text_over_likely_silence_is_dropped():
    rows = rel.drop_repetition_loops(
        [(0.0, 30.0, "la la la"), (30.0, 32.0, "Welcome back.")],
        [(3.1, 0.8), (1.1, 0.02)])
    assert rows == [(30.0, 32.0, "Welcome back.")]


def test_normal_speech_passes_unchanged():
    lines = [(0.0, 2.0, "We tried three times."), (2.0, 4.0, "It worked on the third.")]
    assert rel.drop_repetition_loops(lines, [(1.3, 0.01), (1.2, 0.02)]) == lines


def test_transcribe_media_applies_the_filter_and_decode_options(monkeypatch, media):
    looping = FakeModel("base", segments=[
        seg(0.0, 2.0, "Intro music."), seg(2.0, 4.0, "Thanks for watching."),
        seg(4.0, 6.0, "Thanks for watching."), seg(6.0, 8.0, "Thanks for watching."),
        seg(8.0, 30.0, "na na na na na na", ratio=3.0, no_speech=0.9)])
    models(monkeypatch, base=looping)
    rows = rel.transcribe_media(media, model_name="base")
    assert [text for _s, _e, text in rows] == [
        "Intro music.", "Thanks for watching.", "Thanks for watching."]
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
