"""Offline coverage for the YouTube transcript cascade and MCP tool."""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


VIDEO_ID = "abcdef12345"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
CAPTION_429 = (
    "ERROR: Unable to download video subtitles for 'en': "
    "HTTP Error 429: Too Many Requests"
)
BOT_CHECK = "Sign in to confirm you're not a bot"
TRACK = [{"ext": "srt"}]


@pytest.fixture(scope="module")
def transcript_backend(tmp_path_factory):
    # server imports settings, a log handler, and a WhisperX availability probe.
    # Redirect those before importing it, including in a standalone pytest run.
    import _platform
    import uoink_install_isolation

    root = tmp_path_factory.mktemp("transcript-import")
    data = root / "data"
    output = root / "output"
    data.mkdir()
    output.mkdir()
    already_imported = "server" in sys.modules

    def forbid_external_io(*_args, **_kwargs):
        pytest.fail("unexpected external I/O")

    unexpected_io = Mock(side_effect=forbid_external_io)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_platform, "user_data_dir", lambda: data)
        patch.setattr(_platform, "app_state_path", lambda _app, data, name: data / name)
        patch.setattr(_platform, "desktop_dir", lambda: output)
        patch.setattr(_platform, "media_capability", lambda: {"available": False})
        patch.setattr(uoink_install_isolation, "apply_from_process", lambda: None)
        patch.setattr(uoink_install_isolation, "current_binding", lambda: None)
        patch.setenv("UOINK_OUTPUT_DIR", str(output))
        # The optional keyring import probes Windows with a subprocess.
        patch.setitem(sys.modules, "keyring", None)
        for owner, name in (
            (subprocess, "run"), (subprocess, "Popen"),
            (urllib.request, "urlopen"), (socket, "create_connection"),
            (socket, "getaddrinfo"), (socket.socket, "connect"),
            (socket.socket, "connect_ex"), (socket.socket, "bind"),
        ):
            patch.setattr(owner, name, unexpected_io)

        import server
        import uoink_mcp_tools as tools

        try:
            yield server, tools
        finally:
            if not already_imported:
                logging.getLogger().removeHandler(server._server_log_handler)
                server._error_detail_log.removeHandler(server._server_log_handler)
                server._server_log_handler.close()
            unexpected_io.assert_not_called()


