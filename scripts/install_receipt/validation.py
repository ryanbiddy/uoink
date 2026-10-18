"""Fail-closed validation of C22 operator inputs.

Required: installed path, package hash, isolated profile, non-5179 port.
Nothing is auto-discovered. Ordinary profiles, relative roots, port 5179,
checkout resolution and user-site resolution are refused.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    DEFAULT_HELPER_NAMES,
    FORBIDDEN_PORT,
    INNO_DIR_FLAG,
    INNO_FORBIDDEN_OVERRIDES,
    INNO_ISOLATED_FLAG,
    INNO_NOCLOSE_FLAG,
    INNO_NORESTARTAPPS_FLAG,
    INNO_PORT_FLAG,
    INNO_PROFILE_FLAG,
    ISOLATED_PORT_FLAG,
    ISOLATED_PROFILE_FLAG,
    LIVE_INDEX_TAIL,
    ORDINARY_LIVE_INDEX,
    ORDINARY_USERPROFILE,
    YOINK_INDEX_TAIL,
)
from .hashes import sha256_file


class C22ValidationError(ValueError):
    """Operator input was refused. Partial receipt state must be kept."""


def as_absolute(path: str | Path, *, label: str) -> Path:
    text = str(path or "").strip()
    if not text:
        raise C22ValidationError(f"{label} is required")
    candidate = Path(text)
    if not candidate.is_absolute():
        raise C22ValidationError(f"{label} must be an absolute path: {text}")
    try:
        return candidate.resolve()
    except OSError as exc:
        raise C22ValidationError(f"{label} is not resolvable: {exc}") from exc


def validate_port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise C22ValidationError("isolated port must be an integer") from exc
    if port == FORBIDDEN_PORT:
        raise C22ValidationError(
            f"port {FORBIDDEN_PORT} is forbidden; pass {ISOLATED_PORT_FLAG} "
            "with a declared non-5179 loopback port")
    if port < 1024 or port > 65535:
        raise C22ValidationError(
            f"isolated port {port} is out of range 1024-65535 excluding "
            f"{FORBIDDEN_PORT}")
    return port


def ordinary_userprofile() -> str:
    return os.environ.get("USERPROFILE") or str(Path.home())


def ordinary_localappdata() -> str:
    home = Path(ordinary_userprofile())
    return os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")


def live_index_path() -> Path:
    """Path object for comparisons only. Callers must not open or hash it."""
    return Path(forbidden_live_path_string())


def forbidden_live_path_string() -> str:
    """Integrator IG_FORBIDDEN_LIVE, else the conventional live index string.

    Never derived from a redirected LOCALAPPDATA. Never opened or hashed.
    """
    ig = (os.environ.get("IG_FORBIDDEN_LIVE") or "").strip()
    if ig:
        return ig
    return ORDINARY_LIVE_INDEX


def _is_same_or_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_ordinary_profile(path: Path) -> bool:
    """True when *path* is the live Uoink/Yoink data root, not merely under
    the ordinary Windows user directory (worktrees and receipt scratch live
    there too)."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    local = Path(ordinary_localappdata())
    ordinary_local = Path(ORDINARY_USERPROFILE) / "AppData" / "Local"
    forbidden_roots = (
        local / "Uoink",
        local / "Yoink",
        ordinary_local / "Uoink",
        ordinary_local / "Yoink",
        Path(os.environ.get("APPDATA") or local.parent / "Roaming") / "Uoink",
        Path(os.environ.get("APPDATA") or local.parent / "Roaming") / "Yoink",
    )
    return any(_is_same_or_under(resolved, root) for root in forbidden_roots)


def validate_not_ordinary_user() -> str:
    profile = ordinary_userprofile()
    if os.path.normcase(os.path.normpath(profile)) == os.path.normcase(
            os.path.normpath(ORDINARY_USERPROFILE)):
        raise C22ValidationError(
            "Use the throwaway Windows profile, not Ryan's ordinary profile "
            f"({ORDINARY_USERPROFILE}).")
    return profile


