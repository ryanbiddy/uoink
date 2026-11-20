"""Windows: clicking Uoink in the Start menu while it runs brings up the dashboard.

Bug (3.2 to 3.17): the Start menu and desktop shortcuts run
``uoink_supervisor.py --show-dashboard``. With a resident supervisor holding the
lock, the second launch opened the dashboard only when the saved status was
already "running". A click while the helper was still starting (login, an
upgrade, a crash restart) exited silently. The Mac answers such a click by
queueing it for the resident supervisor (3.11.2); Windows now does the same.

No window is opened: show_running_dashboard and Supervisor are replaced.
"""
from __future__ import annotations

import io

import pytest

import uoink_supervisor


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setattr(uoink_supervisor.sys, "platform", "win32")
    monkeypatch.setattr(uoink_supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(uoink_supervisor, "login_session", lambda: "session")
    return uoink_supervisor


def _wait_for(items, timeout=1.0):
    deadline = uoink_supervisor.time.monotonic() + timeout
    while not items and uoink_supervisor.time.monotonic() < deadline:
        uoink_supervisor.time.sleep(0.01)
    return items


def _next_tick():
    start = uoink_supervisor.time.monotonic()
    while uoink_supervisor.time.monotonic() <= start:
        uoink_supervisor.time.sleep(0.001)


@pytest.mark.parametrize("state", ["starting", "backoff"])
def test_click_while_the_helper_starts_is_queued_for_the_resident(windows, monkeypatch, tmp_path, state):
    shown = []
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root) or True)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda *a, **k: pytest.fail("started a second helper"))
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": state})
    with windows.admission(tmp_path) as owned:  # The resident supervisor holds the lock.
        assert owned
        assert windows.main(["--show-dashboard"]) == 0
    assert shown == []
    assert windows.take_dashboard_request(tmp_path) is not None


def test_click_while_the_helper_is_ready_opens_the_dashboard_now(windows, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root) or True)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda *a, **k: pytest.fail("started a second helper"))
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": "running"})
    with windows.admission(tmp_path) as owned:
        assert owned
        assert windows.main(["--show-dashboard"]) == 0
    assert shown == [tmp_path]
    assert windows.take_dashboard_request(tmp_path) is None


class _Fake:
    """A supervisor that owns the lock and records its ready callback."""
    owned = True
    captured: dict = {}

    def __init__(self, root, command, url, **kw):
        _Fake.captured = dict(kw, command=command)

    def run(self):
        return 0


def test_login_resident_answers_a_click_made_while_it_started(windows, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(windows, "Supervisor", _Fake)
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    assert windows.main(["--startup"]) == 0  # The scheduled login start: no flag.
    on_ready = _Fake.captured["on_ready"]
    assert on_ready is not None
    windows.request_dashboard_later(tmp_path)  # A Start menu click during startup.
    on_ready(False)  # The login start opens no window of its own.
    assert _wait_for(shown) == [tmp_path]
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()


def test_a_click_before_the_launch_window_is_not_opened_twice(windows, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(windows, "Supervisor", _Fake)
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    assert windows.main(["--show-dashboard"]) == 0
    assert "--show-dashboard" in _Fake.captured["command"]
    on_ready = _Fake.captured["on_ready"]
    windows.request_dashboard_later(tmp_path)  # A second click while it started.
    _next_tick()
    on_ready(True)  # server.py --show-dashboard already opened a window.
    on_ready(False)
    assert shown == []
    _next_tick()
    windows.request_dashboard_later(tmp_path)  # A later click.
    on_ready(False)
    assert _wait_for(shown) == [tmp_path]


def test_every_windows_start_with_the_flag_reports_its_own_window(monkeypatch, tmp_path):
    """Windows passes --show-dashboard on every start (not first_args), and each
    such start's helper opens the dashboard itself, so its first ready tick
    must say so or a queued click would open a second window."""
    ready = []

    class Child:
        pid = 4242

        def __init__(self):
            self.stdout, self.polls = io.BytesIO(b""), 0

        def poll(self):
            self.polls += 1
            return None if self.polls < 4 else 1

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(uoink_supervisor.subprocess, "Popen", lambda command, **k: Child())
    supervisor = uoink_supervisor.Supervisor(
        tmp_path, ["pythonw", "server.py", "--show-dashboard"], "http://127.0.0.1:1/health",
        session="s", first_args=[], on_ready=ready.append, backoff=(0,), poll=0,
        probe=lambda *a: True, notify=lambda state: None, sleep=lambda seconds: None)
    assert supervisor.loop() == 0
    assert ready.count(True) == 2  # One per start: the first and the crash restart.
