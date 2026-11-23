"""Windows: clicking Uoink in the Start menu while it runs brings up the dashboard.

Bug (3.2 to 3.17): the Start menu and desktop shortcuts run
``uoink_supervisor.py --show-dashboard``. With a resident supervisor holding the
lock, the second launch opened the dashboard only when the saved status was
already "running". A click while the helper was still starting (login, an
upgrade, a crash restart) exited silently. The Mac answers such a click by
queueing it for the resident supervisor (3.11.2); Windows now does the same.

Windows also passed --show-dashboard to every helper start, so each crash
restart popped the dashboard at the user. Like the Mac, only the first start
gets it now.

No window is opened: show_running_dashboard and the helper process are fakes.
"""
from __future__ import annotations

import io

import pytest

import uoink_supervisor

REAL_SUPERVISOR = uoink_supervisor.Supervisor


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


@pytest.mark.parametrize("state", ["starting", "backoff", "running"])
def test_click_while_a_supervisor_runs_is_queued_for_it(windows, monkeypatch, tmp_path, state):
    # "running" too: the file can still say so for a moment after a crash, and
    # only the resident can coalesce with the window its own launch opened.
    shown = []
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root) or True)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda *a, **k: pytest.fail("started a second helper"))
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": state})
    with windows.admission(tmp_path) as owned:  # The resident supervisor holds the lock.
        assert owned
        assert windows.main(["--show-dashboard"]) == 0
    assert shown == []
    assert windows.read_json(tmp_path / windows.DASHBOARD_REQUEST)["session"] == "session"
    assert windows.take_dashboard_request(tmp_path) is not None


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
    assert _Fake.captured["first_args"] == ["--show-dashboard"]
    assert "--show-dashboard" not in _Fake.captured["command"]
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


class _Child:
    """A helper that answers health for ``alive`` polls, then exits with ``code``."""
    pid = 4242

    def __init__(self, alive, code):
        self.stdout, self.alive, self.code, self.polls = io.BytesIO(b""), alive, code, 0

    def poll(self):
        self.polls += 1
        return None if self.polls <= self.alive else self.code

    def wait(self, timeout=None):
        return self.code


def _run_main_with_helpers(windows, monkeypatch, argv, children):
    """windows.main(argv) with the real Supervisor and fake helper processes."""
    commands, shown = [], []
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    monkeypatch.setattr(windows.subprocess, "Popen",
                        lambda command, **k: commands.append(command) or children.pop(0))
    monkeypatch.setattr(windows, "Supervisor", lambda root, command, url, **kw: REAL_SUPERVISOR(
        root, command, url, **dict(kw, backoff=(0, 0), poll=0, probe=lambda *a: True,
                                   notify=lambda state: None, sleep=lambda seconds: None)))
    assert windows.main(argv) == 0
    return commands, shown


def test_a_crash_restart_does_not_reopen_the_dashboard(windows, monkeypatch, tmp_path):
    # Start menu click: the helper opens its window, runs, crashes, restarts.
    commands, shown = _run_main_with_helpers(
        windows, monkeypatch, ["--show-dashboard"], [_Child(alive=5, code=1), _Child(alive=5, code=0)])
    assert len(commands) == 2
    assert "--show-dashboard" in commands[0]
    assert "--show-dashboard" not in commands[1], "a crash restart popped the dashboard again"
    _wait_for(shown, timeout=0.2)
    assert shown == []
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()


def test_a_launch_that_dies_before_its_window_still_opens_the_dashboard(windows, monkeypatch, tmp_path):
    # The click's own start never got ready; the restart has no flag, so the
    # supervisor answers the click itself once the restarted helper is ready.
    commands, shown = _run_main_with_helpers(
        windows, monkeypatch, ["--show-dashboard"], [_Child(alive=0, code=1), _Child(alive=5, code=0)])
    assert "--show-dashboard" in commands[0] and "--show-dashboard" not in commands[1]
    assert _wait_for(shown) == [tmp_path]


def test_a_click_during_sign_in_survives_the_login_start(windows, monkeypatch, tmp_path):
    # Last boot's state, then a click that lost the lock to the login start.
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": "stopped", "session": "last-boot"})
    windows.request_dashboard_later(tmp_path, session="session")
    monkeypatch.setattr(windows.subprocess, "Popen", lambda command, **k: _Child(alive=0, code=0))
    REAL_SUPERVISOR(tmp_path, ["pythonw", "server.py"], "http://127.0.0.1:1/health",
                    session="session", startup=True, poll=0, sleep=lambda seconds: None).run()
    assert windows.take_dashboard_request(tmp_path) is not None


@pytest.mark.parametrize("pending", [None, "last-boot"])
def test_a_new_login_drops_an_open_from_an_earlier_one(windows, monkeypatch, tmp_path, pending):
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": "stopped", "session": "last-boot"})
    windows.request_dashboard_later(tmp_path, session=pending)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda command, **k: _Child(alive=0, code=0))
    REAL_SUPERVISOR(tmp_path, ["pythonw", "server.py"], "http://127.0.0.1:1/health",
                    session="session", startup=True, poll=0, sleep=lambda seconds: None).run()
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()


def test_a_quiet_upgrade_start_ignores_an_older_click(windows, monkeypatch, tmp_path):
    # A click queued as the old resident exited must not pop a window during a
    # silent upgrade minutes later. A click during the upgrade still opens.
    shown = []
    windows.request_dashboard_later(tmp_path, uoink_supervisor.time.monotonic(), session="session")
    _next_tick()
    monkeypatch.setattr(windows, "Supervisor", _Fake)
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    assert windows.main(["--quiet"]) == 0
    on_ready = _Fake.captured["on_ready"]
    on_ready(False)
    _wait_for(shown, timeout=0.2)
    assert shown == []
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()  # Taken and dropped.
    _next_tick()
    windows.request_dashboard_later(tmp_path, session="session")
    on_ready(False)
    assert _wait_for(shown) == [tmp_path]
