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
import stat
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
INPUTS = ('plain_state_reader.py', 'state_bridge.py', 'owned_cpu_tensor_port.py', 'model_binding_registry.py', 'owned_factory_port.py', 'owned_guard.py', 'fake_torch_support.py', 'fixed_schema_helpers.py', 'worker_runtime_owner.py', 'reservation_file_port.py', 'snapshot_reservations.py', 'snapshot_lifecycle.py', 'durable_lifecycle.py', 'win32_worker_connection.py', 'windows_reservation_port.py', 'owned_generation_protocol.py', 'win32_private_pipe.py', 'pinned_buffer_namespace.py', 'inherited_readset.py', 'generated_worker_flow.py', 'generated_operation_flow.py', 'trusted_asr_resolver.py', 'asr_loading_adapter.py', 'generated_journal_setup.py', 'generated_writer_exclusion.py', 'generated_worker_factory_inputs.py', 'generated_worker_runtime_bridge.py', 'generated_adapter_flow.py', 'generated_factory_fixture.py', 'generated_unit_cases.py', 'generated_bootstrap_fixture.py', 'connection_cases.py', 'generated_native_owner_fixture.py', 'native_owner_cases.py', 'qualify_owner.py', 'EXPECTED-CASES.json')
READS = {os.path.normcase(os.path.join(HERE, name)) for name in INPUTS}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"}
assert HEAVY.intersection(name.split(".")[0] for name in sys.modules) == {"winreg"}
ALLOWED_IMPORTS = set(sys.modules) | set(('plain_state_reader', 'state_bridge', 'owned_cpu_tensor_port', 'model_binding_registry', 'owned_factory_port', 'owned_guard', 'fake_torch_support', 'fixed_schema_helpers', 'worker_runtime_owner', 'reservation_file_port', 'snapshot_reservations', 'snapshot_lifecycle', 'durable_lifecycle', 'win32_worker_connection', 'windows_reservation_port', 'owned_generation_protocol', 'win32_private_pipe', 'pinned_buffer_namespace', 'inherited_readset', 'generated_worker_flow', 'generated_operation_flow', 'trusted_asr_resolver', 'asr_loading_adapter', 'generated_journal_setup', 'generated_writer_exclusion', 'generated_worker_factory_inputs', 'generated_worker_runtime_bridge', 'generated_adapter_flow', 'generated_factory_fixture', 'generated_unit_cases', 'generated_bootstrap_fixture', 'connection_cases', 'generated_native_owner_fixture', 'native_owner_cases'))
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
SOURCE_PINS = {"plain_state_reader.py":"3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c","state_bridge.py":"b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2","owned_cpu_tensor_port.py":"ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964","model_binding_registry.py":"48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb","owned_factory_port.py":"2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4","owned_guard.py":"7672f614d81cf0be5e7bd408f8f856af328fe34e6ca7ee707c9d0db838e56d1f","fake_torch_support.py":"5e1381eac70634292945422dfaf70786bb5fb96cbab7ea14a3fcc08fa29a185b","fixed_schema_helpers.py":"d61e9a48ecfa906862fedb5b91415f1d2a0b71adc27d3e43ef245842c9e5b188","worker_runtime_owner.py":"5647023ed03c5acfd8b1aa981a56171dd92228ccc0972f12546bb0b3d411ce87","reservation_file_port.py":"708554378ab8a8e6c4477e637c999256665cbd2855b94c6fa3c2d04a19d3a224","snapshot_reservations.py":"e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98","snapshot_lifecycle.py":"a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd","durable_lifecycle.py":"ef1519262dc0762c96d86582e211e8c2d9dfcbf93d8a3a03b0a6fc4dba5de352","win32_worker_connection.py":"60d22036d6827205be5d0657af8e4693aa534605bdfb1b501878eb2a889fe25f","windows_reservation_port.py":"b93076ab07b8c0567f6608520c99f5e5523be3dd388010a5a49037a4a899f775","owned_generation_protocol.py":"bd5204ef0d3fc2a459df19bc5f02fd7b6d78041e2306b4031ab888387aa362c0","win32_private_pipe.py":"73a1109a55f2bc807594655c71b24a3e35eb88d7f744497df2cc328dc224cae7","pinned_buffer_namespace.py":"2cc25a7a254f35d802336ef121cc860887a4301b3257588438dddec392fe0b7b","inherited_readset.py":"02be8e04f4bea3030faf0882ae48ead40716c5782f95e2790e1a9897c5be76e3","generated_worker_flow.py":"1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238","generated_operation_flow.py":"6f09b4e6490b2078e792e49559a9dd0db95a895a778c31294a3577eeabdc98ed","trusted_asr_resolver.py":"16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833","asr_loading_adapter.py":"635d2c22db75d12ffe6965fb656fdca47450ccbbaeb4d8cc8aaff9fcc79dd243","generated_journal_setup.py":"e6a0b9aab01c1ee4f8da948bd76b420c709d10b79b094026493384a2fe89d9d6","generated_writer_exclusion.py":"8173d7394f4a893c14d2979283a0c17ed273e25f196e14560590be3a0f22058b","generated_worker_factory_inputs.py":"dbf5f1859fbe6f90d0f892e5a8dc7652f7336b32f51bf1dec0278f5fecfca046","generated_worker_runtime_bridge.py":"11eff72f6d96b5c4248987635b5373672da706e1ac0fac53188aac7a3a253716","generated_adapter_flow.py":"4d1bc0ac6e25733b13cc2d16c327be23d90c68d22b1402736ff8147b302a0e8c","generated_factory_fixture.py":"1c60507a82c238116b630f146c44e7a81fdc57eb74f05841489c3128f150eb6f","generated_unit_cases.py":"58ce1ba84b4baa457c3973cea5745ad3be94caa4ce627da732d67e9c8e148979","generated_bootstrap_fixture.py":"6ea5e4e7cebff54380193b1ad0cc1b1cf08e4a7f34a8162d2f0f6ce73371d469","connection_cases.py":"2e598f26c7edd2e60b06495a62a350411ceb0a60ed6fd3486c1a1294d04cbea6","generated_native_owner_fixture.py":"a86b143a11f4abb8683f859ff7fd9f04b374aa591a6f478b724a4866fab51beb","native_owner_cases.py":"2a2ec0245524532e383472e737b60a9dea125c27118b75c16ec00ade634e851d","EXPECTED-CASES.json":"2c1fadce72b41ed443fcbcd2be88758db9f1cb55e530c7a33010377c598d164e"}
assert all(HASHES[name] == expected for name, expected in SOURCE_PINS.items())
EXPECTED_CASES = ('generated_unit_cases.OwnerContracts.test_01_actual_factory_publication_keeps_registry_identity', 'generated_unit_cases.OwnerContracts.test_02_foreign_vad_and_namespace_refused', 'generated_unit_cases.OwnerContracts.test_03_foreign_pcm_and_sample_rate_refused', 'generated_unit_cases.OwnerContracts.test_04_replaced_mutated_and_expired_pcm_refused', 'generated_unit_cases.OwnerContracts.test_05_overlapping_operation_and_release_refused', 'generated_unit_cases.OwnerContracts.test_06_revocation_blocks_publication_and_retains_owners', 'generated_unit_cases.OwnerContracts.test_07_real_constructor_pcm_and_filter_routes_remain_closed', 'generated_unit_cases.OwnerContracts.test_08_vad_only_retirement_blocks_publication', 'generated_unit_cases.OwnerContracts.test_09_replaced_completed_product_blocks_publication', 'generated_unit_cases.OwnerContracts.test_10_replaced_runtime_module_blocks_publication', 'generated_unit_cases.OwnerContracts.test_11_revoked_model_lease_blocks_publication', 'connection_cases.BootstrapContracts.test_01_actual_bootstrap_build_register_use_release', 'connection_cases.BootstrapContracts.test_02_missing_guard_refuses_before_constructor', 'connection_cases.BootstrapContracts.test_03_registration_failure_retains_completed_product', 'connection_cases.BootstrapContracts.test_04_first_error_survives_both_revocation_failures', 'connection_cases.BootstrapContracts.test_05_release_cannot_overlap_use', 'connection_cases.BootstrapContracts.test_06_constructor_error_retains_inputs_before_factory_assignment', 'native_owner_cases.NativeOwnerContracts.test_01_actual_child_build_segment_cancel_retire', 'native_owner_cases.NativeOwnerContracts.test_02_clean_initial_cancel_allocates_nothing', 'native_owner_cases.NativeOwnerContracts.test_03_initial_control_requires_ready', 'native_owner_cases.NativeOwnerContracts.test_04_wrong_initial_manifest_closes_before_allocation', 'native_owner_cases.NativeOwnerContracts.test_05_consumed_cancel_refuses_both_begin_entries', 'native_owner_cases.NativeOwnerContracts.test_06_policy_required_before_initial_entry', 'native_owner_cases.NativeOwnerContracts.test_07_constructor_error_survives_final_revoke', 'native_owner_cases.NativeOwnerContracts.test_08_partial_generated_input_failure_retained', 'native_owner_cases.NativeOwnerContracts.test_09_registration_error_retains_actual_product', 'native_owner_cases.NativeOwnerContracts.test_10_mutated_pcm_blocks_segment_publication', 'native_owner_cases.NativeOwnerContracts.test_11_revoked_model_lease_blocks_segment_publication', 'native_owner_cases.NativeOwnerContracts.test_12_unread_release_failure_has_no_closed_write', 'native_owner_cases.NativeOwnerContracts.test_13_factory_retirement_failure_retains_read_guards', 'native_owner_cases.NativeOwnerContracts.test_14_closed_write_failure_retains_inputs', 'native_owner_cases.NativeOwnerContracts.test_15_revoke_failure_after_closed_is_not_clean_return', 'native_owner_cases.NativeOwnerContracts.test_16_owner_revocation_inside_encode_prevents_send')
expected_file = json.loads(RAW["EXPECTED-CASES.json"].decode("utf-8"))
assert expected_file == {"schema": "uoink.runtime-owner-native-expected-cases.v1", "count": 33, "ordered_cases": list(EXPECTED_CASES)}


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

