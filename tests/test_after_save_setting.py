"""The "After a save" setting (3.17.0): the helper's /settings holds the choice.

The browser extension keeps a chrome.storage copy; the dashboard edits this one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import server

DASHBOARD = Path(__file__).resolve().parent.parent / "assets" / "dashboard" / "index.html"


def _handler(monkeypatch, stored=None):
    written, responses = [], []
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(server, "_read_settings", lambda: dict(stored or {}))
    monkeypatch.setattr(server, "_write_settings", written.append)
    monkeypatch.setattr(server, "_public_settings", lambda data=None: data or {})
    return handler, written, responses


def test_default_is_stay_on_the_page():
    assert server._default_settings()["after_save"] == "stay"
    assert server._normalize_after_save(None) == "stay"
    assert server._normalize_after_save("CLAUDE") == "claude"
    assert server._normalize_after_save("sepia") == "stay"


@pytest.mark.parametrize("choice", ["stay", "claude", "chatgpt", "copy"])
def test_each_choice_saves(monkeypatch, choice):
    handler, written, responses = _handler(monkeypatch)
    handler._handle_settings_post({"after_save": choice})
    assert written[-1]["after_save"] == choice
    assert responses[-1][0] == 200


def test_unknown_choice_is_refused(monkeypatch):
    handler, written, responses = _handler(monkeypatch)
    for bad in ("open-everything", 7, ["claude"]):
        handler._handle_settings_post({"after_save": bad})
        assert responses[-1][0] == 400
    assert written == []


def test_empty_choice_resets_to_stay(monkeypatch):
    handler, written, _ = _handler(monkeypatch, {"after_save": "claude"})
    handler._handle_settings_post({"after_save": ""})
    assert written[-1]["after_save"] == "stay"


def test_public_settings_report_the_choice(monkeypatch):
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    pub = server._public_settings({"after_save": "chatgpt"})
    assert pub["after_save"] == "chatgpt"
    assert pub["after_save_supported"] == ["stay", "claude", "chatgpt", "copy"]
    assert server._public_settings({})["after_save"] == "stay"


def test_dashboard_settings_has_the_control():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert 'afterSave: ["after_save", "stay"],' in html
    assert 'id="afterSave"' in html
    for label in ("Stay on the page", "Copy, then open Claude", "Copy, then open ChatGPT", "Copy only"):
        assert label in html
