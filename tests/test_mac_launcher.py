"""Portable launch contracts; no Apple tools or existing user state."""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import signal
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["cli.sh", "mcpb-launch.sh", "launcher.sh"])
def test_shell_launchers_clear_all_loader_and_python_overrides(name):
    source = (ROOT / "installer/mac" / name).read_text(encoding="utf-8")
    cleanup = 'for variable in "${!DYLD_@}"; do unset "$variable"; done'
    assert cleanup in source  # Prefix enumeration must cover future DYLD names.
    python_cleanup = "unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE PYTHONEXECUTABLE"
    assert python_cleanup in source
    assert source.index(cleanup) < source.index('exec "$python"')
    assert source.index(python_cleanup) < source.index('exec "$python"')


def test_native_launcher_cleanup_and_build_contract():
    source = (ROOT / "installer/mac/launcher.c").read_text(encoding="utf-8")
    assert 'strncmp(environ[i], "DYLD_", 5)' in source
    assert "unsetenv(name)" in source
    for name in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE"):
        assert f'"{name}"' in source
    assert source.index("if (clear_environment())") < source.index("execv(python, args)")
    assert 'strcmp(user[0], "--helper")' in source
    builder = (ROOT / "scripts/mac/build_bundle.py").read_text(encoding="utf-8")
    assert '"clang", "-arch", "arm64", f"-mmacosx-version-min={MINIMUM_MACOS}"' in builder
    assert '"CFBundleExecutable": "Uoink"' in builder


@pytest.fixture
def startup(monkeypatch, tmp_path):
    """Keep server.main's bind/serve/signal path; stub unrelated boot jobs."""
    import server
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="darwin", exit=sys.exit))
    monkeypatch.setattr(server, "HOST", "127.0.0.1")
    monkeypatch.setattr(server, "PORT", 0)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "TOKEN_PATH", tmp_path / "token.txt")
    # This loop outlives main() and would sync consent into later tests' stores.
    monkeypatch.setattr(server.uoink_usage, "start_sender", lambda *_: None)
    for name in ("_existing_server_responds", "_is_installed_layout", "_apply_output_root_fallback",
                 "_migrate_plaintext_anthropic_key", "_migrate_jobs_json_to_index",
                 "_migrate_taxonomy_json_to_index", "_seed_default_style_anchors",
                 "_heal_stale_corpus_paths_at_boot", "_restore_jobs_from_disk",
                 "_source_startup_reconciliation", "_resume_podcast_transcription_jobs",
                 "_start_backfill_thread", "_start_trash_purge_thread",
                 "_start_retry_pending_thread", "_start_podcast_feed_scheduler_thread", "maybe_toast"):
        monkeypatch.setattr(server, name, lambda *a, **k: None)
    monkeypatch.setattr(server, "_maybe_post_migration_toast", lambda: True)
    monkeypatch.setattr(server._install_isolation, "current_binding", lambda: None)
    monkeypatch.setattr(server.migrate_install, "run_migration", lambda **k: {})
    monkeypatch.setattr(server, "_get_index", lambda: SimpleNamespace(
        schema_version=lambda: 1, reset_running_pending=lambda: 0))
    monkeypatch.setattr(server.podcasts, "repair_stranded_auto_ingest", lambda _: {"marked_eligible": 0})
    monkeypatch.setattr(server._platform, "editable_extension_dir", lambda *a: None)
    monkeypatch.setattr(server._platform, "app_state_path", lambda *a: tmp_path / "server.pid")
    monkeypatch.setattr(server._platform, "write_darwin_identity", lambda *a: tmp_path / "identity.json")
    monkeypatch.setattr(server.suite_service, "write_runtime_lease", lambda **k: None)
    return server


