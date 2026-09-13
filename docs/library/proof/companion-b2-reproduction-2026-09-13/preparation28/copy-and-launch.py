"""Prepared private-stdlib copy and separate exact wheel reproduction launcher."""
import sys
if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Requires reviewed Python 3.14.6 -I -S -B")
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import traceback

OUT = Path(__file__).absolute().parent
SCRATCH = OUT.parent
RUNTIME = SCRATCH / "b2-stdlib313-runtime01"
COPY_RUN = SCRATCH / "b2-stdlib313-copy01"
BUILD_RUN = SCRATCH / "b2-real-wheel-py313-01"
PLAN_HASH = "8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b"
PTH = b"python313.zip\n.\n"
CAP = 8 * 1024 * 1024
digest = lambda raw: hashlib.sha256(raw).hexdigest()

def no_links(path):
    for part in (*reversed(path.parents), path):
        try:
            data = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(data.st_mode) or getattr(data, "st_reparse_tag", 0) or getattr(data, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked or reparse path refused")

def bounded(path, size):
    if not isinstance(size, int) or not 0 <= size <= CAP:
        raise ValueError("Invalid read bound")
    no_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        raise ValueError("Regular exact-sized input required")
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
            raise ValueError("Input changed before open")
        raw = stream.read(size + 1)
        if len(raw) != size or identity(os.fstat(stream.fileno())) != identity(opened):
            raise ValueError("Input changed during bounded read")
    no_links(path)
    if identity(path.lstat()) != identity(before):
        raise ValueError("Input pathname changed")
    return raw

def write_json(directory, name, value):
    no_links(directory)
    with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")

def verify_preparation(expected):
    if not re.fullmatch("[a-f0-9]{64}", expected):
        raise ValueError("An externally reviewed preparation seal is required")
    seal = OUT / "SHA256.json"
    no_links(seal)
    size = seal.stat().st_size
    if size > 256 * 1024:
        raise ValueError("Preparation manifest exceeds cap")
    raw = bounded(seal, size)
    if digest(raw) != expected:
        raise ValueError("Externally pinned preparation seal mismatch")
    rows = json.loads(raw)["payloads"]
    names = set()
    for row in rows:
        name = row["file"]
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or name in names or row["bytes"] > 1024 * 1024:
            raise ValueError("Invalid/duplicate preparation member")
        names.add(name)
        if digest(bounded(OUT / path, row["bytes"])) != row["sha256"]:
            raise ValueError("Preparation input mismatch: " + name)
    return rows

def plan():
    source = OUT / "runtime-copy-plan.json"
    raw = bounded(source, source.stat().st_size)
    if digest(raw) != PLAN_HASH:
        raise ValueError("Prior exact runtime plan mismatch")
    data = json.loads(raw)
    if Path(data["source_directory"]) != SCRATCH / "python313-graph-01/python" or Path(data["proposed_private_directory"]) != RUNTIME:
        raise ValueError("Unexpected runtime roots")
    names = [row["filename"] for row in data["files"]]
    if len(names) != 33 or len(set(names)) != 33 or any(Path(name).name != name or ":" in name or name == "python313._pth" for name in names):
        raise ValueError("Unexpected runtime member set")
    if data["private_pth"]["text"].encode() != PTH or digest(PTH) != data["private_pth"]["sha256"]:
        raise ValueError("Private no-site configuration mismatch")
    return data

def verify_runtime(data):
    no_links(RUNTIME)
    expected = {row["filename"] for row in data["files"]} | {"python313._pth"}
    names = []
    for path in RUNTIME.iterdir():
        names.append(path.name)
        if len(names) > 34:
            raise ValueError("Unexpected runtime entry count")
    if set(names) != expected:
        raise ValueError("Unexpected runtime files or directories")
    for row in data["files"]:
        if digest(bounded(RUNTIME / row["filename"], row["bytes"])) != row["sha256"]:
            raise ValueError("Private runtime hash mismatch")
    if bounded(RUNTIME / "python313._pth", len(PTH)) != PTH:
        raise ValueError("Private no-site configuration mismatch")

def fresh(path):
    no_links(path)
    if not path.parent.is_dir():
        raise ValueError("Existing scratch parent required")
    path.mkdir(exist_ok=False)

def copy_runtime(data, seal):
    fresh(COPY_RUN)
    receipt = {"status": "FAILED", "copied": [], "private_runtime_launched": False, "manifest_sha256": seal,
        "started_utc": datetime.now(timezone.utc).isoformat()}
    code = 1
    try:
        fresh(RUNTIME)
        for row in data["files"]:
            source = Path(data["source_directory"]) / row["filename"]
            raw = bounded(source, row["bytes"])
            if digest(raw) != row["sha256"]:
                raise ValueError("Retained stdlib source hash mismatch")
            no_links(RUNTIME)
            with (RUNTIME / row["filename"]).open("xb") as stream:
                stream.write(raw)
            receipt["copied"].append(row)
        no_links(RUNTIME)
        with (RUNTIME / "python313._pth").open("xb") as stream:
            stream.write(PTH)
        verify_runtime(data)
        receipt.update(status="COPIED_AND_BYTE_VERIFIED", runtime=str(RUNTIME), exact_file_count=34, private_pth_sha256=digest(PTH))
        code = 0
    except Exception as exc:
        receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    receipt.update(exit=code, finished_utc=datetime.now(timezone.utc).isoformat())
    write_json(COPY_RUN, "copy-result.json", receipt)
    return code

def build(data, seal):
    verify_runtime(data)
    copy_receipt = COPY_RUN / "copy-result.json"
    copied = json.loads(bounded(copy_receipt, copy_receipt.stat().st_size))
    if copied.get("status") != "COPIED_AND_BYTE_VERIFIED" or copied.get("exit") != 0 or copied.get("manifest_sha256") != seal:
        raise ValueError("Matching successful runtime copy receipt required")
    fresh(BUILD_RUN)
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
        SOURCE_DATE_EPOCH="2000000000", IG_FORBIDDEN_LIVE=r"C:\Users\hello\AppData\Local\Uoink\index.db")
    command = [str(RUNTIME / "python.exe"), "-I", "-S", "-B", str(OUT / "build-guarded313.py"), "py313-01", "--execute-reviewed-build"]
    write_json(BUILD_RUN, "launch-plan.json", {"command": command, "cwd": str(OUT), "manifest_sha256": seal,
        "source_date_epoch": env["SOURCE_DATE_EPOCH"], "scrubbed_variable_names": sorted(removed),
        "runtime_plan_sha256": PLAN_HASH, "started_utc": datetime.now(timezone.utc).isoformat()})
    result = {"actual_child_exit": None, "launcher_return_code": 1, "inputs_unchanged": False, "runtime_unchanged": False}
    try:
        with (BUILD_RUN / "console.log").open("x", encoding="utf-8", newline="\n") as log:
            result["actual_child_exit"] = subprocess.run(command, cwd=OUT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        verify_preparation(seal)
        result["inputs_unchanged"] = True
        verify_runtime(data)
        result["runtime_unchanged"] = True
        result["launcher_return_code"] = result["actual_child_exit"]
    except Exception as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(BUILD_RUN, "launch-result.json", result)
    return result["launcher_return_code"]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("copy", "build"))
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--execute-reviewed-action", action="store_true")
    args = parser.parse_args()
    if not args.execute_reviewed_action:
        print("Prepared only. No runtime copy, launch or artifact access.")
        return 0
    verify_preparation(args.manifest_sha256)
    data = plan()
    return copy_runtime(data, args.manifest_sha256) if args.action == "copy" else build(data, args.manifest_sha256)

if __name__ == "__main__":
    raise SystemExit(main())
