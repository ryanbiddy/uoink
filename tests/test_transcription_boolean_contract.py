from __future__ import annotations

import sys
import types

import pytest

import podcasts
import server
import uoink_mcp_tools
import whisper_runner


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("consent_given", "false"),
        ("diarize", "false"),
        ("diarize", None),
    ),
)
def test_mcp_rejects_non_boolean_transcription_flags_before_episode_lookup(
    monkeypatch, field, value
):
    uoink_mcp_tools.bind_backend(server)
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(
        podcasts,
        "get_episode",
        lambda *_args: pytest.fail(
            "malformed consent reached episode lookup"),
    )

    result = uoink_mcp_tools.transcribe_podcast_episode({
        "episode_id": 1,
        field: value,
    })

    assert result == {
        "ok": False,
        "error": f"{field} must be a boolean",
    }


class _ResponseCapture:
    def _send_json(self, status, payload):
        return status, payload


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("consent_given", "false"),
        ("diarize", "false"),
        ("diarize", None),
    ),
)
def test_http_rejects_non_boolean_transcription_flags_before_episode_lookup(
    monkeypatch, field, value
):
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(
        podcasts,
        "get_episode",
        lambda *_args: pytest.fail(
            "malformed consent reached episode lookup"),
    )

    status, result = server.Handler._handle_podcasts_episode_transcribe(
        _ResponseCapture(),
        {"episode_id": 1, field: value},
    )

    assert status == 400
    assert result == {
        "ok": False,
        "error": f"{field} must be a boolean",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("consent_given", "false"),
        ("diarize", "false"),
        ("diarize", None),
    ),
)
def test_transcription_boundary_rejects_non_booleans_before_model_load(
    tmp_path, monkeypatch, field, value
):
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"fixture")
    monkeypatch.setattr(whisper_runner, "_WHISPERX_AVAILABLE", True)
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        types.SimpleNamespace(
            load_model=lambda *_args, **_kwargs: pytest.fail(
                "malformed consent reached model loading"),
        ),
    )
    options = {"consent_given": True, "diarize": False}
    options[field] = value

    with pytest.raises(ValueError, match=f"{field} must be a boolean"):
        whisper_runner.transcribe_audio(
            audio,
            data_root=tmp_path / "data",
            **options,
        )


def test_real_false_consent_blocks_an_uncached_model_before_load(
    tmp_path, monkeypatch
):
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"fixture")
    monkeypatch.setattr(whisper_runner, "_WHISPERX_AVAILABLE", True)
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        types.SimpleNamespace(
            load_model=lambda *_args, **_kwargs: pytest.fail(
                "false consent reached model loading"),
        ),
    )

    with pytest.raises(PermissionError, match="consent_given=False"):
        whisper_runner.transcribe_audio(
            audio,
            data_root=tmp_path / "data",
            consent_given=False,
        )
