"""Future exact-text byte build/verification only; not admitted by its presence."""
import sys

RUNTIME = r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\b2-stdlib313-runtime01"
normalized = lambda value: value.replace("/", "\\").rstrip("\\").casefold()
assert sys.version_info[:3] == (3, 13, 15)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and "site" not in sys.modules
assert normalized(sys.executable) == normalized(RUNTIME + r"\python.exe")
assert len(sys.path) == 2 and {normalized(p) for p in sys.path} == {
    normalized(RUNTIME), normalized(RUNTIME + r"\python313.zip")}
assert len(sys.argv) == 2 and sys.argv[1] in {"build", "verify"}
mode = sys.argv[1]

import os
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
assert os.environ.get("PYANNOTE_METRICS_ENABLED") == "0"
import base64
import binascii
import csv
import email.parser
import email.policy
import hashlib
import importlib.abc
import io
import json
from pathlib import Path
import stat
import struct
import time
import tomllib
import zipfile

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\whisperx-owned-builder-proposal01")
HERE = Path(__file__).absolute().parent
LAUNCH = HERE / "launch-build01"
RUN = BASE / "runs" / "build01"
manifest_bytes = (BASE / "INPUT-HASHES.json").read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == "5602d0e46f91739c40799e0ce2592560274cc70c252421f856d3cf77133bcd9f"
rows = json.loads(manifest_bytes)
assert len(rows) == 46
sources = {str(BASE / r["path"]): r for r in rows}
runtime_bytes = (HERE / "runtime-copy-plan.json").read_bytes()
assert hashlib.sha256(runtime_bytes).hexdigest() == "8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b"
runtime_plan = json.loads(runtime_bytes)
runtime_names = [r["filename"] for r in runtime_plan["files"]] + [runtime_plan["private_pth"]["filename"]]
read_names = {normalized(p) for p in sources} | {normalized(str(BASE / "INPUT-HASHES.json")),
    normalized(str(HERE / "runtime-copy-plan.json")), normalized(__file__)}
read_names |= {normalized(RUNTIME + "\\" + name) for name in runtime_names}
write_paths = {RUN, RUN / "inputs-before.json", RUN / "inputs-after.json", RUN / "result.json",
    RUN / "whisperx-3.8.6+uoink.owned1-py3-none-any.whl", RUN / "independent-verification.json",
    LAUNCH / (mode + "-guard.json")}
write_names = {normalized(str(p)) for p in write_paths}
all_names = read_names | write_names
ancestors = {normalized(str(parent)) for p in all_names for parent in Path(p).parents}
violations = []
heavy = {"whisperx", "whisper_runner", "server", "faster_whisper", "ctranslate2", "torch", "torchaudio",
    "numpy", "pyannote", "transformers", "tokenizers", "torchcodec", "scipy", "huggingface_hub"}
preloaded = sorted(n for n in sys.modules if n.split(".")[0] in heavy)
assert not preloaded
original_lstat = os.lstat
def reject(event):
    violations.append(event)
    raise PermissionError("Operation outside exact byte-build scope")
def pathname(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        reject("descriptor-path")
    return normalized(os.path.abspath(os.fsdecode(value)))
def chain(name):
    for path in reversed((Path(name),) + tuple(Path(name).parents)):
        item = normalized(str(path))
        if item not in all_names | ancestors:
            reject("ancestor")
        try:
            info = original_lstat(str(path))
        except FileNotFoundError:
            if item in write_names:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            reject("linked-path")
        if item != name and not stat.S_ISDIR(info.st_mode):
            reject("ancestor-kind")
originals = {n: getattr(os, n) for n in ("stat", "lstat", "readlink", "scandir", "listdir")}
originals["realpath"] = os.path.realpath
wrappers = {}
for key, original in originals.items():
    def wrapped(value, *args, _name=key, _call=original, **kwargs):
        name = pathname(value)
        if name not in all_names | ancestors or _name in {"scandir", "listdir"} or kwargs.get("dir_fd") is not None:
            reject("metadata:" + _name)
        chain(name)
        return _call(value, *args, **kwargs)
    wrappers[key] = wrapped
    if key == "realpath": os.path.realpath = wrapped
    else: setattr(os, key, wrapped)
class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in heavy or root not in sys.stdlib_module_names | set(sys.builtin_module_names):
            reject("import:" + fullname)
finder = Finder()
sys.meta_path.insert(0, finder)
def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "_winapi.CreateProcess", "ctypes.dlopen", "sqlite3.connect", "os.listdir", "os.scandir"}:
        reject(event)
    if event == "open":
        name = pathname(args[0])
        mode_arg, flags = args[1], args[2]
        writing = isinstance(mode_arg, str) and any(c in mode_arg for c in "wax+") or isinstance(flags, int) and bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if name not in (write_names if writing else all_names):
            reject("file-open")
        chain(name)
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink"}:
        name = pathname(args[0])
        if event != "os.mkdir" or name not in {normalized(str(RUN)), normalized(str(RUN.parent))}:
            reject("mutation:" + event)
        chain(name)
sys.addaudithook(audit)

started = time.monotonic()
exitcode, failure = 1, None
script = BASE / ("build_wheel.py" if mode == "build" else "verify_wheel.py")
try:
    row = sources[str(script)]
    raw = script.read_bytes()
    assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    namespace = {"__name__": "owned_byte_operation", "__file__": str(script)}
    exec(compile(raw, str(script), "exec"), namespace)
    sys.argv = [str(script), "build01"]
    exitcode = namespace["main"]()
    assert type(exitcode) is int
except BaseException as error:
    failure = {"type": type(error).__name__, "message": str(error)}
    exitcode = 1
elapsed = time.monotonic() - started
postloaded = sorted(n for n in sys.modules if n.split(".")[0] in heavy)
intact = all((os.path.realpath if n == "realpath" else getattr(os, n)) is fn for n, fn in wrappers.items())
valid = not preloaded and not postloaded and not violations and finder in sys.meta_path and intact and elapsed <= 30
if not valid: exitcode = 96
receipt = {"mode": mode, "exit": exitcode, "error": failure, "guard_valid": valid,
    "preloaded_heavy": preloaded, "postloaded_heavy": postloaded, "violations": violations,
    "metadata_wrappers_installed": intact, "finder_installed": finder in sys.meta_path,
    "startup_binding": True, "sys_path": sys.path, "python": sys.version,
    "elapsed_seconds": elapsed, "deadline": "cooperative 30 seconds; not a hard timeout",
    "scope": "Reviewed stdlib byte construction/verification; no wheel member import, model runtime or installation."}
with (LAUNCH / (mode + "-guard.json")).open("xb") as stream:
    stream.write((json.dumps(receipt, indent=2) + "\n").encode())
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(receipt))
raise SystemExit(exitcode)