def test_server_starts_in_thread_under_simulated_darwin(startup, monkeypatch):
    server = startup
    ready = threading.Event()
    stopped = threading.Event()
    errors, instances, registrations = [], [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"threaded server online")

        def log_message(self, *args):
            pass

    class TestServer(HTTPServer):
        def serve_forever(self):
            ready.set()
            super().serve_forever(poll_interval=0.01)

    def bind(address, _handler):
        instance = TestServer(address, Handler)
        instances.append(instance)
        return instance

    original_signal = signal.signal
    def register(*args):
        registrations.append(args)
        return original_signal(*args)

    def start():
        try:
            server.main()
        except BaseException as exc:
            errors.append(exc)
        finally:
            stopped.set()

    monkeypatch.setattr(server, "_YoinkHTTPServer", bind)
    monkeypatch.setattr(signal, "signal", register)
    worker = threading.Thread(target=start, daemon=True)
    worker.start()
    try:
        assert ready.wait(5), errors
        assert not errors and not registrations
        port = instances[0].server_port
        assert port != 5179
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            assert response.status == 200
            assert response.read() == b"threaded server online"
        finally:
            connection.close()
    finally:
        if ready.is_set() and not stopped.is_set():
            instances[0].shutdown()
        worker.join(5)
        for instance in instances:
            instance.server_close()
    assert not worker.is_alive() and not errors


@pytest.mark.parametrize("platform,reject,expected", [
    ("darwin", False, 1), ("darwin", True, 1), ("win32", False, 0), ("linux", False, 0)])
def test_main_thread_handler_and_subinterpreter_refusal(startup, monkeypatch, platform, reject, expected):
    server = startup
    server.sys.platform = platform
    calls, served = [], []
    monkeypatch.setattr(server, "_YoinkHTTPServer", lambda *a: SimpleNamespace(
        serve_forever=lambda: served.append(True), server_close=lambda: None, shutdown=lambda: None))
    def register(*args):
        calls.append(args)
        if reject:
            raise ValueError("signal only works in main thread of the main interpreter")
    monkeypatch.setattr(signal, "signal", register)
    server.main()
    assert len(calls) == expected and served == [True]
    if calls:
        assert calls[0][0] == signal.SIGTERM


def test_startup_fixture_does_not_start_usage_sender(startup, monkeypatch):
    started = []

    def thread(*args, **kwargs):
        return SimpleNamespace(start=lambda: started.append(kwargs.get("name")))

    monkeypatch.setattr(startup.uoink_usage.threading, "Thread", thread)
    # Exercise the real main() call site, including the fixture's sender stub.
    test_main_thread_handler_and_subinterpreter_refusal(
        startup, monkeypatch, "win32", False, 0)
    assert started == [], "Launcher tests must not leave a usage sender running"


