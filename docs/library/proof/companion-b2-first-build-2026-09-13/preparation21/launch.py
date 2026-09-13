"""Prepared root-only real ZIP build launcher. Not run during preparation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

def bounded(path, size):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_reparse_tag", 0) or before.st_size != size:
        raise ValueError("Input is not a regular exact-sized file")
    with path.open("rb") as stream:
        raw = stream.read(size + 1)
    after = path.lstat()
    if len(raw) != size or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Input changed")
    return raw

def main():
    if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
        raise RuntimeError("Launcher requires reviewed Python 3.14.6 -I -S -B")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=("py314-01",))
    parser.add_argument("--execute-reviewed-build", action="store_true")
    args = parser.parse_args()
    if not args.execute_reviewed_build:
        print("Prepared only; no wheel read or process launched. Root review is required before the execution flag is used.")
        return 0
    out = Path(__file__).absolute().parent
    manifest_path = out / "SHA256.json"
    if manifest_path.stat().st_size > 256 * 1024:
        raise ValueError("Oversized preparation seal")
    manifest = json.loads(bounded(manifest_path, manifest_path.stat().st_size))
    hashes = {}
    for row in manifest["payloads"]:
        name = row["file"]
        if Path(name).is_absolute() or ".." in Path(name).parts or row["bytes"] > 1024 * 1024:
            raise ValueError("Invalid preparation seal row")
        raw = bounded(out / name, row["bytes"])
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("Preparation input hash mismatch: " + name)
        hashes[name] = row["sha256"]
    run = out.parent / ("b2-real-wheel-" + args.label)
    run.mkdir(exist_ok=False)
    env = os.environ.copy()
    removed = []
    for key in list(env):
        upper = key.upper()
        if (re.search("API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL", upper)
            or upper.startswith(("ANTHROPIC_", "OPENAI_", "GOOGLE_API_", "GEMINI_API_", "XAI_", "GROK_", "CLAUDE_CODE_USE_"))
            or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "PYTHONPATH", "PYTHONHOME"}):
            removed.append(key)
            env.pop(key)
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1",
               SOURCE_DATE_EPOCH="1", IG_FORBIDDEN_LIVE=r"C:\Users\hello\AppData\Local\Uoink\index.db")
    command = [r"C:\Python314\python.exe", "-I", "-S", "-B", str(out / "build-guarded.py"), args.label, "--execute-reviewed-build"]
    def write(name, value):
        (run / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    write("launch-plan.json", {"command": command, "cwd": str(out), "input_hashes": hashes,
        "scrubbed_variable_names": sorted(removed), "started_utc": datetime.now(timezone.utc).isoformat()})
    child_exit = None
    try:
        with (run / "console.log").open("x", encoding="utf-8", newline="\n") as log:
            child_exit = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    finally:
        unchanged = all(hashlib.sha256(bounded(out / row["file"], row["bytes"])).hexdigest() == row["sha256"] for row in manifest["payloads"])
        write("launch-result.json", {"actual_child_exit": child_exit, "launcher_return_code": child_exit if unchanged else 99,
            "inputs_unchanged": unchanged, "finished_utc": datetime.now(timezone.utc).isoformat()})
    return child_exit if unchanged else 99

if __name__ == "__main__":
    raise SystemExit(main())
