"""Update notices: the automatic check is off by default, and the tray and menu
bar read the saved result without any network call."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import uoink_tray  # noqa: E402


def _no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("update notices must not touch the network here")
    monkeypatch.setattr(server.urllib.request, "urlopen", fail)
    monkeypatch.setattr(uoink_tray.urllib.request, "urlopen", fail)


def test_auto_update_check_defaults_off_and_normalizes_boolean(monkeypatch):
    assert server._default_settings()["auto_update_check"] is False
    assert server._normalize_settings({})["auto_update_check"] is False
    assert server._normalize_settings({"auto_update_check": "yes"})["auto_update_check"] is False
    assert server._normalize_settings({"auto_update_check": True})["auto_update_check"] is True
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    assert server._public_settings({})["auto_update_check"] is False
    assert server._public_settings({"auto_update_check": True})["auto_update_check"] is True


def test_auto_update_check_saves_through_settings_handler(monkeypatch):
    written, responses = [], []
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_write_settings", written.append)
    monkeypatch.setattr(server, "_public_settings", lambda data=None: data or {})
    handler._handle_settings_post({"auto_update_check": True})
    assert written[0]["auto_update_check"] is True
    handler._handle_settings_post({"auto_update_check": "true"})
    assert responses[-1] == (400, {"ok": False, "error": "auto_update_check must be boolean"})


def test_cached_read_makes_no_network_call(monkeypatch, tmp_path):
    _no_network(monkeypatch)
    cache = tmp_path / "update_check.json"
    monkeypatch.setattr(server, "_UPDATE_CACHE_PATH", cache)
    monkeypatch.setattr(server, "VERSION", "3.15.0")
    # No cache yet: nothing to report, still no request.
    empty = server._cached_update_result()
    assert empty["update_available"] is False and empty["latest"] is None
    # An old cache is still returned (no TTL) and is judged against this version.
    cache.write_text(json.dumps({
        "latest": "3.16.0", "url": "https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0",
        "checked_at": "2026-11-01T00:00:00", "_ts": 1.0}), encoding="utf-8")
    result = server._cached_update_result()
    assert result["update_available"] is True
    assert result["latest"] == "3.16.0" and result["cached"] is True
    monkeypatch.setattr(server, "VERSION", "3.16.0")
    assert server._cached_update_result()["update_available"] is False


def test_cached_only_query_serves_the_saved_result(monkeypatch, tmp_path):
    _no_network(monkeypatch)
    monkeypatch.setattr(server, "_UPDATE_CACHE_PATH", tmp_path / "missing.json")
    sent = []
    handler = object.__new__(server.Handler)
    handler.path = "/update/check?cached_only=1"
    handler._require_token = lambda: True
    handler._send_json = lambda status, payload: sent.append((status, payload))
    handler._handle_update_check()
    assert sent[0][0] == 200 and sent[0][1]["ok"] is True
    assert sent[0][1]["update_available"] is False


def test_tray_item_text_follows_the_saved_result():
    assert uoink_tray.update_item_latest(None) is None
    assert uoink_tray.update_item_latest({"update_available": False, "latest": "3.16.0"}) is None
    assert uoink_tray.update_item_latest({"update_available": True, "latest": None}) is None
    assert uoink_tray.update_item_latest({"update_available": True, "latest": "3.16.0"}) == "3.16.0"


def _tray(tmp_path):
    return uoink_tray.UoinkTray(
        host="127.0.0.1", port=1, version="3.15.0", token_path=tmp_path / "t",
        output_dir=tmp_path, dashboard_url="http://127.0.0.1:1/dashboard",
        stop_callback=lambda: None)


def test_tray_asks_the_local_helper_only(monkeypatch, tmp_path):
    tray = _tray(tmp_path)
    assert tray.update_title() is None
    asked = []

    def fake_get(path, *, auth, timeout=2.0):
        asked.append(path)
        return {"update_available": True, "latest": "3.16.0"}, 200
    monkeypatch.setattr(tray, "_get", fake_get)
    tray._refresh_update()
    assert asked == ["/update/check?cached_only=1"]
    assert tray.update_title() == "Update available: 3.16.0"
    # The helper going away (or a cleared cache) removes the item.
    monkeypatch.setattr(tray, "_get", lambda *a, **k: (None, None))
    tray._refresh_update()
    assert tray.update_title() is None


def test_menu_bar_client_inherits_the_update_item():
    from helper import mac_menubar
    source = Path(mac_menubar.__file__).read_text(encoding="utf-8")
    assert issubclass(mac_menubar.MenuClient, uoink_tray.UoinkTray)
    assert "client.update_title()" in source and "_refresh_update()" in source