def _clang():
    import shutil
    import subprocess
    if sys.platform != "darwin":
        return None
    try:
        clang = subprocess.run(["xcrun", "--find", "clang"], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        return clang, sdk
    except (OSError, subprocess.SubprocessError):
        tools = Path("/Library/Developer/CommandLineTools")
        clang, sdk = tools / "usr/bin/clang", tools / "SDKs/MacOSX.sdk"
        return (str(clang), str(sdk)) if clang.is_file() and sdk.is_dir() and shutil.which(str(clang)) else None


@pytest.fixture(scope="module")
def launcher_app(tmp_path_factory):
    """The real launcher.c in a fake bundle whose python3 records its argv."""
    import subprocess
    tools = _clang()
    if tools is None:
        pytest.skip("needs macOS clang")
    app = tmp_path_factory.mktemp("launcher") / "Uoink.app/Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "Resources/Python/bin").mkdir(parents=True)
    for script in ("uoink_supervisor.py", "server.py"):
        (app / "Resources" / script).write_text("", encoding="utf-8")
    python = app / "Resources/Python/bin/python3"
    python.write_text('#!/bin/sh\nfor arg in "$@"; do printf \'%s\\n\' "$arg"; done\n', encoding="utf-8")
    python.chmod(0o755)
    subprocess.run([tools[0], "-isysroot", tools[1], "-arch", "arm64", "-mmacosx-version-min=15.0",
                    "-Wall", "-Wextra", "-Werror", str(ROOT / "installer/mac/launcher.c"),
                    "-o", str(app / "MacOS/Uoink")], check=True, capture_output=True, timeout=120)
    return app


@pytest.mark.parametrize("argv,script,forwarded", [
    ([], "uoink_supervisor.py", ["--show-dashboard"]),
    (["-psn_0_1234567"], "uoink_supervisor.py", ["--show-dashboard"]),
    (["-NSDocumentRevisionsDebugMode", "YES"], "uoink_supervisor.py", ["--show-dashboard"]),
    (["-NSQuitAlwaysKeepsWindows", "NO", "-psn_0_9"], "uoink_supervisor.py", ["--show-dashboard"]),
    (["--helper", "--startup"], "uoink_supervisor.py", ["--startup"]),
    (["-psn_0_1", "--helper", "--startup"], "uoink_supervisor.py", ["--startup"]),
    (["--helper"], "uoink_supervisor.py", []),
    (["status"], "server.py", ["status"]),
    (["--show-dashboard"], "server.py", ["--show-dashboard"]),
    (["mcp", "-psn_0_1"], "server.py", ["mcp"]),
])
def test_compiled_launcher_classifies_after_dropping_framework_args(launcher_app, argv, script, forwarded):
    import subprocess
    result = subprocess.run([str(launcher_app / "MacOS/Uoink"), *argv], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    args = result.stdout.splitlines()
    assert args[:2] == ["-B", "-s"] and Path(args[2]).name == script
    assert args[3:] == forwarded


@pytest.fixture
def supervisor(monkeypatch, tmp_path):
    import uoink_supervisor
    monkeypatch.setattr(uoink_supervisor.sys, "platform", "darwin")
    return uoink_supervisor


def _dashboard_helper(monkeypatch, ok=True):
    """A loopback stand-in for the resident helper's /helper/dashboard route."""
    import json
    import uoink_install_isolation
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, self.headers.get("X-Uoink-Token"),
                         json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            body = json.dumps({"ok": ok}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    monkeypatch.setattr(uoink_install_isolation, "helper_url",
                        lambda path: f"http://127.0.0.1:{httpd.server_port}{path}")
    return httpd, seen


def test_duplicate_darwin_launch_asks_resident_helper(supervisor, monkeypatch, tmp_path):
    httpd, seen = _dashboard_helper(monkeypatch)
    spawned = []
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    (tmp_path / "token.txt").write_text("resident-token\n", encoding="utf-8")
    try:
        assert supervisor.show_running_dashboard(tmp_path) is True
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert seen == [("/helper/dashboard", "resident-token", {"settings": False})]
    assert spawned == []  # No untracked uoink_dashboard.py on Darwin.


@pytest.mark.parametrize("token", [None, b"", b"\xff\xfe"])
def test_duplicate_darwin_launch_never_mints_a_token(supervisor, monkeypatch, tmp_path, token):
    httpd, seen = _dashboard_helper(monkeypatch)
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or False)
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned a dashboard"))
    if token is not None:
        (tmp_path / "token.txt").write_bytes(token)
    try:
        # The real webbrowser.open result is reported, not an assumed success.
        assert supervisor.show_running_dashboard(tmp_path) is False
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert seen == [] and len(opened) == 1 and opened[0].endswith("/dashboard")
    assert (tmp_path / "token.txt").read_bytes() == token if token is not None else not (tmp_path / "token.txt").exists()


def test_duplicate_darwin_launch_falls_back_when_helper_refuses(supervisor, monkeypatch, tmp_path):
    httpd, seen = _dashboard_helper(monkeypatch, ok=False)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    (tmp_path / "token.txt").write_text("stale-token", encoding="utf-8")
    try:
        assert supervisor.show_running_dashboard(tmp_path) is True
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert len(seen) == 1


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_duplicate_launch_off_darwin_still_spawns_dashboard_script(monkeypatch, tmp_path, platform):
    import uoink_supervisor
    monkeypatch.setattr(uoink_supervisor.sys, "platform", platform)
    spawned = []
    monkeypatch.setattr(uoink_supervisor.subprocess, "Popen", lambda args, **k: spawned.append(args))
    assert uoink_supervisor.show_running_dashboard(tmp_path) is True
    assert len(spawned) == 1 and spawned[0][1].endswith("uoink_dashboard.py")


@pytest.mark.parametrize("platform,command_flag,first_args", [
    ("darwin", False, ["--show-dashboard"]),
    ("win32", True, []),
])
def test_show_dashboard_reaches_only_the_first_darwin_helper(monkeypatch, tmp_path, platform, command_flag, first_args):
    import uoink_supervisor
    captured = {}

    class Fake:
        owned = True

        def __init__(self, root, command, url, **kw):
            captured.update(command=command, **kw)

        def run(self):
            return 0

    monkeypatch.setattr(uoink_supervisor.sys, "platform", platform)
    monkeypatch.setattr(uoink_supervisor, "Supervisor", Fake)
    monkeypatch.setattr(uoink_supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(uoink_supervisor, "login_session", lambda: "session")
    resident = ["--resident"] if platform == "darwin" else []
    assert uoink_supervisor.main([*resident, "--show-dashboard"]) == 0
    assert ("--show-dashboard" in captured["command"]) is command_flag
    assert captured["first_args"] == first_args


def test_crash_restarts_do_not_repeat_first_only_args(monkeypatch, tmp_path):
    import io
    import uoink_supervisor
    commands = []

    class Child:
        pid = 4242

        def __init__(self):
            self.stdout = io.BytesIO(b"")

        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(uoink_supervisor.subprocess, "Popen", lambda command, **k: commands.append(command) or Child())
    supervisor = uoink_supervisor.Supervisor(
        tmp_path, ["python", "server.py"], "http://127.0.0.1:1/health", session="s",
        first_args=["--show-dashboard"], backoff=(0, 0), poll=0, notify=lambda state: None,
        sleep=lambda seconds: None)
    assert supervisor.loop() == 0
    assert commands == [["python", "server.py", "--show-dashboard"],
                        ["python", "server.py"], ["python", "server.py"]]


@pytest.mark.parametrize("splash,expected", [(True, []), (False, ["launch-flag"])])
def test_first_run_splash_replaces_launch_dashboard_on_darwin(startup, monkeypatch, splash, expected):
    server = startup
    from helper import mac_ui
    reasons = []
    monkeypatch.setattr(server, "_is_installed_layout", lambda: True)
    monkeypatch.setattr(mac_ui, "start_menu", lambda **k: SimpleNamespace(pid=1))
    monkeypatch.setattr(mac_ui, "spawn", lambda *a: None)
    monkeypatch.setattr(server, "_splash_should_spawn", lambda _: splash)
    monkeypatch.setattr(server, "_spawn_dashboard_window", lambda **k: reasons.append(k["reason"]) or True)

    class Immediate(HTTPServer):
        def serve_forever(self, poll_interval=0.5):
            pass

    monkeypatch.setattr(server, "_YoinkHTTPServer", lambda address, _h: Immediate(address, BaseHTTPRequestHandler))
    errors = []
    worker = threading.Thread(target=lambda: _run(server, errors), daemon=True)
    worker.start()
    worker.join(10)
    assert not worker.is_alive() and not errors
    assert reasons == expected
    assert (server.TOKEN_PATH).read_text(encoding="utf-8") == server.TOKEN


def _run(server, errors):
    try:
        server.main(show_dashboard=True)
    except BaseException as exc:
        errors.append(exc)


def test_menu_bar_process_handles_the_reopen_event():
    source = (ROOT / "helper/mac_menubar.py").read_text(encoding="utf-8")
    assert "def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):" in source
    assert source.index("app.setDelegate_(reopen)") < source.index("app.run()")
    try:
        import AppKit
    except ImportError:
        return  # Portable runners lack PyObjC; the bundled interpreter has it.
    from helper import mac_menubar
    done = threading.Event()
    delegate = mac_menubar.reopen_delegate(SimpleNamespace(dashboard=done.set))
    assert delegate.applicationShouldHandleReopen_hasVisibleWindows_(AppKit.NSApp, False) is False
    assert done.wait(2)



def test_darwin_open_hands_off_to_a_detached_resident(supervisor, monkeypatch, tmp_path):
    """LaunchServices must never be left holding a long-lived process to reopen."""
    spawned = []
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "Supervisor", lambda *a, **k: pytest.fail("stayed resident"))
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda args, **kw: spawned.append((args, kw)))
    assert supervisor.main(["--show-dashboard"]) == 0
    (args, kw), = spawned
    assert Path(args[3]).name == "uoink_supervisor.py" and args[4:6] == ["--resident", "--show-dashboard"]
    assert kw["start_new_session"] is True and kw["stdin"] is supervisor.subprocess.DEVNULL


@pytest.mark.parametrize("state", ["running", "starting", "backoff", "crash_loop"])
def test_darwin_open_while_resident_asks_or_queues(supervisor, monkeypatch, tmp_path, state):
    shown = []
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "show_running_dashboard", lambda root: shown.append(root) or True)
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("started a second resident"))
    supervisor.write_json(tmp_path / supervisor.STATE_FILE, {"status": state})
    with supervisor.admission(tmp_path) as owned:  # The resident holds the lock.
        assert owned
        assert supervisor.main(["--show-dashboard"]) == 0
    assert shown == ([tmp_path] if state == "running" else [])
    # Not ready yet: the open waits for the resident's helper instead of vanishing.
    assert (tmp_path / supervisor.DASHBOARD_REQUEST).exists() is (state != "running")


