"""Headless checks for the Windows shortcut, cold startup and recovery opens."""
from __future__ import annotations

import io

import pytest

import uoink_supervisor

REAL_SUPERVISOR = uoink_supervisor.Supervisor


@pytest.fixture
def windows(monkeypatch, tmp_path):
    import uoink_dashboard
    monkeypatch.setattr(uoink_dashboard, "has_window_candidate", lambda: False)
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


@pytest.mark.parametrize("already_ready", [True, False])
def test_installed_shortcut_opens_in_clicking_process(windows, monkeypatch, tmp_path, already_ready):
    import os
    import uoink_dashboard
    import uoink_install_isolation as iso
    from pathlib import Path
    shortcut = (Path(windows.__file__).parent / "installer" / "uoink.iss").read_text(encoding="utf-8")
    entry = shortcut.split('Name: "{group}\\Uoink";', 1)[1].split("Check:", 1)[0]
    assert 'Filename: "{app}\\python\\pythonw.exe"' in entry
    assert 'Parameters: """{app}\\uoink_supervisor.py"" --show-dashboard"' in entry
    calls = []
    readiness = iter([already_ready, True, True])
    monkeypatch.setattr(windows, "ready", lambda url: next(readiness))
    monkeypatch.setattr(uoink_dashboard, "main", lambda: calls.append(os.getpid()) or 0)
    monkeypatch.setattr(windows.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicate resident"))
    windows.write_json(tmp_path / windows.STATE_FILE, {"status": "running", "session": "other-login"})
    with windows.admission(tmp_path) as owned:
        assert owned
        assert windows.main(["--show-dashboard", *iso.child_argv()]) == 0
    assert calls == [os.getpid()]
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()


@pytest.mark.parametrize("ready_session,expected", [("session", [True]), ("other-session", [])])
def test_cold_click_starts_only_helper_in_background(windows, monkeypatch, tmp_path, ready_session, expected):
    import uoink_dashboard
    import uoink_install_isolation as iso
    sessions = iter(["session", ready_session])
    health = iter([False, True])
    monkeypatch.setattr(windows, "login_session", lambda: next(sessions))
    monkeypatch.setattr(windows, "ready", lambda url: next(health))
    started, shown = [], []
    monkeypatch.setattr(windows.subprocess, "Popen", lambda cmd, **kwargs: started.append(cmd))
    monkeypatch.setattr(uoink_dashboard, "main", lambda: shown.append(True) or 0)
    with iso.bound_isolation(profile=tmp_path, port=18123):
        assert windows.open_windows_app(tmp_path, False) == 0
        assert started == [[windows.sys.executable, "-B", "-s", str(windows.HERE / "uoink_supervisor.py"),
                            "--resident", *iso.child_argv()]]
    assert shown == expected


def test_resident_drops_deferred_request_from_other_windows_session(windows, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(windows, "Supervisor", _Fake)
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    assert windows.main(["--startup"]) == 0
    windows.request_dashboard_later(tmp_path, session="other-session")
    _Fake.captured["on_ready"](False)
    assert _wait_for(shown, timeout=0.1) == []


def test_reopen_visible_dashboard_while_resident_helper_restarts(windows, monkeypatch, tmp_path):
    import uoink_dashboard
    from unittest.mock import Mock
    probe = Mock(side_effect=[False, AssertionError("waited for helper with an open dashboard")])
    monkeypatch.setattr(windows, "ready", probe)
    monkeypatch.setattr(uoink_dashboard, "has_window_candidate", lambda: True)
    opened = Mock(return_value=0)
    monkeypatch.setattr(uoink_dashboard, "main", opened)
    with windows.admission(tmp_path) as owned:
        assert owned and windows.open_windows_app(tmp_path, False) == 0
    opened.assert_called_once()


def test_isolated_shortcut_reopens_dashboard_in_clicked_server_process(monkeypatch):
    import server
    import uoink_dashboard
    monkeypatch.setattr(server, "_existing_server_responds", lambda: True)
    monkeypatch.delenv("UOINK_SUPERVISOR_RUN_ID", raising=False)
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "_spawn_dashboard_window", lambda **kwargs: pytest.fail("delegated click"))
    called = []
    monkeypatch.setattr(uoink_dashboard, "main", lambda: called.append(True) or 0)
    with pytest.raises(SystemExit) as exit_status:
        server.main(show_dashboard=True)
    assert exit_status.value.code == 0 and called == [True]


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
    windows.request_dashboard_later(tmp_path, session="session")  # A Start menu click during startup.
    on_ready(False)  # The login start opens no window of its own.
    assert _wait_for(shown) == [tmp_path]
    assert not (tmp_path / windows.DASHBOARD_REQUEST).exists()


def test_a_click_before_the_launch_window_is_not_opened_twice(windows, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(windows, "Supervisor", _Fake)
    monkeypatch.setattr(windows, "show_running_dashboard", lambda root: shown.append(root))
    assert windows.main(["--resident", "--show-dashboard"]) == 0
    assert _Fake.captured["first_args"] == ["--show-dashboard"]
    assert "--show-dashboard" not in _Fake.captured["command"]
    on_ready = _Fake.captured["on_ready"]
    windows.request_dashboard_later(tmp_path, session="session")  # A second click while it started.
    _next_tick()
    on_ready(True)  # server.py --show-dashboard already opened a window.
    on_ready(False)
    assert shown == []
    _next_tick()
    windows.request_dashboard_later(tmp_path, session="session")  # A later click.
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
        windows, monkeypatch, ["--resident", "--show-dashboard"], [_Child(alive=5, code=1), _Child(alive=5, code=0)])
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
        windows, monkeypatch, ["--resident", "--show-dashboard"], [_Child(alive=0, code=1), _Child(alive=5, code=0)])
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


def test_upgrade_in_same_windows_logon_keeps_quit_and_crash_history(windows, monkeypatch, tmp_path):
    luid = "0100000000000000"
    windows.write_json(tmp_path / windows.STATE_FILE, {"session": "windows:" + luid,
                       "status": "crash_loop", "restart_count": 3})
    windows.write_json(tmp_path / windows.STOP_FILE, {"reason": "quit"})
    supervisor = REAL_SUPERVISOR(tmp_path, [], "unused", session="windows:2:" + luid, startup=True)
    monkeypatch.setattr(supervisor, "loop", lambda: pytest.fail("restarted after Quit"))
    assert supervisor.run() == 0
    assert (tmp_path / windows.STOP_FILE).exists()
    assert supervisor.state["restart_count"] == 3


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
