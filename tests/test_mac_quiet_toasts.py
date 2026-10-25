"""macOS keeps desktop alerts for capture results and helper failures.

osascript alerts are credited to Script Editor until Uoink has its own
notifier, and a Mac launch already opens the dashboard or splash.
"""
from __future__ import annotations

import server


def test_only_darwin_limits_desktop_alerts(monkeypatch):
    for platform, limited in (("darwin", True), ("win32", False), ("linux", False)):
        monkeypatch.setattr(server.sys, "platform", platform)
        assert server._desktop_alerts_for_results_only() is limited


def test_discovered_items_go_to_activity_on_macos(monkeypatch):
    monkeypatch.setattr(server, "_desktop_alerts_for_results_only", lambda: True)
    toasts, queued = [], []
    monkeypatch.setattr(server, "maybe_toast", lambda *a, **k: toasts.append(a))
    monkeypatch.setattr(server, "_queue_dashboard_notification",
                        lambda title, body, *, reason: queued.append((title, body, reason)))
    service = type("Service", (), {"run_claimed_poll": lambda self, claim: {
        "ok": True, "inserted": 3, "enrollment": {"enrolled": 3}}})()
    monkeypatch.setattr(server, "_source_service", lambda: service)
    server._poll_source_for_watch({"source_id": "src-1", "owner_token": "lease"})
    assert toasts == []
    assert queued == [("New source items", "3 new item(s) discovered from a watched source.",
                       "macOS desktop alerts are kept for results")]


def test_capture_results_still_alert_on_macos(monkeypatch):
    monkeypatch.setattr(server, "_desktop_alerts_for_results_only", lambda: True)
    monkeypatch.setattr(server, "_read_settings", lambda: {"notifications_enabled": True})
    monkeypatch.setattr(server._platform, "is_foreground_fullscreen", lambda: False)
    shown = []
    monkeypatch.setattr(server._platform, "show_toast", lambda title, body, **k: shown.append(title))
    assert server.maybe_toast("Uoinked", "A video\nSaved to Uncategorized") is True
    assert shown == ["Uoinked"]


def test_mac_launch_skips_the_ready_toast_but_windows_keeps_it():
    source = (server.HERE / "server.py").read_text(encoding="utf-8")
    block = source[source.index('log.info("toast: skipped regular ready toast while first-run splash is visible")'):]
    block = block[:block.index('"Uoink is Active & Ready ✓"')]
    # Mac returns before the migration and ready toasts; others reach both.
    assert block.index("elif _desktop_alerts_for_results_only():") < block.index("elif not _maybe_post_migration_toast():")
