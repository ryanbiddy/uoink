"""Linux runtime contracts on every test host, without real user state or GUIs."""
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import _platform
import uoink_agent_runtime as runtime
import uoink_cli as cli
import uoink_connect as connect
import uoink_supervisor as supervisor


@pytest.mark.parametrize("missing", [None, "ffmpeg", "ffprobe", "both"])
def test_linux_media_requires_both_binaries(monkeypatch, missing):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(_platform.shutil, "which", lambda name:
                        None if missing in (name, "both") else f"/usr/bin/{name}")
    capability = _platform.media_capability()
    assert capability["available"] is (missing is None)
    if missing is None:
        assert capability == {"available": True, "code": None, "reason": None}
    else:
        assert capability["code"] == "media_requires_ffmpeg"
        for hint in ("apt-get install ffmpeg", "dnf install ffmpeg", "pacman -S ffmpeg", "apk add ffmpeg"):
            assert hint in capability["reason"]


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_other_platform_media_does_not_require_path_binaries(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: None)
    monkeypatch.setattr(_platform.shutil, "which", lambda _: pytest.fail("unexpected PATH lookup"))
    assert _platform.media_capability() == {"available": True, "code": None, "reason": None}


def test_darwin_bundle_keeps_its_media_self_test(monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: tmp_path)
    assert _platform.media_capability()["available"] is False
    helpers = tmp_path / "Helpers"
    helpers.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        (helpers / name).touch()
    monkeypatch.setattr(_platform, "_media_self_test", lambda *args: True)
    assert _platform.media_capability()["available"] is True
    monkeypatch.setattr(_platform, "_media_self_test", lambda *args: False)
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"