def test_darwin_open_with_helper_but_no_supervisor_asks_that_helper(supervisor, monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "request_dashboard", lambda root: asked.append(root) or True)
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicated a live helper"))
    assert supervisor.main(["--show-dashboard"]) == 0
    assert asked == [tmp_path]


def test_dashboard_request_is_taken_once_and_expires(supervisor, monkeypatch, tmp_path):
    assert supervisor.take_dashboard_request(tmp_path) is False
    supervisor.request_dashboard_later(tmp_path)
    assert supervisor.take_dashboard_request(tmp_path) is True
    assert supervisor.take_dashboard_request(tmp_path) is False
    supervisor.write_json(tmp_path / supervisor.DASHBOARD_REQUEST,
                          {"requested_at": supervisor.time.time() - supervisor.REQUEST_WINDOW - 1})
    assert supervisor.take_dashboard_request(tmp_path) is False
    (tmp_path / supervisor.DASHBOARD_REQUEST).write_text("not json", encoding="utf-8")
    assert supervisor.take_dashboard_request(tmp_path) is False
    assert not (tmp_path / supervisor.DASHBOARD_REQUEST).exists()


@pytest.mark.parametrize("first_args,shown", [([], [False, False]), (["--show-dashboard"], [True, False])])
def test_ready_callback_runs_on_every_helper_start(monkeypatch, tmp_path, first_args, shown):
    import io
    import uoink_supervisor
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
        tmp_path, ["python", "server.py"], "http://127.0.0.1:1/health", session="s",
        first_args=first_args, on_ready=ready.append, backoff=(0,), poll=0,
        probe=lambda *a: True, notify=lambda state: None, sleep=lambda seconds: None)
    assert supervisor.loop() == 0
    # Crash restarts honor a waiting open too; only the launch flag's start says shown.
    assert ready == shown


