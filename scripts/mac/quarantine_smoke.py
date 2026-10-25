"""Launch a quarantined DMG copy via LaunchServices after signing keys are gone."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace
import urllib.request
import uuid

import bundle_smoke
import dmg_smoke
import receipt
from qualify_deps import write_json
from verify_signing import command, require, verify_notarized


def bind_menu(app: Path, bound: dict, log_files: list[Path]) -> dict:
    """Credit the AppKit event loop and icon, bound to the verified helper."""
    port, helper = bound["port"], bound["identity"]
    require(port != 5179, "Menu must use a disposable port")

    def same_helper():
        require(receipt.listeners(port) == [helper["pid"]] and receipt.observe(helper["pid"]) == helper,
                "Menu helper identity changed")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Menu endpoint redirected")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(path, headers):
        same_helper()
        request = urllib.request.Request(f"http://127.0.0.1:{port}" + path, headers=headers)
        with opener.open(request, timeout=5) as response:
            result = json.load(response)
        same_helper()
        return result

    # Same local UI handshake as bundle_smoke. Never persist the token.
    token = get("/token", {"X-Uoink-Client": "uoink-extension", "Sec-Fetch-Site": "same-origin",
                           "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"})["token"]
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        menu = get("/helper/ui", {"X-Uoink-Token": token})
        require(menu.get("helper_pid") == helper["pid"], "Menu belongs to another helper")
        if menu.get("alive") and menu.get("connected"):
            identity = receipt.observe(menu["pid"])
            origin = receipt.interpreter_origin(app, identity["executable"])
            require(origin == bound["origin"], "Menu belongs to another app copy")
            icon = bundle_smoke.menu_icon_evidence(log_files, menu["pid"], Path(origin["bundle"]))
            require(receipt.observe(menu["pid"]) == identity, "Menu identity changed")
            return {**menu, "identity": identity, "origin": origin, "icon": icon}
        time.sleep(.25)
    raise RuntimeError("AppKit menu did not connect within 45s; see launch stderr")


def launch(app: Path, scratch: Path, output: Path, report: dict, *, translocated: bool = True) -> None:
    output.mkdir(parents=True, exist_ok=True)
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
    identities = []
    failed = False
    try:
        opened = subprocess.run(argv, cwd=scratch, env=env, capture_output=True, text=True, timeout=30)
        report["open"] = {"exit": opened.returncode, "stdout": opened.stdout, "stderr": opened.stderr}
        require(opened.returncode == 0, "LaunchServices refused the quarantined app")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            owners = receipt.listeners(port)
            if len(owners) == 1:
                # The listener is the supervisor's helper child; bind_health rechecks
                # both interpreters, the parent link and listener ownership.
                parent = receipt.describe(owners[0]).get("ppid")
                if parent is None:  # The listener exited between the two reads.
                    time.sleep(.25)
                    continue
                try:
                    proc = SimpleNamespace(pid=parent, poll=lambda: None)
                    report["health"] = receipt.bind_health(proc, app, port)
                    identities.extend([report["health"]["supervisor_identity"], report["health"]["identity"]])
                    require(report["health"]["origin"]["translocated"] is translocated,
                            f"Expected translocated={translocated} launch")
                    report["menubar"] = bind_menu(app, report["health"], bundle_smoke.helper_logs(output / "launch-stderr.txt", env))
                    identities.append(report["menubar"]["identity"])
                    return
                except OSError:
                    pass
            time.sleep(.25)
        raise RuntimeError("Quarantined launch did not serve /health within 120s; see launch stderr")
    except Exception as exc:
        failed = True
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            report["cleanup"] = receipt.stop_owned(app, identities, port)
            require(report["cleanup"]["ok"], "Launch left surviving processes")
        except Exception as exc:
            report["cleanup_error"] = f"{type(exc).__name__}: {exc}"
            if not failed:
                raise


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
                # A first open of a downloaded app shows macOS's one-time "downloaded from
                # the internet" confirmation, which nobody can click on a headless runner.
                # Mark the copy user-approved the way that click does (quarantine flag 0x40),
                # keeping the quarantine so Gatekeeper still evaluates signature and ticket.
                fields = report["app_quarantine"]["stdout"].strip().split(";")
                fields[0] = f"{int(fields[0], 16) | 0x40:04x}"
                report["user_approval"] = command(["xattr", "-w", "com.apple.quarantine", ";".join(fields), app])
                require(report["user_approval"]["exit"] == 0, "Cannot record the simulated first-open approval")
                launch(app, scratch, output, report["launch"])
                # Confirm execution did not break either final signature/ticket.
                report["after_launch"] = {}
                verify_notarized(app, download, team, report["after_launch"])
                # Exercise the same signed bytes in a second, unquarantined
                # Applications-style copy. The downloaded copy stays quarantined.
                normal_root = scratch / "normal"
                normal = normal_root / "Applications With Spaces/Uoink.app"
                normal.parent.mkdir(parents=True)
                dmg_smoke.run(["ditto", app, normal], timeout=300)
                normal_report = report["normal_install"] = {}
                dmg_smoke.prepare_normal_install(normal, normal_report)
                normal_report["notarization"] = {}
                verify_notarized(normal, download, team, normal_report["notarization"])
                normal_report["launch"] = {}
                launch(normal, normal_root, output / "normal", normal_report["launch"], translocated=False)
                normal_report["after_launch"] = {}
                verify_notarized(normal, download, team, normal_report["after_launch"])
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
