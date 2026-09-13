"""Prepared stdlib-only ZIP transformation; no model package is imported."""
import sys
if tuple(sys.version_info[:3]) != (3, 13, 15) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Unexpected interpreter or non-isolated startup")

# Inspect startup before further imports or any artifact access.
EXPECTED_RUNTIME = "E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/b2-stdlib313-runtime01"
normalize = lambda value: value.replace("/", "\\").rstrip("\\").casefold()
expected_paths = {normalize(EXPECTED_RUNTIME), normalize(EXPECTED_RUNTIME + "/python313.zip")}
if normalize(sys.executable) != normalize(EXPECTED_RUNTIME + "/python.exe") or len(sys.path) != 2 or {normalize(value) for value in sys.path} != expected_paths:
    raise RuntimeError("Private executable and exactly two private stdlib paths required")

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import stat
import traceback
import types
import zipfile

out = Path(__file__).absolute().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("label", choices=("py313-01",))
parser.add_argument("--execute-reviewed-build", action="store_true", required=True)
args = parser.parse_args()
run = out.parent / ("b2-real-wheel-" + args.label)
if not run.is_dir() or not (run / "launch-plan.json").is_file() or (run / "build-result.json").exists():
    raise ValueError("Fresh outer launch directory required")

heavy = {"server", "whisper_runner", "whisper", "whisperx", "faster_whisper", "ctranslate2", "torch", "torchaudio",
         "pyannote", "tokenizers", "transformers", "huggingface_hub", "safetensors", "numpy", "scipy", "onnx", "onnxruntime"}
preloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
if preloaded:
    raise RuntimeError("Heavy modules loaded before guard")
violations = []
class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in heavy or root not in sys.stdlib_module_names and root not in sys.builtin_module_names:
            violations.append("import:" + fullname)
            raise ImportError("Only stdlib imports permitted")
finder = Finder()
sys.meta_path.insert(0, finder)
upstream = out.parent / "python313-graph-01/cache/http-v2/7/5/8/3/f/7583fef67084ddf87aa2564c995bb7778718a460ee10db0da2a67f4b.body"
stdlib_root = Path(EXPECTED_RUNTIME)
comparison = out.parent / "b2-real-wheel-py314-01/artifact/faster_whisper-1.2.1+uoink.localassets1-py3-none-any.whl"
def audit(event, values):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.spawn", "_winapi.CreateProcess", "ctypes.dlopen"}:
        violations.append(event)
        raise PermissionError("Network/process/ctypes operation forbidden")
    if event in {"open", "sqlite3.connect"} and isinstance(values[0], (str, bytes, os.PathLike)):
        path = Path(os.path.abspath(os.fsdecode(values[0])))
        normalized = str(path).replace("\\", "/").lower()
        mode = values[1] if event == "open" and len(values) > 1 else ""
        flags = values[2] if event == "open" and len(values) > 2 else 0
        writing = any(ch in (mode or "") for ch in "wax+") or bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        allowed = path.is_relative_to(run) if writing else (path in (upstream, comparison) or any(path.is_relative_to(root) for root in (out, run, stdlib_root)))
        if "c:/users/hello/appdata/local/uoink/index.db" in normalized or normalized.endswith((".onnx", ".pt", ".pth", ".bin", ".safetensors")) or not allowed:
            violations.append(event + ":forbidden-path")
            raise PermissionError("Open outside scoped bytes refused")
sys.addaudithook(audit)