def test_darwin_ready_callback_honors_a_waiting_open(supervisor, monkeypatch, tmp_path):
    captured, shown = {}, []

    class Fake:
        def __init__(self, root, command, url, **kw):
            captured.update(kw)
            self.owned = True

        def run(self):
            return 0

    monkeypatch.setattr(supervisor, "Supervisor", Fake)
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "login_session", lambda: "session")
    monkeypatch.setattr(supervisor, "show_running_dashboard", lambda root: shown.append(root))
    assert supervisor.main(["--startup"]) == 0
    on_ready = captured["on_ready"]
    supervisor.request_dashboard_later(tmp_path)
    on_ready(True)  # The launch flag already opened a window.
    supervisor.request_dashboard_later(tmp_path)
    on_ready(False)
    for _ in range(50):
        if shown:
            break
        supervisor.time.sleep(0.02)
    assert shown == [tmp_path] and not (tmp_path / supervisor.DASHBOARD_REQUEST).exists()


def test_resident_that_loses_admission_leaves_its_open_queued(supervisor, monkeypatch, tmp_path):
    class Lost:
        owned = False

        def __init__(self, *a, **k):
            pass

        def run(self):
            return 0

    monkeypatch.setattr(supervisor, "Supervisor", Lost)
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "login_session", lambda: "session")
    supervisor.write_json(tmp_path / supervisor.STATE_FILE, {"status": "starting"})
    assert supervisor.main(["--resident", "--show-dashboard"]) == 0
    assert supervisor.take_dashboard_request(tmp_path) is True


def test_resident_and_login_launches_still_supervise(supervisor, monkeypatch, tmp_path):
    runs = []

    class Fake:
        owned = True

        def __init__(self, root, command, url, **kw):
            runs.append(kw)

        def run(self):
            return 0

    monkeypatch.setattr(supervisor, "Supervisor", Fake)
    monkeypatch.setattr(supervisor, "data_root", lambda: tmp_path)
    monkeypatch.setattr(supervisor, "login_session", lambda: "session")
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("detached again"))
    assert supervisor.main(["--resident", "--show-dashboard"]) == 0
    assert supervisor.main(["--startup"]) == 0
    assert [run["first_args"] for run in runs] == [["--show-dashboard"], []]
    assert [run["startup"] for run in runs] == [False, True]
