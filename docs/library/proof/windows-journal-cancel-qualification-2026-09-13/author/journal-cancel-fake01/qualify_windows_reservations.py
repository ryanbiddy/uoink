"""Fixed generated reservation cases; reviewed source only, no native ports."""
import sys

BASELINE_WINREG = sys.modules.get("winreg")
assert BASELINE_WINREG is not None
assert getattr(BASELINE_WINREG, "__name__", None) == "winreg"
assert getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
assert not hasattr(BASELINE_WINREG, "__file__")
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
REGISTRY_DENIALS = []

def deny_registry(*args, **kwargs):
    REGISTRY_DENIALS.append("registry_callable")
    raise AssertionError("Registry operations prohibited")

REGISTRY_TRAPS = tuple((name, value, deny_registry) for name, value in sorted(REGISTRY_NAMESPACE.items())
                      if not name.startswith("_") and callable(value))
assert 1 <= len(REGISTRY_TRAPS) <= 64
for name, original, installed in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, installed)

def registry_audit(event, args):
    if event.startswith("winreg."):
        REGISTRY_DENIALS.append(event)
        raise AssertionError("Registry audit prohibited")

REGISTRY_AUDIT = registry_audit
sys.addaudithook(REGISTRY_AUDIT)

import contextlib
import hmac
import re
import stat
import dataclasses
import enum
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import threading
import time
import types
import unittest

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
STARTUP_BOUND = os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert STARTUP_BOUND
HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ("reservation_file_port", "snapshot_reservations", "snapshot_lifecycle", "durable_lifecycle", "win32_worker_connection", "windows_reservation_port", "trusted_asr_resolver", "asr_loading_adapter", "pinned_buffer_namespace", "owned_generation_protocol", "inherited_readset", "generated_worker_flow", "generated_operation_flow", "generated_journal_setup", "generated_writer_exclusion", "generated_adapter_flow", "win32_private_pipe", "test_reservations", "test_windows_reservations", "test_creation_transfer", "test_stable_directory", "test_journal_cancel")
INPUTS = tuple(name + ".py" for name in MODULES) + ("qualify_windows_reservations.py", "EXPECTED-CASES.json")
READS = {os.path.normcase(os.path.join(HERE, name)) for name in INPUTS}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"}
assert HEAVY.intersection(name.split(".")[0] for name in sys.modules) == {"winreg"}
ALLOWED_IMPORTS = set(sys.modules) | set(MODULES)
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
        raise AssertionError("Generated reservation boundary refused " + event)

AUDIT = audit
sys.addaudithook(AUDIT)
RAW = {}
for name in INPUTS:
    with open(os.path.join(HERE, name), "rb") as stream:
        RAW[name] = stream.read(1048577)
        assert len(RAW[name]) <= 1048576
CONTENT_OPEN = False
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}
EXPECTED = json.loads(RAW["EXPECTED-CASES.json"])
assert type(EXPECTED) is list and len(EXPECTED) == 89 and len(set(EXPECTED)) == 89

def deny_metadata(*args, **kwargs):
    DENIALS.append("metadata")
    raise AssertionError("Filesystem metadata prohibited")

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
        self.parts, self.count, self.overflow = [], 0, False
    def write(self, value):
        if type(value) is not str or len(value) > 8192 - self.count:
            self.overflow = True
            raise AssertionError("Capture exceeded 8192 characters")
        self.parts.append(value)
        self.count += len(value)
        return len(value)
    def flush(self):
        pass

OUTPUT = sys.stdout
CAPTURE_OUT, CAPTURE_ERR = BoundedCapture(), BoundedCapture()
sys.stdout, sys.stderr = CAPTURE_OUT, CAPTURE_ERR
LOADED = {}
for name in MODULES:
    module = types.ModuleType(name)
    module.__file__ = os.path.join(HERE, name + ".py")
    sys.modules[name] = module
    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)
    LOADED[name] = module
REAL_ENTRIES = ((LOADED["reservation_file_port"], "real_journal_port", LOADED["reservation_file_port"].real_journal_port),
                (LOADED["snapshot_reservations"], "real_reservation_service", LOADED["snapshot_reservations"].real_reservation_service),
                (LOADED["windows_reservation_port"], "real_windows_reservation_service", LOADED["windows_reservation_port"].real_windows_reservation_service),
                (LOADED["win32_worker_connection"], "real_kernel_port", LOADED["win32_worker_connection"].real_kernel_port))