def validate_contained_root(path: str | Path, *, label: str,
                            must_be_empty: bool = False,
                            must_not_exist: bool = False) -> Path:
    root = as_absolute(path, label=label)
    if root.drive and root == Path(root.drive + "\\"):
        raise C22ValidationError(f"{label} may not be a volume root")
    if is_ordinary_profile(root):
        raise C22ValidationError(
            f"{label} collides with an ordinary user profile or live Uoink/"
            "Yoink data root")
    live = live_index_path()
    try:
        if root == live.parent or root == live or live.is_relative_to(root):
            raise C22ValidationError(
                f"{label} must not contain or equal the live index "
                f"{live}")
    except AttributeError:
        pass
    if must_not_exist and root.exists():
        raise C22ValidationError(
            f"{label} already exists. Preserve it; do not overwrite or rerun: "
            f"{root}")
    if root.exists() and not root.is_dir():
        raise C22ValidationError(f"{label} exists and is not a directory")
    if must_be_empty and root.exists():
        leftover = [p.name for p in root.iterdir()]
        if leftover:
            raise C22ValidationError(
                f"{label} is not a fresh empty root: {leftover[:8]}")
    return root


def validate_receipt_root(path: str | Path) -> Path:
    return validate_contained_root(
        path, label="receipt_root", must_not_exist=True)


def validate_isolated_profile(path: str | Path, *, receipt_root: Path) -> Path:
    profile = validate_contained_root(path, label="isolated_profile")
    try:
        profile.relative_to(receipt_root.resolve())
    except ValueError as exc:
        raise C22ValidationError(
            f"isolated profile must stay inside the receipt root: {profile}"
        ) from exc
    if profile == receipt_root.resolve():
        raise C22ValidationError(
            "isolated profile must be a named child of the receipt root "
            "(empty or populated), not the receipt root itself")
    return profile


