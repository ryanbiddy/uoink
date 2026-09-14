"""Unexecuted generated-data worker flow; caller supplies reviewed bound APIs.

No ctypes import, DLL load, process, filesystem or model operation at import.
Only a separately reviewed exact dummy launcher may call these functions.
"""
import hashlib
from owned_generation_protocol import GenerationBinding, GenerationChannel, ControllerHandshake
from owned_generation_protocol import encode_private_bootstrap, decode_private_bootstrap
from win32_worker_connection import KernelUnconfirmed, KernelUnavailable
from win32_worker_connection import WAIT_OBJECT_0, WAIT_TIMEOUT, JOB_BASIC_ACCOUNTING_CLASS
from snapshot_lifecycle import SnapshotLifecycle, OwnedRuntimeFactory, Phase
from inherited_readset import (NAMES, GENERATED, PAYLOAD_BYTES, AdoptionRefusal,
    InheritedReadSetAdoption, controller_manifest, manifest_digest, namespace_digest, fixed_paths)

GENERATED_TEXT = "0123456789abcdef" * 2500
GENERATED_SHA256 = hashlib.sha256(GENERATED_TEXT.encode("ascii")).hexdigest()
MAX_WAIT_MS = 5000


def declare_exit_call(api, kernel32):
    ffi = api.ffi
    function = kernel32.GetExitCodeProcess
    function.restype = ffi.c_int32
    function.argtypes = [ffi.c_void_p, ffi.POINTER(ffi.c_uint32)]
    api.functions["GetExitCodeProcess"] = function


def _assert(condition, reason):
    if not condition:
        raise KernelUnconfirmed(reason)


def _remaining(clock):
    # Pipe code independently verifies finite, positive, <=30-second deadlines.
    return clock() + 10.0


def _write_access_probe(primitives, generated_path, expected_locked):
    # The fixed outer plan must bind this one newly generated path. Never take
    # it from IPC, a model manifest, user input or an existing product path.
    from win32_worker_connection import _absolute_local_path
    _absolute_local_path(generated_path)
    value = primitives.api.call("CreateFileW", generated_path, 0x40000000, 7, None, 3, 0x00200000, None)
    error = primitives.api.ffi.get_last_error()
    invalid = value is None or value == (1 << 64) - 1
    if expected_locked:
        if not invalid:
            handle = primitives._retain(value, "dummy-unexpected-write-access")
            primitives._close(handle)
        _assert(invalid and error == 32, "generated_file_write_share_guard_not_observed")
        return {"write_open_refused": True, "winerror": error}
    _assert(not invalid, "generated_file_guard_not_released")
    handle = primitives._retain(value, "dummy-postrelease-write-access")
    primitives._close(handle)
    return {"write_open_succeeded": True, "bytes_written": 0}


def _observe_graceful_exit(primitives, worker, expected_exit):
    _assert(type(expected_exit) is int and expected_exit in (0, 2), "fixed_generated_child_exit")
    _assert(any(item is worker for item in primitives.workers) and worker.assigned
            and not worker.unconfirmed and not worker.shutdown_started, "exact_clean_dummy_worker_required")
    worker.shutdown_started = True
    try:
        _assert(worker.creation_time == primitives._creation_time(worker.process), "dummy_process_identity_changed")
        process = primitives._owned(worker.process)
        _assert(primitives.api.call("WaitForSingleObject", process, MAX_WAIT_MS) == WAIT_OBJECT_0,
                "dummy_process_exit_not_observed")
        exit_code = primitives.api.ffi.c_uint32()
        primitives.api.checked("GetExitCodeProcess", process, primitives.api.ffi.byref(exit_code))
        _assert(exit_code.value == expected_exit, "generated_child_exit_differs_from_fixed_case")
        accounting = primitives.api.structure("JOBOBJECT_BASIC_ACCOUNTING_INFORMATION")
        returned = primitives.api.ffi.c_uint32()
        primitives.api.checked("QueryInformationJobObject", primitives._owned(worker.job), JOB_BASIC_ACCOUNTING_CLASS,
            primitives.api.ffi.byref(accounting), primitives.api.ffi.sizeof(accounting), primitives.api.ffi.byref(returned))
        _assert(returned.value == primitives.api.ffi.sizeof(accounting) and accounting.active_processes == 0,
                "dummy_owned_job_not_empty")
        worker.quiescent = True
        return {"child_native_exit": int(exit_code.value), "process_wait_observed": True, "job_active_processes": 0}
    except BaseException:
        worker.unconfirmed = True
        worker.read_set.unconfirmed = True
        raise