class Results(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []
    def startTest(self, test):
        super().startTest(test)
        self.rows.append({"id": test.id(), "passed": False, "skipped": False, "errors": [], "subtests": []})
    def addSuccess(self, test):
        self.rows[-1]["passed"] = not self.rows[-1]["errors"]
    def failure(self, err):
        return {"type": type(err[1]).__name__, "message": str(err[1])[:512]}
    def addError(self, test, err):
        failure = self.failure(err)
        self.rows[-1]["errors"].append(failure)
        self.errors.append((test, failure["message"]))
    def addFailure(self, test, err):
        failure = self.failure(err)
        self.rows[-1]["errors"].append(failure)
        self.failures.append((test, failure["message"]))
    def addSkip(self, test, reason):
        self.rows[-1]["skipped"] = True
        self.skipped.append((test, str(reason)[:256]))
    def addSubTest(self, test, subtest, err):
        row = {"id": subtest.id()[:512], "passed": err is None}
        self.rows[-1]["subtests"].append(row)
        assert len(self.rows[-1]["subtests"]) <= 64
        if err is not None:
            self.addFailure(test, err)

suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(LOADED[name]) for name in ("test_reservations", "test_windows_reservations", "test_creation_transfer", "test_stable_directory", "test_journal_cancel"))
result = Results()
started = time.perf_counter()
suite.run(result)
elapsed = time.perf_counter() - started
cases = result.rows
heavy = sorted((HEAVY - {"winreg"}).intersection(name.split(".")[0] for name in sys.modules))
registry_expected = dict(REGISTRY_NAMESPACE)
for name, original, installed in REGISTRY_TRAPS:
    registry_expected[name] = installed
guards = {
    "startup_bound": STARTUP_BOUND,
    "content_reads_closed": CONTENT_OPEN is False,
    "audit_identity_unchanged": audit is AUDIT,
    "metadata_traps_installed": len(TRAPS) == 12 and all(getattr(owner, name, None) is fn for owner, name, fn in TRAPS),
    "baseline_winreg_identity_unchanged": sys.modules.get("winreg") is BASELINE_WINREG
        and getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in" and not hasattr(BASELINE_WINREG, "__file__"),
    "registry_namespace_unchanged": set(vars(BASELINE_WINREG)) == set(registry_expected)
        and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items()),
    "registry_traps_installed": registry_audit is REGISTRY_AUDIT
        and all(getattr(BASELINE_WINREG, name, None) is installed for name, original, installed in REGISTRY_TRAPS),
    "captures_installed": sys.stdout is CAPTURE_OUT and sys.stderr is CAPTURE_ERR,
    "capture_valid": not CAPTURE_OUT.overflow and not CAPTURE_ERR.overflow and CAPTURE_OUT.count == CAPTURE_ERR.count == 0,
    "real_entrypoints_unchanged": all(getattr(module, name) is function for module, name, function in REAL_ENTRIES)
        and LOADED["trusted_asr_resolver"].REAL_APPROVAL is None
        and all(getattr(LOADED["asr_loading_adapter"], name) is None for name in ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")),
}
membership = [row["id"] for row in cases] == EXPECTED and result.testsRun == len(EXPECTED)
passed = sum(row["passed"] for row in cases)
skipped = sum(row["skipped"] for row in cases)
valid = membership and all(guards.values()) and not DENIALS and not REGISTRY_DENIALS and not heavy
code = 0 if valid and passed == 89 and skipped == 0 else 1
payload = json.dumps({"schema": "uoink.windows-reservation-fake-preflight.v1", "cases": cases,
    "passed": passed, "failed": len(cases) - passed - skipped, "skipped": skipped,
    "count": len(cases), "expected_cases": EXPECTED, "membership_valid": membership,
    "guards": guards, "guard_valid": valid, "guard_denials": DENIALS, "registry_denials": REGISTRY_DENIALS,
    "heavy_roots_loaded": heavy, "metadata_trap_count": len(TRAPS), "registry_trap_count": len(REGISTRY_TRAPS),
    "input_sha256": HASHES, "elapsed_seconds": elapsed, "qualification_exit": code,
    "scope": "Generated bytes and fake Windows services; actual source paths exercised, native behavior unmeasured"}, indent=2)
assert len(payload.encode("utf-8")) <= 262144
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(code)
