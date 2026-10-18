"""Supported isolated installed profile and non-5179 loopback binding.

Dependency-free (stdlib only). Entry points import this module and call
``apply_from_process()`` before any product code can open the default
library. When isolation is not requested this module is a no-op and
production still uses ``127.0.0.1:5179`` plus the normal per-user data root.

Isolation is explicit: ``--isolated-profile`` and ``--isolated-port`` together,
or the matching environment variables for subprocess inheritance, or a durable
``isolated-install.json`` marker next to an isolated install. Partial or
conflicting requests fail closed. Port 5179 is never a valid isolated port.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PRODUCTION_PORT = 5179
PRODUCTION_HOST = "127.0.0.1"
MARKER_FILENAME = "isolated-install.json"
IDENTITY_FILENAME = "runtime-identity.json"
CLI_PROFILE = "--isolated-profile"
CLI_PORT = "--isolated-port"
CLI_FROM_INSTALL = "--isolated-from-install-dir"
CLI_STOP = "--isolated-stop"
CLI_UPGRADE_CHECK = "--isolated-upgrade-check"
ENV_PROFILE = "UOINK_ISOLATED_PROFILE"
ENV_PORT = "UOINK_ISOLATED_PORT"
ENV_APP_DIR = "UOINK_ISOLATED_APP_DIR"
ISOLATION_MODE = "isolated"

# Exit codes for the isolation CLI (start still uses the helper's 0/1).
EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_RUNNING = 3
EXIT_STOP_IDENTITY = 4
EXIT_USAGE = 5

_FILETIME_EPOCH_OFFSET_100NS = 116_444_736_000_000_000
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_ERROR_INVALID_PARAMETER = 87
_STOP_WAIT_MS = 15_000
_VALUE_FLAGS = (CLI_PROFILE, CLI_PORT, CLI_FROM_INSTALL)
_BARE_FLAGS = (CLI_STOP, CLI_UPGRADE_CHECK)

_CURRENT: IsolationBinding | None = None
_ENV_SNAPSHOT: dict[str, str | None] | None = None


class IsolationError(ValueError):
    """Fail-closed isolation request. ``code`` is the stable operator token."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class IsolationBinding:
    """One declared isolated profile and loopback port."""

    profile: Path
    port: int
    host: str = PRODUCTION_HOST
    app_dir: Path | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def output_dir(self) -> Path:
        return self.profile / "output"

    @property
    def token_path(self) -> Path:
        return self.profile / "token.txt"

    @property
    def pid_path(self) -> Path:
        return self.profile / "server.pid"

    @property
    def identity_path(self) -> Path:
        return self.profile / IDENTITY_FILENAME

    @property
    def log_path(self) -> Path:
        return self.profile / "server.log"

    def suite_registry_dir(self) -> Path:
        return self.profile / "suite-services.d"

    def helper_url(self, path: str) -> str:
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{suffix}"


def current_binding() -> IsolationBinding | None:
    return _CURRENT


def production_user_data_dir(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Normal (non-isolated) per-user data root. Never consults isolation."""
    platform_name = sys.platform if platform_name is None else platform_name
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform_name == "win32":
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "Uoink"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "Uoink"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "Uoink"


def production_legacy_data_dir(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform_name = sys.platform if platform_name is None else platform_name
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform_name == "win32":
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "Yoink"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "Yoink"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "Yoink"


def production_desktop_corpus_dirs(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[Path, Path]:
    platform_name = sys.platform if platform_name is None else platform_name
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform_name == "win32":
        desktop = Path(environ.get("USERPROFILE") or str(home)) / "Desktop"
    else:
        desktop = home / "Desktop"
    return desktop / "Uoink", desktop / "Yoink"


def production_default_install_dir(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Ordinary Inno DefaultDirName: the same folder as the normal data root."""
    return production_user_data_dir(
        platform_name=platform_name, environ=environ, home=home
    )


def data_root(production: Path) -> Path:
    binding = current_binding()
    return binding.profile if binding is not None else Path(production)


def listen_port(production_port: int = PRODUCTION_PORT) -> int:
    binding = current_binding()
    return binding.port if binding is not None else int(production_port)


def listen_host(production_host: str = PRODUCTION_HOST) -> str:
    binding = current_binding()
    return binding.host if binding is not None else production_host


def base_url(production: str = f"http://{PRODUCTION_HOST}:{PRODUCTION_PORT}") -> str:
    binding = current_binding()
    return binding.base_url if binding is not None else production


def helper_url(path: str) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base_url()}{suffix}"