class GeneratedLifecyclePort:
    """One connected dummy run; no model operation methods are implemented.

    Inputs must come from the future exact generated-only launcher. This class
    does not turn a manifest, object permit or message into runtime authority.
    It has no durable crash-recovery implementation and does not publish assets.
    """

    def __init__(self, primitives, pipes, expectations, executable, arguments,
                 working_directory, environment, generation_hex, manifest_sha256,
                 namespace_sha256, child_source_sha256, master_key, pipe_name_material, case):
        _assert(type(expectations) is tuple and len(expectations) == 5, "five_generated_files_only")
        _assert(tuple(path for path, identity in expectations) == fixed_paths(working_directory), "fixed_generated_paths")
        _assert(type(case) is str and case in ("positive", "wrong_identity"), "fixed_generated_case")
        _assert(namespace_sha256 == namespace_digest(), "fixed_generated_namespace")
        self.case = case
        self.expected_exit = 0 if case == "positive" else 2
        self.adoption_response = None
        self.adoption_payload = None
        self.primitives, self.pipes, self.expectations = primitives, pipes, expectations
        self.executable, self.arguments, self.cwd, self.environment = executable, arguments, working_directory, environment
        self.generation, self.manifest, self.namespace, self.source = generation_hex, manifest_sha256, namespace_sha256, child_source_sha256
        self.master_key, self.pipe_material = master_key, pipe_name_material
        self.lifecycle = SnapshotLifecycle(self)
        self.profile = object()
        self.key = self.read_set = self.worker = self.pair = self.channel = self.handshake = self.permit = None
        self.exit_observation = None
        self.observations = []
        self.parent_guards_held_through_exit = False
        self._start_attempted = self._resume_attempted = False

    def acquire_read(self, key):
        _assert(self.key is None and self.read_set is None, "single_generated_acquisition")
        self.key = key
        self.read_set = self.primitives.pin_exact_members(self.expectations)
        return self.read_set

    def _record(self, protection, permit):
        record = self.lifecycle._records.get(self.key)
        _assert(record is not None and record.protection is protection and record.permit is permit
                and record.owner is not None and record.owner._manager is self.lifecycle,
                "exact_lifecycle_record_and_permit_required")
        return record

    def start_owned_worker(self, protection, permit, profile):
        raise KernelUnavailable("Split durable startup is required")

    def create_suspended(self, protection, permit, profile):
        record = self._record(protection, permit)
        _assert(record.phase is Phase.NATIVE_RESERVED and profile is self.profile and self.worker is None,
                "dummy_start_order_and_profile")
        self._start_attempted = True
        self.permit = permit
        self.pair = self.pipes.create_pair(self.pipe_material, _remaining(self.pipes.clock))
        self.pair.read_set = protection
        try:
            self.worker = self.pipes.attach_to_suspended_worker(self.pair, protection, self.executable,
                self.arguments, self.cwd, self.environment)
            self.adoption_payload = controller_manifest(self.primitives, protection, self.worker, self.cwd, self.case)
            self.manifest = manifest_digest(self.adoption_payload)
            binding = GenerationBinding(self.generation, self.manifest, self.namespace, self.source, self.worker.creation_time)
            self.channel = GenerationChannel(binding, self.master_key, "controller")
            self.handshake = ControllerHandshake(self.channel, record.owner, permit, self.primitives, self.worker)
            return self.worker
        except BaseException:
            self.pipes._quarantine(self.pair)
            raise

    def resume(self, worker):
        record = self._record(self.read_set, self.permit)
        _assert(worker is self.worker and record.phase is Phase.NATIVE_RESERVED
                and not record.owner._revoked, "exact_suspended_resume_owner")
        self._resume_attempted = True
        self.primitives._resume_after_future_admission(worker)
        return True

    def finish_start(self, worker, permit, profile):
        record = self._record(self.read_set, permit)
        _assert(worker is self.worker and permit is self.permit and profile is self.profile
                and worker.resumed and record.phase is Phase.NATIVE_RESERVED
                and not record.owner._revoked and self.adoption_response is None,
                "exact_postresume_start_owner")
        try:
            self.pipes.write_bytes(self.pair, encode_private_bootstrap(self.channel.binding, self.master_key), _remaining(self.pipes.clock))
            self.pipes.write_bytes(self.pair, self.handshake.challenge(), _remaining(self.pipes.clock))
            self.handshake.accept_ready(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
            self.handshake._owned_phase(True)
            self.pipes.write_bytes(self.pair, self.channel.encode("adopt_readset", self.adoption_payload), _remaining(self.pipes.clock))
            operation, response = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
            self.handshake._owned_phase(True)
            expected_operation = "readset_ready" if self.case == "positive" else "readset_rejected"
            _assert(operation == expected_operation and response == expected_adoption_response(self.case), "fixed_adoption_response")
            self.adoption_response = response
            return True
        except BaseException:
            self.pipes._quarantine(self.pair)
            raise

    def stop_start_failure(self, worker):
        _assert(worker is self.worker and any(item is worker for item in self.primitives.workers)
                and self.pair is not None and self.pair.worker is worker and self.pair.role == "controller",
                "exact_retained_start_failure_owner")
        # This is terminal observation only, never logical cleanup or guard
        # retirement. The pipe port retains uncertainty and pending buffers.
        if self.channel is not None:
            self.channel.revoke()
        self.pipes._quarantine(self.pair)
        _assert(self.pair.forced_stop_attempted and self.pair.forced_process_stop_observed is True,
                "start_failure_process_exit_unconfirmed")
        api = self.primitives.api
        exit_code = api.ffi.c_uint32()
        api.checked("GetExitCodeProcess", self.primitives._owned(worker.process), api.ffi.byref(exit_code))
        accounting, returned = api.structure("JOBOBJECT_BASIC_ACCOUNTING_INFORMATION"), api.ffi.c_uint32()
        api.checked("QueryInformationJobObject", self.primitives._owned(worker.job), JOB_BASIC_ACCOUNTING_CLASS,
                    api.ffi.byref(accounting), api.ffi.sizeof(accounting), api.ffi.byref(returned))
        _assert(exit_code.value != 259 and returned.value == api.ffi.sizeof(accounting)
                and accounting.active_processes == 0, "start_failure_job_exit_unconfirmed")
        return not self.pair.operations

    def probe_generated(self, worker, permit):
        record = self._record(self.read_set, permit)
        _assert(worker is self.worker and record.phase is Phase.NATIVE_RUNNING
                and self.adoption_response == expected_adoption_response(self.case), "adoption_before_probe")
        self.handshake._owned_phase(False)
        if self.case == "positive":
            self.pipes.write_bytes(self.pair, self.handshake.begin(), _remaining(self.pipes.clock))
            self.pipes.write_bytes(self.pair, self.channel.encode("next", {"read_generated_namespace": True}), _remaining(self.pipes.clock))
            operation, result = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
            _assert(operation == "done" and result == expected_readback(), "complete_child_generated_readback")
        else:
            # Expected refusal does not call begin, seek, materialize or a model.
            _assert(not self.handshake._begun, "refused_adoption_cannot_begin")
            result = {"expected_identity_refusal": True, "materialization_started": False}
        self.handshake._owned_phase(False)
        _assert(self.primitives.api.call("WaitForSingleObject", self.primitives._owned(worker.process), 0) == WAIT_TIMEOUT,
                "child_not_alive_before_cancel")
        _assert(len(self.read_set.members) == 5 and all(not handle.closed for handle in self.read_set.members)
                and all(handle.closed for handle in worker.inherited_copies), "parent_guards_must_remain_held")
        for path, expected in self.expectations:
            self.observations.append(_write_access_probe(self.primitives, path, True))
        return result

    def close_and_join(self, worker, permit):
        record = self._record(self.read_set, permit)
        _assert(worker is self.worker and record.phase is Phase.NATIVE_RUNNING, "dummy_close_owner")
        self.pipes.write_bytes(self.pair, self.channel.encode("cancel", {}), _remaining(self.pipes.clock))
        operation, payload = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
        _assert(operation == "closed" and payload == {}, "dummy_close_response")
        _assert(all(not handle.closed for handle in self.read_set.members), "parent_guards_before_exit")
        self.exit_observation = _observe_graceful_exit(self.primitives, worker, self.expected_exit)
        self.parent_guards_held_through_exit = all(not handle.closed for handle in self.read_set.members)
        _assert(self.parent_guards_held_through_exit, "parent_guard_lifetime")
        self.channel.revoke()
        return True

    def confirm_quiescent(self, protection, worker, permit):
        self._record(protection, permit)
        _assert(protection is self.read_set and worker is self.worker and worker.read_set is protection,
                "dummy_quiescence_owner")
        # This exact record was created only by the immediately preceding
        # retained-process wait/GetExitCode/empty-job queries, not a wire value.
        return (self.exit_observation == {"child_native_exit": self.expected_exit, "process_wait_observed": True, "job_active_processes": 0}
                and worker.quiescent and not worker.unconfirmed and not self.pair.operations)

    def release_read(self, protection):
        _assert(protection is self.read_set and self.worker is not None and self.worker.quiescent,
                "dummy_release_requires_observed_native_exit")
        self.pipes.retire_endpoint(self.pair)
        self.primitives.close_quiescent_worker_handles(self.worker)
        return self.primitives.release_read_set(protection)

    def quarantine(self, key, protection, permit, reason):
        if protection is not None:
            protection.unconfirmed = True
        if self.channel is not None:
            self.channel.revoke()
        if self.pair is not None:
            self.pipes._quarantine(self.pair)
        # Local ownership/forced-stop attempt only. There is no durable recovery
        # port here, so never report durable quarantine as successfully persisted.
        return False


def controller_flow(port):
    _assert(type(port) is GeneratedLifecyclePort, "fixed_generated_lifecycle_port_required")
    # The dummy key labels generated scope only. This never opens a real model
    # snapshot or calls the production frozen manifest resolver.
    with port.lifecycle.read_lease(port.cwd, "generated-dummy", port.generation) as lease:
        permit = lease.begin_native_session()
        session = OwnedRuntimeFactory(port.lifecycle).open_owned_session(port.profile, permit)
        result = session._call(port.probe_generated, permit.identity)
        _assert(session.close_and_join() is True, "dummy_owned_session_join_unconfirmed")
        lease.confirm_native_closed()
    for path, expected in port.expectations:
        port.observations.append(_write_access_probe(port.primitives, path, False))
    return {"generated_result": result, "lifecycle_phase": lease._record.phase.value,
            "read_set_released": port.read_set.released, "pipe_retired": port.pair.closed,
            "exit_observation": port.exit_observation, "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


def expected_adoption_response(case):
    if case == "positive":
        return {"case": case, "namespace_sha256": namespace_digest(), "owned_members": 5,
                "inheritance_cleared": 5, "identities_checked": 5, "materialization_started": False}
    _assert(case == "wrong_identity", "fixed_refusal_case")
    return {"case": case, "reason": "inherited_file_identity_mismatch", "owned_members": 5,
            "inheritance_cleared": 5, "identities_checked": 1, "materialization_started": False,
            "read_set_unconfirmed": True}


def expected_readback():
    return {"namespace_sha256": namespace_digest(), "payload_bytes": PAYLOAD_BYTES,
            "members": [{"name": name, "bytes": len(GENERATED[name]),
                         "sha256": hashlib.sha256(GENERATED[name]).hexdigest()} for name in NAMES]}


def child_flow(primitives, pipes, inherited_control_value, expected_child_source_sha256, fixed_root, fixed_case):
    """Generated files only. No native loader, factory, registry or model call."""
    _assert(type(fixed_case) is str and fixed_case in ("positive", "wrong_identity"), "fixed_child_case")
    fixed_paths(fixed_root)
    pair = pipes.adopt_inherited_client(inherited_control_value)
    channel = None
    adoption = InheritedReadSetAdoption(primitives)
    try:
        binding, key = decode_private_bootstrap(pipes.read_private_bootstrap(pair, _remaining(pipes.clock)))
        _assert(binding.bootstrap_source_sha256 == expected_child_source_sha256
                and binding.namespace_sha256 == namespace_digest(), "fixed_adoption_source_and_namespace")
        current = primitives.api.call("GetCurrentProcess")
        values = [primitives.api.structure("FILETIME") for _ in range(4)]
        primitives.api.checked("GetProcessTimes", current, *(primitives.api.ffi.byref(value) for value in values))
        creation = int(values[0].low) | int(values[0].high) << 32
        _assert(creation == binding.process_creation_time, "child_creation_binding")
        channel = GenerationChannel(binding, key, "worker")
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        expected = {"generation": binding.generation_hex, "namespace_sha256": binding.namespace_sha256}
        _assert(operation == "challenge" and payload == expected, "adoption_challenge_binding")
        pipes.write_bytes(pair, channel.encode("ready", expected), _remaining(pipes.clock))
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == "adopt_readset", "adoption_before_begin")
        refused = False
        try:
            adoption.adopt(payload, fixed_root, fixed_case, inherited_control_value, binding.manifest_sha256)
        except AdoptionRefusal as error:
            _assert(fixed_case == "wrong_identity" and str(error) == "inherited_file_identity_mismatch",
                    "unexpected_adoption_failure")
            _assert(adoption.status == "refused" and adoption.read_set is not None
                    and len(adoption.read_set.members) == 5 and adoption.read_set.unconfirmed
                    and not adoption.read_set.released and adoption.inheritance_cleared == 5
                    and adoption.identities_checked == 1 and not adoption.materialization_started,
                    "exact_identity_refusal_boundary")
            refused = True
        _assert(refused == (fixed_case == "wrong_identity"), "generated_case_outcome")
        if refused:
            pipes.write_bytes(pair, channel.encode("readset_rejected", expected_adoption_response(fixed_case)), _remaining(pipes.clock))
        else:
            _assert(adoption.status == "adopted" and adoption.inheritance_cleared == adoption.identities_checked == 5,
                    "complete_inherited_adoption")
            pipes.write_bytes(pair, channel.encode("readset_ready", expected_adoption_response(fixed_case)), _remaining(pipes.clock))
            operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
            _assert(operation == "begin" and payload == {"manifest_sha256": binding.manifest_sha256}, "adoption_begin_binding")
            operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
            _assert(operation == "next" and payload == {"read_generated_namespace": True}, "fixed_generated_read_request")
            result = adoption.materialize_generated()
            _assert(result == expected_readback(), "generated_result_binding")
            pipes.write_bytes(pair, channel.encode("done", result), _remaining(pipes.clock))
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == "cancel" and payload == {}, "adoption_cancel_required")
        if not refused:
            adoption.release_after_reads()
        # The rejected set remains uncertain and open until this process exits.
        # Its raw native exit2 is deliberate and must be independently recorded.
        pipes.write_bytes(pair, channel.encode("closed", {}), _remaining(pipes.clock))
        pipes.retire_endpoint(pair)
        return {"child_flow_return": 2 if refused else 0, "adoption": adoption.receipt(),
                "readback": None if refused else result, "model_calls": 0}
    except BaseException:
        if adoption.read_set is not None:
            adoption.read_set.unconfirmed = True
        pipes._quarantine(pair)
        raise
    finally:
        if channel is not None:
            channel.revoke()