def bounded(path, cap, expected):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_reparse_tag", 0) or before.st_size != expected or expected > cap:
        raise ValueError("Regular exact-sized bounded input required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if identity(before) != identity(opened):
            raise ValueError("Path changed before open")
        raw = stream.read(cap + 1)
        if identity(os.fstat(stream.fileno())) != identity(opened):
            raise ValueError("Opened file changed")
    if len(raw) != expected or identity(path.lstat()) != identity(before):
        raise ValueError("Input changed while reading")
    return raw

receipt = {"status": "FAILED", "label": args.label, "actual_wheel_read_attempted": False, "actual_wheel_read": False, "model_execution": False,
    "runtime_acceptance": False, "release_ready": False, "python": sys.version, "sys_path": sys.path,
    "flags": {"isolated": sys.flags.isolated, "no_site": sys.flags.no_site, "dont_write_bytecode": sys.flags.dont_write_bytecode},
    "started_utc": datetime.now(timezone.utc).isoformat()}
code = 1
try:
    source = out / "inputs/build_faster_whisper_localassets_wheel.py"
    builder_bytes = bounded(source, 16354, 16354)
    if hashlib.sha256(builder_bytes).hexdigest() != "ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f":
        raise ValueError("Reviewed builder identity mismatch")
    builder = types.ModuleType("reviewed_localassets_builder")
    builder.__file__ = str(source)
    exec(compile(builder_bytes, str(source), "exec"), builder.__dict__)
    builder.check_no_links(out)
    builder.check_no_links(run)
    recipe = builder.load_recipe()
    # Verify copied runtime bytes before any wheel access; do not run original runtime.
    plan_path = out / "runtime-copy-plan.json"
    plan_bytes = builder.read_regular_file(plan_path, 256 * 1024)
    if builder.digest(plan_bytes) != "8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b":
        raise ValueError("Runtime plan identity mismatch")
    runtime_plan = json.loads(plan_bytes)
    expected_runtime_names = {row["filename"] for row in runtime_plan["files"]} | {"python313._pth"}
    names = []
    for path in stdlib_root.iterdir():
        names.append(path.name)
        if len(names) > 34:
            raise ValueError("Extra runtime entries")
    if len(names) != 34 or set(names) != expected_runtime_names:
        raise ValueError("Runtime file set mismatch")
    for row in runtime_plan["files"]:
        data = builder.read_regular_file(stdlib_root / row["filename"], row["bytes"], row["bytes"])
        if builder.digest(data) != row["sha256"]:
            raise ValueError("Private runtime identity mismatch")
    if builder.read_regular_file(stdlib_root / "python313._pth", 16, 16) != b"python313.zip\n.\n":
        raise ValueError("Private no-site configuration mismatch")
    receipt.update(private_runtime_verified=True, private_runtime_file_count=34,
                   source_date_epoch=os.environ.get("SOURCE_DATE_EPOCH"))
    if os.environ.get("SOURCE_DATE_EPOCH") != "2000000000":
        raise ValueError("Different fixed ambient epoch required")
    # First permitted read of the real captured wheel. Nothing above reads it.
    receipt["actual_wheel_read_attempted"] = True
    raw = builder.read_regular_file(upstream, builder.EXPECTED_WHEEL_SIZE, builder.EXPECTED_WHEEL_SIZE)
    receipt["actual_wheel_read"] = True
    if builder.digest(raw) != builder.EXPECTED_WHEEL_SHA256:
        raise ValueError("Captured upstream identity mismatch")
    upstream_dir = run / "upstream"
    upstream_dir.mkdir(exist_ok=False)
    copy = upstream_dir / builder.EXPECTED_WHEEL_NAME
    with copy.open("xb") as stream:
        stream.write(raw)
    if builder.read_regular_file(copy, len(raw), len(raw)) != raw:
        raise ValueError("Upstream copy drift")
    built = builder.build(copy, run / "artifact")
    target = Path(built["output"]["path"])
    blob = builder.read_regular_file(target, builder.MAX_ARCHIVE_SIZE, built["output"]["size"])
    original = builder.validate_archive(raw)
    members = builder.validate_archive(blob, builder.OUTPUT_VERSION)
    manifest = json.loads(recipe["member-manifest.json"])
    builder.verify_manifest(members, manifest["members"])
    asset = "faster_whisper/assets/silero_vad_v6.onnx"
    if members[asset] != original[asset] or members[builder.dist_info(builder.OUTPUT_VERSION) + "/LICENSE"] != original[builder.dist_info(builder.UPSTREAM_VERSION) + "/LICENSE"]:
        raise ValueError("Opaque asset/license changed")
    record = builder.dist_info(builder.OUTPUT_VERSION) + "/RECORD"
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        infos = archive.infolist()
        if len(infos) != 16 or archive.namelist() != sorted(set(members) - {record}) + [record] or archive.comment:
            raise ValueError("Output member count/order/comment mismatch")
        if any(info.date_time != builder.ZIP_TIME or info.create_system != 3 or info.external_attr != 0o100644 << 16
               or info.compress_type != zipfile.ZIP_STORED or info.extra or info.comment for info in infos):
            raise ValueError("Output deterministic ZIP metadata mismatch")
    # Byte comparison only. No model-member interpretation or package import.
    reference = builder.read_regular_file(comparison, 1387859, 1387859)
    if builder.digest(reference) != "d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883":
        raise ValueError("First output identity mismatch")
    if blob != reference:
        raise ValueError("Python 3.13 output differs from first output")
    receipt.update(status="BUILT_AND_BYTE_VERIFIED", builder_sha256=builder.digest(builder_bytes),
        recipe_hashes=builder.RECIPE_HASHES, output=built["output"], member_count=len(members),
        manifest_and_record_verified=True, opaque_asset_and_license_unchanged=True,
        opaque_asset_sha256=builder.digest(members[asset]), reproducibility_python313="BYTE_IDENTICAL", comparison_wheel_sha256=builder.digest(reference), comparison_wheel_bytes=len(reference))
    code = 0
except Exception as exc:
    receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    traceback.print_exc()
finally:
    postloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
    valid = not preloaded and not postloaded and not violations and finder in sys.meta_path
    if not valid:
        code = 1
        receipt["status"] = "FAILED_GUARD"
    receipt.update(exit=code, guard={"preloaded_heavy": preloaded, "postloaded_heavy": postloaded,
        "violations": violations, "finder_installed_at_finish": finder in sys.meta_path, "valid": valid},
        finished_utc=datetime.now(timezone.utc).isoformat())
    with (run / "build-result.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"status": receipt["status"], "exit": code, "guard": receipt["guard"]}))
raise SystemExit(code)
