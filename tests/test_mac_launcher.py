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
    assert 'strcmp(argv[1], "--helper")' in source
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
