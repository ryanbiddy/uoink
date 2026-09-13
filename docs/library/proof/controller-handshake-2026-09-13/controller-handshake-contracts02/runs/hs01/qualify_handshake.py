"""Proposed in-memory qualification; all native calls use explicit fake seams."""
import sys

# Root's module-name diagnostic found winreg present before setup imports.
# Bind that exact built-in object; neither import nor invoke a registry API.
BASELINE_WINREG = sys.modules.get("winreg")
assert BASELINE_WINREG is not None
assert getattr(BASELINE_WINREG, "__name__", None) == "winreg"
assert getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
assert not hasattr(BASELINE_WINREG, "__file__")
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
REGISTRY_DENIALS = []


def deny_registry(*args, **kwargs):
    REGISTRY_DENIALS.append("registry_callable")
    raise AssertionError("Registry operations are prohibited")


REGISTRY_TRAPS = tuple((name, value, deny_registry) for name, value in sorted(REGISTRY_NAMESPACE.items())
                      if not name.startswith("_") and callable(value))
assert 1 <= len(REGISTRY_TRAPS) <= 64
for name, original, installed in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, installed)


def registry_audit(event, args):
    if event.startswith("winreg."):
        REGISTRY_DENIALS.append(event)
        raise AssertionError("Registry audit operation is prohibited")


REGISTRY_AUDIT = registry_audit
sys.addaudithook(REGISTRY_AUDIT)

import dataclasses
import contextlib
import hmac
import struct
import enum
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import types

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = ('snapshot_lifecycle.py', 'owned_generation_protocol.py', 'handshake_cases.py', 'qualify_handshake.py')
READS = {os.path.normcase(os.path.join(HERE, name)) for name in INPUTS}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"}
assert HEAVY.intersection(name.split(".")[0] for name in sys.modules) == {"winreg"}
ALLOWED_IMPORTS = set(sys.modules) | set(('snapshot_lifecycle', 'owned_generation_protocol'))
DENIALS = []
CONTENT_OPEN = True


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = CONTENT_OPEN and isinstance(path, str) and os.path.normcase(os.path.abspath(path)) in READS
        allowed = allowed and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS and args[0].split(".")[0] not in HEAVY
    elif event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    if not allowed:
        DENIALS.append(event)
        raise AssertionError("Synthetic lifecycle boundary refused " + event)


sys.addaudithook(audit)
RAW = {}
for name in INPUTS:
    with open(os.path.join(HERE, name), "rb") as stream:
        RAW[name] = stream.read(1048577)
        assert len(RAW[name]) <= 1048576
CONTENT_OPEN = False
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}


def deny_metadata(*args, **kwargs):
    DENIALS.append("metadata")
    raise AssertionError("No filesystem metadata is permitted")


TRAPS = []
for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),
                     (os, ("stat", "lstat", "fstat", "scandir", "listdir")),
                     (os.path, ("realpath",))):
    for name in names:
        setattr(owner, name, deny_metadata)
        TRAPS.append((owner, name, deny_metadata))
TRAPS = tuple(TRAPS)


class BoundedCapture:
    def __init__(self):
        self.parts = []
        self.count = 0
        self.overflow = False

    def write(self, value):
        if type(value) is not str or len(value) > 8192 - self.count:
            self.overflow = True
            raise AssertionError("Synthetic output capture exceeded 8192 characters")
        self.parts.append(value)
        self.count += len(value)
        return len(value)

    def flush(self):
        pass


OUTPUT = sys.stdout
CAPTURE_OUT, CAPTURE_ERR = BoundedCapture(), BoundedCapture()
sys.stdout, sys.stderr = CAPTURE_OUT, CAPTURE_ERR

for module_name in ('snapshot_lifecycle', 'owned_generation_protocol'):
    module = types.ModuleType(module_name)
    module.__file__ = os.path.join(HERE, module_name + '.py')
    sys.modules[module_name] = module
    exec(compile(RAW[module_name + '.py'], module.__file__, 'exec'), module.__dict__)
