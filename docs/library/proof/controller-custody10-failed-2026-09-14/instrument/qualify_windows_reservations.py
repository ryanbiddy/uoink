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
MODULES = ("trusted_asr_resolver", "snapshot_lifecycle", "snapshot_reservations", "reservation_file_port", "durable_lifecycle", "asr_loading_adapter", "test_reservations", "controller_boundary_fixture", "test_controller_resume_publication")
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
assert type(EXPECTED) is list and len(EXPECTED) == 10 and len(set(EXPECTED)) == 10

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
AUTHORITY_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")

def startup_pair_valid():
    resolver = LOADED["trusted_asr_resolver"]
    adapter = LOADED["asr_loading_adapter"]
    durable = LOADED["durable_lifecycle"]
    lifecycle = LOADED["snapshot_lifecycle"]
    reservations = LOADED["snapshot_reservations"]
    return (all(sys.modules.get(name) is module for name, module in LOADED.items())
        and adapter.resolver is resolver and adapter._STARTUP_RESOLVER is resolver
        and resolver.REAL_APPROVAL is None
        and all(getattr(adapter, name) is None for name in AUTHORITY_NAMES)
        and adapter._STARTUP_LOAD is resolver.load_manifest
        and adapter._STARTUP_ADMIT is resolver.admit_snapshot
        and adapter._STARTUP_BIND is resolver.bind_for_constructor
        and adapter._STARTUP_RELEASE is adapter._release
        and adapter._STARTUP_PROFILE is adapter._runtime_profile
        and durable._FIXED_FACTORY_START_CHECK is durable._require_factory_start
        and adapter.DurableOwnedRuntimeFactory is durable.DurableOwnedRuntimeFactory
        and adapter.DurableSnapshotLifecycle is durable.DurableSnapshotLifecycle
        and adapter._DurableKernel is durable._DurableKernel
        and adapter._DurableLease is durable._DurableLease
        and adapter.OwnedSession is lifecycle.OwnedSession
        and adapter._NativePermit is lifecycle._NativePermit
        and adapter.Phase is lifecycle.Phase
        and adapter.Reservation is reservations.Reservation)

STARTUP_VALIDATOR = startup_pair_valid
STARTUP_ENTRY_VALID = False
STARTUP_FUNCTIONS = ()
STARTUP_TYPES = ()
STARTUP_METHODS = ()
STARTUP_KERNEL_TYPE = None
BOUNDARY_FUNCTIONS = None
FACTORY_CHECK = None
REAL_ENTRIES = ()
BOUNDARY_NAMES = ("_capture_controller_boundary", "_check_controller_entry", "_check_controller_boundary", "_require_fixed_controller_functions", "_classify_controller_custody", "_require_controller_binding", "_validate_controller_pre_resume", "_validate_controller_pre_resume_locked", "_validate_controller_worker_stage", "_validate_controller_worker_stage_locked", "_validate_controller_startup", "_validate_startup_locked", "_startup_selection_current", "_startup_references", "_startup_values", "_startup_authority_snapshot", "_startup_configuration", "_require", "_STARTUP_PROFILE")
for name in MODULES:
    module = types.ModuleType(name)
    module.__file__ = os.path.join(HERE, name + ".py")
    sys.modules[name] = module
    if name == "test_reservations":
        # Capture original canonical subjects before any fixture/test definitions.
        STARTUP_ENTRY_VALID = startup_pair_valid()
        assert STARTUP_ENTRY_VALID
        adapter = LOADED["asr_loading_adapter"]
        durable = LOADED["durable_lifecycle"]
        STARTUP_KERNEL_TYPE = durable._DurableKernel
        BOUNDARY_FUNCTIONS = adapter._CONTROLLER_BOUNDARY_FUNCTIONS
        FACTORY_CHECK = durable._FIXED_FACTORY_START_CHECK
        assert type(BOUNDARY_FUNCTIONS) is tuple and len(BOUNDARY_FUNCTIONS) == 19
        assert all(function is getattr(adapter, name) for name, function in zip(BOUNDARY_NAMES, BOUNDARY_FUNCTIONS))
        STARTUP_FUNCTIONS = tuple(
            (LOADED[module_name], method, getattr(LOADED[module_name], method))
            for module_name, methods in (
                ("trusted_asr_resolver", ("load_manifest", "admit_snapshot", "bind_for_constructor", "_checked_chain", "_inventory", "_hash_asset")),
                ("asr_loading_adapter", ("_require", "policy_status", "_release", "_plan", "_leased_admission", "ensure_assets", "_runtime_profile", "_model_session", "whisperx_session", "faster_whisper_session", "_startup_configuration", "_startup_authority_snapshot", "_startup_selection_current", "_startup_values", "_startup_references", "_validate_startup_locked", "_validate_controller_startup", "_consume_controller_startup", "_fixed_real_worker_start", "_controller_startup_scope", "_validate_controller_worker_stage", "_validate_controller_worker_stage_locked", "_validate_controller_pre_resume", "_validate_controller_pre_resume_locked", "_capture_controller_boundary", "_check_controller_entry", "_check_controller_boundary", "_require_fixed_controller_functions", "_classify_controller_custody", "_require_controller_binding", "_STARTUP_PROFILE")),
                ("durable_lifecycle", ("_require_factory_start",)),
            ) for method in methods)
        assert len(STARTUP_FUNCTIONS) == 38
        STARTUP_TYPES = tuple(
            (LOADED[module_name], name, getattr(LOADED[module_name], name))
            for module_name, names in (
                ("asr_loading_adapter", ("_ControllerASRStart", "_StartupCustody", "_ControllerBoundary")),
                ("durable_lifecycle", ("_FactoryStartAttempt", "DurableOwnedRuntimeFactory", "DurableSnapshotLifecycle", "_DurableKernel", "_DurableLease")),
                ("snapshot_lifecycle", ("OwnedSession", "_NativePermit", "Phase")),
                ("snapshot_reservations", ("Reservation",)),
            ) for name in names)
        assert len(STARTUP_TYPES) == 12
        STARTUP_METHODS = tuple(
            (owner, name, getattr(owner, name))
            for owner, names in (
                (durable.DurableOwnedRuntimeFactory, ("__init__", "open_owned_session")),
                (durable._DurableKernel, ("__init__", "start_owned_worker", "stop_unpublished")),
                (durable.DurableSnapshotLifecycle, ("_flush_quarantine",)),
            ) for name in names)
        assert len(STARTUP_METHODS) == 6
        REAL_ENTRIES = ((LOADED["reservation_file_port"], "real_journal_port", LOADED["reservation_file_port"].real_journal_port),
                        (LOADED["snapshot_reservations"], "real_reservation_service", LOADED["snapshot_reservations"].real_reservation_service))
    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)
    LOADED[name] = module

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

suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name.split(".", 1)[1], LOADED[name.split(".", 1)[0]]) for name in EXPECTED)
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
    "real_entrypoints_unchanged": len(REAL_ENTRIES) == 2
        and all(getattr(module, name) is function for module, name, function in REAL_ENTRIES)
        and STARTUP_ENTRY_VALID and startup_pair_valid is STARTUP_VALIDATOR and startup_pair_valid()
        and len(STARTUP_FUNCTIONS) == 38
        and all(getattr(module, name) is function for module, name, function in STARTUP_FUNCTIONS)
        and len(STARTUP_TYPES) == 12
        and all(getattr(module, name) is original for module, name, original in STARTUP_TYPES)
        and len(STARTUP_METHODS) == 6
        and all(getattr(owner, name) is original for owner, name, original in STARTUP_METHODS)
        and LOADED["durable_lifecycle"]._DurableKernel is STARTUP_KERNEL_TYPE
        and LOADED["asr_loading_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE
        and LOADED["asr_loading_adapter"]._CONTROLLER_BOUNDARY_FUNCTIONS is BOUNDARY_FUNCTIONS
        and type(BOUNDARY_FUNCTIONS) is tuple and len(BOUNDARY_FUNCTIONS) == 19
        and all(function is getattr(LOADED["asr_loading_adapter"], name)
                for name, function in zip(BOUNDARY_NAMES, BOUNDARY_FUNCTIONS))
        and LOADED["durable_lifecycle"]._FIXED_FACTORY_START_CHECK is FACTORY_CHECK
        and LOADED["durable_lifecycle"]._require_factory_start is FACTORY_CHECK,
}
membership = [row["id"] for row in cases] == EXPECTED and result.testsRun == len(EXPECTED)
passed = sum(row["passed"] for row in cases)
skipped = sum(row["skipped"] for row in cases)
valid = membership and all(guards.values()) and not DENIALS and not REGISTRY_DENIALS and not heavy
code = 0 if valid and passed == 10 and skipped == 0 else 1
payload = json.dumps({"schema": "uoink.windows-reservation-fake-preflight.v1", "cases": cases,
    "passed": passed, "failed": len(cases) - passed - skipped, "skipped": skipped,
    "count": len(cases), "expected_cases": EXPECTED, "membership_valid": membership,
    "guards": guards, "guard_valid": valid, "guard_denials": DENIALS, "registry_denials": REGISTRY_DENIALS,
    "heavy_roots_loaded": heavy, "metadata_trap_count": len(TRAPS), "registry_trap_count": len(REGISTRY_TRAPS),
    "input_sha256": HASHES, "elapsed_seconds": elapsed, "qualification_exit": code,
    "scope": "Ten canonical controller custody cases; generated metadata and fake lower services only; generated-start and real worker qualification remain closed"}, indent=2)
assert len(payload.encode("utf-8")) <= 262144
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(code)
