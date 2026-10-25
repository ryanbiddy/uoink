"""Collect an installed Mac receipt from a DMG, never from source execution."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

# The collector may use system Python. Only the tested processes earn credit.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
import bundle_smoke
import dmg_smoke
from build_bundle import PYTHON_EXECUTABLE, sha256
from _platform import darwin_observe, darwin_liveness


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def command(argv, **kwargs) -> dict:
    result = subprocess.run([str(arg) for arg in argv], capture_output=True,
                            text=True, timeout=120, **kwargs)
    return {"argv": [str(arg) for arg in argv], "exit": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def metadata(path: Path) -> dict:
    """lstat only. Do not open files or follow a link in a protected listing."""
    try:
        info = path.lstat()
        return {"exists": True, "mtime_ns": info.st_mtime_ns}
    except FileNotFoundError:
        return {"exists": False, "mtime_ns": None}


def listing(root: Path) -> dict:
    rows = {".": metadata(root)}

    def visit(directory):
        for child in sorted(directory.iterdir()):
            rows[child.relative_to(root).as_posix()] = metadata(child)
            if stat.S_ISDIR(child.lstat().st_mode):
                visit(child)

    if rows["."]["exists"] and stat.S_ISDIR(root.lstat().st_mode):
        visit(root)
    return rows


def listeners(port: int) -> list[int]:
    # Passive kernel query. In particular, never connect or bind to 5179.
    result = command(["/usr/sbin/lsof", "-nP", "-a", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"])
    require(result["exit"] in (0, 1) and not result["stderr"].strip(), "Cannot observe TCP listeners")
    pids = sorted({int(line[1:]) for line in result["stdout"].splitlines() if line.startswith("p")})
    require(result["exit"] == 0 or not pids, "Ambiguous TCP listener observation")
    return pids


def real_home() -> Path:
    import pwd
    # CI overrides HOME. The account database still identifies the real user.
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)


def protected_snapshot(home: Path) -> dict:
    agents = home / "Library/LaunchAgents"
    data = home / "Library/Application Support/Uoink"
    # Do not traverse a redirected Library or LaunchAgents directory.
    require(not any(p.is_symlink() for p in (home / "Library", data.parent, data, agents)),
            "Cannot observe a linked user Library, Uoink data or LaunchAgents directory")
    return {"home": str(home),
            "data": listing(data),
            "launchagents": {p.name: metadata(p) for p in sorted(agents.glob("com.ryanbiddy.uoink*.plist"))},
            "port_5179": {"exists": bool(listeners(5179)), "mtime_ns": None},
            "port_note": "Sockets have no filesystem mtime; observed passively with lsof"}


def bundle_python(app: Path) -> Path:
    require(app.suffix == ".app" and not app.is_symlink(), "Source checkout is not an installed app bundle")
    root = app.resolve(strict=True)
    for relative in ("Contents/Info.plist", "Contents/MacOS/Uoink", "Contents/Resources/server.py",
                     "Contents/Resources/uoink_mcp.py", str(PYTHON_EXECUTABLE)):
        path = app / relative
        require(path.is_file(), f"Incomplete app bundle: {relative}")
        require(path.resolve(strict=True).is_relative_to(root), f"Bundle path resolves outside the app: {relative}")
    python = (app / PYTHON_EXECUTABLE).resolve(strict=True)
    require(python.is_relative_to(root / "Contents/Resources/Python"),
            "python3 resolves outside the bundled Python runtime")
    return python


def observe(pid: int) -> dict:
    observation = darwin_observe(pid, with_executable=True)
    require(observation.status == "alive" and observation.started_us and observation.executable,
            f"Process identity unknown for PID {pid}")
    return {"pid": pid, "created_ms": observation.created_ms,
            "started_us": observation.started_us, "executable": observation.executable}


def bind_health(proc, app: Path, port: int) -> dict:
    require(type(port) is int and 0 < port < 65536 and port != 5179, "Health must use a disposable port")
    python = bundle_python(app)
    supervisor = observe(proc.pid)
    require(Path(supervisor["executable"]).resolve() == python,
            "Supervisor uses a non-bundle interpreter")
    owners = listeners(port)
    require(len(owners) == 1 and owners[0] != proc.pid, "Health listener is not a supervised helper")
    helper_pid = owners[0]
    before = observe(helper_pid)
    require(Path(before["executable"]).resolve() == python,
            "Health process uses a non-bundle interpreter")
    require(describe(helper_pid).get("ppid") == proc.pid, "Health listener is not the launched supervisor's child")
    # Disable ambient proxies, and refuse redirects to any other endpoint.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Health endpoint redirected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(f"http://127.0.0.1:{port}/health", timeout=5) as response:
        health = json.load(response)
    require(health.get("ok") is True, "Installed helper health failed")
    require(health.get("pid") == helper_pid and bool(health.get("supervisor_run_id")),
            "Health does not identify the supervised helper")
    require(listeners(port) == [helper_pid] and observe(helper_pid) == before
            and observe(proc.pid) == supervisor and proc.poll() is None
            and describe(helper_pid).get("ppid") == proc.pid,
            "Health process identity changed during the request")
    return {"identity": before, "supervisor_identity": supervisor,
            "listener_pid": helper_pid, "port": port, "health": health}


def scoped_processes(app: Path) -> list[dict]:
    """Find survivors by executable location, without reading process arguments."""
    result = command(["/bin/ps", "-axo", "pid="])
    require(result["exit"] == 0, "Cannot enumerate processes for cleanup")
    found = []
    for text in result["stdout"].split():
        pid = int(text)
        observation = darwin_observe(pid, with_executable=True)
        if observation.executable and Path(observation.executable).is_relative_to(app):
            require(observation.status == "alive" and observation.started_us, "Owned process identity unknown")
            found.append({"pid": pid, "created_ms": observation.created_ms,
                          "started_us": observation.started_us, "executable": observation.executable})
    return found


def describe(pid: int) -> dict:
    # Only processes running from the disposable copy reach here, so their
    # arguments name disposable paths, never the real user's data.
    result = command(["/bin/ps", "-o", "ppid=,pgid=,etime=,command=", "-p", str(pid)])
    fields = result["stdout"].strip().split(None, 3)
    if result["exit"] != 0 or len(fields) < 4:
        return {"gone": True}
    return {"ppid": int(fields[0]), "pgid": int(fields[1]), "etime": fields[2], "command": fields[3]}


def no_survivors(app: Path, identities: list[dict], port: int, settle: float = 5.0) -> dict:
    rows = [{**item, "state": darwin_liveness(item["pid"], item["created_ms"])} for item in identities]
    # Birth identity is sufficient after uninstall, when samefile cannot work.
    first = [{**row, **describe(row["pid"])} for row in scoped_processes(app)]
    survivors, waited = first, 0.0
    # Lifeline children exit on their parent's death asynchronously; allow a
    # short bounded settle, and record what was alive at the first look.
    while survivors and waited < settle:
        time.sleep(.25)
        waited += .25
        survivors = scoped_processes(app)
    owners = listeners(port)
    return {"identities": rows, "first_look": first, "settled_after_s": waited,
            "survivors": [{**row, **describe(row["pid"])} for row in survivors], "listeners": owners,
            "ok": all(row["state"] == "dead" for row in rows) and not survivors and not owners}


def attest_interpreter(app: Path, mounted: Path, scratch: Path, env: dict) -> dict:
    python = bundle_python(app)
    mounted_python = bundle_python(mounted)
    require(sha256(python) == sha256(mounted_python), "Copied interpreter differs from the DMG")
    result = command([python, "-I", "-B", "-c",
                      "import json,sys; print(json.dumps({'executable':sys.executable,'version':sys.version}))"],
                     cwd=scratch, env=env)
    require(result["exit"] == 0, "Bundled interpreter version probe failed")
    version = json.loads(result["stdout"])
    require(Path(version["executable"]).resolve() == python, "Version probe uses a non-bundle interpreter")
    require(bool(version["version"]), "Bundled interpreter has no sys.version")
    return {"path": str(app / PYTHON_EXECUTABLE), "real_path": str(python),
            "sha256": sha256(python), "mounted_sha256": sha256(mounted_python),
            "sys_version": version["version"], "health_bindings": []}


def artifact_metadata(mounted: Path) -> dict:
    bundle_python(mounted)
    with (mounted / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    require(info.get("CFBundleIdentifier") == "com.ryanbiddy.uoink", "DMG app is not Uoink")
    require(all(info.get(k) for k in ("CFBundleShortVersionString", "CFBundleVersion")), "App version missing")
    signing = command(["/usr/bin/codesign", "-dv", "--verbose=4", mounted])
    require(signing["exit"] == 0, "Cannot collect codesign summary")
    assessment = command(["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4", mounted])
    return {key: info[key] for key in ("CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion")} | {
        "codesign": signing, "spctl": {**assessment, "policy": "recorded as data; ad-hoc assessment does not gate this receipt"}}


def verify_runtime(checks: dict):
    require(checks.get("ok") is True and checks.get("bundle_unchanged") is True, "Bundle smoke did not pass")
    require({(r["toolset"], r["count"], r["ok"]) for r in checks.get("mcp", [])}
            == {("full", 91, True), ("core", 35, True)}, "MCP 91/35 proof missing")
    for name in ("health", "media", "mirror", "connect", "launchagent", "cocoa", "status", "pillow"):
        require(bool(checks.get(name)), f"Runtime proof missing: {name}")
    menu = checks.get("menubar", {})
    for name in ("connected", "duplicate_launch_same_pid", "quit_no_survivor", "relaunch_connected", "helper_death_no_survivor"):
        require(menu.get(name) is True, f"Menu lifecycle proof missing: {name}")


def collect(dmg: Path, output: Path, expected_sha256: str | None = None) -> dict:
    report = {"schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
              "artifact": {}, "interpreter": {}, "install": {}, "runtime": {},
              "isolation": {}, "cleanup": {}, "verdict": "fail", "reasons": []}
    scratch = app = env = home = None
    identities = []

    def failed(exc):
        report["reasons"].append(f"{type(exc).__name__}: {exc}")

    try:
        require(not sys.flags.optimize, "Receipt requires assertions enabled; do not use -O")
        require(dmg.suffix.lower() == ".dmg" and dmg.is_file() and not dmg.is_symlink(),
                "Expected a DMG file; a source checkout or direct app cannot earn installed credit")
        digest = sha256(dmg)
        report["artifact"] = {"path": str(dmg), "sha256": digest, "size": dmg.stat().st_size,
                              "expected_sha256": expected_sha256}
        # The receipt binds to a built artifact, so the build's recorded hash is mandatory.
        require(expected_sha256 is not None, "No --expected-sha256: pass the hash the build recorded")
        require(bool(re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256)), "Invalid expected SHA-256")
        require(digest == expected_sha256.lower(), "DMG SHA-256 differs from --expected-sha256")
        require(sys.platform == "darwin", "Installed receipt requires macOS")
        home = real_home()
        report["isolation"]["before"] = protected_snapshot(home)
        # Do not let an inherited TMPDIR place the test inside live user data.
        scratch = Path(tempfile.mkdtemp(prefix="uoink receipt ", dir="/private/tmp")).resolve()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        require(port != 5179, "Disposable port must not be 5179")
        env = bundle_smoke.environment(scratch, port)
        report["isolation"].update(root=str(scratch), home=env["HOME"], data=env["UOINK_ISOLATED_PROFILE"],
                                   output=env["UOINK_OUTPUT_DIR"], port=port, receipt_output=str(output))
        for key in ("HOME", "UOINK_ISOLATED_PROFILE", "UOINK_OUTPUT_DIR", "TMPDIR"):
            require(Path(env[key]).resolve().is_relative_to(scratch), f"Non-disposable {key}")
        with dmg_smoke.installed_dmg(dmg, scratch, report["install"]) as (mounted, app):
            app = app.resolve(strict=True)
            require(app.is_relative_to(scratch) and " " in str(app), "Install is not disposable with spaces")
            report["artifact"].update(artifact_metadata(mounted))
            copied_signing = command(["/usr/bin/codesign", "-dv", "--verbose=4", app])
            report["install"]["codesign"] = copied_signing
            mounted_hash = re.search(r"(?m)^CDHash=([0-9a-f]+)$", report["artifact"]["codesign"]["stderr"])
            copied_hash = re.search(r"(?m)^CDHash=([0-9a-f]+)$", copied_signing["stderr"])
            require(copied_signing["exit"] == 0 and mounted_hash and copied_hash
                    and mounted_hash.group(1) == copied_hash.group(1), "Copied app signature differs from the DMG")
            report["install"]["cdhash_matches_dmg"] = True
            report["interpreter"] = attest_interpreter(app, mounted, scratch, env)

            def observer(event, proc, menu):
                if event in ("connected", "relaunch"):
                    bound = bind_health(proc, app, port)
                    require(sha256(Path(bound["identity"]["executable"])) == report["interpreter"]["sha256"],
                            "Health interpreter hash changed")
                    menu_identity = observe(menu["pid"])
                    require(Path(menu_identity["executable"]).resolve() == bundle_python(app),
                            "Menu uses a non-bundle interpreter")
                    identities.extend([bound["supervisor_identity"], bound["identity"], menu_identity])
                    report["interpreter"]["health_bindings"].append({"event": event, **bound, "menu_identity": menu_identity})
                else:
                    proof = no_survivors(app, identities, port)
                    report["cleanup"][event] = proof
                    require(proof["ok"], f"Processes survived {event}, or identity is unknown")

            try:
                report["runtime"] = bundle_smoke.smoke(app, scratch / "smoke", scratch=scratch, env=env, observer=observer)
            finally:
                partial = scratch / "smoke/smoke.json"
                if partial.is_file():
                    report["runtime"] = json.loads(partial.read_text(encoding="utf-8"))
            verify_runtime(report["runtime"])
            require(len(report["interpreter"]["health_bindings"]) == 2, "Both helper incarnations must be bound")
            verify = command(["/usr/bin/codesign", "--verify", "--strict", "--deep", app])
            report["install"]["signature_after_runtime"] = verify
            require(verify["exit"] == 0, "Installed signature changed during runtime")
    except Exception as exc:
        failed(exc)
    finally:
        # Cleanup failures cannot hide an earlier failure or prevent isolation's after snapshot.
        if app is not None and env is not None:
            try:
                before = no_survivors(app, identities, port)
                report["cleanup"]["before_uninstall"] = before
                require(before["ok"], "Uninstall refused: run processes survived or identity is unknown")
                profile = Path(env["UOINK_ISOLATED_PROFILE"])
                data_before = listing(profile)
                data_present = (profile / "index.db").is_file()
                # An escaping interpreter must not be executed even for cleanup.
                bundle_python(app)
                removal = command(["/bin/bash", ROOT / "scripts/mac/uninstall.sh", app, "--remove"],
                                  cwd=scratch, env=env)
                report["cleanup"]["uninstall"] = removal
                report["cleanup"].update(app_gone=not app.exists(), data_before=data_before,
                                         data_after=listing(profile), data_policy="preserve", retained_profile=str(profile))
                report["cleanup"]["after_uninstall"] = no_survivors(app, identities, port)
                require(removal["exit"] == 0 and not app.exists(), "Disposable app uninstall failed")
                require(data_present, "Disposable profile has no runtime database to preserve")
                require(data_before == report["cleanup"]["data_after"], "Uninstall changed disposable user data")
                require(report["cleanup"]["after_uninstall"]["ok"], "Processes survived uninstall or identity is unknown")
            except Exception as exc:
                failed(exc)
        if home is not None and "before" in report["isolation"]:
            try:
                report["isolation"]["after"] = protected_snapshot(home)
                report["isolation"]["unchanged"] = report["isolation"]["before"] == report["isolation"]["after"]
                require(report["isolation"]["unchanged"], "Real user data, LaunchAgents or port 5179 changed")
            except Exception as exc:
                failed(exc)
        try:
            if report["artifact"]:
                report["artifact"]["sha256_after"] = sha256(dmg)
                require(report["artifact"]["sha256_after"] == report["artifact"]["sha256"], "DMG changed during receipt")
            require(report["install"].get("detached") is True, "DMG detach not proved")
            require(report["cleanup"].get("app_gone") is True, "App removal not proved")
            require(report["isolation"].get("unchanged") is True, "Isolation not proved")
            require(report["runtime"].get("ok") is True, "Runtime checks not complete")
        except Exception as exc:
            failed(exc)
        if not report["reasons"]:
            report["verdict"] = "installed-pass"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if sys.platform == "darwin":
        home = real_home()
        protected = (home / "Library/Application Support/Uoink", home / "Library/LaunchAgents")
        if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
            print("fail: receipt output overlaps protected user data or LaunchAgents", file=sys.stderr)
            return 1
    # No existing receipt is overwritten, and no partial run leaves a stale pass.
    output.mkdir(parents=True, exist_ok=True)
    with (output / "receipt.json").open("x", encoding="utf-8") as stream:
        report = collect(args.dmg.expanduser().absolute(), output, args.expected_sha256)
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"{report['verdict']}: {output / 'receipt.json'}")
    return 0 if report["verdict"] == "installed-pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
