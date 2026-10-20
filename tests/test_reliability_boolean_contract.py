"""Strict Boolean consent at the transcript-reliability download boundary."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


class _FakeHandler:
    _handle_reliability_compute = server.Handler._handle_reliability_compute

    def _send_json(self, status, payload):
        self.response = (status, payload)
        return self.response


@pytest.mark.parametrize("field", ["allow_model_download", "force"])
@pytest.mark.parametrize("bad_value", ["false", "true", 0, 1, None, [], {}])
def test_http_rejects_non_boolean_flags_before_compute(
    monkeypatch, field, bad_value
):
    def _must_not_compute(*_args, **_kwargs):
        pytest.fail("malformed Boolean reached reliability compute")

    monkeypatch.setattr(server, "_compute_transcript_reliability", _must_not_compute)
    handler = _FakeHandler()

    assert handler._handle_reliability_compute(
        "video-1", {field: bad_value}
    ) == (
        400,
        {"ok": False, "error": f"{field} must be a boolean"},
    )


def test_http_preserves_boolean_flags_and_safe_defaults(monkeypatch):
    calls = []

    def _capture(video_id, **kwargs):
        calls.append((video_id, kwargs))
        return {"ok": True}

    monkeypatch.setattr(server, "_compute_transcript_reliability", _capture)

    explicit = _FakeHandler()
    explicit._handle_reliability_compute(
        "video-1", {"allow_model_download": False, "force": True}
    )
    assert explicit.response == (200, {"ok": True})
    omitted = _FakeHandler()
    omitted._handle_reliability_compute("video-2", {})
    assert omitted.response == (
        200,
        {"ok": True},
    )
    assert calls == [
        (
            "video-1",
            {
                "threshold": server.RELIABILITY_DEFAULT_THRESHOLD,
                "allow_model_download": False,
                "force": True,
            },
        ),
        (
            "video-2",
            {
                "threshold": server.RELIABILITY_DEFAULT_THRESHOLD,
                "allow_model_download": False,
                "force": False,
            },
        ),
    ]


@pytest.mark.parametrize("field", ["allow_model_download", "force"])
@pytest.mark.parametrize("bad_value", ["false", "true", 0, 1, None, [], {}])
def test_core_rejects_non_boolean_flags_before_item_lookup(
    monkeypatch, field, bad_value
):
    def _must_not_lookup(*_args, **_kwargs):
        pytest.fail("malformed Boolean crossed the final reliability boundary")

    monkeypatch.setattr(server, "_folder_for_video_id", _must_not_lookup)
    kwargs = {"allow_model_download": False, "force": False}
    kwargs[field] = bad_value

    with pytest.raises(TypeError, match=rf"^{field} must be a boolean$"):
        server._compute_transcript_reliability("video-1", **kwargs)


def test_false_download_consent_never_loads_or_downloads_model(
    monkeypatch, tmp_path
):
    sidecar = tmp_path / f"{tmp_path.name}.json"
    sidecar.write_text(
        json.dumps(
            {
                "video_id": "video-1",
                "url": "https://www.youtube.com/watch?v=video-1",
                "transcript": [{"text": "saved transcript"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        server,
        "_reliability_model_status",
        lambda _model=None: {"model": "tiny", "cached": False},
    )
    monkeypatch.setattr(
        server,
        "_download_reliability_audio",
        lambda *_args, **_kwargs: pytest.fail("audio download must not start"),
    )
    monkeypatch.setattr(
        server.uoink_reliability,
        "detect_unreliable_spans",
        lambda *_args, **_kwargs: pytest.fail("model must not load"),
    )

    result = server._compute_transcript_reliability(
        "video-1",
        folder=tmp_path,
        allow_model_download=False,
        force=False,
    )

    assert result["ok"] is False
    assert result["reliability"]["reason"] == "model_not_downloaded"
