"""Isolated installed-profile regressions.

Covers fail-closed validation before forbidden access, valid
startup/address/profile bindings, inherited GUI/stdio arguments, occupied-port
refusal, and owned stop identity. Never contacts port 5179, never opens the
live index, and never runs Inno or stock stop/uninstall scripts.
"""

from __future__ import annotations

import json
import os
import site
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import uoink_install_isolation as iso

ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_PORT = 5179


def _free_loopback_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    if port == PRODUCTION_PORT:
        return _free_loopback_port()
    return port


def _child_env(canary: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("UOINK_ISOLATED_PROFILE", None)
    env.pop("UOINK_ISOLATED_PORT", None)
    env.pop("UOINK_ISOLATED_APP_DIR", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["LOCALAPPDATA"] = str(canary)
    env["USERPROFILE"] = str(canary)
    env["XDG_DATA_HOME"] = str(canary / "xdg")
    inherited = [part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part]
    extra = []
    try:
        extra.append(site.getusersitepackages())
    except Exception:
        pass
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), *extra, *inherited])
    env["librarian_apply_enabled"] = "false"
    return env


def _start_isolated_helper(profile: Path, port: int, canary: Path, log_path: Path) -> subprocess.Popen:
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(ROOT / "server.py"),
            iso.CLI_PROFILE,
            str(profile),
            iso.CLI_PORT,
            str(port),
        ],
        cwd=str(ROOT),
        env=_child_env(canary),
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._iso_log_handle = handle  # type: ignore[attr-defined]
    return proc


def _stop_isolated_helper(profile: Path, port: int, canary: Path, proc: subprocess.Popen) -> subprocess.CompletedProcess:
    stop = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "uoink_install_isolation.py"),
            iso.CLI_STOP,
            iso.CLI_PROFILE,
            str(profile),
            iso.CLI_PORT,
            str(port),
        ],
        cwd=str(ROOT),
        env=_child_env(canary),
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    handle = getattr(proc, "_iso_log_handle", None)
    if handle is not None:
        try:
            handle.close()
        except OSError:
            pass
    return stop


def _canary_index(canary: Path) -> Path:
    return canary / "Uoink" / "index.db"


# ---- fail-closed validation -------------------------------------------------
def test_missing_profile_fails_before_default_data(tmp_path):
    canary = tmp_path / "user"
    canary.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.resolve_from_process(
            [iso.CLI_PORT, "5180"],
            environ={"LOCALAPPDATA": str(canary), "USERPROFILE": str(canary)},
        )
    assert caught.value.code == "isolated-profile-missing"
    assert not _canary_index(canary).exists()


