"""Run the unchanged required suites with offline subprocess guards."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCRATCH = ROOT / "_scratch" / "bd"
SUITES = {
    "phase6": ["tests/test_phase6_evaluation.py", "tests/test_phase6_bc2.py"],
    "regression": ["tests/" + name + ".py" for name in (
        "test_c01_mcp_stdio", "test_phase4_stdio", "test_stdio_clip_tools",
        "test_phase0_registry_capture", "test_docs_live_contracts", "test_library_adapters",
        "test_podcast_corpus_bridge", "test_clips", "test_library_resources")],
    "phase3": [str(p.relative_to(ROOT)) for p in sorted(
        (ROOT / "tests/library_work_astra").glob("test_phase3_*.py"))],
    "bd": ["tests/library_work_astra/test_phase6_bd_acceptance.py"],
}


def main():
    suite = sys.argv[1]
    guard = SCRATCH / "guard"
    guard.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "offline_guard.py", guard / "sitecustomize.py")
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "TEMP", "TMP",
                 "UOINK_DATA_ROOT", "UOINK_OUTPUT_ROOT", "UOINK_OUTPUT_DIR"):
        folder = SCRATCH / suite / name.lower()
        folder.mkdir(parents=True, exist_ok=True)
        env[name] = str(folder)
    package_paths = [p for p in sys.path if p and "site-packages" in p]
    env.update(BD_WORKTREE_ROOT=str(ROOT), PYTHONPATH=os.pathsep.join((str(guard), str(ROOT), *package_paths)),
               PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PHASE3_REQUIRE_IMPLEMENTATION="1")
    logdir = HERE / "logs"
    logdir.mkdir(exist_ok=True)
    command = [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *SUITES[suite], *sys.argv[2:]]
    started = time.time()
    with (logdir / (suite + ".txt")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt = {"suite": suite, "command": command, "exit_code": result.returncode,
               "elapsed_seconds": round(time.time() - started, 3),
               "started_unix_seconds": started,
               "isolation": "offline_guard.py via PYTHONPATH/sitecustomize; all environment data/temp roots within _scratch/bd; no credentials"}
    (logdir / (suite + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt), flush=True)
    print("\n".join((logdir / (suite + ".txt")).read_text(encoding="utf-8").splitlines()[-12:]))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