def validate_sha256(value: Any, *, label: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise C22ValidationError(
            f"{label} is required; this kit does not invent package hashes")
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise C22ValidationError(f"{label} is not a SHA-256 hex digest")
    return text


def validate_git_commit(value: Any, *, label: str) -> str:
    """Real 40-hex Git commit. A 64-hex SHA-256 is not a commit."""
    text = str(value or "").strip().lower()
    if not text:
        raise C22ValidationError(f"{label} is required")
    if len(text) == 64:
        raise C22ValidationError(
            f"{label} is a 64-hex digest, not a 40-hex Git commit")
    if len(text) != 40 or any(c not in "0123456789abcdef" for c in text):
        raise C22ValidationError(f"{label} is not a 40-hex Git commit")
    return text


def validate_package(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    package = as_absolute(path, label="package_path")
    if not package.is_file():
        raise C22ValidationError(f"package is not a file: {package}")
    expected = validate_sha256(expected_sha256, label="package_sha256")
    actual = sha256_file(package)
    if actual != expected:
        raise C22ValidationError(
            "package hash differs from the operator-supplied digest "
            f"(actual={actual} expected={expected})")
    return {
        "path": str(package),
        "bytes": package.stat().st_size,
        "sha256": actual,
        "matched_supplied_digest": True,
    }


def validate_installed_app(path: str | Path, *, require_space: bool,
                           require_bundled_python: bool,
                           require_exists: bool = True) -> dict[str, Any]:
    app = as_absolute(path, label="installed_app_path")
    if not require_exists:
        if require_space and " " not in app.name and " " not in str(app):
            raise C22ValidationError(
                "installed application directory must contain a space in its path "
                f"(runbook requirement): {app}")
        return {
            "path": str(app),
            "server_py": str(app / "server.py"),
            "interpreter": None,
            "has_space": " " in str(app),
            "bundled_python": False,
            "present": app.is_dir(),
            "intended_before_install": True,
        }
    if not app.is_dir():
        raise C22ValidationError(f"installed app path is not a directory: {app}")
    if require_space and " " not in app.name and " " not in str(app):
        raise C22ValidationError(
            "installed application directory must contain a space in its path "
            f"(runbook requirement): {app}")
    server = app / "server.py"
    if not server.is_file():
        raise C22ValidationError(
            f"installed server.py is missing; refusing checkout substitution: "
            f"{server}")
    python_exe = app / "python" / "python.exe"
    pythonw = app / "python" / "pythonw.exe"
    interpreter = python_exe if python_exe.is_file() else (
        pythonw if pythonw.is_file() else None)
    if require_bundled_python and interpreter is None:
        raise C22ValidationError(
            "bundled interpreter python/python.exe is missing under "
            f"{app}; will not fall back to PATH or a checkout interpreter")
    return {
        "path": str(app),
        "server_py": str(server),
        "interpreter": str(interpreter) if interpreter else None,
        "has_space": " " in str(app),
        "bundled_python": interpreter is not None,
    }


def assert_isolation_flags(argv: Iterable[str]) -> None:
    args = list(argv)
    names = {Path(part).name.lower() for part in args}
    if names & {n.lower() for n in DEFAULT_HELPER_NAMES}:
        raise C22ValidationError(
            "refusing the production default helper "
            f"{sorted(names & {n.lower() for n in DEFAULT_HELPER_NAMES})}")
    joined = args
    if ISOLATED_PROFILE_FLAG not in joined:
        raise C22ValidationError(
            f"command is missing required {ISOLATED_PROFILE_FLAG}")
    if ISOLATED_PORT_FLAG not in joined:
        raise C22ValidationError(
            f"command is missing required {ISOLATED_PORT_FLAG}")
    profile = _flag_value(args, ISOLATED_PROFILE_FLAG)
    port = _flag_value(args, ISOLATED_PORT_FLAG)
    as_absolute(profile, label="command isolated-profile")
    validate_port(port)
    if str(FORBIDDEN_PORT) in args:
        raise C22ValidationError("command mentions forbidden port 5179")


def child_env_forbidden_resolution(env: dict[str, str], *,
                                   checkout: Path | None = None) -> None:
    pythonpath = env.get("PYTHONPATH") or ""
    parts = [Path(p) for p in pythonpath.split(os.pathsep) if p]
    if env.get("PYTHONNOUSERSITE") not in {"1", "true", "True"}:
        raise C22ValidationError(
            "installed child must set PYTHONNOUSERSITE=1")
    if env.get("ANTHROPIC_API_KEY"):
        raise C22ValidationError("ANTHROPIC_API_KEY must be unset")
    for part in parts:
        resolved = part.resolve()
        if checkout is not None:
            root = checkout.resolve()
            if resolved == root:
                raise C22ValidationError(
                    f"installed child PYTHONPATH includes checkout root: {part}")
            sourceish = {
                root / "server.py", root / "index.py",
                root / "source_subscriptions.py",
            }
            if resolved in {p.parent for p in sourceish}:
                raise C22ValidationError(
                    f"installed child PYTHONPATH includes checkout sources: {part}")
        lowered = str(resolved).replace("\\", "/").lower()
        if "site-packages" in lowered and (
                "/roaming/" in lowered or "/appdata/roaming/" in lowered
                or "/nethood/" in lowered):
            raise C22ValidationError(
                f"installed child PYTHONPATH includes user-site: {part}")


def validate_inno_argv(argv: Iterable[str]) -> list[str]:
    """Require isolated Inno close/restart refusals. Reject positive overrides."""
    args = [str(part) for part in argv]
    joined_upper = " ".join(args).upper()
    for flag in INNO_FORBIDDEN_OVERRIDES:
        if flag in joined_upper or any(
                part.upper().startswith(flag + "=") for part in args):
            raise C22ValidationError(
                f"refusing Inno positive override {flag}; isolated installs "
                f"require {INNO_NOCLOSE_FLAG} {INNO_NORESTARTAPPS_FLAG}")
    missing = [flag for flag in (INNO_NOCLOSE_FLAG, INNO_NORESTARTAPPS_FLAG)
               if flag not in joined_upper]
    if missing:
        raise C22ValidationError(
            "isolated Inno argv missing required switches "
            + " ".join(missing))
    if INNO_ISOLATED_FLAG not in joined_upper:
        raise C22ValidationError("isolated Inno argv missing /ISOLATED=1")
    if not any(part.upper().startswith(INNO_PROFILE_FLAG) or
               part.upper() == "/PROFILE" for part in args):
        raise C22ValidationError("isolated Inno argv missing /PROFILE=")
    if not any(part.upper().startswith(INNO_PORT_FLAG) or
               part.upper() == "/PORT" for part in args):
        raise C22ValidationError("isolated Inno argv missing /PORT=")
    if not any(INNO_DIR_FLAG.rstrip("=") in part.upper() for part in args):
        raise C22ValidationError("isolated Inno argv missing /DIR=")
    if str(FORBIDDEN_PORT) in args or f"/PORT={FORBIDDEN_PORT}" in joined_upper:
        raise C22ValidationError("isolated Inno argv names forbidden port 5179")
    return args


def port_is_open(host: str, port: int) -> bool:
    port = validate_port(port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _flag_value(argv: list[str], flag: str) -> str:
    try:
        index = argv.index(flag)
    except ValueError as exc:
        raise C22ValidationError(f"missing {flag}") from exc
    if index + 1 >= len(argv):
        raise C22ValidationError(f"{flag} requires a value")
    return argv[index + 1]