def test_relative_profile_is_rejected(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(profile="relative-profile", port=5180)
    assert caught.value.code == "isolated-profile-relative"


def test_missing_profile_directory_is_rejected(tmp_path):
    missing = tmp_path / "no-such-profile"
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(profile=missing, port=5180)
    assert caught.value.code == "isolated-profile-not-found"


def test_normal_data_profile_is_rejected(tmp_path):
    canary = tmp_path / "user"
    normal = canary / "Uoink"
    normal.mkdir(parents=True)
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(
            profile=normal,
            port=5180,
            environ={"LOCALAPPDATA": str(canary), "USERPROFILE": str(canary)},
            platform_name="win32",
            home=canary,
        )
    assert caught.value.code == "isolated-profile-normal-data"


def test_legacy_data_profile_is_rejected(tmp_path):
    canary = tmp_path / "user"
    legacy = canary / "Yoink"
    legacy.mkdir(parents=True)
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(
            profile=legacy,
            port=5180,
            environ={"LOCALAPPDATA": str(canary), "USERPROFILE": str(canary)},
            platform_name="win32",
            home=canary,
        )
    assert caught.value.code == "isolated-profile-legacy-data"


def test_root_volume_profile_is_rejected():
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(
            profile="C:\\",
            port=5180,
            require_existing=False,
            platform_name="win32",
            environ={},
            home=Path("C:\\Users\\nobody"),
        )
    assert caught.value.code == "isolated-profile-root-volume"


def test_unsafe_system_profile_is_rejected(tmp_path):
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(
            profile=r"C:\Windows",
            port=5180,
            require_existing=False,
            platform_name="win32",
            environ={"WINDIR": r"C:\Windows", "LOCALAPPDATA": str(tmp_path)},
            home=tmp_path,
        )
    assert caught.value.code == "isolated-profile-unsafe"


def test_conflicting_cli_and_env_profiles_are_rejected(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.resolve_from_process(
            [iso.CLI_PROFILE, str(first), iso.CLI_PORT, "5180"],
            environ={
                iso.ENV_PROFILE: str(second),
                iso.ENV_PORT: "5180",
                "LOCALAPPDATA": str(tmp_path / "user"),
            },
        )
    assert caught.value.code == "isolated-profile-conflict"


def test_production_port_is_forbidden(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(profile=profile, port=PRODUCTION_PORT)
    assert caught.value.code == "isolated-port-forbidden"


def test_invalid_port_is_rejected(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_binding(profile=profile, port="not-a-port")
    assert caught.value.code == "isolated-port-invalid"


def test_ordinary_install_reuse_is_refused(tmp_path):
    app = tmp_path / "Uoink App"
    profile = tmp_path / "profile"
    app.mkdir()
    profile.mkdir()
    (app / "server.py").write_text("# ordinary install\n", encoding="utf-8")
    binding = iso.validate_binding(profile=profile, port=5180)
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_install_reuse(
            app_dir=app,
            binding=binding,
            environ={"LOCALAPPDATA": str(tmp_path / "user")},
            platform_name="win32",
            home=tmp_path / "user",
        )
    assert caught.value.code == "isolated-install-ordinary-reuse"


def test_mismatched_install_marker_is_refused(tmp_path):
    app = tmp_path / "app"
    profile = tmp_path / "profile"
    other = tmp_path / "other"
    app.mkdir()
    profile.mkdir()
    other.mkdir()
    first = iso.validate_binding(profile=other, port=5181, app_dir=app)
    iso.write_install_marker(app, first)
    binding = iso.validate_binding(profile=profile, port=5180, app_dir=app)
    with pytest.raises(iso.IsolationError) as caught:
        iso.validate_install_reuse(app_dir=app, binding=binding)
    assert caught.value.code == "isolated-install-marker-mismatch"


def test_no_isolation_request_leaves_production_unchanged():
    assert iso.resolve_from_process(["--show-dashboard"], environ={}) is None
    assert iso.listen_port(5179) == 5179
    assert iso.base_url() == "http://127.0.0.1:5179"


def test_invalid_isolation_exits_before_server_opens_canary(tmp_path):
    canary = tmp_path / "user"
    canary.mkdir()
    port = _free_loopback_port()
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "server.py"),
            iso.CLI_PROFILE,
            "relative-profile",
            iso.CLI_PORT,
            str(port),
        ],
        cwd=str(ROOT),
        env=_child_env(canary),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == iso.EXIT_VALIDATION
    assert "isolated-profile-relative" in proc.stderr
    assert not _canary_index(canary).exists()
    assert not (canary / "Uoink" / "token.txt").exists()


def test_forbidden_port_argument_does_not_open_canary(tmp_path):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "server.py"),
            iso.CLI_PROFILE,
            str(profile),
            iso.CLI_PORT,
            str(PRODUCTION_PORT),
        ],
        cwd=str(ROOT),
        env=_child_env(canary),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == iso.EXIT_VALIDATION
    assert "isolated-port-forbidden" in proc.stderr
    assert not _canary_index(canary).exists()
    assert list(profile.iterdir()) == []


# ---- valid binding / installer source --------------------------------------
def test_valid_binding_and_durable_marker(tmp_path):
    profile = tmp_path / "receipt" / "empty"
    app = tmp_path / "receipt" / "Uoink App"
    profile.mkdir(parents=True)
    app.mkdir(parents=True)
    port = _free_loopback_port()
    with iso.bound_isolation(profile=profile, port=port, app_dir=app) as binding:
        assert binding.profile == profile.resolve()
        assert binding.port == port
        assert binding.port != PRODUCTION_PORT
        assert binding.base_url == f"http://127.0.0.1:{port}"
        marker = iso.write_install_marker(app, binding)
        payload = iso.read_install_marker(app)
        assert marker.name == "isolated-install.json"
        assert payload["mode"] == "isolated"
        assert payload["port"] == port
        iso.validate_install_reuse(app_dir=app, binding=binding)
        assert iso.child_argv()[:4] == [
            iso.CLI_PROFILE,
            str(binding.profile),
            iso.CLI_PORT,
            str(port),
        ]
    assert iso.current_binding() is None


def test_inno_isolated_mode_skips_5179_prep_and_ordinary_launch():
    iss = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
    assert "function IsolatedInstall(): Boolean;" in iss
    assert "isolated mode skips upgrade_prep.ps1" in iss
    assert "isolated-port-forbidden" in iss
    assert "isolated-install-ordinary-reuse" in iss
    assert "isolated-running-requires-stop" in iss
    assert "Check: IsolatedInstall" in iss
    assert "Check: not IsolatedInstall" in iss
    run_section = iss.split("[Run]", 1)[1].split("[UninstallRun]", 1)[0]
    assert "--show-dashboard" not in run_section
    assert 'Check: not IsolatedInstall' in run_section
    registry = iss.split("[Registry]", 1)[1].split("[Run]", 1)[0]
    assert "CurrentVersion\\Run" in registry
    assert "Check: not IsolatedInstall" in registry
    assert "staging\\uoink_install_isolation.py" in iss
    assert "WriteIsolatedMarker" in iss


