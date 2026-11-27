"""/health names the model check for what it is (3.18.1).

`whisper_model_downloaded` says whether the selected model's files are on this
computer. `whisperx_model_loaded` stays as a deprecated alias with the same
value; whether a model is in memory is `transcription_worker.state`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import server

ROOT = Path(__file__).resolve().parent.parent


class Probe:
    path = "/health"
    client_address = ("127.0.0.1", 1)

    @staticmethod
    def _reject_bad_host() -> bool:
        return False

    def _send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


@pytest.mark.parametrize("on_disk", [True, False])
def test_health_reports_downloaded_and_keeps_the_old_alias(monkeypatch, on_disk):
    asked = []

    def downloaded(root, model):
        asked.append(model)
        return on_disk

    monkeypatch.setattr(server, "_read_settings", lambda: {"whisper_model": "small"})
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", downloaded)
    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": True, "checked": 0, "missing": 0})
    probe = Probe()
    server.Handler.do_GET(probe)
    assert probe.status == 200
    payload = probe.payload
    assert payload["whisper_model"] == "small"
    assert payload["whisper_model_downloaded"] is on_disk
    assert payload["whisperx_model_loaded"] is on_disk
    assert asked == ["small"]  # one disk check serves both keys
    # Files on disk are not a model in memory: that is the worker's state.
    assert payload["transcription_worker"]["state"] in {"not_loaded", "loaded", "running"}


def test_docs_call_the_old_key_an_alias_of_downloaded():
    api = (ROOT / "docs" / "v2-api.md").read_text(encoding="utf-8")
    row = re.search(r"^\| `whisperx_model_loaded` \|.*$", api, re.MULTILINE).group(0)
    assert "alias of `whisper_model_downloaded`" in row
    assert "not a model in memory" in row
    new_row = re.search(r"^\| `whisper_model_downloaded` \|.*$", api, re.MULTILINE).group(0)
    assert "transcription_worker" in new_row
    for name in ("README_server.md", "docs/v2-api.md"):
        assert '"whisper_model_downloaded": false' in (ROOT / name).read_text(encoding="utf-8")
    readme = (ROOT / "README_server.md").read_text(encoding="utf-8")
    assert "`whisperx_model_loaded` is a deprecated alias for `whisper_model_downloaded`" in readme
    assert "`transcription_worker.state`" in readme
