"""Focused Phase 4 diagnostic using the retained integrator guard.

Adds a read-only snapshot plugin. Does not reset globals, release gates,
kill writers, or edit tests. Copies sitecustomize from the sealed
ryan-corrected-01 runner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument("--root", required=True)
p.add_argument("--label", required=True)
p.add_argument("selectors", nargs="+")
args = p.parse_args()

root = Path(args.root).resolve()
here = Path(__file__).resolve().parent
sealed = root / "docs" / "library" / "proof" / "ryan-corrected-01-2026-09-09"
scratch = root / "_scratch" / args.label
scratch.mkdir(parents=True, exist_ok=False)
packages = Path(site.getusersitepackages())
original_local = os.environ["LOCALAPPDATA"]
guard = scratch / "guard"
guard.mkdir()
shutil.copy2(sealed / "ig_paths.py", guard / "ig_paths.py")
shutil.copy2(sealed / "sitecustomize.py", guard / "sitecustomize.py")
shutil.copy2(here / "p4_snap.py", guard / "p4_snap.py")

env = os.environ.copy()
env.pop("ANTHROPIC_API_KEY", None)
env.update(
    PYTHONDONTWRITEBYTECODE="1",
    PYTHONUTF8="1",
    PHASE3_REQUIRE_IMPLEMENTATION="1",
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    IG_FORBIDDEN_LIVE=str(Path(original_local) / "Uoink" / "index.db"),
    P4_SNAP_PATH=str(scratch / "p4-snap.jsonl"),
    PYTHONPATH=os.pathsep.join(
        map(
            str,
            [
                guard,
                root,
                packages,
                packages / "win32",
                packages / "win32/lib",
                packages / "pythonwin",
            ],
        )
    ),
)
for key in (
    "LOCALAPPDATA",
    "APPDATA",
    "XDG_DATA_HOME",
    "TEMP",
    "TMP",
    "UOINK_DATA_ROOT",
    "UOINK_OUTPUT_ROOT",
    "UOINK_OUTPUT_DIR",
    "YOINK_OUTPUT_DIR",
):
    env[key] = str(scratch)
env["UOINK_INDEX_PATH"] = str(scratch / "unused-index.db")

command = [
    sys.executable,
    "-B",
    "-m",
    "pytest",
    "-q",
    "-ra",
    "--tb=short",
    "-p",
    "no:cacheprovider",
    "-p",
    "ig_paths",
    "-p",
    "p4_snap",
    "--basetemp=" + str(root / "_scratch" / f"{args.label}-0"),
    "--junitxml=" + str(scratch / "tests.xml"),
] + args.selectors
log = scratch / "tests.log"
print("START tests", flush=True)
print("command", command, flush=True)
print("executable", sys.executable, flush=True)
with log.open("w", encoding="utf-8") as handle:
    result = subprocess.run(command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
output = log.read_text(encoding="utf-8")
print("tests exit", result.returncode, "\n" + "\n".join(output.splitlines()[-40:]), flush=True)
payload = {
    "name": "tests",
    "command": command,
    "exit": result.returncode,
    "log": str(log),
    "executable": sys.executable,
    "snap": env["P4_SNAP_PATH"],
}
(scratch / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
raise SystemExit(result.returncode)