def test_helper_stdio_and_gui_entries_apply_isolation_before_default_data():
    server_src = (ROOT / "server.py").read_text(encoding="utf-8")
    mcp_src = (ROOT / "uoink_mcp.py").read_text(encoding="utf-8")
    dash_src = (ROOT / "uoink_dashboard.py").read_text(encoding="utf-8")
    splash_src = (ROOT / "uoink_splash.py").read_text(encoding="utf-8")
    assert server_src.index("apply_from_process()") < server_src.index("DATA_ROOT =")
    assert mcp_src.index("apply_from_process()") < mcp_src.index("import server")
    assert "helper_url(\"/dashboard\")" in dash_src
    assert "helper_url(\"/splash\")" in splash_src
    assert "helper_url(\"/health\")" in splash_src
    assert "skipped_isolated_install" in (ROOT / "migrate_install.py").read_text(
        encoding="utf-8"
    )


def test_dashboard_and_splash_inherit_declared_address(tmp_path):
    import uoink_dashboard
    import uoink_splash

    profile = tmp_path / "profile"
    profile.mkdir()
    port = _free_loopback_port()
    with iso.bound_isolation(profile=profile, port=port):
        assert uoink_dashboard._target_url() == f"http://127.0.0.1:{port}/dashboard"
        assert uoink_splash._splash_url() == f"http://127.0.0.1:{port}/splash"
        assert uoink_splash._sentinel_path() == profile.resolve() / ".first-run-done"
        assert iso.helper_url("/health") == f"http://127.0.0.1:{port}/health"
    assert uoink_dashboard._target_url() == "http://127.0.0.1:5179/dashboard"


def test_stdio_child_argv_and_env_are_explicit(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    port = _free_loopback_port()
    binding = iso.validate_binding(profile=profile, port=port)
    argv = iso.child_argv(binding)
    env = iso.child_environ(binding)
    assert argv[0] == iso.CLI_PROFILE
    assert env[iso.ENV_PROFILE] == str(binding.profile)
    assert env[iso.ENV_PORT] == str(port)


# ---- process: startup, occupancy, stop -------------------------------------
def _wait_health(port: int, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=1.0
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as error:
            last = error
            time.sleep(0.2)
    raise AssertionError(f"isolated helper did not answer /health: {last}")


def test_isolated_startup_binds_profile_and_port(tmp_path):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    port = _free_loopback_port()
    log_path = tmp_path / "helper.log"
    proc = _start_isolated_helper(profile, port, canary, log_path)
    try:
        health = _wait_health(port)
        assert isinstance(health, dict)
        assert (profile / "index.db").exists()
        assert (profile / "token.txt").exists()
        assert (profile / iso.IDENTITY_FILENAME).exists()
        assert not _canary_index(canary).exists()
        identity = json.loads((profile / iso.IDENTITY_FILENAME).read_text(encoding="utf-8"))
        assert identity["port"] == port
        assert identity["pid"] == proc.pid
        lease_dir = profile / "suite-services.d"
        if lease_dir.exists():
            lease = json.loads((lease_dir / "uoink.json").read_text(encoding="utf-8"))
            assert lease["base_url"] == f"http://127.0.0.1:{port}"
            assert "5179" not in json.dumps(lease)
    except Exception as error:
        helper_log = (profile / "server.log").read_text(encoding="utf-8")[-4000:] if (profile / "server.log").exists() else ""
        raise AssertionError(f"{error}\n{helper_log}") from error
    finally:
        stop = _stop_isolated_helper(profile, port, canary, proc)
        assert stop.returncode == 0, stop.stderr
        assert proc.returncode is not None


def test_occupied_isolated_port_is_refused(tmp_path):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    holder.bind(("127.0.0.1", 0))
    port = int(holder.getsockname()[1])
    if port == PRODUCTION_PORT:
        holder.close()
        pytest.skip("ephemeral port collided with production port")
    holder.listen(1)
    log_path = tmp_path / "occupied.log"
    proc = _start_isolated_helper(profile, port, canary, log_path)
    try:
        try:
            code = proc.wait(timeout=40)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise AssertionError(log_path.read_text(encoding="utf-8")[-4000:])
        assert code != 0
        combined = log_path.read_text(encoding="utf-8")
        assert "isolated-port-occupied" in combined or "Failed to bind" in combined
        assert not _canary_index(canary).exists()
    finally:
        handle = getattr(proc, "_iso_log_handle", None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        holder.close()


def test_stop_requires_owned_identity_not_pid_name_or_prefix(tmp_path):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    decoy = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(60)"],
        cwd=str(profile),
    )
    try:
        missing = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "uoink_install_isolation.py"),
                iso.CLI_STOP,
                iso.CLI_PROFILE,
                str(profile),
                iso.CLI_PORT,
                str(_free_loopback_port()),
            ],
            cwd=str(ROOT),
            env=_child_env(canary),
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert missing.returncode == 0
        assert decoy.poll() is None

        forged = {
            "mode": "isolated",
            "pid": decoy.pid,
            "executable": str(Path(sys.executable).resolve()),
            "script": str(ROOT / "server.py"),
            "created_ms": 1,
            "port": 5180,
            "profile": str(profile.resolve()),
            "host": "127.0.0.1",
            "nonce": "forged",
        }
        (profile / iso.IDENTITY_FILENAME).write_text(
            json.dumps(forged), encoding="utf-8"
        )
        binding = iso.validate_binding(profile=profile, port=5180)
        # Creation identity does not match, so this is not the owned helper.
        # Stop must not kill the decoy just because the pid/name/prefix match.
        assert iso.stop_owned_helper(binding) == iso.EXIT_OK
        assert decoy.poll() is None
    finally:
        decoy.kill()
        decoy.wait(timeout=5)


