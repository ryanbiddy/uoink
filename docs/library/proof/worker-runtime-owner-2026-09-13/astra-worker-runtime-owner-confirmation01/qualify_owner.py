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
import unittest
import collections
import copy
import weakref
import typing
import re
import encodings.utf_8_sig
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
INPUTS = ('plain_state_reader.py', 'state_bridge.py', 'owned_cpu_tensor_port.py', 'model_binding_registry.py', 'owned_factory_port.py', 'owned_guard.py', 'fake_torch_support.py', 'fixed_schema_helpers.py', 'worker_runtime_owner.py', 'generated_factory_fixture.py', 'generated_unit_cases.py', 'qualify_owner.py', 'EXPECTED-CASES.json')
READS = {os.path.normcase(os.path.join(HERE, name)) for name in INPUTS}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"}
assert HEAVY.intersection(name.split(".")[0] for name in sys.modules) == {"winreg"}
ALLOWED_IMPORTS = set(sys.modules) | set(('plain_state_reader', 'state_bridge', 'owned_cpu_tensor_port', 'model_binding_registry', 'owned_factory_port', 'owned_guard', 'fake_torch_support', 'fixed_schema_helpers', 'worker_runtime_owner', 'generated_factory_fixture', 'generated_unit_cases'))
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
SOURCE_PINS = {'plain_state_reader.py': '3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c', 'state_bridge.py': 'b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2', 'owned_cpu_tensor_port.py': 'ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964', 'model_binding_registry.py': '48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb', 'owned_factory_port.py': '2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4', 'owned_guard.py': '7672f614d81cf0be5e7bd408f8f856af328fe34e6ca7ee707c9d0db838e56d1f', 'fake_torch_support.py': '5e1381eac70634292945422dfaf70786bb5fb96cbab7ea14a3fcc08fa29a185b', 'fixed_schema_helpers.py': 'd61e9a48ecfa906862fedb5b91415f1d2a0b71adc27d3e43ef245842c9e5b188', 'worker_runtime_owner.py': '5647023ed03c5acfd8b1aa981a56171dd92228ccc0972f12546bb0b3d411ce87', 'generated_factory_fixture.py': '1c60507a82c238116b630f146c44e7a81fdc57eb74f05841489c3128f150eb6f', 'generated_unit_cases.py': '58ce1ba84b4baa457c3973cea5745ad3be94caa4ce627da732d67e9c8e148979', 'EXPECTED-CASES.json': '954ca4783d70c2dc654e19a110aee6b7c453cd1e6f00098c46bd1b84a4738ba3'}
assert all(HASHES[name] == expected for name, expected in SOURCE_PINS.items())
EXPECTED_CASES = ('generated_unit_cases.OwnerContracts.test_01_actual_factory_publication_keeps_registry_identity', 'generated_unit_cases.OwnerContracts.test_02_foreign_vad_and_namespace_refused', 'generated_unit_cases.OwnerContracts.test_03_foreign_pcm_and_sample_rate_refused', 'generated_unit_cases.OwnerContracts.test_04_replaced_mutated_and_expired_pcm_refused', 'generated_unit_cases.OwnerContracts.test_05_overlapping_operation_and_release_refused', 'generated_unit_cases.OwnerContracts.test_06_revocation_blocks_publication_and_retains_owners', 'generated_unit_cases.OwnerContracts.test_07_real_constructor_pcm_and_filter_routes_remain_closed', 'generated_unit_cases.OwnerContracts.test_08_vad_only_retirement_blocks_publication', 'generated_unit_cases.OwnerContracts.test_09_replaced_completed_product_blocks_publication', 'generated_unit_cases.OwnerContracts.test_10_replaced_runtime_module_blocks_publication', 'generated_unit_cases.OwnerContracts.test_11_revoked_model_lease_blocks_publication')
expected_file = json.loads(RAW["EXPECTED-CASES.json"].decode("utf-8"))
assert expected_file == {"schema": "uoink.runtime-owner-expected-cases.v1", "count": 11, "ordered_cases": list(EXPECTED_CASES)}


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

