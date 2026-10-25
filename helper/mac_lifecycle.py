"""Opt-in macOS login startup and identity-checked removal. No server import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

from _platform import MAC_BUNDLE_PYTHON

LABEL = "com.ryanbiddy.uoink"


def app_path(location: Path) -> Path:
    location = location.absolute()
    if location.name == "Resources" and location.parent.name == "Contents":
        location = location.parent.parent
    if location.suffix != ".app" or location.is_symlink():
        raise ValueError("Select the installed Uoink.app bundle, not a link or source checkout")
    location = location.resolve(strict=True)
    with (location / "Contents/Info.plist").open("rb") as stream:
        if plistlib.load(stream).get("CFBundleIdentifier") != LABEL:
            raise ValueError("The selected app is not Uoink")
    for relative in ("MacOS/Uoink", MAC_BUNDLE_PYTHON, "Resources/server.py", "Resources/uoink_mcp.py"):
        path = location / "Contents" / relative
        if not path.is_file() or not path.resolve().is_relative_to(location):
            raise ValueError(f"Uoink installation is incomplete: {relative}")
    return location


def agent_path(home: Path) -> Path:
    return home / "Library/LaunchAgents" / (LABEL + ".plist")


def plist(app: Path, home: Path) -> dict:
    contents = app_path(app) / "Contents"
    return {"Label": LABEL,
            "ProgramArguments": [str(contents / "MacOS/Uoink"), "--helper", "--startup"],
            "WorkingDirectory": str(contents / "Resources"),
            "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 30, "ProcessType": "Background",
            "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
            # Helper stdout/stderr are captured and rotated by the supervisor.
            "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}


def launchctl(*args):
    result = subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True, timeout=20)
    return result


def domain() -> str:
    return f"gui/{os.getuid()}"


def loaded() -> bool:
    result = launchctl("print", f"{domain()}/{LABEL}")
    if result.returncode == 0:
        return True
    # launchctl's ESRCH is the only absence we treat as a successful no-op.
    if result.returncode == 113:
        return False
    raise OSError(f"launchctl print failed ({result.returncode}): {result.stderr.strip()}")


def status(app: Path, home: Path | None = None) -> dict:
    home = Path.home() if home is None else home
    path = agent_path(home)
    enabled = False
    if path.exists():
        if path.is_symlink():
            raise ValueError("Refusing a linked LaunchAgent")
        with path.open("rb") as stream:
            enabled = plistlib.load(stream) == plist(app, home)
    return {"enabled": enabled, "loaded": loaded(), "path": str(path)}


def owned_agent(app: Path, home: Path) -> dict | None:
    """Read the on-disk definition before any unload, replacement or removal."""
    path = agent_path(home)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Refusing a linked LaunchAgent path")
    if not path.exists():
        return None
    try:
        with path.open("rb") as stream:
            payload = plistlib.load(stream)
        args = payload.get("ProgramArguments") if isinstance(payload, dict) else None
        if (not isinstance(args, list) or not args or not isinstance(args[0], str) or
                not args[0] or payload.get("Label") != LABEL):
            raise ValueError("Invalid LaunchAgent definition")
        program = Path(args[0])
        if (not program.is_absolute() or not program.resolve(strict=True).is_relative_to(app) or
                not program.is_file()):
            raise ValueError("LaunchAgent belongs to another install")
        # launchd's Program key overrides ProgramArguments[0]. Reject a
        # conflicting executable even when the argument list looks owned.
        if "Program" in payload and payload["Program"] != args[0]:
            raise ValueError("LaunchAgent has a conflicting Program")
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise ValueError(f"Cannot prove LaunchAgent ownership; refusing changes: {exc}") from exc
    return payload


def check_disable(app: Path, home: Path | None = None) -> bool:
    """Validate both file and loaded service without changing either."""
    home = Path.home() if home is None else home
    app = app_path(app)
    payload = owned_agent(app, home)
    if loaded():
        if payload is None:
            raise ValueError("Loaded LaunchAgent has no owned plist; refusing bootout")
        service = launchctl("print", f"{domain()}/{LABEL}")
        if service.returncode != 0:
            raise OSError("LaunchAgent changed before bootout")
        program = re.search(r"(?m)^\s*program = (.+)$", service.stdout)
        expected = Path(payload["ProgramArguments"][0]).resolve(strict=True)
        if not program or Path(program.group(1).strip()).resolve() != expected:
            raise ValueError("Loaded LaunchAgent belongs to another install; refusing bootout")
        pid = re.search(r"(?m)^\s*pid = (\d+)\s*$", service.stdout)
        if pid:
            import _platform
            identity = read_identity(app, home, supervisor="--startup" in payload["ProgramArguments"])
            if (identity is None or identity.get("pid") != int(pid.group(1)) or
                    _platform.darwin_liveness(identity.get("pid"), identity.get("created_ms"), identity.get("executable")) != "alive"):
                raise ValueError("Loaded LaunchAgent process ownership is unknown; refusing bootout")
        return True
    return False


def bootout(app: Path, home: Path | None = None) -> None:
    if check_disable(app, home):
        result = launchctl("bootout", f"{domain()}/{LABEL}")
        if result.returncode != 0:
            raise OSError(f"launchctl bootout failed ({result.returncode}): {result.stderr.strip()}")


def disable_after_reply(app: Path) -> None:
    """Finish a settings disable even if bootout terminates the HTTP helper."""
    app = app_path(app)
    if not check_disable(app):
        set_enabled(app, False)
        return
    contents = app / "Contents"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("DYLD_") and key not in {
               "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE"}}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    # A separate session survives launchd's termination of the service process
    # group. The child rechecks ownership, boots out, then removes the plist.
    subprocess.Popen([str(contents / MAC_BUNDLE_PYTHON), "-B", "-s", "-m",
                      "helper.mac_lifecycle", "disable", str(app)],
                     cwd=contents / "Resources", env=env, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def set_enabled(app: Path, enabled: bool, home: Path | None = None) -> None:
    home = Path.home() if home is None else home
    app = app_path(app)
    path = agent_path(home)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Refusing a linked LaunchAgent path")
    if not enabled:
        bootout(app, home)
        # Do not delete a replacement written while launchctl was running.
        owned_agent(app, home)
        path.unlink(missing_ok=True)
        return
    payload = plist(app, home)
    if status(app, home)["enabled"] and loaded():
        return
    # Never replace a loaded definition without unloading it first.
    bootout(app, home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    logs = home / "Library/Logs/Uoink"
    if any(p.is_symlink() for p in (logs, *logs.parents)):
        raise ValueError("Refusing a linked log directory")
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("launchd.out.log", "launchd.err.log"):
        log = logs / name
        if log.is_symlink() or (log.exists() and (not log.is_file() or log.stat().st_uid != os.getuid())):
            raise ValueError("Refusing a log file not owned by this user")
    fd, name = tempfile.mkstemp(prefix=".uoink-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            plistlib.dump(payload, stream)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    result = launchctl("bootstrap", domain(), str(path))
    if result.returncode != 0:
        path.unlink(missing_ok=True)
        raise OSError(f"launchctl bootstrap failed ({result.returncode}): {result.stderr.strip()}")


def uninstall_plan(app: Path, home: Path) -> dict:
    app = app_path(app)
    return {"app": str(app), "launchagent": str(agent_path(home)),
            "identity": str(home / "Library/Application Support/Uoink/runtime-identity.json"),
            "preserve": ["captures", "settings", "Keychain", "extension", "client configurations", "logs"],
            "process_policy": "Only the recorded helper with matching script, executable and creation identity"}


def read_identity(app: Path, home: Path, *, supervisor: bool = False) -> dict | None:
    filename = "supervisor-identity.json" if supervisor else "runtime-identity.json"
    path = home / "Library/Application Support/Uoink" / filename
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("Refusing a linked runtime identity")
    identity = json.loads(path.read_text(encoding="utf-8"))
    contents = app / "Contents"
    if (not isinstance(identity, dict) or
            Path(identity.get("script", "")).resolve() != (contents / "Resources" / ("uoink_supervisor.py" if supervisor else "server.py")).resolve() or
            Path(identity.get("executable", "")).resolve() != (contents / MAC_BUNDLE_PYTHON).resolve()):
        raise ValueError("Runtime identity belongs to another install; no process stopped or app removed")
    return identity


def stop_verified(app: Path, home: Path) -> None:
    import _platform
    import uoink_install_isolation as identity_api
    identity = read_identity(app, home)
    if identity is None:
        return
    state = _platform.darwin_liveness(identity.get("pid"), identity.get("created_ms"), identity.get("executable"))
    if state == "dead":
        return
    if state != "alive" or not identity_api._terminate_owned(identity):
        raise ValueError("Uoink process ownership or exit could not be verified; app retained")


def uninstall(app: Path, home: Path) -> dict:
    plan = uninstall_plan(app, home)
    app = Path(plan["app"])
    set_enabled(app, False, home)
    # A manually opened app can own a supervisor outside launchd. Validate
    # recorded ownership before preventing its helper from restarting.
    read_identity(app, home)
    read_identity(app, home, supervisor=True)
    from uoink_supervisor import request_stop
    request_stop(home / "Library/Application Support/Uoink", reason="uninstall")
    stop_verified(app, home)
    # Validate again after stopping. Never remove a link or an unrelated bundle.
    if app_path(app) != app:
        raise ValueError("App changed during removal")
    shutil.rmtree(app)
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plist", "enable", "disable", "status", "uninstall"])
    parser.add_argument("app", type=Path)
    parser.add_argument("--remove", action="store_true", help="remove the app; otherwise uninstall only prints a plan")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("This helper requires macOS")
    try:
        home = Path.home()
        if args.action == "plist":
            sys.stdout.buffer.write(plistlib.dumps(plist(args.app, home)))
        elif args.action == "status":
            print(json.dumps(status(args.app, home)))
        elif args.action == "uninstall":
            print(json.dumps(uninstall(args.app, home) if args.remove else uninstall_plan(args.app, home), indent=2))
        else:
            set_enabled(args.app, args.action == "enable", home)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Uoink: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
