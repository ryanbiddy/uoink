"""Prepare text inputs and hash retained stdlib files; never read a real wheel."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat

out = Path(__file__).absolute().parent
scratch = out.parent
original = scratch / "companion-b2-builder01"
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def read_bounded(path, cap):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_reparse_tag", 0) or before.st_size > cap:
        raise ValueError("Regular bounded input required")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    after = path.lstat()
    if len(raw) > cap or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Input changed")
    return raw

manifest_raw = read_bounded(original / "SHA256.json", 1024 * 1024)
assert sha(manifest_raw) == "ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f"
rows = {row["file"]: row for row in json.loads(manifest_raw)["payloads"]}
bindings = []
for name in ["build_faster_whisper_localassets_wheel.py", "recipe/B2.py.txt", "recipe/NOTICE.txt", "recipe/member-manifest.json", "recipe/patch.txt"]:
    source = original / name
    raw = read_bounded(source, rows[name]["bytes"])
    assert len(raw) == rows[name]["bytes"] and sha(raw) == rows[name]["sha256"]
    target = out / "inputs" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    bindings.append({"source": str(source), "target": str(target.relative_to(out)), "bytes": len(raw), "sha256": sha(raw)})

history = {
    "builder63-SHA256.json": original / "SHA256.json",
    "builder-combined100-SHA256.json": scratch / "companion-b2-builder-combined01/SHA256.json",
    "nltk-results.json": scratch / "nltk-wheel-stored-build01/results.json",
    "graph313-version.stdout": scratch / "python313-graph-01/version.stdout",
    "graph313-original-pth.txt": scratch / "python313-graph-01/python/python313._pth",
}
for name, source in history.items():
    raw = read_bounded(source, 1024 * 1024)
    target = out / "historical" / name
    target.parent.mkdir(exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    bindings.append({"source": str(source), "target": str(target.relative_to(out)), "bytes": len(raw), "sha256": sha(raw)})

# Explicit top-level embedded-runtime files only. No Lib/site-packages, wheels,
# model files or original _pth are copied or opened by this inventory.
names = """_asyncio.pyd _bz2.pyd _ctypes.pyd _decimal.pyd _elementtree.pyd _hashlib.pyd
_lzma.pyd _multiprocessing.pyd _overlapped.pyd _queue.pyd _socket.pyd _sqlite3.pyd _ssl.pyd
_uuid.pyd _wmi.pyd _zoneinfo.pyd libcrypto-3.dll libffi-8.dll libssl-3.dll LICENSE.txt
pyexpat.pyd python.cat python.exe python3.dll python313.dll python313.zip pythonw.exe
select.pyd sqlite3.dll unicodedata.pyd vcruntime140_1.dll vcruntime140.dll winsound.pyd""".split()
runtime = scratch / "python313-graph-01/python"
runtime_rows = []
for name in names:
    raw = read_bounded(runtime / name, 8 * 1024 * 1024)
    runtime_rows.append({"filename": name, "bytes": len(raw), "sha256": sha(raw)})
pth = b"python313.zip\n.\n"
with (out / "python313-private-pth.txt").open("xb") as stream:
    stream.write(pth)
plan = {"status": "PREPARED_ONLY_NOT_COPIED_OR_EXECUTED", "source_directory": str(runtime),
    "proposed_private_directory": str(scratch / "b2-stdlib313-runtime01"),
    "files": runtime_rows, "file_count": len(runtime_rows),
    "private_pth": {"filename": "python313._pth", "bytes": len(pth), "sha256": sha(pth), "text": pth.decode()},
    "excluded": ["original python313._pth", "Lib", "site-packages", "Scripts", "all unlisted files"],
    "preflight_before_any_wheel_access": ["exclusive fresh destination; refuse links/reparse paths", "bounded stable reads and exact hash/size of all listed files", "copy only listed bytes plus exact private _pth", "verify complete destination names and hashes", "launch only after root review with -I -S -B", "require 3.13.15, isolated=1, no_site=1, dont_write_bytecode=1 and site absent", "require sys.path contains only the private directory and private python313.zip", "install stdlib-only import/network/process/ctypes guard before artifact access"],
    "limits": "Local identities are bound, not fresh publisher provenance; quiescent paths required. No safe original embedded-startup receipt was found. No copy or execution has occurred.",
    "created_utc": datetime.now(timezone.utc).isoformat()}
(out / "python313-runtime-copy-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
(out / "input-bindings.json").write_text(json.dumps({"bindings": bindings, "actual_wheel_accessed": False, "runtime_copied_or_executed": False}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"text_copies": len(bindings), "runtime_files_hashed_only": len(runtime_rows), "actual_wheel_accessed": False}))
