"""The Settings menu opens the dashboard route without starting the tray."""
import pytest

import uoink_tray as tray


@pytest.mark.parametrize("dashboard_url,expected_url", [
    (
        "http://127.0.0.1:18116/dashboard",
        "http://127.0.0.1:18116/dashboard#settings",
    ),
    (
        "http://127.0.0.1:18116/dashboard?from=tray&return=%23library",
        "http://127.0.0.1:18116/dashboard?from=tray&return=%23library#settings",
    ),
    (
        "http://127.0.0.1:18116/dashboard#settings/app",
        "http://127.0.0.1:18116/dashboard#settings",
    ),
    (
        "http://127.0.0.1:18116/dashboard?from=tray&return=%23library#library",
        "http://127.0.0.1:18116/dashboard?from=tray&return=%23library#settings",
    ),
])
def test_settings_opens_dashboard_settings(monkeypatch, tmp_path, dashboard_url, expected_url):
    instance = tray.UoinkTray(
        host="127.0.0.1", port=18116, version="3.17.0",
        token_path=tmp_path / "token.txt", output_dir=tmp_path / "library",
        dashboard_url=dashboard_url, stop_callback=lambda: None,
    )
    opened = []
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)

    instance._open_settings()

    assert opened == [expected_url]
