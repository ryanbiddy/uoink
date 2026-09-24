from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, FakeAdapter, FakeBackend, make_service, snapshot, turn_on,
)

import _platform  # noqa: E402
import index as index_mod  # noqa: E402
import podcasts  # noqa: E402
import server  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def test_notification_setting_defaults_on_and_normalizes_boolean(monkeypatch):
    assert server._default_settings()["notifications_enabled"] is True
    assert server._normalize_settings({})["notifications_enabled"] is True
    assert server._normalize_settings({"notifications_enabled": 0})[
        "notifications_enabled"
    ] is False
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    public = server._public_settings({"notifications_enabled": False})
    assert public["notifications_enabled"] is False


def test_notification_setting_saves_through_settings_handler(monkeypatch):
    written = []
    responses = []
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: responses.append(
        (status, payload)
    )
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_write_settings", written.append)
    monkeypatch.setattr(server, "_public_settings", lambda data=None: data or {})

    handler._handle_settings_post({"notifications_enabled": False})

    assert written[0]["notifications_enabled"] is False
    assert responses[-1][0] == 200
    assert responses[-1][1]["settings"]["notifications_enabled"] is False

    handler._handle_settings_post({"notifications_enabled": "false"})
    assert responses[-1] == (
        400,
        {
            "ok": False,
            "error": "notifications_enabled must be boolean",
        },
    )


def test_disabled_notification_is_queued_without_desktop_toast(monkeypatch):
    queued = []
    shown = []
    monkeypatch.setattr(
        server,
        "_read_settings",
        lambda: {"notifications_enabled": False},
    )
    monkeypatch.setattr(
        server,
        "_queue_dashboard_notification",
        lambda title, body, *, reason: queued.append((title, body, reason)),
    )
    monkeypatch.setattr(
        server._platform,
        "show_toast",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )
    monkeypatch.setattr(
        server._platform,
        "is_foreground_fullscreen",
        lambda: False,
    )

    assert server.maybe_toast("New episode", "Saved in Uoink") is False
    assert queued == [
        ("New episode", "Saved in Uoink", "notifications disabled")
    ]
    assert shown == []


def test_fullscreen_courtesy_queues_even_when_setting_is_on(monkeypatch):
    queued = []
    monkeypatch.setattr(
        server,
        "_read_settings",
        lambda: {"notifications_enabled": True},
    )
    monkeypatch.setattr(
        server,
        "_queue_dashboard_notification",
        lambda title, body, *, reason: queued.append((title, body, reason)),
    )
    monkeypatch.setattr(
        server._platform,
        "is_foreground_fullscreen",
        lambda: True,
    )
    desktop_toast = monkeypatch.setattr(
        server._platform,
        "show_toast",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("desktop toast must stay suppressed")
        ),
    )

    assert server.maybe_toast("Published", "Episode is ready") is False
    assert queued == [
        ("Published", "Episode is ready", "foreground fullscreen")
    ]
    assert desktop_toast is None


def test_allowed_notification_uses_existing_platform_path(monkeypatch):
    shown = []
    monkeypatch.setattr(
        server,
        "_read_settings",
        lambda: {"notifications_enabled": True},
    )
    monkeypatch.setattr(
        server._platform,
        "is_foreground_fullscreen",
        lambda: False,
    )
    monkeypatch.setattr(
        server._platform,
        "show_toast",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )
    monkeypatch.setattr(
        server,
        "_queue_dashboard_notification",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("allowed toast must not be queued")
        ),
    )

    assert server.maybe_toast("Ready", "Uoink is running", "icon.ico") is True
    assert shown == [
        (("Ready", "Uoink is running"), {"icon_path": "icon.ico"})
    ]


def test_queued_notification_uses_the_durable_activity_job_shape(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        server,
        "_add_job_record",
        lambda job: recorded.append(job) or job,
    )

    public = server._queue_dashboard_notification(
        "New podcast episode",
        "A watched feed has one new episode.",
        reason="notifications disabled",
    )

    assert public["kind"] == "notification"
    assert public["state"] == "completed"
    assert public["title"] == "New podcast episode"
    assert public["message"] == "A watched feed has one new episode."
    assert public["result"] == {"suppressed_reason": "notifications disabled"}
    assert server._validate_persisted_job(public)["kind"] == "notification"


def test_fullscreen_probe_is_bounded_and_ignores_shell_windows():
    full = ((0, 0, 1920, 1080), (0, 0, 1920, 1080), "GameWindow")
    inset = ((20, 20, 1900, 1060), (0, 0, 1920, 1080), "GameWindow")
    shell = ((0, 0, 1920, 1080), (0, 0, 1920, 1080), "WorkerW")

    assert _platform.is_foreground_fullscreen(
        platform_name="win32", bounds_probe=lambda: full
    ) is True
    assert _platform.is_foreground_fullscreen(
        platform_name="win32", bounds_probe=lambda: inset
    ) is False
    assert _platform.is_foreground_fullscreen(
        platform_name="win32", bounds_probe=lambda: shell
    ) is False
    assert _platform.is_foreground_fullscreen(
        platform_name="linux", bounds_probe=lambda: full
    ) is False


def test_dashboard_and_installer_surfaces_honor_the_setting():
    dashboard = (ROOT / "assets" / "dashboard" / "index.html").read_text(
        encoding="utf-8"
    )
    stop_script = (ROOT / "installer" / "templates" / "stop-server.ps1").read_text(
        encoding="utf-8"
    )

    assert 'id="notificationsEnabled"' in dashboard
    assert "notifications_enabled: els.notificationsEnabled.checked" in dashboard
    assert 'job.kind === "notification"' in dashboard
    assert "$settings.notifications_enabled" in stop_script
    assert "if ($stoppedAny -and $notificationsEnabled)" in stop_script


def test_next_due_source_tick_queues_without_a_desktop_toast(
    tmp_path,
    monkeypatch,
):
    """Phase 3 (run AM): the tick claims the due standing-source poll through
    the subscription service and raises its discovery notification when a
    consented source enrolls newly observed items. The Phase 0 protection is
    unchanged: with notifications off that notification is queued to the
    dashboard Activity stream and never becomes a desktop toast."""
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(idx, "https://quiet.example/feed.xml")
    # The old add route stamps the source with the real clock; a service clock
    # at or after that instant is due immediately without a clock regression.
    clock = Clock(int(time.time() * 1000))
    adapter = FakeAdapter(
        [snapshot(["quiet-episode"], titles={"quiet-episode": "Quiet episode"})]
    )
    service = make_service(idx, clock=clock, adapter=adapter, backend=FakeBackend())
    turn_on(service, feed["source_id"])
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_source_service", lambda: service)
    monkeypatch.setattr(
        server,
        "_read_settings",
        lambda: {"notifications_enabled": False},
    )
    monkeypatch.setattr(
        server._platform,
        "is_foreground_fullscreen",
        lambda: False,
    )
    queued = []
    monkeypatch.setattr(
        server,
        "_queue_dashboard_notification",
        lambda title, body, *, reason: queued.append((title, body, reason)),
    )
    monkeypatch.setattr(
        server._platform,
        "show_toast",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("due-source tick must not create a desktop toast")
        ),
    )

    results = server._podcast_feed_scheduler_tick()

    assert [c["source_id"] for c in adapter.calls] == [feed["source_id"]]
    assert results[0]["ok"] is True and results[0]["inserted"] == 1
    assert results[0]["enrollment"]["enrolled"] == 1
    assert queued == [
        (
            "New source items",
            "1 new item(s) discovered from a watched source.",
            "notifications disabled",
        )
    ]
    idx.close()