exec(compile(RAW['handshake_cases.py'], os.path.join(HERE, 'handshake_cases.py'), 'exec'), globals())

EXPECTED_CASES = ('handshake_real_lifecycle_reserved_ready_running_begin', 'handshake_begin_during_reserved_startup_refused', 'handshake_foreign_local_permit_refused_before_frame', 'handshake_unregistered_worker_refused_before_frame', 'handshake_wrong_lifecycle_phase_refused_before_frame', 'handshake_substituted_registry_record_refused', 'handshake_repeated_ready_refused_while_reserved', 'handshake_begin_after_owned_session_close_refused')
assert tuple(name for name, _ in CASES) == EXPECTED_CASES
assert len(CASES) == 8
assert len({name for name, _ in CASES}) == len(CASES)
results = []
started = time.perf_counter()
for name, fn in CASES:
    try:
        fn()
        results.append({"name": name, "passed": True})
    except BaseException as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)[:512]})
elapsed = time.perf_counter() - started
heavy = sorted((HEAVY - {"winreg"}).intersection(name.split(".")[0] for name in sys.modules))
registry_identity = (sys.modules.get("winreg") is BASELINE_WINREG
                     and getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
                     and not hasattr(BASELINE_WINREG, "__file__"))
registry_expected = dict(REGISTRY_NAMESPACE)
for name, original, installed in REGISTRY_TRAPS:
    registry_expected[name] = installed
registry_namespace_unchanged = (set(vars(BASELINE_WINREG)) == set(registry_expected)
                                and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items()))
registry_traps_installed = (bool(REGISTRY_TRAPS)
                            and registry_audit is REGISTRY_AUDIT
                            and all(getattr(BASELINE_WINREG, name, None) is installed for name, original, installed in REGISTRY_TRAPS))
traps_installed = len(TRAPS) == 12 and all(getattr(owner, name, None) is installed for owner, name, installed in TRAPS)
captures_installed = sys.stdout is CAPTURE_OUT and sys.stderr is CAPTURE_ERR
capture_valid = not CAPTURE_OUT.overflow and not CAPTURE_ERR.overflow and CAPTURE_OUT.count == CAPTURE_ERR.count == 0
valid = (not DENIALS and not heavy and traps_installed and CONTENT_OPEN is False and captures_installed and capture_valid
         and registry_identity and registry_namespace_unchanged and registry_traps_installed and not REGISTRY_DENIALS)
passed = sum(row["passed"] for row in results)
exit_code = 0 if passed == len(results) and valid else 1
payload = json.dumps({"schema": "uoink.controller-handshake-synthetic.v1", "cases": results, "passed": passed,
                  "failed": len(results) - passed, "input_sha256": HASHES, "guard_denials": DENIALS,
                  "heavy_roots_loaded": heavy, "metadata_traps_installed": traps_installed,
                  "metadata_trap_count": len(TRAPS), "content_reads_closed": CONTENT_OPEN is False,
                  "baseline_winreg_identity_unchanged": registry_identity,
                  "registry_namespace_unchanged": registry_namespace_unchanged,
                  "registry_traps_installed": registry_traps_installed,
                  "registry_trap_names": [name for name, original, installed in REGISTRY_TRAPS],
                  "registry_trap_count": len(REGISTRY_TRAPS), "registry_denials": REGISTRY_DENIALS,
                  "captures_installed": captures_installed, "capture_valid": capture_valid,
                  "stdout_capture": "".join(CAPTURE_OUT.parts), "stderr_capture": "".join(CAPTURE_ERR.parts),
                  "guard_valid": valid, "native_exit": exit_code, "count": len(results), "skipped": 0,
                  "elapsed_seconds": elapsed, "expected_cases": EXPECTED_CASES,
                  "scope": "Eight in-memory lifecycle-owned ControllerHandshake cases only; no kernel, model, factory or native-loader qualification"}, indent=2)
assert len(payload.encode("utf-8")) <= 131072
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(exit_code)