def child_argv(binding: IsolationBinding | None = None) -> list[str]:
    """Arguments a helper must pass to splash, dashboard and stdio children."""
    chosen = current_binding() if binding is None else binding
    if chosen is None:
        return []
    args = [CLI_PROFILE, str(chosen.profile), CLI_PORT, str(chosen.port)]
    if chosen.app_dir is not None:
        args.extend([CLI_FROM_INSTALL, str(chosen.app_dir)])
    return args


def child_environ(binding: IsolationBinding | None = None) -> dict[str, str]:
    chosen = current_binding() if binding is None else binding
    if chosen is None:
        return {}
    env = {
        ENV_PROFILE: str(chosen.profile),
        ENV_PORT: str(chosen.port),
    }
    if chosen.app_dir is not None:
        env[ENV_APP_DIR] = str(chosen.app_dir)
    return env


def strip_cli(argv: list[str]) -> list[str]:
    """Return argv without isolation flags so the ordinary CLI can dispatch."""
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in {CLI_PROFILE, CLI_PORT, CLI_FROM_INSTALL} and i + 1 < len(argv):
            i += 2
            continue
        if arg in {CLI_STOP, CLI_UPGRADE_CHECK}:
            i += 1
            continue
        remaining.append(arg)
        i += 1
    return remaining