MODULES = ('plain_state_reader', 'state_bridge', 'owned_cpu_tensor_port', 'model_binding_registry', 'owned_factory_port', 'owned_guard', 'fake_torch_support', 'fixed_schema_helpers', 'worker_runtime_owner', 'generated_factory_fixture', 'generated_unit_cases')

for module_name in MODULES:
    module = types.ModuleType(module_name)
    module.__file__ = os.path.join(HERE, module_name + '.py')
    sys.modules[module_name] = module
    exec(compile(RAW[module_name + '.py'], module.__file__, 'exec'), module.__dict__)

registry_module = sys.modules['model_binding_registry']
factory_module = sys.modules['owned_factory_port']
cpu_module = sys.modules['owned_cpu_tensor_port']
bridge_module = sys.modules['state_bridge']
owner_module = sys.modules['worker_runtime_owner']
guard_module = sys.modules['owned_guard']
fixture_module = sys.modules['generated_factory_fixture']
case_module = sys.modules['generated_unit_cases']
assert guard_module._RUNTIME is None and fixture_module.Model is object
assert tuple(case_module.EXPECTED_CASES) == EXPECTED_CASES
case_class = case_module.OwnerContracts
assert tuple('generated_unit_cases.OwnerContracts.' + name for name in vars(case_class) if name.startswith('test_')) == EXPECTED_CASES
assert not any(name in vars(case_class) for name in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass'))
CLASSES = (registry_module._WorkerModelRegistryProposal, registry_module._FactoryModelCapability,
           registry_module._ModelRegistrationLease, factory_module._OwnedFactoryPortProposal,
           factory_module._FactoryOwner, cpu_module._OwnedCPUTorchPortProposal,
           owner_module._WorkerRuntimeOwnerProposal)
METHODS = tuple((cls, name, value) for cls in CLASSES for name, value in vars(cls).items()
                if callable(value) or isinstance(value, (property, staticmethod, classmethod)))
CLOSED = tuple((module, name, getattr(module, name)) for module, name in (
    (registry_module, 'open_real_model_registry'), (factory_module, 'open_real_factory_port'),
    (cpu_module, 'open_real_tensor_port'), (bridge_module, 'build_real_vad'),
    (owner_module, 'open_real_runtime_owner')))
ORIGINAL_REQUIRE = guard_module.require_owned_runtime
results = []
started = time.perf_counter()
for name in EXPECTED_CASES:
    try:
        case = case_class(name.rsplit('.', 1)[1])
        getattr(case, name.rsplit('.', 1)[1])()
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
methods_unchanged = all(vars(cls).get(name) is value for cls, name, value in METHODS)
closed_entries_unchanged = all(getattr(module, name, None) is value for module, name, value in CLOSED)
owner_binding_valid = (guard_module._RUNTIME is None and fixture_module.Model is object
                       and guard_module.require_owned_runtime is ORIGINAL_REQUIRE)
valid = (methods_unchanged and closed_entries_unchanged and owner_binding_valid and not DENIALS and not heavy and traps_installed and CONTENT_OPEN is False and captures_installed and capture_valid
         and registry_identity and registry_namespace_unchanged and registry_traps_installed and not REGISTRY_DENIALS)
passed = sum(row["passed"] for row in results)
exit_code = 0 if passed == len(results) and valid else 1
payload = json.dumps({"schema": "uoink.runtime-owner-synthetic.v1", "cases": results, "passed": passed,
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
                  "methods_unchanged": methods_unchanged, "closed_entries_unchanged": closed_entries_unchanged,
                  "owner_binding_valid": owner_binding_valid, "guard_valid": valid, "native_exit": exit_code, "count": len(results), "skipped": 0,
                  "elapsed_seconds": elapsed, "expected_cases": EXPECTED_CASES,
                  "scope": "Generated fake factory/tensor/ownership only; no kernel, model, decoder, filters or real-loader qualification"}, indent=2)
assert len(payload.encode("utf-8")) <= 131072
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(exit_code)