MODULES = ('plain_state_reader', 'state_bridge', 'owned_cpu_tensor_port', 'model_binding_registry', 'owned_factory_port', 'owned_guard', 'fake_torch_support', 'fixed_schema_helpers', 'worker_runtime_owner', 'reservation_file_port', 'snapshot_reservations', 'snapshot_lifecycle', 'durable_lifecycle', 'win32_worker_connection', 'windows_reservation_port', 'owned_generation_protocol', 'win32_private_pipe', 'pinned_buffer_namespace', 'inherited_readset', 'generated_worker_flow', 'generated_operation_flow', 'trusted_asr_resolver', 'asr_loading_adapter', 'generated_journal_setup', 'generated_writer_exclusion', 'generated_worker_factory_inputs', 'generated_worker_runtime_bridge', 'generated_adapter_flow', 'generated_factory_fixture', 'generated_unit_cases', 'generated_bootstrap_fixture', 'connection_cases', 'generated_native_owner_fixture', 'native_owner_cases')

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
protocol_module = sys.modules['owned_generation_protocol']
bootstrap_fixture_module = sys.modules['generated_bootstrap_fixture']
connection_module = sys.modules['connection_cases']
new_case_module = sys.modules['native_owner_cases']
new_bridge_module = sys.modules['generated_worker_runtime_bridge']
new_input_module = sys.modules['generated_worker_factory_inputs']
flow_module = sys.modules['generated_adapter_flow']
real_resolver = sys.modules['trusted_asr_resolver']
adapter_module = sys.modules['asr_loading_adapter']
ADAPTER_GLOBAL_NAMES = ('RELEASE_AUTHORITY', 'RUNTIME_PROFILE', 'SNAPSHOT_LIFECYCLE', 'RUNTIME_FACTORY', 'ACQUISITION_SERVICE')
ORIGINAL_ADAPTER_RELEASE = adapter_module._release
ORIGINAL_RESOLVER_FUNCTIONS = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
assert real_resolver.REAL_APPROVAL is None and flow_module._RETAINED_CHILD_RUNTIME_BRIDGE is None
assert adapter_module.resolver is real_resolver and all(getattr(adapter_module, name) is None for name in ADAPTER_GLOBAL_NAMES)
assert guard_module._RUNTIME is None and fixture_module.Model is object and bootstrap_fixture_module.Model is object
CASE_GROUPS = ((case_module, case_module.OwnerContracts, EXPECTED_CASES[:11]),
               (connection_module, connection_module.BootstrapContracts, EXPECTED_CASES[11:17]),
               (new_case_module, new_case_module.NativeOwnerContracts, EXPECTED_CASES[17:]))