@pytest.mark.parametrize("git_kind", ["dir", "file"])
def test_linux_source_checkout_keeps_state_next_to_server(monkeypatch, tmp_path, git_kind):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    app, data = tmp_path / "app", tmp_path / "data"
    app.mkdir()
    # A worktree has a .git file; a clone has a .git directory.
    if git_kind == "dir":
        (app / ".git").mkdir()
    else:
        (app / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    assert _platform.app_state_path(app, data, "token.txt") == app / "token.txt"


@pytest.mark.parametrize("platform,in_data", [("linux", True), ("darwin", True), ("win32", False)])
def test_app_state_locations(monkeypatch, tmp_path, platform, in_data):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    app, data = tmp_path / "app", tmp_path / "data"
    _platform.prepare_app_state(data)
    for name in ("token.txt", "server.log", "server.pid", "topics.json"):
        assert _platform.app_state_path(app, data, name) == (data if in_data else app) / name
    assert data.exists() is in_data
    assert not app.exists()


@pytest.mark.parametrize("platform,display,wayland,override,expected", [
    ("linux", "", "", "", True), ("linux", ":0", "", "", False),
    ("linux", "", "wayland-0", "", False), ("linux", ":0", "", "1", True),
    ("linux", "", "", "0", True), ("win32", "", "", "", False),
    ("darwin", "", "", "", False), ("darwin", "", "", "1", False),
])
def test_headless_detection(monkeypatch, platform, display, wayland, override, expected):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    for key, value in (("DISPLAY", display), ("WAYLAND_DISPLAY", wayland), ("UOINK_HEADLESS", override)):
        monkeypatch.setenv(key, value)
    assert _platform.is_headless() is expected


@pytest.fixture
def linux_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(_platform, "user_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(_platform, "desktop_dir", lambda: tmp_path / "home/Desktop")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(runtime.isolation, "current_binding", lambda: None)
    for name in ("UOINK_OUTPUT_DIR", "YOINK_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)
    import server
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="linux", executable=sys.executable))
    monkeypatch.setattr(server, "HERE", tmp_path / "app")
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_is_writable_dir", lambda path: path.is_dir())
    return server


def test_linux_output_default_does_not_create_desktop(linux_backend, tmp_path):
    assert linux_backend._get_output_root() == tmp_path / "data/output"
    desktop = tmp_path / "home/Desktop"
    assert not desktop.exists()
    desktop.mkdir(parents=True)
    assert linux_backend._get_output_root() == desktop / "Uoink"
    (desktop / "Yoink").mkdir()
    assert linux_backend._get_output_root() == desktop / "Yoink"


def test_linux_output_overrides_keep_precedence(linux_backend, monkeypatch, tmp_path):
    chosen, override, isolated = (tmp_path / name for name in ("chosen", "override", "isolated"))
    chosen.mkdir()
    override.mkdir()
    monkeypatch.setattr(linux_backend, "_read_settings", lambda: {"output_dir": str(chosen)})
    assert linux_backend._get_output_root() == chosen
    monkeypatch.setenv("UOINK_OUTPUT_DIR", str(override))
    assert linux_backend._get_output_root() == override
    monkeypatch.setattr(runtime.isolation, "current_binding", lambda: SimpleNamespace(output_dir=isolated))
    assert linux_backend._get_output_root() == isolated


@pytest.mark.parametrize("platform,filename", [("linux", "uoink"), ("win32", "uoink.cmd")])
def test_text_recipe_uses_platform_launcher(monkeypatch, tmp_path, platform, filename):
    monkeypatch.setattr(connect, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setitem(connect.CLIENTS, "test-cli", connect.Client(
        "text", "test", guide="<CLI>\n<CLI_COMMAND>", platforms=("linux", "win32")))
    rendered = connect.render("test-cli", tmp_path, tmp_path / "python/bin/python3")
    assert str(tmp_path / "cli" / filename) in rendered
    if platform == "linux":
        assert ".cmd" not in rendered


def test_linux_recipes_preserve_venv_python_symlink(monkeypatch, tmp_path):
    python = tmp_path / "python/bin/python3"
    python.parent.mkdir(parents=True)
    python.touch()
    resolve = Path.resolve
    # Simulate a venv symlink even on Windows runners without symlink privileges.
    monkeypatch.setattr(Path, "resolve", lambda path, *a, **k:
                        tmp_path / "system-python" if path == python else resolve(path, *a, **k))
    monkeypatch.setattr(connect, "sys", SimpleNamespace(platform="linux"))
    assert connect.python_command(tmp_path) == python
    entry = connect.server_entry("claude-code", tmp_path, python)
    assert entry["command"] == str(python)


def test_helper_running_reads_linux_data_pid(monkeypatch, tmp_path):
    app, data = tmp_path / "app", tmp_path / "data"
    app.mkdir()
    data.mkdir()
    (app / "server.pid").write_text("88", encoding="utf-8")
    pid_path = data / "server.pid"
    pid_path.write_text("77", encoding="utf-8")
    monkeypatch.setattr(runtime, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(runtime, "os", SimpleNamespace(name="posix", getpid=lambda: 99))
    monkeypatch.setattr(runtime.isolation, "current_binding", lambda: None)
    executable = str(tmp_path / "python")
    monkeypatch.setattr(runtime.isolation, "current_process_executable", lambda: executable)
    monkeypatch.setattr(runtime.isolation, "_process_executable", lambda pid: executable if pid == 77 else None)
    monkeypatch.setattr(runtime.isolation, "_posix_process_created_ms", lambda pid:
                        pid_path.stat().st_mtime_ns // 1_000_000 - 1000)
    monkeypatch.setattr(runtime.isolation, "_pid_liveness", lambda *args: "alive")
    backend = SimpleNamespace(HERE=app, DATA_ROOT=data)
    assert runtime.helper_running(backend)
    pid_path.unlink()
    assert not runtime.helper_running(backend)


def test_linux_status_reports_missing_ffmpeg(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "sys", SimpleNamespace(platform="linux", stderr=sys.stderr))
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(_platform.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli.isolation, "apply_from_process", lambda *args: None)
    model_status = {"cached": False, "bundled_model": None, "source": None}
    monkeypatch.setattr(cli, "backend", lambda: SimpleNamespace(
        VERSION="1.0.0", DATA_ROOT=tmp_path, _platform=_platform,
        _reliability_model_status=lambda: model_status))
    monkeypatch.setattr(runtime, "helper_running", lambda _: False)
    assert cli.main(["status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["capabilities"]["media"]["available"] is False
    assert result["capabilities"]["media"]["code"] == "media_requires_ffmpeg"
    assert result["reliability_model"] == model_status


@pytest.mark.parametrize("display", ["", ":0"])
def test_linux_dashboard_logs_url_without_gui(linux_backend, monkeypatch, tmp_path, caplog, display):
    monkeypatch.setenv("DISPLAY", display)
    monkeypatch.setattr(supervisor, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(runtime.isolation, "helper_url", lambda path: f"http://127.0.0.1:18191{path}")
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned a GUI"))
    monkeypatch.setattr(linux_backend.webbrowser, "open", lambda *a, **k: pytest.fail("opened a browser"))
    with caplog.at_level(logging.INFO):
        assert linux_backend._spawn_dashboard_window(reason="launch-flag")
        assert supervisor.show_running_dashboard(tmp_path)
    assert "http://127.0.0.1:18191/dashboard" in caplog.text


def test_installed_linux_boot_skips_tray_splash_and_ready_toast(linux_backend, monkeypatch, tmp_path):
    import atexit
    server = linux_backend
    monkeypatch.setenv("DISPLAY", "")
    monkeypatch.setenv("WAYLAND_DISPLAY", "")
    monkeypatch.delenv("UOINK_HEADLESS", raising=False)
    server.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "TOKEN_PATH", server.DATA_ROOT / "token.txt")
    monkeypatch.setattr(server, "TOKEN", "test-token")
    monkeypatch.setattr(server, "_TOKEN_OWNED", False)
    monkeypatch.setattr(server, "_active_migration_version", None)
    monkeypatch.setattr(server, "_local_search_singleton", None)
    monkeypatch.setattr(server, "PORT", 18191)
    monkeypatch.setattr(server, "_is_installed_layout", lambda: True)
    for name in ("_existing_server_responds", "_apply_output_root_fallback",
                 "_migrate_plaintext_anthropic_key", "_migrate_jobs_json_to_index",
                 "_migrate_taxonomy_json_to_index", "_seed_default_style_anchors",
                 "_heal_stale_corpus_paths_at_boot", "_restore_jobs_from_disk",
                 "_source_startup_reconciliation", "_resume_podcast_transcription_jobs",
                 "_start_backfill_thread", "_start_trash_purge_thread",
                 "_start_retry_pending_thread", "_start_podcast_feed_scheduler_thread",
                 "_start_relay_inbox_thread", "_stop_relay_inbox_thread", "_resume_local_search",
                 "_start_saves_thread"):
        monkeypatch.setattr(server, name, lambda *a, **k: None)
    monkeypatch.setattr(server, "_get_index", lambda: SimpleNamespace(
        schema_version=lambda: 1, reset_running_pending=lambda: 0))
    monkeypatch.setattr(server.podcasts, "repair_stranded_auto_ingest", lambda _: {"marked_eligible": 0})
    monkeypatch.setattr(server.migrate_install, "run_migration", lambda **k: {})
    monkeypatch.setattr(server.suite_service, "write_runtime_lease", lambda **k: None)
    monkeypatch.setattr(server.uoink_usage, "start_sender", lambda *_: None)
    monkeypatch.setattr(server, "_YoinkHTTPServer", lambda *a: SimpleNamespace(
        serve_forever=lambda: None, server_close=lambda: None))
    monkeypatch.setattr(atexit, "register", lambda *a: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Headless boot attempted a GUI or ready toast")

    monkeypatch.setitem(sys.modules, "uoink_tray", SimpleNamespace(start=forbidden))
    monkeypatch.setattr(server.subprocess, "Popen", forbidden)
    monkeypatch.setattr(server.webbrowser, "open", forbidden)
    monkeypatch.setattr(server, "maybe_toast", forbidden)
    monkeypatch.setattr(server, "_maybe_post_migration_toast", forbidden)
    server.main(show_dashboard=True)
    assert (server.DATA_ROOT / "server.pid").is_file()
    assert server.TOKEN_PATH.read_text(encoding="utf-8").strip() == "test-token"
    assert not server.HERE.exists()
