"""Unexecuted inert qualification: fake ports only, no asset or runtime I/O."""
import ast
import contextlib
import dataclasses
import encodings.utf_8_sig
import enum
import math
import threading
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

HERE = Path(__file__).parent
INPUTS = ("asr_loading_adapter.py", "trusted_asr_resolver.py", "snapshot_lifecycle.py", "connection_cases.py", "qualify_adapter.py")
EXPECTED_ADAPTER = "2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c"
EXPECTED_RESOLVER = "16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833"
EXPECTED_SOURCE = {'asr_loading_adapter.py': '2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c', 'connection_cases.py': '0ef40eab642099f83ce35d2e70a0d0521d57ad2f7e8d467e940cb2600365630a', 'snapshot_lifecycle.py': 'a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd', 'trusted_asr_resolver.py': '16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'}
EXPECTED_CASES = ('exact_lease_permit_and_usage_reach_owned_startup', 'retained_facade_refuses_after_context_close', 'lazy_segments_require_live_owned_lease', 'foreign_factory_refused_before_native_reservation', 'binding_or_start_failure_preserves_original_and_quarantine', 'unconfirmed_close_keeps_snapshot_quarantined')
CONTENT_OPEN = True
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "PYANNOTE_METRICS_ENABLED": "0"}
assert all(os.environ.get(name) == value for name, value in OFFLINE.items())
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
READS = {os.path.normcase(str(HERE / name)) for name in INPUTS}
ALLOWED_IMPORTS = set(sys.modules) | {"trusted_asr_resolver", "asr_loading_adapter", "snapshot_lifecycle", "connection_cases"}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2", "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy"}
assert not (HEAVY & {name.split(".")[0] for name in sys.modules})
DENIED = []


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = CONTENT_OPEN and isinstance(path, (str, bytes, os.PathLike))
        if allowed:
            path = os.path.normcase(os.path.abspath(os.fsdecode(path)))
            allowed = path in READS and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS and args[0].split(".")[0] not in HEAVY
    elif event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    if not allowed:
        DENIED.append(event)
        raise AssertionError("Inert adapter qualification boundary refused " + event)


sys.addaudithook(audit)
RAW = {name: (HERE / name).read_bytes() for name in INPUTS}
CONTENT_OPEN = False
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}
assert HASHES["asr_loading_adapter.py"] == EXPECTED_ADAPTER
assert HASHES["trusted_asr_resolver.py"] == EXPECTED_RESOLVER
assert all(HASHES[name] == digest for name, digest in EXPECTED_SOURCE.items())


def reviewed_module(name):
    module = types.ModuleType(name)
    module.__file__ = str(HERE / (name + ".py"))
    sys.modules[name] = module
    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)
    return module


def metadata_trap(*args, **kwargs):
    DENIED.append("metadata")
    raise AssertionError("No filesystem metadata operation is permitted in this harness")


# The five reviewed source strings are loaded and content reads are closed.
# Install metadata traps before candidate compilation and module execution.
METADATA_TRAPS = []
for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),
                     (os, ("stat", "lstat", "fstat", "scandir", "listdir")),
                     (os.path, ("realpath",))):
    for name in names:
        setattr(owner, name, metadata_trap)
        METADATA_TRAPS.append((owner, name, metadata_trap, ("Path" if owner is Path else "os" if owner is os else "os.path") + "." + name))
METADATA_TRAPS = tuple(METADATA_TRAPS)


real_resolver = reviewed_module("trusted_asr_resolver")
lifecycle = reviewed_module("snapshot_lifecycle")
adapter = reviewed_module("asr_loading_adapter")
connection_cases = reviewed_module("connection_cases")
assert real_resolver.REAL_APPROVAL is None
ORIGINAL_REAL_FUNCTIONS = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
ORIGINAL_RELEASE = adapter._release
GLOBAL_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
assert all(getattr(adapter, name) is None for name in GLOBAL_NAMES)
assert connection_cases.EXPECTED_CASES == EXPECTED_CASES
CASES = connection_cases.define_cases(adapter, lifecycle, real_resolver)
assert tuple(name for name, _ in CASES) == EXPECTED_CASES

assert len(CASES) == 6
assert len({name for name, _ in CASES}) == len(CASES)
results = []
started = time.monotonic()
for name, fn in CASES:
    try:
        fn()
        assert real_resolver.REAL_APPROVAL is None and adapter.resolver is real_resolver
        assert all(getattr(adapter, field) is None for field in GLOBAL_NAMES)
        assert adapter._release is ORIGINAL_RELEASE
        results.append({"name": name, "passed": True})
    except Exception as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)})
passed = sum(result["passed"] for result in results)
failed = len(results) - passed
heavy_loaded = sorted(HEAVY & {name.split(".")[0] for name in sys.modules})
real_approval_closed = real_resolver.REAL_APPROVAL is None
real_functions_unchanged = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == ORIGINAL_REAL_FUNCTIONS
adapter_globals_restored = adapter.resolver is real_resolver and all(getattr(adapter, field) is None for field in GLOBAL_NAMES)
metadata_trap_mismatches = [label for owner, name, installed, label in METADATA_TRAPS
                            if getattr(owner, name, None) is not installed]
metadata_traps_installed = len(METADATA_TRAPS) == 12 and not metadata_trap_mismatches
release_restored = adapter._release is ORIGINAL_RELEASE
content_reads_closed = CONTENT_OPEN is False
ordered_membership = tuple(row["name"] for row in results) == EXPECTED_CASES
guard_valid = content_reads_closed and release_restored and ordered_membership and not DENIED and not heavy_loaded and real_approval_closed and real_functions_unchanged and adapter_globals_restored and metadata_traps_installed
result = {"schema": "uoink.inert-asr-adapter-qualification.v1", "passed": passed, "failed": failed, "skipped": 0,
          "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results,
          "input_sha256": HASHES, "guard_denials": DENIED, "heavy_roots_loaded": heavy_loaded,
          "real_resolver_approval_unchanged_none": real_approval_closed,
          "real_resolver_functions_unchanged": real_functions_unchanged,
          "adapter_globals_restored": adapter_globals_restored, "guard_valid": guard_valid,
          "metadata_traps_installed": metadata_traps_installed, "metadata_trap_count": len(METADATA_TRAPS),
          "metadata_trap_mismatches": metadata_trap_mismatches,
          "content_reads_closed": content_reads_closed, "adapter_release_restored": release_restored,
          "ordered_membership_matches": ordered_membership, "offline_flags": OFFLINE,
          "scope": "Six connected cases with actual pure-Python lifecycle and dummy kernel; no assets or native worker",
          "startup_binding_asserted": True, "torch_backend_autoload_disabled_before_startup": True,
          "qualification_exit": 0 if not failed and guard_valid else 1}
print(json.dumps(result, indent=2))
sys.exit(result["qualification_exit"])