CASE_CLASSES = {}
for module, case_class, expected_group in CASE_GROUPS:
    assert tuple(module.EXPECTED_CASES) == expected_group
    prefix = module.__name__ + '.' + case_class.__name__ + '.'
    assert tuple(prefix + name for name in vars(case_class) if name.startswith('test_')) == expected_group
    assert not any(name in vars(case_class) for name in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass'))
    for name in expected_group:
        CASE_CLASSES[name] = case_class
assert tuple(CASE_CLASSES) == EXPECTED_CASES
CLASSES = (registry_module._WorkerModelRegistryProposal, registry_module._FactoryModelCapability,
           registry_module._ModelRegistrationLease, factory_module._OwnedFactoryPortProposal,
           factory_module._FactoryOwner, cpu_module._OwnedCPUTorchPortProposal,
           owner_module._WorkerRuntimeOwnerProposal, protocol_module.GenerationChannel,
           protocol_module.WorkerBootstrap, protocol_module.ControllerHandshake, protocol_module.GenerationBinding,
           new_bridge_module.GeneratedWorkerRuntimeBridge, new_input_module.GeneratedFactoryInputs,
           sys.modules['inherited_readset'].InheritedReadSetAdoption)
METHODS = tuple((cls, name, value) for cls in CLASSES for name, value in vars(cls).items()
                if callable(value) or isinstance(value, (property, staticmethod, classmethod)))
CLOSED = tuple((module, name, getattr(module, name)) for module, name in (
    (registry_module, 'open_real_model_registry'), (factory_module, 'open_real_factory_port'),
    (cpu_module, 'open_real_tensor_port'), (bridge_module, 'build_real_vad'),
    (owner_module, 'open_real_runtime_owner'), (protocol_module, 'activate_real_worker'),
    (sys.modules['windows_reservation_port'], 'real_windows_reservation_service'),
    (sys.modules['snapshot_reservations'], 'real_reservation_service'),
    (sys.modules['reservation_file_port'], 'real_journal_port')))
ORIGINAL_REQUIRE = guard_module.require_owned_runtime
results = []
started = time.perf_counter()
for name in EXPECTED_CASES:
    try:
        case = CASE_CLASSES[name](name.rsplit('.', 1)[1])
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
                       and bootstrap_fixture_module.Model is object
                       and fixture_module.require_owned_runtime is ORIGINAL_REQUIRE
                       and bootstrap_fixture_module.require_owned_runtime is ORIGINAL_REQUIRE
                       and guard_module.require_owned_runtime is ORIGINAL_REQUIRE
                       and flow_module._RETAINED_CHILD_RUNTIME_BRIDGE is None
                       and real_resolver.REAL_APPROVAL is None and adapter_module.resolver is real_resolver
                       and adapter_module._release is ORIGINAL_ADAPTER_RELEASE
                       and all(getattr(adapter_module, name) is None for name in ADAPTER_GLOBAL_NAMES)
                       and (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == ORIGINAL_RESOLVER_FUNCTIONS)
valid = (methods_unchanged and closed_entries_unchanged and owner_binding_valid and not DENIALS and not heavy and traps_installed and CONTENT_OPEN is False and captures_installed and capture_valid
         and registry_identity and registry_namespace_unchanged and registry_traps_installed and not REGISTRY_DENIALS)
passed = sum(row["passed"] for row in results)
exit_code = 0 if passed == len(results) and valid else 1
payload = json.dumps({"schema": "uoink.runtime-owner-native-fake.v1", "cases": results, "passed": passed,
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
                  "scope": "Original17 owner/bootstrap plus16 generated child-route cases; fake adoption/transport only, no kernel/model/decoder/filter/real-loader qualification"}, indent=2)
assert len(payload.encode("utf-8")) <= 131072
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(exit_code)
