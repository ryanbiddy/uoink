"""Launch a quarantined DMG copy via LaunchServices after signing keys are gone."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace
import uuid

import bundle_smoke
import dmg_smoke
import receipt
from qualify_deps import write_json
from verify_signing import command, require, verify_notarized


def launch(app: Path, scratch: Path, output: Path, report: dict) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    require(port != 5179, "Refusing the live helper port")
    env = bundle_smoke.environment(scratch, port)
    (Path(env["UOINK_ISOLATED_PROFILE"]) / ".first-run-done").write_text(
        (app / "Contents/Resources/VERSION").read_text())
    # LaunchServices needs explicit overrides; its parent does not inherit our env.
    keys = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME", "UOINK_ISOLATED_PROFILE", "UOINK_ISOLATED_PORT", "UOINK_OUTPUT_DIR",
            "YOINK_OUTPUT_DIR", "TMPDIR", "TMP", "TEMP", "PATH", "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "PYTHON_KEYRING_BACKEND")
    argv = ["/usr/bin/open", "-n", "-a", str(app), "--stdout", str(output / "launch-stdout.txt"),
            "--stderr", str(output / "launch-stderr.txt")]
    for key in keys:
        argv += ["--env", f"{key}={env[key]}"]
    argv += ["--args", "--helper"]
    try:
        opened = subprocess.run(argv, cwd=scratch, env=env, capture_output=True, text=True, timeout=30)
        report["open"] = {"exit": opened.returncode, "stdout": opened.stdout, "stderr": opened.stderr}
        require(opened.returncode == 0, "LaunchServices refused the quarantined app")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            owners = receipt.listeners(port)
            if len(owners) == 1:
                # bind_health rechecks interpreter identity and listener ownership.
                proc = SimpleNamespace(pid=owners[0], poll=lambda: None)
                try:
                    report["health"] = receipt.bind_health(proc, app, port)
                    return
                except OSError:
                    pass
            time.sleep(.25)
        raise RuntimeError("Quarantined launch did not serve /health within 120s; see launch stderr")
    finally:
        # open does not return the app PID. Only signal identities from this copy.
        for item in receipt.scoped_processes(app):
            if receipt.darwin_liveness(item["pid"], item["created_ms"], item["executable"]) == "alive":
                try:
                    os.kill(item["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        report["cleanup"] = receipt.no_survivors(app, [], port, settle=15)
        require(report["cleanup"]["ok"], "Quarantined launch left surviving processes")


def smoke(dmg: Path, output: Path, team: str) -> None:
    require(not (Path(os.environ["RUNNER_TEMP"]) / "uoink-signing-private").exists(),
            "Signing keys must be deleted before runtime checks")
    output.mkdir(parents=True, exist_ok=False)
    report = {"ok": False, "install": {}, "notarization": {}, "launch": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="uoink quarantine ") as temporary:
            scratch = Path(temporary)
            download = scratch / dmg.name
            shutil.copy2(dmg, download)
            quarantine = f"0083;{int(time.time()):x};Safari;{str(uuid.uuid4()).upper()}"
            report["quarantine_write"] = command(["xattr", "-w", "com.apple.quarantine", quarantine, download])
            require(report["quarantine_write"]["exit"] == 0, "Cannot quarantine the DMG copy")
            with dmg_smoke.installed_dmg(download, scratch, report["install"]) as (_, app):
                # Never manufacture the app attribute: the mount/copy must propagate it.
                report["app_quarantine"] = command(["xattr", "-p", "com.apple.quarantine", app])
                require(report["app_quarantine"]["exit"] == 0 and
                        bool(report["app_quarantine"]["stdout"].strip()), "Copied app lost quarantine")
                verify_notarized(app, download, team, report["notarization"])
                policy = shutil.which("syspolicy_check")
                report["syspolicy_check"] = command([policy, "distribution", app]) if policy else {"available": False}
                if policy:
                    require(report["syspolicy_check"]["exit"] == 0, "syspolicy_check distribution failed")
                launch(app, scratch, output, report["launch"])
                # Confirm execution did not break either final signature/ticket.
                report["after_launch"] = {}
                verify_notarized(app, download, team, report["after_launch"])
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(output / "quarantine.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-team-id", required=True)
    args = parser.parse_args()
    smoke(args.dmg.resolve(), args.output.resolve(), args.expected_team_id)