def apply_from_process(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> IsolationBinding | None:
    """Validate an isolation request from argv/env. No-op when not requested.

    Invalid requests print the stable error code and exit 2 so a product
    import cannot continue into default data.
    """
    try:
        binding = resolve_from_process(argv=argv, environ=environ)
    except IsolationError as error:
        print(f"uoink isolated install: {error}", file=sys.stderr)
        raise SystemExit(EXIT_VALIDATION) from error
    _set_current(binding)
    if binding is not None:
        _export_env(binding)
    return binding


def apply_explicit(
    *,
    profile: Path | str,
    port: int | str,
    app_dir: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
    require_existing: bool = True,
) -> IsolationBinding:
    binding = validate_binding(
        profile=profile,
        port=port,
        app_dir=app_dir,
        environ=environ,
        platform_name=platform_name,
        home=home,
        require_existing=require_existing,
    )
    _set_current(binding)
    _export_env(binding)
    return binding


@contextmanager
def bound_isolation(
    *,
    profile: Path | str,
    port: int | str,
    app_dir: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
    require_existing: bool = True,
):
    """Apply an isolated binding for the duration of a test or helper."""
    previous = current_binding()
    previous_env = _capture_env()
    try:
        yield apply_explicit(
            profile=profile,
            port=port,
            app_dir=app_dir,
            environ=environ,
            platform_name=platform_name,
            home=home,
            require_existing=require_existing,
        )
    finally:
        _set_current(previous)
        _restore_env(previous_env)


def resolve_from_process(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    require_existing: bool = True,
) -> IsolationBinding | None:
    argv = list(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    parsed = _parse_isolation_inputs(argv, environ)
    if not parsed["requested"]:
        return None
    if parsed["conflicts"]:
        raise IsolationError(
            "isolated-profile-conflict",
            parsed["conflicts"][0],
        )
    profile = parsed["profile"]
    port = parsed["port"]
    app_dir = parsed["app_dir"]
    if not profile:
        raise IsolationError(
            "isolated-profile-missing",
            "isolated mode requires an absolute --isolated-profile "
            f"(or {ENV_PROFILE} / {CLI_FROM_INSTALL} marker)",
        )
    if port is None or port == "":
        raise IsolationError(
            "isolated-port-missing",
            "isolated mode requires --isolated-port "
            f"(or {ENV_PORT} / {CLI_FROM_INSTALL} marker)",
        )
    return validate_binding(
        profile=profile,
        port=port,
        app_dir=app_dir,
        environ=environ,
        platform_name=platform_name,
        home=home,
        require_existing=require_existing,
    )


def validate_binding(
    *,
    profile: Path | str,
    port: int | str,
    app_dir: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
    require_existing: bool = True,
) -> IsolationBinding:
    environ = os.environ if environ is None else environ
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else Path(home)
    resolved_profile = _validate_profile(
        profile,
        environ=environ,
        platform_name=platform_name,
        home=home,
        require_existing=require_existing,
    )
    resolved_port = _validate_port(port)
    resolved_app: Path | None = None
    if app_dir:
        resolved_app = _validate_app_dir(
            app_dir,
            profile=resolved_profile,
            environ=environ,
            platform_name=platform_name,
            home=home,
        )
    return IsolationBinding(
        profile=resolved_profile,
        port=resolved_port,
        host=PRODUCTION_HOST,
        app_dir=resolved_app,
    )


def validate_install_reuse(
    *,
    app_dir: Path | str,
    binding: IsolationBinding,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> None:
    """Refuse to treat an ordinary install as isolated, and refuse mismatched markers."""
    environ = os.environ if environ is None else environ
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else Path(home)
    app = Path(app_dir)
    if not _is_absolute(app):
        raise IsolationError(
            "isolated-install-app-relative",
            "isolated install directory must be an absolute path",
        )
    try:
        resolved_app = app.resolve()
    except OSError as error:
        raise IsolationError(
            "isolated-install-app-unsafe",
            f"isolated install directory could not be resolved: {error}",
        ) from error
    default_install = production_default_install_dir(
        platform_name=platform_name, environ=environ, home=home
    )
    if _same_path(resolved_app, default_install):
        raise IsolationError(
            "isolated-install-ordinary-reuse",
            "isolated mode refuses the ordinary install directory "
            f"{default_install}",
        )
    if _same_path(resolved_app, binding.profile):
        raise IsolationError(
            "isolated-profile-conflict",
            "isolated profile must not be the install directory",
        )
    marker_path = resolved_app / MARKER_FILENAME
    server_present = (resolved_app / "server.py").is_file()
    if marker_path.is_file():
        marker = read_install_marker(resolved_app)
        if not _same_path(Path(marker["profile"]), binding.profile):
            raise IsolationError(
                "isolated-install-marker-mismatch",
                "existing isolated-install.json profile does not match "
                "the requested profile",
            )
        if int(marker["port"]) != binding.port:
            raise IsolationError(
                "isolated-install-marker-mismatch",
                "existing isolated-install.json port does not match "
                "the requested port",
            )
        return
    if server_present:
        raise IsolationError(
            "isolated-install-ordinary-reuse",
            "refusing to label an ordinary installation isolated; "
            f"{MARKER_FILENAME} is missing next to server.py",
        )


def install_marker_payload(binding: IsolationBinding) -> dict:
    payload = {
        "mode": ISOLATION_MODE,
        "profile": str(binding.profile),
        "port": binding.port,
        "host": binding.host,
    }
    if binding.app_dir is not None:
        payload["app_dir"] = str(binding.app_dir)
    return payload


def write_install_marker(app_dir: Path | str, binding: IsolationBinding) -> Path:
    destination = Path(app_dir) / MARKER_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(install_marker_payload(binding), indent=2) + "\n"
    tmp = destination.with_suffix(".json.tmp")
    tmp.write_text(encoded, encoding="utf-8")
    os.replace(tmp, destination)
    return destination


def read_install_marker(app_dir: Path | str) -> dict:
    path = Path(app_dir) / MARKER_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise IsolationError(
            "isolated-install-marker-missing",
            f"{MARKER_FILENAME} is missing under {app_dir}",
        ) from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IsolationError(
            "isolated-install-marker-mismatch",
            f"{MARKER_FILENAME} is unreadable: {error}",
        ) from error
    if not isinstance(payload, dict) or payload.get("mode") != ISOLATION_MODE:
        raise IsolationError(
            "isolated-install-marker-mismatch",
            f"{MARKER_FILENAME} is not an isolated-install marker",
        )
    if not payload.get("profile") or payload.get("port") is None:
        raise IsolationError(
            "isolated-install-marker-mismatch",
            f"{MARKER_FILENAME} is missing profile or port",
        )
    return payload


def write_runtime_identity(
    binding: IsolationBinding,
    *,
    pid: int,
    executable: str,
    script: str,
    created_ms: int | None,
    nonce: str,
) -> Path:
    expected_exe = str(executable or "").strip()
    if not expected_exe:
        raise IsolationError(
            "isolated-identity-incomplete",
            "runtime identity requires the owned executable path",
        )
    if created_ms is None:
        raise IsolationError(
            "isolated-identity-incomplete",
            "runtime identity requires the owned process creation time",
        )
    try:
        created = int(created_ms)
    except (TypeError, ValueError) as error:
        raise IsolationError(
            "isolated-identity-incomplete",
            "runtime identity creation time is not an integer",
        ) from error
    payload = {
        "mode": ISOLATION_MODE,
        "pid": int(pid),
        "executable": str(Path(expected_exe).resolve()),
        "script": str(Path(script).resolve()) if script else "",
        "created_ms": created,
        "port": binding.port,
        "profile": str(binding.profile),
        "host": binding.host,
        "nonce": nonce,
    }
    if binding.app_dir is not None:
        payload["app_dir"] = str(binding.app_dir)
    path = binding.identity_path
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_runtime_identity(binding: IsolationBinding) -> dict:
    path = binding.identity_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise IsolationError(
            "isolated-stop-identity-missing",
            f"{IDENTITY_FILENAME} is missing under {binding.profile}",
        ) from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IsolationError(
            "isolated-stop-identity-mismatch",
            f"{IDENTITY_FILENAME} is unreadable: {error}",
        ) from error
    if not isinstance(payload, dict) or payload.get("mode") != ISOLATION_MODE:
        raise IsolationError(
            "isolated-stop-identity-mismatch",
            f"{IDENTITY_FILENAME} is not an isolated runtime identity",
        )
    return payload


def current_process_created_ms() -> int | None:
    try:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            return _windows_process_created_ms(kernel32.GetCurrentProcess())
        return _posix_process_created_ms(os.getpid())
    except Exception:
        return None


def current_process_executable() -> str | None:
    """Image path of this process, taken from the current-process handle."""
    try:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            return _windows_process_image(kernel32.GetCurrentProcess())
        return os.path.realpath(f"/proc/{os.getpid()}/exe")
    except Exception:
        return None


def owned_process_status(binding: IsolationBinding) -> str:
    """``alive``, ``dead`` or ``unknown`` for the profile-owned identity."""
    try:
        identity = read_runtime_identity(binding)
    except IsolationError as error:
        if error.code == "isolated-stop-identity-missing":
            return "dead"
        return "unknown"
    return _identity_liveness(identity)


def stop_owned_helper(binding: IsolationBinding) -> int:
    """Stop only the process named by the profile-owned runtime identity.

    Never kills by PID, process name, a shared-port probe, or a directory
    prefix. Missing identity is a no-op success when nothing is recorded.
    """
    try:
        identity = read_runtime_identity(binding)
    except IsolationError as error:
        if error.code == "isolated-stop-identity-missing":
            return EXIT_OK
        print(f"uoink isolated install: {error}", file=sys.stderr)
        return EXIT_STOP_IDENTITY
    if int(identity.get("port", -1)) != binding.port:
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "identity port does not match the declared isolated port",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    if not _same_path(Path(str(identity.get("profile") or "")), binding.profile):
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "identity profile does not match the declared isolated profile",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    status = _identity_liveness(identity)
    if status == "dead":
        _unlink_identity(binding)
        return EXIT_OK
    if status != "alive":
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "owned process identity could not be confirmed",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    if not _terminate_owned(identity):
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "refusing to terminate a process that failed the ownership check",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    if _identity_liveness(identity) != "dead":
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "owned process did not exit after terminate",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    _unlink_identity(binding)
    return EXIT_OK


def upgrade_allowed(binding: IsolationBinding) -> int:
    """Refuse a running isolated upgrade; require the explicit stop command."""
    status = owned_process_status(binding)
    if status == "alive":
        print(
            "uoink isolated install: isolated-running-requires-stop: "
            "the owned isolated helper is still running; "
            "run the isolated stop command before upgrade",
            file=sys.stderr,
        )
        return EXIT_RUNNING
    if status == "unknown":
        print(
            "uoink isolated install: isolated-stop-identity-mismatch: "
            "cannot prove the owned helper is stopped",
            file=sys.stderr,
        )
        return EXIT_STOP_IDENTITY
    return EXIT_OK


def cli(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if CLI_STOP in argv:
            binding = resolve_from_process(argv)
            if binding is None:
                raise IsolationError(
                    "isolated-profile-missing",
                    "isolated stop requires a declared profile and port",
                )
            return stop_owned_helper(binding)
        if CLI_UPGRADE_CHECK in argv:
            binding = resolve_from_process(argv)
            if binding is None:
                raise IsolationError(
                    "isolated-profile-missing",
                    "isolated upgrade check requires a declared profile and port",
                )
            if parsed_app_dir(argv) is not None:
                validate_install_reuse(
                    app_dir=parsed_app_dir(argv),
                    binding=binding,
                )
            return upgrade_allowed(binding)
        binding = resolve_from_process(argv)
    except IsolationError as error:
        print(f"uoink isolated install: {error}", file=sys.stderr)
        return EXIT_VALIDATION
    if binding is None:
        print(
            "usage: python uoink_install_isolation.py "
            f"{CLI_STOP}|{CLI_UPGRADE_CHECK} {CLI_PROFILE} PATH {CLI_PORT} PORT",
            file=sys.stderr,
        )
        return EXIT_USAGE
    print(json.dumps(install_marker_payload(binding), indent=2))
    return EXIT_OK


def parsed_app_dir(argv: list[str]) -> str | None:
    parsed = _parse_isolation_inputs(argv, os.environ)
    return parsed["app_dir"]


# --------------------------------------------------------------------------
# Internal validation
# --------------------------------------------------------------------------
def _looks_like_cli_flag(arg: str) -> bool:
    return arg.startswith("-") and arg != "-"


def _assign_unique_flag(store: dict[str, str], flag: str, value: str) -> None:
    previous = store.get(flag)
    if previous is not None and previous != value:
        raise IsolationError(
            "isolated-profile-conflict",
            f"duplicate {flag} values disagree",
        )
    store[flag] = value


def _parse_isolation_inputs(
    argv: list[str],
    environ: Mapping[str, str],
) -> dict:
    seen: dict[str, str] = {}
    i = 0
    stop_or_check = False
    while i < len(argv):
        arg = argv[i]
        if arg in _VALUE_FLAGS:
            if i + 1 >= len(argv) or _looks_like_cli_flag(argv[i + 1]):
                raise IsolationError(
                    "isolated-argument-invalid",
                    f"{arg} requires a value",
                )
            _assign_unique_flag(seen, arg, argv[i + 1])
            i += 2
            continue
        if arg in _BARE_FLAGS:
            stop_or_check = True
            i += 1
            continue
        if arg.startswith("--isolated-"):
            raise IsolationError(
                "isolated-argument-invalid",
                f"unknown isolation argument {arg}",
            )
        i += 1
    cli_profile = seen.get(CLI_PROFILE)
    cli_port = seen.get(CLI_PORT)
    cli_app = seen.get(CLI_FROM_INSTALL)
    env_profile = (environ.get(ENV_PROFILE) or "").strip() or None
    env_port = (environ.get(ENV_PORT) or "").strip() or None
    env_app = (environ.get(ENV_APP_DIR) or "").strip() or None
    marker_profile = None
    marker_port = None
    marker_app = None
    conflicts: list[str] = []
    if cli_app:
        try:
            marker = read_install_marker(cli_app)
            marker_profile = str(marker["profile"])
            marker_port = str(marker["port"])
            marker_app = str(Path(cli_app))
        except IsolationError as error:
            conflicts.append(str(error))
    profile_sources = [
        value for value in (cli_profile, marker_profile, env_profile) if value
    ]
    port_sources = [value for value in (cli_port, marker_port, env_port) if value]
    if cli_profile and marker_profile and not _same_path(Path(cli_profile), Path(marker_profile)):
        conflicts.append("CLI profile does not match isolated-install.json")
    if cli_profile and env_profile and not _same_path(Path(cli_profile), Path(env_profile)):
        conflicts.append("CLI profile does not match UOINK_ISOLATED_PROFILE")
    if marker_profile and env_profile and cli_profile is None:
        if not _same_path(Path(marker_profile), Path(env_profile)):
            conflicts.append("isolated-install.json profile does not match environment")
    if cli_port and marker_port and str(cli_port) != str(marker_port):
        conflicts.append("CLI port does not match isolated-install.json")
    if cli_port and env_port and str(cli_port) != str(env_port):
        conflicts.append("CLI port does not match UOINK_ISOLATED_PORT")
    if marker_port and env_port and cli_port is None and str(marker_port) != str(env_port):
        conflicts.append("isolated-install.json port does not match environment")
    profile = cli_profile or marker_profile or env_profile
    port = cli_port or marker_port or env_port
    app_dir = cli_app or marker_app or env_app
    requested = bool(
        profile_sources
        or port_sources
        or cli_app
        or env_app
        or stop_or_check
    )
    return {
        "requested": requested,
        "profile": profile,
        "port": port,
        "app_dir": app_dir,
        "conflicts": conflicts,
    }


def _validate_port(port: int | str) -> int:
    raw = str(port).strip()
    if not raw:
        raise IsolationError(
            "isolated-port-missing",
            "isolated mode requires a declared loopback port",
        )
    try:
        value = int(raw, 10)
    except (TypeError, ValueError) as error:
        raise IsolationError(
            "isolated-port-invalid",
            f"isolated port {raw!r} is not an integer",
        ) from error
    if value < 1 or value > 65535:
        raise IsolationError(
            "isolated-port-invalid",
            f"isolated port {value} is outside 1-65535",
        )
    if value == PRODUCTION_PORT:
        raise IsolationError(
            "isolated-port-forbidden",
            f"isolated mode cannot use production port {PRODUCTION_PORT}",
        )
    return value


def _validate_profile(
    profile: Path | str,
    *,
    environ: Mapping[str, str],
    platform_name: str,
    home: Path,
    require_existing: bool,
) -> Path:
    raw = str(profile).strip()
    if not raw:
        raise IsolationError(
            "isolated-profile-missing",
            "isolated mode requires an absolute profile directory",
        )
    path = Path(raw)
    if not _is_absolute(path):
        raise IsolationError(
            "isolated-profile-relative",
            f"isolated profile {raw!r} is not absolute",
        )
    try:
        resolved = path.resolve()
    except OSError as error:
        raise IsolationError(
            "isolated-profile-unsafe",
            f"isolated profile could not be resolved: {error}",
        ) from error
    if _is_root_volume(resolved, platform_name=platform_name):
        raise IsolationError(
            "isolated-profile-root-volume",
            f"isolated profile {resolved} is a root volume",
        )
    if _is_unsafe_system_path(resolved, platform_name=platform_name, environ=environ, home=home):
        raise IsolationError(
            "isolated-profile-unsafe",
            f"isolated profile {resolved} is a protected system path",
        )
    forbidden = _forbidden_library_paths(
        platform_name=platform_name, environ=environ, home=home
    )
    for candidate in forbidden:
        if _same_path(resolved, candidate) or _is_nested(resolved, candidate) or _is_nested(candidate, resolved):
            code = (
                "isolated-profile-legacy-data"
                if candidate.name.lower() == "yoink"
                else "isolated-profile-normal-data"
            )
            raise IsolationError(
                code,
                f"isolated profile {resolved} collides with {candidate}",
            )
    if require_existing:
        if not path.exists() and not resolved.exists():
            raise IsolationError(
                "isolated-profile-not-found",
                f"isolated profile {resolved} does not exist",
            )
        if not resolved.is_dir():
            raise IsolationError(
                "isolated-profile-not-directory",
                f"isolated profile {resolved} is not a directory",
            )
    return resolved


def _validate_app_dir(
    app_dir: Path | str,
    *,
    profile: Path,
    environ: Mapping[str, str],
    platform_name: str,
    home: Path,
) -> Path:
    path = Path(str(app_dir).strip())
    if not _is_absolute(path):
        raise IsolationError(
            "isolated-install-app-relative",
            "isolated install directory must be an absolute path",
        )
    try:
        resolved = path.resolve()
    except OSError as error:
        raise IsolationError(
            "isolated-install-app-unsafe",
            f"isolated install directory could not be resolved: {error}",
        ) from error
    if _is_root_volume(resolved, platform_name=platform_name):
        raise IsolationError(
            "isolated-profile-root-volume",
            f"isolated install directory {resolved} is a root volume",
        )
    if _same_path(resolved, profile):
        raise IsolationError(
            "isolated-profile-conflict",
            "isolated profile must not be the install directory",
        )
    default_install = production_default_install_dir(
        platform_name=platform_name, environ=environ, home=home
    )
    if _same_path(resolved, default_install):
        raise IsolationError(
            "isolated-install-ordinary-reuse",
            "isolated mode refuses the ordinary install directory",
        )
    return resolved


def _forbidden_library_paths(
    *,
    platform_name: str,
    environ: Mapping[str, str],
    home: Path,
) -> list[Path]:
    paths = [
        production_user_data_dir(
            platform_name=platform_name, environ=environ, home=home
        ),
        production_legacy_data_dir(
            platform_name=platform_name, environ=environ, home=home
        ),
    ]
    paths.extend(
        production_desktop_corpus_dirs(
            platform_name=platform_name, environ=environ, home=home
        )
    )
    return [_safe_resolve(path) for path in paths]


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _is_absolute(path: Path) -> bool:
    return path.is_absolute()


def _is_root_volume(path: Path, *, platform_name: str) -> bool:
    resolved = _safe_resolve(path)
    if resolved.parent == resolved:
        return True
    if platform_name == "win32":
        drive = resolved.drive
        if drive and resolved == Path(drive + "\\"):
            return True
        parts = resolved.parts
        if len(parts) <= 1:
            return True
        if resolved.anchor == resolved:
            return True
    return False


def _is_unsafe_system_path(
    path: Path,
    *,
    platform_name: str,
    environ: Mapping[str, str],
    home: Path,
) -> bool:
    resolved = _safe_resolve(path)
    if platform_name == "win32":
        windir = Path(environ.get("WINDIR") or r"C:\Windows")
        program_files = Path(environ.get("ProgramFiles") or r"C:\Program Files")
        program_files_x86 = Path(
            environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        )
        protected = [windir, program_files, program_files_x86]
        for candidate in protected:
            candidate = _safe_resolve(candidate)
            if _same_path(resolved, candidate) or _is_nested(resolved, candidate):
                return True
        return False
    protected = [Path("/"), Path("/etc"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/System")]
    for candidate in protected:
        if _same_path(resolved, candidate) or (
            candidate != Path("/") and _is_nested(resolved, candidate)
        ):
            return True
    return False


def _same_path(left: Path, right: Path) -> bool:
    try:
        a = os.path.normcase(os.path.normpath(str(left.resolve())))
        b = os.path.normcase(os.path.normpath(str(right.resolve())))
    except OSError:
        a = os.path.normcase(os.path.normpath(str(left)))
        b = os.path.normcase(os.path.normpath(str(right)))
    return a == b


def _is_nested(inner: Path, outer: Path) -> bool:
    try:
        inner.resolve().relative_to(outer.resolve())
        return not _same_path(inner, outer)
    except (OSError, ValueError):
        return False


def _set_current(binding: IsolationBinding | None) -> None:
    global _CURRENT
    _CURRENT = binding


def _export_env(binding: IsolationBinding) -> None:
    global _ENV_SNAPSHOT
    if _ENV_SNAPSHOT is None:
        _ENV_SNAPSHOT = _capture_env()
    os.environ[ENV_PROFILE] = str(binding.profile)
    os.environ[ENV_PORT] = str(binding.port)
    if binding.app_dir is not None:
        os.environ[ENV_APP_DIR] = str(binding.app_dir)
    elif ENV_APP_DIR in os.environ and _ENV_SNAPSHOT.get(ENV_APP_DIR) is None:
        os.environ.pop(ENV_APP_DIR, None)


def _capture_env() -> dict[str, str | None]:
    return {
        ENV_PROFILE: os.environ.get(ENV_PROFILE),
        ENV_PORT: os.environ.get(ENV_PORT),
        ENV_APP_DIR: os.environ.get(ENV_APP_DIR),
    }


def _restore_env(snapshot: dict[str, str | None] | None) -> None:
    global _ENV_SNAPSHOT
    if snapshot is None:
        return
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _ENV_SNAPSHOT = None


def _unlink_identity(binding: IsolationBinding) -> None:
    try:
        binding.identity_path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        binding.pid_path.unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Process identity
# --------------------------------------------------------------------------
def _parse_owned_identity(identity: dict) -> dict | None:
    """Return pid/created_ms/executable only when the record is complete."""
    try:
        pid = int(identity["pid"])
        created = int(identity["created_ms"])
    except (KeyError, TypeError, ValueError):
        return None
    expected_exe = str(identity.get("executable") or "").strip()
    if not expected_exe:
        return None
    return {"pid": pid, "created_ms": created, "executable": expected_exe}


def _identity_liveness(identity: dict) -> str:
    parsed = _parse_owned_identity(identity)
    if parsed is None:
        return "unknown"
    return _pid_identity_liveness(
        parsed["pid"], parsed["created_ms"], parsed["executable"]
    )


def _pid_liveness(pid: int, created_ms: int | None) -> str:
    """PID plus exact creation identity. Incomplete creation is never alive."""
    if created_ms is None:
        return "unknown"
    try:
        created = int(created_ms)
    except (TypeError, ValueError):
        return "unknown"
    return _pid_identity_liveness(int(pid), created, None)


def _pid_identity_liveness(
    pid: int, created_ms: int, expected_exe: str | None
) -> str:
    try:
        if os.name == "nt":
            handle, error = _windows_open_process(
                int(pid), _PROCESS_QUERY_LIMITED_INFORMATION
            )
            if not handle:
                return "dead" if error == _ERROR_INVALID_PARAMETER else "unknown"
            try:
                return _windows_handle_liveness(handle, created_ms, expected_exe)
            finally:
                _windows_close_handle(handle)
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return "dead"
        except PermissionError:
            return "unknown"
        actual = _posix_process_created_ms(int(pid))
        if actual is None:
            return "unknown"
        if actual != int(created_ms):
            return "dead"
        if expected_exe is not None:
            live_exe = _process_executable(int(pid))
            if not live_exe:
                return "unknown"
            if not _same_path(Path(live_exe), Path(expected_exe)):
                return "dead"
        return "alive"
    except Exception:
        return "unknown"


def _windows_open_process(pid: int, access: int):
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(int(access), False, int(pid))
    if not handle:
        return None, int(ctypes.get_last_error())
    return handle, 0


def _windows_close_handle(handle) -> None:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle(ctypes.c_void_p(handle))


def _windows_exit_code(handle) -> int | None:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
        return None
    return int(code.value)


def _windows_handle_liveness(
    handle, created_ms: int, expected_exe: str | None
) -> str:
    code = _windows_exit_code(handle)
    if code is None:
        return "unknown"
    if code != _STILL_ACTIVE:
        return "dead"
    actual = _windows_process_created_ms(handle)
    if actual is None:
        return "unknown"
    if actual != int(created_ms):
        return "dead"
    if expected_exe is not None:
        live_exe = _windows_process_image(handle)
        if not live_exe:
            return "unknown"
        if not _same_path(Path(live_exe), Path(expected_exe)):
            return "dead"
    return "alive"


def _windows_process_image(handle) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    size = wintypes.DWORD(32768)
    buf = ctypes.create_unicode_buffer(size.value)
    if not kernel32.QueryFullProcessImageNameW(
        wintypes.HANDLE(handle), 0, buf, ctypes.byref(size)
    ):
        return None
    return buf.value or None


def _process_executable(pid: int) -> str | None:
    try:
        if os.name == "nt":
            handle, _error = _windows_open_process(
                int(pid), _PROCESS_QUERY_LIMITED_INFORMATION
            )
            if not handle:
                return None
            try:
                return _windows_process_image(handle)
            finally:
                _windows_close_handle(handle)
        return os.path.realpath(f"/proc/{pid}/exe")
    except OSError:
        return None


def _windows_process_created_ms(handle) -> int | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not isinstance(handle, ctypes.c_void_p):
        handle = ctypes.c_void_p(handle)

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    creation, exit_, kernel, user = (_FILETIME() for _ in range(4))
    kernel32.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
    ]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    if not kernel32.GetProcessTimes(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        return None
    value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return (value - _FILETIME_EPOCH_OFFSET_100NS) // 10_000


def _posix_process_created_ms(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="ascii", errors="replace") as handle:
            stat = handle.read()
        with open("/proc/stat", "r", encoding="ascii", errors="replace") as handle:
            boot = next(int(line.split()[1]) for line in handle if line.startswith("btime "))
        ticks = int(stat.rsplit(")", 1)[1].split()[19])
        hertz = os.sysconf("SC_CLK_TCK")
        return boot * 1000 + (ticks * 1000) // hertz
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return None


def _windows_wait_handle_exit(handle, timeout_ms: int) -> bool:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    waited = kernel32.WaitForSingleObject(ctypes.c_void_p(handle), int(timeout_ms))
    if waited == _WAIT_OBJECT_0:
        code = _windows_exit_code(handle)
        return code is not None and code != _STILL_ACTIVE
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        code = _windows_exit_code(handle)
        if code is not None and code != _STILL_ACTIVE:
            return True
        time.sleep(0.05)
    code = _windows_exit_code(handle)
    return code is not None and code != _STILL_ACTIVE


def _posix_wait_pid_exit(pid: int, created_ms: int, expected_exe: str, timeout_ms: int) -> bool:
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        if _pid_identity_liveness(pid, created_ms, expected_exe) == "dead":
            return True
        time.sleep(0.05)
    return _pid_identity_liveness(pid, created_ms, expected_exe) == "dead"


def _terminate_owned(identity: dict) -> bool:
    """Terminate only after the same open handle proves exact ownership."""
    parsed = _parse_owned_identity(identity)
    if parsed is None:
        return False
    pid = parsed["pid"]
    created_ms = parsed["created_ms"]
    expected_exe = parsed["executable"]
    try:
        if os.name == "nt":
            import ctypes

            access = (
                _PROCESS_QUERY_LIMITED_INFORMATION
                | _PROCESS_TERMINATE
                | _SYNCHRONIZE
            )
            handle, _error = _windows_open_process(pid, access)
            if not handle:
                handle, _error = _windows_open_process(
                    pid, _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_TERMINATE
                )
            if not handle:
                return False
            try:
                if _windows_handle_liveness(handle, created_ms, expected_exe) != "alive":
                    return False
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                kernel32.TerminateProcess.restype = ctypes.c_int
                if not kernel32.TerminateProcess(ctypes.c_void_p(handle), 1):
                    return False
                return _windows_wait_handle_exit(handle, _STOP_WAIT_MS)
            finally:
                _windows_close_handle(handle)
        if _pid_identity_liveness(pid, created_ms, expected_exe) != "alive":
            return False
        os.kill(pid, 15)
        return _posix_wait_pid_exit(pid, created_ms, expected_exe, _STOP_WAIT_MS)
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