@pytest.fixture
def transcript(monkeypatch, tmp_path, transcript_backend):
    server, tools = transcript_backend
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    state = SimpleNamespace(
        server=server,
        tools=tools,
        folder=None,
        row=None,
        metadata={
            "id": VIDEO_ID, "title": "Offline transcript", "duration": 120,
            "language": "en", "subtitles": {"en": TRACK},
            "automatic_captions": {"de": TRACK, "en-orig": TRACK},
        },
        settings=server._default_settings(),
        caption_errors={},
        caption_text={
            "en": "Manual English captions.",
            "en-orig": "Original automatic captions.",
            "de": "Translated German captions.",
        },
        calls=[],
        language="en",
    )

    def fake_run(cmd, **kwargs):
        state.calls.append((list(cmd), kwargs))
        assert "--skip-download" in cmd, "only caption commands may reach this fake"
        key = cmd[cmd.index("--sub-lang") + 1]
        folder = Path(cmd[cmd.index("-o") + 1]).parent
        assert folder.is_relative_to(scratch)
        if key in state.caption_errors:
            raise subprocess.CalledProcessError(1, cmd, stderr=state.caption_errors[key])
        (folder / f"captions.{key}.srt").write_text(
            f"1\n00:00:00,000 --> 00:00:02,000\n{state.caption_text[key]}\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def fake_audio(url, folder):
        assert url == URL
        assert folder.is_relative_to(scratch)
        audio = folder / "audio.m4a"
        audio.write_bytes(b"offline audio")
        return audio

    def fake_asr(audio, *, model_name, model_root, info, initial_prompt=None):
        assert audio.read_bytes() == b"offline audio"
        assert model_name == state.settings["whisper_model"]
        assert model_root == tmp_path / "data" / "models" / "whisper"
        info["language"] = state.language
        return [(0.0, 2.0, "hello world")]

    def save_library(segments, **fields):
        state.folder = tmp_path / "saved-video"
        state.folder.mkdir(exist_ok=True)
        state.row = {"title": "Saved transcript"}
        sidecar = {
            "title": "Saved transcript", "duration_seconds": 120,
            "transcript_source": "captions", "transcript_language": "en",
            "transcript": [
                {"start": start, "end": end, "text": text}
                for start, end, text in segments
            ],
            **fields,
        }
        (state.folder / f"{state.folder.name}.json").write_text(
            json.dumps(sidecar), encoding="utf-8")

    state.save_library = save_library
    state.lookup = Mock(side_effect=lambda _video_id: (state.folder, state.row))
    state.metadata_fetch = Mock(side_effect=lambda _url: state.metadata)
    state.download_audio = Mock(side_effect=fake_audio)
    state.asr = Mock(side_effect=fake_asr)
    state.model_status = Mock(return_value={"cached": True})
    unexpected_io = Mock(side_effect=AssertionError("unexpected index or model access"))

    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
    monkeypatch.setattr(server, "RELIABILITY_MODEL_ROOT", tmp_path / "data" / "models" / "whisper")
    monkeypatch.setattr(server.tempfile, "tempdir", str(scratch))
    monkeypatch.setattr(server, "_folder_for_video_id", state.lookup)
    monkeypatch.setattr(server, "_get_index", unexpected_io)
    monkeypatch.setattr(server, "_fetch_metadata", state.metadata_fetch)
    monkeypatch.setattr(server, "_run_subprocess", fake_run)
    monkeypatch.setattr(server, "_download_reliability_audio", state.download_audio)
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", state.asr)
    monkeypatch.setattr(server.uoink_reliability, "ensure_model", unexpected_io)
    monkeypatch.setattr(server.uoink_reliability, "_load_model", unexpected_io)
    monkeypatch.setattr(server, "_reliability_model_status", state.model_status)
    monkeypatch.setattr(server, "_read_settings", lambda: state.settings)
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    monkeypatch.setattr(server._platform, "capability_refusal", lambda _capability: None)
    monkeypatch.setattr(tools, "_backend", tools._backend)
    tools.bind_backend(server)

    yield state
    unexpected_io.assert_not_called()


def caption_keys(transcript):
    return [cmd[cmd.index("--sub-lang") + 1] for cmd, _kwargs in transcript.calls]


@pytest.mark.parametrize("provider,language,transcribed_by", [
    ("captions", "en", "captions"),
    ("asr", "fr", "whisper"),
])
def test_library_hit_returns_provenance_without_downloads(
        transcript, provider, language, transcribed_by):
    transcript.save_library(
        [(0.0, 2.0, "Saved words.")],
        transcript_source=provider, transcript_language=language,
    )

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is True
    assert result["source"] == "library"
    assert result["transcribed_by"] == transcribed_by
    assert result["slug"] == "saved-video"
    assert result["language"] == language
    assert result["transcript"] == "Saved words."
    assert result["why"] is None
    transcript.lookup.assert_called_once_with(VIDEO_ID)
    assert transcript.calls == []
    transcript.metadata_fetch.assert_not_called()
    transcript.download_audio.assert_not_called()
    transcript.asr.assert_not_called()


def test_manual_english_captions_precede_auto_and_are_cached(transcript, tmp_path):
    first = transcript.tools.get_transcript({"url": URL})

    assert first["ok"] is True
    assert first["source"] == "captions"
    assert first["language"] == "en"
    assert first["why"] is None
    assert first["cached"] is False
    assert first["transcript"] == "Manual English captions."
    assert caption_keys(transcript) == ["en"]
    cmd, kwargs = transcript.calls[0]
    assert "--write-subs" in cmd
    assert "--write-auto-subs" not in cmd
    assert cmd[-1] == URL
    assert kwargs["check"] is True
    cache_files = list((tmp_path / "data" / "transcript-cache").glob("*.json"))
    assert len(cache_files) == 1
    cached_record = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cached_record["segments"] == [[0.0, 2.0, "Manual English captions."]]

    transcript.calls.clear()
    transcript.metadata_fetch.reset_mock()
    second = transcript.tools.get_transcript({"url": URL})

    assert second == {**first, "cached": True}
    assert transcript.calls == []
    transcript.metadata_fetch.assert_not_called()
    transcript.download_audio.assert_not_called()
    transcript.asr.assert_not_called()


def test_original_auto_captions_report_clean_language(transcript):
    transcript.metadata["subtitles"] = {}

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is True
    assert result["source"] == "auto_captions"
    assert result["language"] == "en"
    assert result["translated"] is False
    assert result["transcript"] == "Original automatic captions."
    assert caption_keys(transcript) == ["en-orig"]
    cmd, _kwargs = transcript.calls[0]
    assert "--write-auto-subs" in cmd
    assert "--write-subs" not in cmd
    transcript.asr.assert_not_called()


@pytest.mark.parametrize("stderr", [CAPTION_429, CAPTION_429.encode()], ids=["text", "bytes"])
@pytest.mark.parametrize("key", ["en", "en-orig"], ids=["manual", "original-auto"])
def test_caption_429_uses_whisper_after_one_original_track_attempt(transcript, stderr, key):
    # Leave other candidates available so the assertion detects unwanted retries.
    if key == "en-orig":
        transcript.metadata["subtitles"] = {"fr": TRACK}
    else:
        transcript.metadata["subtitles"]["en-US"] = TRACK
    transcript.caption_errors[key] = stderr

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is True
    assert result["source"] == "whisper"
    assert result["reason"] == "captions_rate_limited"
    assert "429" in result["why"]
    assert "Whisper" in result["why"]
    assert result["language"] == "en"
    assert result["transcript"] == "hello world"
    assert result["whisper_model"] == "base"
    assert caption_keys(transcript) == [key]
    transcript.model_status.assert_called_once_with("base")
    transcript.download_audio.assert_called_once()
    transcript.asr.assert_called_once()


def test_caption_bot_check_falls_back_to_whisper(transcript):
    transcript.caption_errors["en"] = BOT_CHECK

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is True
    assert result["source"] == "whisper"
    assert result["reason"] == "captions_bot_check"
    assert "bot check" in result["why"]
    assert "Whisper" in result["why"]
    assert caption_keys(transcript) == ["en"]
    transcript.download_audio.assert_called_once()
    transcript.asr.assert_called_once()


def test_no_listed_captions_falls_back_to_whisper(transcript):
    transcript.metadata.pop("subtitles")
    transcript.metadata.pop("automatic_captions")

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is True
    assert result["source"] == "whisper"
    assert result["reason"] == "no_captions"
    assert "no captions" in result["why"]
    assert "Whisper" in result["why"]
    assert transcript.calls == []
    transcript.download_audio.assert_called_once()
    transcript.asr.assert_called_once()


def test_translated_german_429_falls_back_to_original_english(transcript):
    transcript.metadata["subtitles"] = {}
    transcript.caption_errors["de"] = CAPTION_429.replace("'en'", "'de'")

    result = transcript.tools.get_transcript({"url": URL, "lang": "de"})

    assert result["ok"] is True
    assert result["source"] == "auto_captions"
    assert result["language"] == "en"
    assert result["translated"] is False
    assert result["transcript"] == "Original automatic captions."
    assert caption_keys(transcript) == ["de", "en-orig"]
    assert "429" in result["why"]
    assert "machine-translated 'de' track" in result["why"]
    assert "'en' track instead" in result["why"]
    transcript.download_audio.assert_not_called()
    transcript.asr.assert_not_called()


def test_disabled_whisper_reports_caption_429(transcript):
    transcript.settings["asr_fallback_enabled"] = False
    transcript.caption_errors["en"] = CAPTION_429

    result = transcript.tools.get_transcript({"url": URL})

    assert result["ok"] is False
    assert result["reason"] == "whisper_disabled"
    assert "429" in result["error"]
    assert "Whisper" in result["error"]
    assert caption_keys(transcript) == ["en"]
    transcript.model_status.assert_not_called()
    transcript.download_audio.assert_not_called()
    transcript.asr.assert_not_called()


@pytest.mark.parametrize("url", [None, "", "not a video", "https://example.com/video", 123])
def test_invalid_url_returns_reason_without_io(transcript, url):
    result = transcript.tools.get_transcript({"url": url})

    assert result["ok"] is False
    assert result["reason"] == "invalid_url"
    assert result["error"]
    transcript.lookup.assert_not_called()
    transcript.metadata_fetch.assert_not_called()
    assert transcript.calls == []
    transcript.asr.assert_not_called()


@pytest.mark.parametrize("lang", ["", "en_US", "../de", "e", 123, ["en"]])
def test_invalid_language_returns_reason_without_io(transcript, lang):
    result = transcript.tools.get_transcript({"url": URL, "lang": lang})

    assert result["ok"] is False
    assert result["reason"] == "invalid_lang"
    assert result["error"]
    transcript.lookup.assert_not_called()
    transcript.metadata_fetch.assert_not_called()
    assert transcript.calls == []
    transcript.asr.assert_not_called()


def test_bare_video_id_is_accepted_and_canonicalized(transcript):
    result = transcript.tools.get_transcript({"url": VIDEO_ID})

    assert result["ok"] is True
    assert result["video_id"] == VIDEO_ID
    assert result["url"] == URL
    assert result["source"] == "captions"
    transcript.metadata_fetch.assert_called_once_with(URL)
    assert transcript.calls[0][0][-1] == URL


@pytest.mark.parametrize("include_timestamps", [False, True], ids=["plain", "timestamps"])
def test_long_transcript_pages_continue_without_loss_under_frame_limit(
        transcript, include_timestamps):
    # Escaped quotes, backslashes and Unicode cost more than their raw lengths.
    segments = [
        (float(i * 3), float(i * 3 + 2), f"Segment {i:03d}: " + ('"caf\u00e9" \\ words ' * 100).rstrip())
        for i in range(180)
    ]
    transcript.save_library(segments)
    args = {"url": URL, "include_timestamps": include_timestamps}
    result = transcript.tools.get_transcript(args)
    assert result["next_cursor"] is not None
    cursor = 0
    pages = []
    seen_segments = []

    for _ in range(len(segments)):
        assert result["ok"] is True
        assert result["segment_count"] == len(segments)
        assert len(json.dumps(result)) < 65536
        pages.append(result["transcript"])
        next_cursor = result["next_cursor"]
        end = len(segments) if next_cursor is None else next_cursor
        assert cursor < end <= len(segments)
        expected = segments[cursor:end]
        if include_timestamps:
            assert result["segments"] == [
                {"start": start, "end": finish, "text": text}
                for start, finish, text in expected
            ]
            seen_segments.extend(result["segments"])
        else:
            assert result["transcript"] == " ".join(text for _start, _end, text in expected)
            assert "segments" not in result
        if next_cursor is None:
            break
        cursor = next_cursor
        result = transcript.tools.get_transcript({**args, "next_cursor": cursor})
    else:
        pytest.fail("paging never reached the final page")

    assert len(pages) > 1
    assert result["next_cursor"] is None
    if include_timestamps:
        assert [segment["text"] for segment in seen_segments] == [s[2] for s in segments]
    else:
        assert " ".join(pages) == " ".join(s[2] for s in segments)
    assert transcript.calls == []
    transcript.metadata_fetch.assert_not_called()
    transcript.asr.assert_not_called()


def test_include_timestamps_returns_clock_lines_and_segments(transcript):
    transcript.save_library([
        (0.0, 2.0, "Opening words."),
        (65.0, 67.5, "Later words."),
        (3601.0, 3603.0, "An hour later."),
    ])

    result = transcript.tools.get_transcript({"url": URL, "include_timestamps": True})

    assert result["ok"] is True
    assert result["transcript"] == (
        "[0:00] Opening words.\n[1:05] Later words.\n[1:00:01] An hour later."
    )
    assert result["segments"] == [
        {"start": 0.0, "end": 2.0, "text": "Opening words."},
        {"start": 65.0, "end": 67.5, "text": "Later words."},
        {"start": 3601.0, "end": 3603.0, "text": "An hour later."},
    ]
    assert result["next_cursor"] is None


def test_get_transcript_registration_and_untrusted_content(transcript):
    tools = transcript.tools
    for toolset in ("search", "core", "full"):
        assert "get_transcript" in tools.stdio_tool_names(toolset)
    assert "get_transcript" in tools.stdio_tool_names()
    assert "get_transcript" in tools.SEARCH_STDIO_TOOLS
    assert "get_transcript" in tools.CORE_STDIO_TOOLS
    spec = tools.TOOL_REGISTRY["get_transcript"]
    assert spec.handler is tools.get_transcript
    assert spec.annotations["readOnlyHint"] is True
    assert "get_transcript" in tools.UNTRUSTED_CONTENT_TOOL_NAMES


@pytest.mark.parametrize("lang", [None, "en"])
def test_caption_candidates_put_manual_english_before_auto(transcript, lang):
    tracks = transcript.server._caption_track_candidates({
        "language": "en",
        "subtitles": {"en-US": TRACK, "fr": TRACK, "en": TRACK},
        "automatic_captions": {"en-orig": TRACK},
    }, lang)

    assert [(track["key"], track["kind"]) for track in tracks[:3]] == [
        ("en", "captions"), ("en-US", "captions"), ("en-orig", "auto_captions"),
    ]


def test_caption_candidates_prefer_orig_spoken_track_over_translation(transcript):
    metadata = {
        "language": "de",
        "automatic_captions": {"en": TRACK, "de-orig": TRACK, "fr": TRACK},
    }

    default = transcript.server._caption_track_candidates(metadata, None)
    assert default == [{
        "key": "de-orig", "kind": "auto_captions", "translated": False, "language": "de",
    }]

    requested = transcript.server._caption_track_candidates(metadata, "en")
    assert [(track["key"], track["translated"]) for track in requested] == [
        ("en", True), ("de-orig", False),
    ]


@pytest.mark.parametrize("has_captions", [False, True], ids=["chat-only", "with-captions"])
def test_caption_candidates_ignore_live_chat(transcript, has_captions):
    metadata = {"subtitles": {"live_chat": [{"ext": "json"}]}}
    if has_captions:
        metadata["subtitles"]["en"] = TRACK
        metadata["automatic_captions"] = {"en-orig": TRACK}

    tracks = transcript.server._caption_track_candidates(metadata, None)

    assert [track["key"] for track in tracks] == (["en", "en-orig"] if has_captions else [])


def _wire_size(result):
    # The tool result travels as JSON text inside a JSON-RPC frame.
    frame = {"jsonrpc": "2.0", "id": 1, "result": {
        "content": [{"type": "text", "text": json.dumps(result)}], "isError": False}}
    return len(json.dumps(frame).encode("utf-8"))


@pytest.mark.parametrize("include_timestamps", [False, True])
def test_one_giant_cue_and_cjk_text_stay_inside_the_frame(transcript, include_timestamps):
    giant = "\u8a71\u3057\"q\" " * 30_000  # one unpunctuated cue far over a page
    transcript.save_library([(0.0, 5.0, giant), (5.0, 9.0, "tail")])
    args = {"url": URL, "include_timestamps": include_timestamps}
    result = transcript.tools.get_transcript(args)
    texts = []
    while True:
        assert result["ok"] is True
        assert _wire_size(result) < 65536
        texts.append(result["transcript"])
        if result["next_cursor"] is None:
            break
        result = transcript.tools.get_transcript({**args, "next_cursor": result["next_cursor"]})
    assert len(texts) > 2
    if not include_timestamps:
        assert "".join(texts[:-1]).replace(" ", "") .startswith("\u8a71")
    assert texts[-1].endswith("tail")


def test_unsafe_track_keys_from_metadata_are_never_passed_to_ytdlp(transcript):
    transcript.metadata["subtitles"] = {"--exec=calc": TRACK, "en,de": TRACK, "en.*": TRACK}
    transcript.metadata["automatic_captions"] = {"en-orig": TRACK}
    result = transcript.tools.get_transcript({"url": URL})
    assert result["source"] == "auto_captions"
    assert caption_keys(transcript) == ["en-orig"]


def test_caption_429_logged_as_warning_with_exit_zero_still_counts(transcript, monkeypatch):
    server = transcript.server
    calls = []

    def warn_only(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"WARNING: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(server, "_run_subprocess", warn_only)
    result = transcript.tools.get_transcript({"url": URL})
    assert result["source"] == "whisper"
    assert result["reason"] == "captions_rate_limited"
    assert len(calls) == 1


def test_unknown_spoken_language_still_tries_matching_auto_track(transcript):
    transcript.metadata["subtitles"] = {}
    transcript.metadata.pop("language")
    transcript.metadata["automatic_captions"] = {"de": TRACK, "en": TRACK, "fr": TRACK}
    transcript.caption_text["en"] = "Auto English."
    result = transcript.tools.get_transcript({"url": URL})
    assert result["source"] == "auto_captions"
    assert result["translated"] is False
    assert result["transcript"] == "Auto English."


def test_default_language_fallback_says_why_and_requested_mismatch_is_not_cached(transcript, tmp_path):
    transcript.metadata["subtitles"] = {"fr": TRACK}
    transcript.metadata["language"] = "fr"
    transcript.metadata["automatic_captions"] = {}
    transcript.caption_text["fr"] = "Bonjour."
    result = transcript.tools.get_transcript({"url": URL})
    assert result["language"] == "fr"
    assert "English" in result["why"]
    transcript.calls.clear()
    asked = transcript.tools.get_transcript({"url": URL, "lang": "de"})
    assert asked["language"] == "fr" and "'de'" in asked["why"]
    assert not (tmp_path / "data" / "transcript-cache" / f"{VIDEO_ID}__de.json").exists()


def test_output_matches_its_schema_for_each_source(transcript):
    import jsonschema
    schema = transcript.tools.OUTPUT_SCHEMAS["get_transcript"]
    transcript.save_library([(0.0, 1.0, "Saved.")])
    jsonschema.validate(transcript.tools.get_transcript({"url": URL, "include_timestamps": True}), schema)
    transcript.folder = None
    jsonschema.validate(transcript.tools.get_transcript({"url": URL}), schema)
    transcript.metadata["subtitles"] = {}
    transcript.metadata["automatic_captions"] = {}
    jsonschema.validate(transcript.tools.get_transcript({"url": URL, "lang": "en-GB"}), schema)
    jsonschema.validate(transcript.tools.get_transcript({"url": "x"}), schema)