def test_upgrade_check_refuses_a_live_owned_helper(tmp_path):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    port = _free_loopback_port()
    log_path = tmp_path / "upgrade.log"
    proc = _start_isolated_helper(profile, port, canary, log_path)
    try:
        _wait_health(port)
        check = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "uoink_install_isolation.py"),
                iso.CLI_UPGRADE_CHECK,
                iso.CLI_PROFILE,
                str(profile),
                iso.CLI_PORT,
                str(port),
            ],
            cwd=str(ROOT),
            env=_child_env(canary),
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert check.returncode == iso.EXIT_RUNNING
        assert "isolated-running-requires-stop" in check.stderr
        assert proc.poll() is None
    except Exception as error:
        helper_log = (profile / "server.log").read_text(encoding="utf-8")[-4000:] if (profile / "server.log").exists() else ""
        raise AssertionError(f"{error}\n{helper_log}") from error
    finally:
        _stop_isolated_helper(profile, port, canary, proc)


def test_stdio_inherits_isolated_profile(tmp_path):
    try:
        import anyio  # noqa: F401
        from mcp.server.fastmcp import FastMCP  # noqa: F401
    except ImportError:
        pytest.skip("mcp SDK not installed")
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    port = _free_loopback_port()
    env = _child_env(canary)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-P",
            str(ROOT / "uoink_mcp.py"),
            iso.CLI_PROFILE,
            str(profile),
            iso.CLI_PORT,
            str(port),
        ],
        cwd=str(tmp_path),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    err_chunks: list[str] = []

    def _drain_err() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            err_chunks.append(line)

    threading.Thread(target=_drain_err, daemon=True).start()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "iso", "version": "0"},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        deadline = time.time() + 40
        answered = None
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError(
                    f"stdio exited {proc.returncode}: {''.join(err_chunks[-20:])}"
                )
            line = proc.stdout.readline()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == 1:
                answered = message
                break
        assert answered is not None and "result" in answered
        assert (profile / "index.db").exists() or (profile / "token.txt").exists()
        assert not _canary_index(canary).exists()
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)


def test_spawn_dashboard_passes_isolation_argv(tmp_path, monkeypatch):
    import server

    profile = tmp_path / "profile"
    profile.mkdir()
    port = _free_loopback_port()
    captured = {}

    class _Proc:
        pass

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return _Proc()

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(server, "HERE", tmp_path)
    (tmp_path / "uoink_dashboard.py").write_text("# stub\n", encoding="utf-8")
    with iso.bound_isolation(profile=profile, port=port):
        assert server._spawn_dashboard_window(reason="iso") is True
    assert iso.CLI_PROFILE in captured["cmd"]
    assert str(port) in captured["cmd"]
    assert captured["env"][iso.ENV_PORT] == str(port)


def test_suite_lease_follows_isolated_port(tmp_path):
    import suite_service

    profile = tmp_path / "profile"
    profile.mkdir()
    port = _free_loopback_port()
    with iso.bound_isolation(profile=profile, port=port):
        manifest = suite_service.service_manifest("3.8.0")
        lease = suite_service.runtime_lease("3.8.0", pid=1, started_at="2026-09-09T00:00:00Z")
        path = suite_service.write_runtime_lease(
            service_version="3.8.0",
            pid=1,
            started_at="2026-09-09T00:00:00Z",
        )
        assert manifest["service"]["default_port"] == port
        assert lease["base_url"] == f"http://127.0.0.1:{port}"
        assert path.parent == profile.resolve() / "suite-services.d"
        assert "5179" not in json.dumps(lease)
    production = suite_service.service_manifest("3.8.0")
    assert production["service"]["default_port"] == PRODUCTION_PORT
