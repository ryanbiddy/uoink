"""Transcript-only saves (the episode path of a whole-show capture).

Drives the real server._run_extraction with the subprocess and network
boundary mocked (the test_lite_recovery_a01 approach) and checks:
  - captions are fetched and no media is downloaded or screenshotted
  - the sidecar records the caption kind (uploaded vs automatic), the
    source's publish date and description, separate from yoinked_at
  - no comments, hook typing, channel context or entity extraction run
  - a video with no captions saves nothing and says why
  - a caption bot check or 429 becomes the error the retry worker already
    backs off on (never an audio download while YouTube is refusing)
  - local ASR runs only in transcript_asr mode, on the audio alone
  - an existing capture is never stripped by a transcript-only save
Fixtures are made up; nothing touches the network or a real model.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import index as index_mod  # noqa: E402
import server  # noqa: E402

URL = "https://www.youtube.com/watch?v=showep00001"
SRT = ("1\n00:00:01,000 --> 00:00:03,500\nwelcome back to the show\n\n"
       "2\n00:00:03,500 --> 00:00:06,000\ntoday we talk about tide pools\n")


def _metadata(**extra):
    base = {
        "id": "showep00001", "title": "Episode 12: Tide pools",
        "duration": 1800, "channel": "The Example Hour",
        "channel_url": "https://www.youtube.com/@examplehour",
        "upload_date": "20250304", "timestamp": 1741100400,
        "description": "We visit the tide pools.\nGuest: a made-up marine biologist.",
    }
    base.update(extra)
    return base


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    behaviour = {"subs": "write", "audio": True}
    started = {"comments": 0, "entities": 0, "channel_urls": []}
    idx = index_mod.Index.open(tmp_path / "index.db")

    def fake_run(cmd, **_kwargs):
        cmd = [str(c) for c in cmd]
        calls.append(cmd)
        if cmd[0] == "ffmpeg":
            out = cmd[-1]
            Path(out.replace("%04d", "0001")).write_bytes(b"jpeg")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        out = Path(cmd[cmd.index("-o") + 1]) if "-o" in cmd else None
        if "--skip-download" in cmd:
            if behaviour["subs"] == "bot":
                raise subprocess.CalledProcessError(
                    1, cmd, b"", b"ERROR: [youtube] showep00001: Sign in to confirm you're not a bot")
            if behaviour["subs"] == "429":
                raise subprocess.CalledProcessError(
                    1, cmd, b"", b"ERROR: Unable to download video subtitles for 'en': HTTP Error 429")
            if behaviour["subs"] == "write":
                Path(str(out).replace("%(ext)s", "en.srt")).write_text(SRT, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if out is not None and "bestaudio/best" in cmd:
            if behaviour["audio"]:
                Path(str(out).replace("%(ext)s", "m4a")).write_bytes(b"audio")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if out is not None:
            Path(str(out).replace("%(ext)s", "mp4")).write_bytes(b"media")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def fake_channel_context(url, **_kwargs):
        started["channel_urls"].append(url)
        return {"description": "", "recent_videos": []}

    monkeypatch.setattr(server, "_run_subprocess", fake_run)
    monkeypatch.setattr(server, "_download_thumbnail", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_fetch_channel_context", fake_channel_context)
    monkeypatch.setattr(server, "_should_start_hook_type", lambda *_a, **_k: True)
    monkeypatch.setattr(server, "_read_settings", lambda: {"asr_fallback_enabled": False})
    monkeypatch.setattr(server, "_incremental_index_update", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_generate_paste_corpus", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_anthropic_key_for_feature", lambda *_a, **_k: "key-set")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    (tmp_path / "data").mkdir()

    def fake_comments(*_a, **_k):
        started["comments"] += 1

    def fake_entities(*_a, **_k):
        started["entities"] += 1

    monkeypatch.setattr(server, "_start_comments_thread", fake_comments)
    monkeypatch.setattr(server, "_start_entity_extraction_thread", fake_entities)
    yield type("Env", (), {"calls": calls, "behaviour": behaviour, "started": started,
                           "idx": idx, "root": tmp_path})
    idx.close()


def _run(env, mode, metadata=None, folder_name="ep"):
    folder = env.root / "lib" / folder_name
    folder.parent.mkdir(parents=True, exist_ok=True)
    return server._run_extraction(
        URL, 30, folder, notify=False, metadata=metadata or _metadata(),
        topic="Shows", generate_paste=False, long_video_mode=mode)


def _sidecar(result):
    folder = Path(result["folder"])
    return json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))


def test_normalizer_accepts_the_internal_transcript_modes():
    assert server._normalize_long_video_mode("transcript") == "transcript"
    assert server._normalize_long_video_mode(" Transcript_ASR ") == "transcript_asr"
    with pytest.raises(ValueError) as err:
        server._normalize_long_video_mode("bogus")
    assert "lite" in str(err.value) and "transcript" not in str(err.value)


def test_transcript_mode_saves_captions_without_media(env):
    result = _run(env, "transcript", _metadata(subtitles={"en": [{"ext": "vtt"}]}))
    media = [c for c in env.calls if "-o" in c and "--skip-download" not in c]
    assert media == [], f"no media download in transcript mode: {media}"
    assert not [c for c in env.calls if c[0] == "ffmpeg"], "no screenshots"
    assert result["long_video_mode"] == "transcript"
    assert result["transcript_source"] == "captions"
    assert result["screenshot_count"] == 0
    sidecar = _sidecar(result)
    assert sidecar["caption_kind"] == "captions"
    assert sidecar["published_at"] == "2025-03-04T15:00:00Z"
    assert sidecar["description"].startswith("We visit the tide pools.")
    assert sidecar["yoinked_at"] != sidecar["published_at"]
    assert [row["text"] for row in sidecar["transcript"]] == [
        "welcome back to the show", "today we talk about tide pools"]
    assert sidecar["screenshots"] == []
    assert sidecar["comments_status"] == "skipped"
    assert sidecar["hook_type_status"] == "skipped"
    assert sidecar["entity_extraction_status"] == "skipped"
    assert sidecar["health"]["screenshots"] == "skipped"
    assert sidecar["health"]["transcript"] == "ok"
    # No comments, entity extraction or channel lookup for a whole-show episode.
    assert env.started["comments"] == 0 and env.started["entities"] == 0
    assert env.started["channel_urls"] == [""]
    folder = Path(result["folder"])
    assert not (folder / "screenshots").exists()
    assert not list(folder.glob("video.mp4"))
    corpus = next(folder.glob("*.md")).read_text(encoding="utf-8")
    assert "Skipped for a transcript-only save." in corpus
    assert "Fetching comments" not in corpus
    assert "Transcript-only save" in corpus
    # The library row carries the publish date for date-range search.
    row = env.idx.get_yoink("showep00001")
    assert json.loads(row["metadata_json"])["published_at"] == "2025-03-04T15:00:00Z"


def test_auto_captions_are_recorded_as_automatic(env):
    result = _run(env, "transcript", _metadata(automatic_captions={"en": [{"ext": "vtt"}]}))
    assert _sidecar(result)["caption_kind"] == "auto_captions"


def test_uploaded_track_wins_when_both_exist(env):
    result = _run(env, "transcript", _metadata(
        subtitles={"en": [{}]}, automatic_captions={"en": [{}], "fr": [{}]}))
    assert _sidecar(result)["caption_kind"] == "captions"


def test_no_captions_saves_nothing_and_says_why(env):
    env.behaviour["subs"] = "none"
    with pytest.raises(server.ExtractionPhaseError) as err:
        _run(env, "transcript")
    assert str(err.value) == server.TRANSCRIPT_NO_CAPTIONS_MESSAGE
    assert err.value.phase == "transcript"
    # The attempt's own files go, so a show with many caption-less videos
    # leaves no empty folders behind.
    folder = env.root / "lib" / "ep"
    assert not folder.exists()
    assert env.idx.get_yoink("showep00001") is None
    assert not [c for c in env.calls if "bestaudio/best" in c], "no audio without ASR opt-in"


def test_a_retry_after_a_refused_attempt_still_saves(env):
    env.behaviour["subs"] = "bot"
    with pytest.raises(subprocess.CalledProcessError):
        _run(env, "transcript")
    env.behaviour["subs"] = "write"
    result = _run(env, "transcript")
    assert result["transcript_source"] == "captions"
    assert env.idx.get_yoink("showep00001") is not None


@pytest.mark.parametrize("refusal,kind", [("bot", "bot_check"), ("429", "rate_limit")])
def test_caption_refusal_waits_in_the_queue_instead_of_failing(env, refusal, kind):
    env.behaviour["subs"] = refusal
    with pytest.raises(subprocess.CalledProcessError) as err:
        _run(env, "transcript_asr")
    assert server._is_youtube_block(err.value)
    if kind == "bot_check":
        assert server._is_youtube_bot_check(err.value)
        assert server._youtube_block_detail(err.value).startswith("youtube_bot_check")
    else:
        assert server._is_youtube_rate_limit(err.value)
    # Never fall through to an audio download while YouTube is refusing.
    assert not [c for c in env.calls if "bestaudio/best" in c]
    assert env.idx.get_yoink("showep00001") is None


def test_transcript_asr_transcribes_the_audio_alone(env, monkeypatch):
    env.behaviour["subs"] = "none"
    seen = {}
    monkeypatch.setattr(server, "_reliability_model_status", lambda *_a, **_k: {"cached": True})
    monkeypatch.setattr(server, "_media_has_audio", lambda *_a, **_k: True)

    def fake_transcribe(path, **_kwargs):
        seen["path"] = Path(path)
        return [(0.0, 2.0, "local words one"), (2.0, 4.5, "local words two")]

    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", fake_transcribe)
    result = _run(env, "transcript_asr")
    assert result["transcript_source"] == "asr"
    assert seen["path"].name.startswith("audio.")
    assert not seen["path"].exists(), "the downloaded audio is removed"
    assert not list(Path(result["folder"]).glob(".asr-*")), "temp folder removed"
    assert [c for c in env.calls if "bestaudio/best" in c], "audio-only download"
    assert not [c for c in env.calls if c[0] == "ffmpeg"]
    sidecar = _sidecar(result)
    assert sidecar["transcript_source"] == "asr"
    assert sidecar["caption_kind"] is None
    assert [row["text"] for row in sidecar["transcript"]] == ["local words one", "local words two"]


def test_transcript_asr_without_the_model_fails_plainly(env, monkeypatch):
    env.behaviour["subs"] = "none"
    monkeypatch.setattr(server, "_reliability_model_status", lambda *_a, **_k: {"cached": False})
    with pytest.raises(server.ExtractionPhaseError) as err:
        _run(env, "transcript_asr")
    assert str(err.value) == server.TRANSCRIPT_NO_MODEL_MESSAGE
    assert not [c for c in env.calls if "bestaudio/best" in c]


def test_transcript_mode_never_strips_an_existing_capture(env):
    full = _run(env, "full", _metadata(subtitles={"en": [{}]}))
    folder = Path(full["folder"])
    before = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert any(name.startswith("screenshots/") for name in before)
    with pytest.raises(server.ExtractionPhaseError) as err:
        _run(env, "transcript")
    assert str(err.value) == server.TRANSCRIPT_ALREADY_SAVED_MESSAGE
    after = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert after == before


def test_full_capture_also_records_publish_date_and_caption_kind(env):
    result = _run(env, "full", _metadata(automatic_captions={"en": [{}]}, timestamp=None))
    sidecar = _sidecar(result)
    assert sidecar["published_at"] == "2025-03-04"
    assert sidecar["caption_kind"] == "auto_captions"
    assert sidecar["description"].startswith("We visit")
    assert sidecar["comments_status"] == "pending"
    assert env.started["comments"] == 1
    assert env.started["channel_urls"] == ["https://www.youtube.com/@examplehour"]
    assert [c for c in env.calls if c[0] == "ffmpeg"], "full mode still screenshots"


def test_source_facts_shapes():
    facts = server._source_facts({"upload_date": "20240101", "description": "  x  "})
    assert facts == {"published_at": "2024-01-01", "description": "x"}
    assert server._source_facts({})["published_at"] is None
    assert server._source_facts({"release_timestamp": 0, "upload_date": "bad"})["published_at"] is None
    long = server._source_facts({"description": "a" * 9000})["description"]
    assert len(long) == server._SOURCE_DESCRIPTION_MAX_CHARS
