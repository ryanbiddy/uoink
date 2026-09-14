"""Unexecuted actual-adapter/generated-worker bridge. No real authority.

Only a separately reviewed generated bootstrap may invoke this module. Import
executes definitions and hashes fixed generated text; it performs no I/O.
"""
from contextlib import contextmanager, ExitStack
from types import SimpleNamespace
from dataclasses import dataclass
import hashlib
import json
import asr_loading_adapter as adapter
import trusted_asr_resolver as real_resolver
import generated_operation_flow as operation_flow
from snapshot_lifecycle import OperationFacade, TranscribeRequest, Phase, CleanupUnconfirmed
from durable_lifecycle import DurableSnapshotLifecycle, DurableOwnedRuntimeFactory, _RetiredRecovery, _InterruptedRetirement
from snapshot_reservations import ReservationService, SnapshotSemantics, decode_journal
import generated_journal_setup as journal_setup_module
from windows_reservation_port import WindowsGateRegistry
from owned_generation_protocol import GenerationChannel, decode_private_bootstrap
from inherited_readset import InheritedReadSetAdoption, GENERATED, NAMES, namespace_digest, fixed_paths
from generated_writer_exclusion import OwnedContender
from win32_private_pipe import PrivatePipeController, PipePair
from win32_worker_connection import WorkerRecord, ReadSet, HandleRecord

_assert = operation_flow._assert
_remaining = operation_flow._remaining
_fixed = operation_flow._fixed
declare_exit_call = operation_flow.declare_exit_call
CHOICE = "large-v3-turbo"
REVISION = real_resolver.MODEL_SPECS[CHOICE][1]
PROFILE_ID = "generated-asr-reliability-v1"
FILES = tuple((name, len(GENERATED[name]), hashlib.sha256(GENERATED[name]).hexdigest()) for name in NAMES)
RECIPE = {"purpose": "generated-adapter-connection-only", "profile_id": PROFILE_ID,
          "choice": CHOICE, "revision": REVISION,
          "files": [{"name": name, "bytes": size, "sha256": digest} for name, size, digest in FILES]}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def policy_payload(root, binding):
    # This root is the fixed private generated run, already selected by the
    # bootstrap. It is never opened or treated as a caller-supplied model path.
    return {"action": "bind_generated_adapter_start", "generated_only": True,
            "profile_id": PROFILE_ID, "usage": "reliability", "device": "cpu", "compute_type": "int8",
            "choice": CHOICE, "revision": REVISION, "generated_root": root,
            "recipe_sha256": RECIPE_SHA256, "namespace_sha256": namespace_digest(),
            "inherited_manifest_sha256": binding.manifest_sha256,
            "local_files_only": True, "constructor_called": False, "real_runtime_approved": False}


def policy_ack(payload):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return {"action": "generated_adapter_start_bound", "policy_sha256": digest, "model_calls": 0}


class _RetiredClearProbe:
    """One fixed Python interruption; never a client callback or OS signal."""
    def __init__(self, port, setup):
        _assert(type(port) is GeneratedLifecyclePort
                and type(setup) is journal_setup_module.GeneratedJournalSetup
                and setup.port is port and setup.gates is port.reservations.gates
                and port.key is None and port.worker is None,
                "fixed_recovery_probe_before_lease")
        self.port, self.setup = port, setup
        self.error = KeyboardInterrupt("fixed_after_teardown_before_clear")
        self.armed = self.fired = self.observed = self.close_observed = False
        self.owner = self.record = self.token = self.worker = self.gate_attempt = None
        self.manager_attempt = self.service_attempt = None
        self.raw = self.head = self.handle = self.revision = self.close_head = None

    def _require_retired(self, worker):
        port = self.port
        _assert(port._retired(worker) and port.pair.worker is worker and not port.pair.unconfirmed
                and worker.read_set is port.read_set
                and all(h.closed and not h.unconfirmed for h in (worker.process, worker.thread, worker.job))
                and all(h.closed and not h.unconfirmed for h in port.read_set.members),
                "recovery_has_no_uncertain_retained_native_owners")

    def interrupt_after_teardown(self, worker):
        port, setup = self.port, self.setup
        self._require_retired(worker)
        token = port.lifecycle._token(port.key)
        record = port.lifecycle._records.get(port.key)
        attempt = setup.gates.attempts.get(token.physical)
        _assert(self.armed and not self.fired and not self.observed
                and port._retired_clear_probe is self and setup._recovery_probe is self
                and port._completion is None and port._retired(worker)
                and record is not None and record.owner is not None
                and record.phase is Phase.RELEASED and record.protection is None
                and record.owner._worker is worker and token.worker is worker
                and token.phase == "CLEAR_PENDING" and not token.revoked
                and type(token.pending) is object and setup.flush_successes == 3
                and attempt is not None and attempt.token is token.gate
                and attempt.journal is token.journal and attempt.failure is None
                and attempt.handle is setup.created_handle and not attempt.handle.closed
                and not attempt.handle.unconfirmed and token.journal.confirmed_bytes == token.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned,
                "exact_retired_boundary_before_fixed_interrupt")
        rows, head = decode_journal(token.raw)
        _assert([r["phase"] for r in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND"],
                "fixed_interrupt_has_three_confirmed_frames")
        self.owner, self.record, self.token, self.worker = record.owner, record, token, worker
        self.gate_attempt, self.handle = attempt, attempt.handle
        self.raw, self.head, self.revision = token.raw, head, token.revision
        self.fired = True
        raise self.error

    def observe_interruption(self, error):
        port, token, record, setup = self.port, self.token, self.record, self.setup
        self._require_retired(self.worker)
        _assert(error is self.error and self.fired and not self.observed
                and port.lifecycle._records.get(port.key) is record and record.owner is self.owner
                and record.phase is Phase.QUARANTINED and record.protection is None
                and self.owner._revoked is True and port._retired(self.worker)
                and token is port.lifecycle._token(port.key) and token.phase == "QUARANTINED"
                and token.revoked is True and token.pending is None and token.raw == self.raw
                and token.revision == self.revision and token.journal.confirmed_bytes == self.raw
                and setup.flush_successes == 3 and not self.handle.closed and not self.handle.unconfirmed
                and setup.gates._held.get(token.physical) is token.gate
                and setup.gates.attempts.get(token.physical) is self.gate_attempt
                and self.gate_attempt.failure is None,
                "same_interrupted_owner_gate_and_three_frames")
        self.observed = True

    def bind_service_attempt(self, worker, physical, generation, head, attempt):
        port, token = self.port, self.token
        self._require_retired(worker)
        manager_attempt = port.lifecycle._retired_recoveries.get(port.key)
        _assert(self.observed and self.service_attempt is None and not self.close_observed
                and type(manager_attempt) is _RetiredRecovery
                and manager_attempt.manager is port.lifecycle and manager_attempt.owner is self.owner
                and manager_attempt.record is self.record and manager_attempt.token is token
                and manager_attempt.worker is worker and worker is self.worker
                and manager_attempt.raw == self.raw and manager_attempt.head == self.head
                and manager_attempt.revision == self.revision
                and physical == token.physical and generation == token.generation and head == self.head
                and token.raw == self.raw and token.revision == self.revision
                and token.journal.confirmed_bytes == self.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned
                and token.phase == "CLEAR_PENDING" and token.revoked is True
                and type(attempt) is object and token.pending is attempt,
                "fixed_manager_and_service_recovery_attempt")
        self.manager_attempt, self.service_attempt = manager_attempt, attempt

    def before_recovery_close(self, token):
        port, setup = self.port, self.setup
        self._require_retired(self.worker)
        rows, head = decode_journal(token.raw)
        _assert(self.observed and not self.close_observed and self.service_attempt is not None
                and token is self.token and port.lifecycle._retired_recoveries.get(port.key) is self.manager_attempt
                and self.manager_attempt.owner is self.owner and self.manager_attempt.token is token
                and port.lifecycle._records.get(port.key) is self.record
                and self.record.owner is self.owner and self.record.phase is Phase.QUARANTINED
                and self.owner._revoked is True and port._retired(self.worker)
                and token.revoked is True and token.phase == "CLEAR_PENDING" and token.pending is None
                and token.revision == self.revision and token.worker is self.worker
                and token.raw.startswith(self.raw) and rows[-1]["previous"] == self.head
                and [r["phase"] for r in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND", "CLEARED"]
                and setup.gates._held.get(token.physical) is token.gate
                and setup.gates.attempts.get(token.physical) is self.gate_attempt
                and self.gate_attempt.journal is token.journal and self.gate_attempt.handle is self.handle
                and self.gate_attempt.failure is None and self.handle is setup.created_handle
                and not self.handle.closed and not self.handle.unconfirmed
                and token.journal.confirmed_bytes == token.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned
                and setup.flush_successes == 4,
                "exact_revoked_recovery_clear_before_close")
        self.close_observed, self.close_head = True, head
        return head


@dataclass(frozen=True)
class _InterruptedNativeBinding:
    manager: object
    record: object
    owner: object
    token: object
    port: object
    primitives: object
    pipes: object
    pair: object
    worker: object
    protection: object
    permit: object
    channel: object
    pair_lock: object
    server: object
    client: object
    process: object
    thread: object
    job: object
    members: tuple
    inherited: tuple
    handle_states: tuple
    creation_time: int
    retire: object
    reconcile: object


@dataclass(frozen=True)
class _InterruptedRetirementWitness:
    attempt: object
    native: object
    closed_handles: tuple
    process_wait_observed: bool
    child_native_exit: int
    job_active_processes: int


def _capture_interrupted_native(manager, probe):
    # Called only by the manager while its state/token locks are held at the
    # completed owned operation. This captures identities, never OS metadata.
    port, owner, record, token = probe.port, probe.owner, probe.record, probe.token
    _assert(type(port) is GeneratedLifecyclePort and port.lifecycle is manager
            and manager._delegate is port and owner._manager is manager
            and owner._record is record and manager._records.get(port.key) is record
            and record.owner is owner and record.phase is Phase.NATIVE_RUNNING
            and owner._active == 1 and type(owner._active) is int
            and not owner._revoked and not owner._closing and not owner._closed_verified
            and manager._tokens.get(port.key) is token and token.worker is owner._worker
            and token.service is manager._reservations and port.reservations is token.service
            and token.phase == 'WORKER_BOUND' and token.pending is None and not token.revoked,
            'exact_owned_operation_boundary')
    p, pipes, pair, worker, protection = port.primitives, port.pipes, port.pair, port.worker, port.read_set
    _assert(type(pipes) is PrivatePipeController and type(pair) is PipePair
            and type(worker) is WorkerRecord and type(protection) is ReadSet
            and pipes.primitives is p and any(item is pair for item in pipes.pairs)
            and any(item is worker for item in p.workers)
            and any(item is protection for item in p.read_sets)
            and pair.worker is worker and pair.read_set is protection
            and worker.read_set is protection and owner._worker is worker
            and record.protection is protection and record.permit is port.permit
            and manager._kernel._starts.get(record.permit) is worker
            and pair.role == 'controller' and pair.active is False and not pair.operations
            and pair.closed is False and pair.unconfirmed is False
            and worker.unconfirmed is False and protection.unconfirmed is False
            and worker.assigned is True and worker.resumed is True
            and protection.released is False and protection.worker_reserved is True
            and type(worker.creation_time) is int and worker.creation_time > 0,
            'exact_confirmed_native_boundary')
    members, inherited = tuple(protection.members), tuple(worker.inherited_copies)
    _assert(len(members) == len(protection.identities) == 5 and len(inherited) == 6,
            'fixed_generated_native_member_set')
    live = (pair.server, worker.process, worker.thread, worker.job) + members
    handles = live + (() if pair.client is None else (pair.client,)) + inherited
    _assert(len({id(h) for h in handles}) == len(handles), 'distinct_native_handle_owners')
    for handle in handles:
        _assert(type(handle) is HandleRecord and any(item is handle for item in p.handles)
                and handle.unconfirmed is False and type(handle.closed) is bool
                and type(handle.value) is int and handle.value > 0,
                'confirmed_exact_handle_at_boundary')
    _assert(all(h.closed is False for h in live)
            and all(h.closed is True for h in inherited),
            'live_owners_and_confirmed_retired_parent_duplicates')
    return _InterruptedNativeBinding(manager, record, owner, token, port, p, pipes, pair,
        worker, protection, record.permit, port.channel, pair.lock, pair.server, pair.client,
        worker.process, worker.thread, worker.job, members, inherited,
        tuple((h, h.value, h.kind, h.closed) for h in handles), worker.creation_time,
        port.retire_interrupted_worker, token.service._reconcile_live)


def _require_interrupted_bindings(native):
    # Pure current-identity check. The native primitive owner remains private
    # and serial; no manager lock is held across a native wait or close.
    _assert(type(native) is _InterruptedNativeBinding, 'exact_interrupted_native_binding')
    m, port, p, pair, worker, protection = (native.manager, native.port,
        native.primitives, native.pair, native.worker, native.protection)
    _assert(type(port) is GeneratedLifecyclePort and m._delegate is port
            and port.lifecycle is m and port.primitives is p and port.pipes is native.pipes
            and type(native.pipes) is PrivatePipeController and native.pipes.primitives is p
            and port.pair is pair and type(pair) is PipePair and pair.lock is native.pair_lock
            and any(item is pair for item in native.pipes.pairs)
            and port.worker is worker and type(worker) is WorkerRecord
            and any(item is worker for item in p.workers)
            and port.read_set is protection and type(protection) is ReadSet
            and any(item is protection for item in p.read_sets)
            and pair.worker is worker and pair.read_set is protection and worker.read_set is protection
            and port.permit is native.permit and port.channel is native.channel
            and m._kernel._starts.get(native.permit) is worker
            and pair.server is native.server and pair.client is native.client
            and worker.process is native.process and worker.thread is native.thread and worker.job is native.job
            and len(protection.members) == len(native.members)
            and all(a is b for a, b in zip(protection.members, native.members))
            and len(worker.inherited_copies) == len(native.inherited)
            and all(a is b for a, b in zip(worker.inherited_copies, native.inherited))
            and worker.creation_time == native.creation_time and worker.assigned is True
            and worker.resumed is True and protection.worker_reserved is True
            and pair.role == 'controller' and pair.active is False and not pair.operations
            and getattr(port.retire_interrupted_worker, '__self__', None) is port
            and getattr(port.retire_interrupted_worker, '__func__', None) is native.retire.__func__
            and getattr(native.token.service._reconcile_live, '__self__', None) is port
            and getattr(native.token.service._reconcile_live, '__func__', None) is native.reconcile.__func__,
            'interrupted_native_binding_changed')
    for handle, value, kind, initially_closed in native.handle_states:
        _assert(type(handle) is HandleRecord and any(item is handle for item in p.handles)
                and handle.value == value and handle.kind == kind
                and handle.unconfirmed is False and type(handle.closed) is bool
                and (not initially_closed or handle.closed is True),
                'interrupted_individual_handle_changed_or_uncertain')
    _assert(pair.unconfirmed is True and worker.unconfirmed is True and protection.unconfirmed is True,
            'aggregate_quarantine_history_must_remain')
    return True


def _require_interrupted_witness(attempt, witness):
    native = attempt.native
    _require_interrupted_bindings(native)
    _assert(type(witness) is _InterruptedRetirementWitness
            and witness is native.port._interrupted_witness and witness.attempt is attempt
            and witness.native is native and witness.process_wait_observed is True
            and type(witness.child_native_exit) is int and 0 <= witness.child_native_exit < 1 << 32
            and witness.child_native_exit != 259 and type(witness.job_active_processes) is int
            and witness.job_active_processes == 0 and native.worker.quiescent is True
            and native.pair.closed is True and native.protection.released is True
            and type(witness.closed_handles) is tuple
            and len(witness.closed_handles) == len(native.handle_states)
            and all(a is row[0] for a, row in zip(witness.closed_handles, native.handle_states))
            and all(h.closed is True and h.unconfirmed is False for h in witness.closed_handles),
            'exact_current_interrupted_retirement_witness_required')
    return True


class _InterruptedOperationProbe:
    """One fixed Python interruption during operation; never an OS signal."""
    def __init__(self, port, setup):
        _assert(type(port) is GeneratedLifecyclePort
                and type(setup) is journal_setup_module.GeneratedJournalSetup
                and setup.port is port and setup.gates is port.reservations.gates
                and port.key is None and port.worker is None,
                "fixed_interrupted_probe_before_lease")
        self.port, self.setup = port, setup
        self.error = KeyboardInterrupt("fixed_after_second_segment_exchange")
        self.armed = self.fired = self.observed = self.close_observed = False
        self.owner = self.record = self.token = self.worker = self.gate_attempt = None
        self.manager_attempt = self.service_attempt = None
        self.raw = self.head = self.handle = self.revision = self.close_head = None
        self.quarantine_raw = self.quarantine_head = None
        self.quarantine_revision = self.native = None

    def interrupt_after_exchange(self, worker):
        port, setup = self.port, self.setup
        _assert(self.armed and not self.fired and not self.observed
                and port._interrupted_probe is self and setup._interrupted_probe is self
                and port._next_index == 2 and port.worker is worker,
                "exact_interrupted_boundary_before_fixed_interrupt")
        token = port.lifecycle._token(port.key)
        record = port.lifecycle._records.get(port.key)
        attempt = setup.gates.attempts.get(token.physical)
        _assert(record is not None and record.owner is not None
                and record.phase is Phase.NATIVE_RUNNING
                and record.owner._worker is worker and token.worker is worker
                and token.phase == "WORKER_BOUND" and not token.revoked
                and token.pending is None and setup.flush_successes == 3
                and attempt is not None and attempt.token is token.gate
                and attempt.journal is token.journal and attempt.failure is None
                and attempt.handle is setup.created_handle and not attempt.handle.closed
                and not attempt.handle.unconfirmed and token.journal.confirmed_bytes == token.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned,
                "exact_running_boundary_before_interruption")
        rows, head = decode_journal(token.raw)
        _assert([r["phase"] for r in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND"],
                "fixed_interrupt_has_three_confirmed_frames")
        self.owner, self.record, self.token, self.worker = record.owner, record, token, worker
        self.gate_attempt, self.handle = attempt, attempt.handle
        self.raw, self.head, self.revision = token.raw, head, token.revision
        self.native = port.lifecycle._remember_interrupted_boundary(self)
        self.fired = True
        raise self.error

    def observe_interruption(self, error):
        port, token, record, setup = self.port, self.token, self.record, self.setup
        _assert(error is self.error and self.fired and not self.observed
                and port.lifecycle._records.get(port.key) is record and record.owner is self.owner
                and record.phase is Phase.QUARANTINED and record.protection is port.read_set
                and self.owner._revoked is True and not self.owner._closed_verified and self.owner._active == 0
                and token is port.lifecycle._token(port.key) and token.phase == "QUARANTINED"
                and token.revoked is True and token.pending is None
                and setup.flush_successes == 4 and not self.handle.closed and not self.handle.unconfirmed
                and setup.gates._held.get(token.physical) is token.gate
                and setup.gates.attempts.get(token.physical) is self.gate_attempt
                and self.gate_attempt.failure is None,
                "same_interrupted_owner_quarantined_with_four_frames")
        rows, head = decode_journal(token.raw)
        _assert(token.raw.startswith(self.raw) and rows[-1]["previous"] == self.head
                and [r["phase"] for r in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"],
                "quarantined_journal_has_four_frames")
        _require_interrupted_bindings(self.native)
        _assert(port.lifecycle._interrupted_boundaries.get(port.key) is self.native
                and type(token.revision) is int and token.revision > self.revision,
                "exact_post_quarantine_boundary_revision")
        self.observed = True
        self.quarantine_raw, self.quarantine_head = token.raw, head
        self.quarantine_revision = token.revision

    def bind_service_attempt(self, worker, physical, generation, head, attempt):
        port, token = self.port, self.token
        _assert(port._interrupted_retired(worker), "interrupted_retired_worker_required_for_service_bind")
        manager_attempt = port.lifecycle._interrupted_retirements.get(port.key)
        _assert(self.observed and self.service_attempt is None and not self.close_observed
                and type(manager_attempt) is _InterruptedRetirement
                and manager_attempt.manager is port.lifecycle and manager_attempt.owner is self.owner
                and manager_attempt.record is self.record and manager_attempt.token is token
                and manager_attempt.worker is worker and worker is self.worker
                and manager_attempt.raw == self.quarantine_raw and manager_attempt.head == self.quarantine_head
                and manager_attempt.revision == self.quarantine_revision
                and physical == token.physical and generation == token.generation and head == self.quarantine_head
                and token.raw == self.quarantine_raw and token.revision == self.quarantine_revision
                and token.journal.confirmed_bytes == self.quarantine_raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned
                and token.phase == "CLEAR_PENDING" and token.revoked is True
                and type(attempt) is object and token.pending is attempt,
                "fixed_manager_and_service_interrupted_attempt")
        self.manager_attempt, self.service_attempt = manager_attempt, attempt

    def before_interrupted_close(self, token):
        port, setup = self.port, self.setup
        _assert(port._interrupted_retired(self.worker) and port.pair.worker is self.worker
                and not port.pair.operations and port.pair.closed
                and self.worker.read_set is port.read_set
                and all(h.closed and not h.unconfirmed for h in (self.worker.process, self.worker.thread, self.worker.job))
                and all(h.closed and not h.unconfirmed for h in port.read_set.members),
                "interrupted_recovery_has_no_uncertain_retained_native_owners")
        rows, head = decode_journal(token.raw)
        _assert(self.observed and not self.close_observed and self.service_attempt is not None
                and token is self.token and port.lifecycle._interrupted_retirements.get(port.key) is self.manager_attempt
                and self.manager_attempt.owner is self.owner and self.manager_attempt.token is token
                and port.lifecycle._records.get(port.key) is self.record
                and self.record.owner is self.owner and self.record.phase is Phase.QUARANTINED
                and self.record.protection is None
                and self.owner._revoked is True and self.owner._closed_verified is True
                and port._interrupted_retired(self.worker)
                and token.revoked is True and token.phase == "CLEAR_PENDING" and token.pending is None
                and token.revision == self.quarantine_revision and token.worker is self.worker
                and token.raw.startswith(self.quarantine_raw) and rows[-1]["previous"] == self.quarantine_head
                and [r["phase"] for r in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"]
                and setup.gates._held.get(token.physical) is token.gate
                and setup.gates.attempts.get(token.physical) is self.gate_attempt
                and self.gate_attempt.journal is token.journal and self.gate_attempt.handle is self.handle
                and self.gate_attempt.failure is None and self.handle is setup.created_handle
                and not self.handle.closed and not self.handle.unconfirmed
                and token.journal.confirmed_bytes == token.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned
                and setup.flush_successes == 5,
                "exact_interrupted_recovery_clear_before_close")
        self.close_observed, self.close_head = True, head
        return head


class GeneratedLifecyclePort(operation_flow.GeneratedLifecyclePort):
    def __init__(self, *args, operation_mode="drain", **kwargs):
        if operation_mode == "cancel":
            _assert(type(operation_mode) is str, "exact_actual_adapter_cancel_mode")
        else:
            _assert(operation_mode == "drain", "one_actual_adapter_drain_scope")
        super().__init__(*args, operation_mode=operation_mode, **kwargs)
        _assert(real_resolver.REAL_APPROVAL is None, "real_model_authority_must_remain_absent")
        self.adapter_profile = adapter.RuntimeProfile(PROFILE_ID, "cpu", "int8", None, None)
        self.generated_authority = SimpleNamespace(runtime_profile_id=PROFILE_ID,
            manifest_approval=SimpleNamespace(manifest_sha256=RECIPE_SHA256))
        self.generated_trusted = object()
        self.generated_selected = SimpleNamespace(revision=REVISION)
        self.generated_admission = SimpleNamespace(snapshot=self.cwd)
        self.generated_binding = real_resolver.LocalBinding(self.cwd, CHOICE, REVISION, RECIPE_SHA256, FILES)
        self.binding_calls = 0
        self.adapter_startup = self.adapter_start_payload = self.adapter_start_ack = None
        self.authority_events = []
        self._retired_witness = self._completion = None
        self._no_worker_witness = None
        self._interrupted_witness = None
        self._reconciliation_attempts = set()
        self._contender = None
        self._retired_clear_probe = None
        self._interrupted_probe = None

    def _bind_retired_clear_probe(self, probe):
        _assert(type(self) is GeneratedLifecyclePort and type(probe) is _RetiredClearProbe
                and probe.port is self and probe.setup.port is self
                and self._retired_clear_probe is None and probe.setup._recovery_probe is None
                and not probe.armed and not probe.fired and self.key is None and self.worker is None
                and not self._start_attempted and not self._resume_attempted,
                "one_fixed_retired_clear_probe_binding")
        self._retired_clear_probe = probe
        probe.setup._recovery_probe = probe
        probe.armed = True

    def _bind_interrupted_probe(self, probe):
        _assert(type(self) is GeneratedLifecyclePort and type(probe) is _InterruptedOperationProbe
                and probe.port is self and probe.setup.port is self
                and self._interrupted_probe is None and probe.setup._interrupted_probe is None
                and self._retired_clear_probe is None and probe.setup._recovery_probe is None
                and not probe.armed and not probe.fired and self.key is None and self.worker is None
                and not self._start_attempted and not self._resume_attempted,
                "one_fixed_interrupted_probe_binding")
        self._interrupted_probe = probe
        probe.setup._interrupted_probe = probe
        probe.armed = True

    def _bind_contender(self, contender):
        # Private fixed-bootstrap seam, before any lease or startup authority.
        _assert(type(self) is GeneratedLifecyclePort and type(contender) is OwnedContender
                and self._contender is None and contender._bound_port is None
                and not contender.entered and contender.port is None
                and contender.primitives is self.primitives and contender.monitor is self.primitives.api
                and contender.monitor.contender is contender and contender.primary.port is self
                and contender.primary.primitives is self.primitives
                and self.key is None and self.worker is None and self.read_set is None
                and self.adapter_startup is None and self.binding_calls == 0
                and not self._start_attempted and not self._resume_attempted,
                "one_exact_contender_binding_before_adapter_entry")
        self._contender = contender
        contender._bound_port = self

    def connect_durable_registry(self, gates, physical, creation_ticket):
        _assert(type(gates) is WindowsGateRegistry and self.key is None and self.worker is None
                and self.read_set is None and physical in gates.bindings,
                "exact_generated_windows_registry_before_lease")
        binding = gates.bindings[physical]
        _assert(binding.snapshot.path == self.cwd, "generated_snapshot_registry_path")
        semantic = SnapshotSemantics(physical.volume, physical.file_id, CHOICE, REVISION, RECIPE_SHA256)
        def lookup(store, choice, revision):
            _assert((store, choice, revision) == (self.cwd, CHOICE, REVISION), "fixed_durable_semantics")
            return physical, semantic, self.generation, creation_ticket
        self.reservations = ReservationService(gates, gates.open_journal, self.observe_owned_worker,
                                               self.confirm_teardown, self.confirm_live_reconciliation)
        self.lifecycle = DurableSnapshotLifecycle(self, self.reservations, lookup)
        self._physical = physical

    def observe_owned_worker(self, worker):
        _assert(worker is self.worker and any(item is worker for item in self.primitives.workers)
                and worker.assigned and not worker.resumed and not worker.unconfirmed,
                "exact_suspended_worker_observation")
        created = self.primitives._creation_time(worker.process)
        _assert(created == worker.creation_time, "suspended_creation_time_changed")
        return [int(worker.creation_info.pid), created]

    def _retired(self, worker):
        witness = self._retired_witness
        record = self.lifecycle._records.get(self.key)
        return (witness is not None and witness[0] is worker and worker is self.worker
                and worker.creation_time == witness[2]
                and record is not None and record.owner is witness[1]
                and record.owner._active == 0 and record.owner._closed_verified
                and worker.quiescent and not worker.unconfirmed
                and all(handle is not None and handle.closed for handle in (worker.process, worker.thread, worker.job))
                and self.read_set.released and not self.read_set.unconfirmed
                and self.pair.closed and not self.pair.operations)

    def _interrupted_retired(self, worker):
        witness = self._interrupted_witness
        if type(witness) is not _InterruptedRetirementWitness or witness.native.worker is not worker:
            return False
        attempt = witness.attempt
        if type(attempt) is not _InterruptedRetirement or attempt.delegate is not self:
            return False
        token, record = attempt.token, attempt.record
        stage = ("released" if record.phase is Phase.RELEASED else
                 "service" if token.pending is not None else "close")
        self.lifecycle._check_interrupted_attempt(attempt, stage)
        return _require_interrupted_witness(attempt, witness)

    def _never_started(self, protection):
        return (protection is self.read_set and self.worker is None and self.pair is None
                and self.channel is None and self.handshake is None and self.permit is None
                and not self._start_attempted and not self._resume_attempted
                and not protection.worker_reserved
                and not any(worker.read_set is protection for worker in self.primitives.workers))

    def _no_worker_retired(self, *, reconciling=False):
        witness = self._no_worker_witness
        if witness is None:
            return False
        record, token, protection = witness
        return (self.lifecycle._records.get(self.key) is record
                and self.lifecycle._tokens.get(self.key) is token
                and record.phase is (Phase.QUARANTINED if reconciling else Phase.RELEASED)
                and record.owner is None and record.permit is None
                and token.worker is None and self._never_started(protection)
                and protection.released and not protection.unconfirmed
                and all(handle.closed and not handle.unconfirmed for handle in protection.members))

    def _retirement_matches(self, worker):
        return self._no_worker_retired() if worker is None else self._retired(worker)

    def release_read(self, protection):
        record = self.lifecycle._records.get(self.key)
        _assert(record is not None and self._retired_witness is None and self._no_worker_witness is None,
                "single_observed_guard_retirement")
        if record.owner is None:
            token = self.lifecycle._token(self.key)
            with token._lock:
                _assert(record.phase is Phase.PROTECTED and record.permit is None
                        and record.protection is protection and self._never_started(protection)
                        and token.worker is None and token.phase == "RESERVED" and not token.revoked
                        and token.pending is None and token.generation == self.generation,
                        "current_no_worker_reservation_before_guard_retirement")
            _assert(self.primitives.release_read_set(protection) is True,
                    "actual_no_worker_guard_release")
            _assert(protection.released and not protection.unconfirmed
                    and all(handle.closed and not handle.unconfirmed for handle in protection.members),
                    "all_no_worker_guards_retired")
            self._no_worker_witness = (record, token, protection)
            self._completion = object()
            return True
        _assert(super().release_read(protection) is True, "actual_generated_guard_release")
        self._retired_witness = (self.worker, record.owner, self.worker.creation_time)
        self._completion = object()
        _assert(self._retired(self.worker), "retired_lifetime_observation")
        return True

    def completion_evidence(self, worker):
        _assert(self._completion is not None and self._retirement_matches(worker), "current_retired_lifetime_required")
        return self._completion

    def confirm_teardown(self, worker, evidence):
        _assert(evidence is not None and evidence is self._completion and self._retirement_matches(worker),
                "exact_current_completion_witness_required")
        self._completion = None
        if self._retired_clear_probe is not None:
            self._retired_clear_probe.interrupt_after_teardown(worker)
        return True

    def confirm_live_reconciliation(self, worker, physical, generation, head, attempt):
        _assert(physical == self._physical and generation == self.generation and type(head) is str
                and len(head) == 64 and type(attempt) is object and attempt not in self._reconciliation_attempts
                and (self._no_worker_retired(reconciling=True) if worker is None
                     else (self._retired(worker) or self._interrupted_retired(worker))),
                "current_exact_retired_generation_required")
        self._reconciliation_attempts.add(attempt)
        if self._retired_clear_probe is not None:
            self._retired_clear_probe.bind_service_attempt(worker, physical, generation, head, attempt)
        if self._interrupted_probe is not None:
            self._interrupted_probe.bind_service_attempt(worker, physical, generation, head, attempt)
        # Fresh inspection of exact retired guards and either never-started
        # state or the observed-dead lifetime; never a recorded-PID reopen/kill.
        return True

    def next_segment(self, worker, cursor):
        result = super().next_segment(worker, cursor)
        if self._interrupted_probe is not None and self._next_index == 2:
            self._interrupted_probe.interrupt_after_exchange(worker)
        return result

    def retire_interrupted_worker(self, attempt):
        # Only the exact manager-issued attempt may reach retained native
        # handles. This function never clears aggregate quarantine history.
        _assert(type(attempt) is _InterruptedRetirement and attempt.delegate is self
                and attempt.native.port is self and self._interrupted_witness is None,
                "single_interrupted_worker_retirement")
        manager, native = attempt.manager, attempt.native
        manager._assert_interrupted_active(attempt)
        primitives, worker, pair, read_set = native.primitives, native.worker, native.pair, native.protection
        _assert(pair.closed is False and read_set.released is False
                and all(h.closed is was_closed for h, value, kind, was_closed in native.handle_states),
                "confirmed_native_preflight_before_first_os_call")
        _assert(worker.creation_time == primitives._creation_time(native.process),
                "process_creation_time_changed")
        manager._assert_interrupted_active(attempt)
        _assert(type(pair.forced_stop_attempted) is bool, "exact_existing_pipe_stop_latch")
        if pair.forced_stop_attempted is False:
            pair.forced_stop_attempted = True
            try:
                pair.forced_process_stop_observed = (
                    primitives._stop_partial_worker(worker, 5000) is True)
            except BaseException as error:
                pair.forced_stop_error_type = type(error).__name__
                raise
        # A consumed pipe latch permits only fresh retained-handle observation;
        # worker.shutdown_started cannot authorize a second termination.
        manager._assert_interrupted_active(attempt)
        waited = primitives.api.call("WaitForSingleObject", primitives._owned(native.process), 5000)
        _assert(waited == 0, "process_exit_not_observed")
        manager._assert_interrupted_active(attempt)
        exit_code = primitives.api.ffi.c_uint32()
        primitives.api.checked("GetExitCodeProcess", primitives._owned(native.process),
                               primitives.api.ffi.byref(exit_code))
        _assert(type(exit_code.value) is int and 0 <= exit_code.value < 1 << 32
                and exit_code.value != 259, "process_still_active_or_invalid_exit")
        manager._assert_interrupted_active(attempt)
        accounting = primitives.api.structure("JOBOBJECT_BASIC_ACCOUNTING_INFORMATION")
        returned = primitives.api.ffi.c_uint32()
        primitives.api.checked("QueryInformationJobObject", primitives._owned(native.job), 1,
                               primitives.api.ffi.byref(accounting), primitives.api.ffi.sizeof(accounting),
                               primitives.api.ffi.byref(returned))
        _assert(returned.value == primitives.api.ffi.sizeof(accounting)
                and accounting.active_processes == 0, "job_active_processes_not_zero")
        manager._assert_interrupted_active(attempt)
        worker.quiescent = True
        self.exit_observation = {"child_native_exit": int(exit_code.value),
            "process_wait_observed": True, "job_active_processes": 0}

        # Preserve the original endpoint -> worker -> guard closure order.
        # Closed optional clients/duplicates were already checked at preflight.
        for handle in (native.client, native.server, native.thread, native.process, native.job) + tuple(reversed(native.members)):
            manager._assert_interrupted_active(attempt)
            if handle is not None and handle.closed is False:
                primitives._close(handle)
        manager._assert_interrupted_active(attempt)
        _assert(all(h.closed is True and h.unconfirmed is False
                    for h, value, kind, was_closed in native.handle_states),
                "every_retained_native_owner_confirmed_closed")
        pair.closed = True
        read_set.released = True
        witness = _InterruptedRetirementWitness(attempt, native,
            tuple(row[0] for row in native.handle_states), True, int(exit_code.value), 0)
        self._interrupted_witness = witness
        _require_interrupted_witness(attempt, witness)
        return witness

    def acquire_read(self, key):
        _assert((key.store_root, key.choice, key.revision) == (self.cwd, CHOICE, REVISION),
                "exact_generated_adapter_lease_key")
        return super().acquire_read(key)

    def generated_release(self, choice, caller_root, *, root_kind):
        _assert(type(choice) is str and choice == CHOICE and type(caller_root) is str
                and caller_root == self.cwd and root_kind == "reliability"
                and self.read_set is None and real_resolver.REAL_APPROVAL is None,
                "fixed_visible_generated_release_seam")
        self.authority_events.append("generated_release")
        return self.generated_authority, self.generated_trusted, self.generated_selected, self.cwd, self.cwd

    def generated_admit(self, trusted, choice, store, snapshot):
        record = self.lifecycle._records.get(self.key)
        _assert(trusted is self.generated_trusted and choice == CHOICE
                and type(store) is str and store == self.cwd and type(snapshot) is str and snapshot == self.cwd
                and record is not None and record.protection is self.read_set and record.phase is Phase.PROTECTED
                and record.permit is None and not self.read_set.unconfirmed and not self.read_set.released,
                "generated_admission_requires_actual_protection")
        self.authority_events.append("generated_admit")
        return self.generated_admission

    def generated_bind(self, admission):
        record = self.lifecycle._records.get(self.key)
        _assert(admission is self.generated_admission and record is not None
                and record.phase is Phase.NATIVE_RESERVED and record.permit is not None and record.owner is None
                and record.protection is self.read_set and len(self.read_set.members) == len(self.read_set.identities) == 5
                and all(not handle.closed for handle in self.read_set.members)
                and not self.read_set.unconfirmed and self.binding_calls == 0
                and real_resolver.REAL_APPROVAL is None, "generated_binding_requires_reserved_owned_handles")
        self.binding_calls += 1
        self.authority_events.append("generated_bind")
        return self.generated_binding

    def start_owned_worker(self, protection, permit, startup):
        raise RuntimeError("Split durable adapter startup is required")

    def create_suspended(self, protection, permit, startup):
        record = self._record(protection, permit)
        _assert(type(startup) is adapter._OwnedASRStart and startup.policy is self.adapter_profile
                and type(startup.policy) is adapter.RuntimeProfile and startup.usage == "reliability"
                and startup.binding is self.generated_binding and type(startup.binding) is real_resolver.LocalBinding
                and startup.binding.model_path == self.cwd and startup.binding.choice == CHOICE
                and startup.binding.revision == REVISION and startup.binding.manifest_sha256 == RECIPE_SHA256
                and startup.binding.files == FILES and startup.binding.local_files_only is True
                and startup.binding.constructor_called is False and startup.binding.real_runtime_approved is False
                and record.phase is Phase.NATIVE_RESERVED and record.permit is permit and self.binding_calls == 1
                and self.adapter_startup is None and real_resolver.REAL_APPROVAL is None,
                "exact_generated_owned_asr_start_before_process")
        self.adapter_startup = startup
        self.authority_events.append("owned_start_validated")
        _assert(type(self._contender) is OwnedContender and self._contender._bound_port is self
                and self.adapter_startup is startup,
                "exact_contender_after_adapter_start_validation")
        self._contender.run(self, protection, permit, startup, self.profile)
        # The inherited sentinel is only an internal generated transport check,
        # reached after the exact adapter startup and lease validation above.
        return super().create_suspended(protection, permit, self.profile)

    def finish_start(self, worker, permit, startup):
        _assert(startup is self.adapter_startup and worker is self.worker, "exact_adapter_finish_start")
        _assert(super().finish_start(worker, permit, self.profile) is True, "adoption_completion_required")
        try:
            self.handshake._owned_phase(True)
            payload = policy_payload(self.cwd, self.channel.binding)
            self.pipes.write_bytes(self.pair, self.channel.encode("next", payload), _remaining(self.pipes.clock))
            operation, response = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
            _assert(operation == "done" and _fixed(response, policy_ack(payload)), "generated_worker_start_binding_ack")
            self.handshake._owned_phase(True)
            self.adapter_start_payload, self.adapter_start_ack = payload, response
            self.authority_events.append("worker_start_bound")
            return True
        except BaseException:
            self.pipes._quarantine(self.pair)
            raise


@contextmanager
def _replace(owner, name, value):
    before = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, before)


@contextmanager
def generated_authority_seams(port):
    """Visible fake release/admission only; actual lifecycle/factory/adapter."""
    _assert(type(port) is GeneratedLifecyclePort and real_resolver.REAL_APPROVAL is None,
            "exact_generated_bridge_required")
    _assert(type(port.lifecycle) is DurableSnapshotLifecycle, "connected_durable_lifecycle_required")
    names = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
    _assert(adapter.resolver is real_resolver and all(getattr(adapter, name) is None for name in names),
            "real_adapter_services_must_be_unconfigured")
    original_release = adapter._release
    original_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
    proxy = SimpleNamespace(LocalBinding=real_resolver.LocalBinding, AdmissionRefusal=real_resolver.AdmissionRefusal,
        admit_snapshot=port.generated_admit, bind_for_constructor=port.generated_bind, REAL_APPROVAL=None)
    replacements = {"_release": port.generated_release, "resolver": proxy, "RUNTIME_PROFILE": port.adapter_profile,
                    "SNAPSHOT_LIFECYCLE": port.lifecycle, "RUNTIME_FACTORY": DurableOwnedRuntimeFactory(port.lifecycle)}
    primary = None
    try:
        with ExitStack() as stack:
            for name, value in replacements.items():
                stack.enter_context(_replace(adapter, name, value))
            yield
    except BaseException as error:
        primary = error
        raise
    finally:
        restored = (adapter._release is original_release and adapter.resolver is real_resolver
            and all(getattr(adapter, name) is None for name in names)
            and real_resolver.REAL_APPROVAL is None
            and (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == original_functions)
        if not restored:
            if primary is not None:
                BaseException.add_note(primary, "Generated authority seam restoration failed")
            else:
                raise AssertionError("Generated authority seam restoration failed")


def controller_flow(port):
    _assert(type(port) is GeneratedLifecyclePort, "exact_actual_adapter_generated_port")
    with generated_authority_seams(port):
        # The migrated adapter opens the actual lease, retains its permit,
        # constructs _OwnedASRStart and creates the actual owned factory/session.
        with adapter.faster_whisper_session(CHOICE, model_root=port.cwd) as facade:
            _assert(type(facade) is OperationFacade and facade._session._manager is port.lifecycle,
                    "actual_adapter_owned_facade")
            session = facade._session
            record = session._record
            _assert(record.protection is port.read_set and record.permit is port.permit
                    and record.owner is session and port.adapter_startup.policy is port.adapter_profile
                    and port.adapter_startup.binding is port.generated_binding and port.adapter_start_ack is not None,
                    "actual_start_permit_and_worker_ack")
            ticket = port.issue_generated_media_ticket(session)
            request = TranscribeRequest(ticket, language="en")
            stream = facade.transcribe(request)
            _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media", "begin_generated_transcription"],
                    "actual_adapter_start_keeps_segments_lazy")
            observed = [next(stream), next(stream)]
            try:
                next(stream)
            except StopIteration:
                pass
            else:
                raise AssertionError("Actual adapter generated stream must end")
            _assert(port._cursor_state == "eof" and all(not h.closed for h in port.read_set.members),
                    "actual_adapter_consumption_holds_read_guards")
            for path, expected in port.expectations:
                port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, True))
        # Only the adapter's actual finally performed close/join and lease exit.
        _assert(record.phase is Phase.RELEASED and session._closed_verified
                and port.read_set.released and port.pair.closed, "actual_adapter_finally_released_after_join")
    before = tuple(port.operation_events)
    operation_flow._require_session_closed(lambda: facade.transcribe(request))
    operation_flow._require_session_closed(lambda: next(stream))
    _assert(tuple(port.operation_events) == before, "actual_adapter_retained_references_have_no_wire_use")
    for path, expected in port.expectations:
        port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, False))
    return {"operation_mode": "drain", "actual_adapter_context": "faster_whisper_session",
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
            "operation_events": port.operation_events, "cursor_state": port._cursor_state, "cursor_start": port.start_observation,
            "authority_events": port.authority_events, "adapter_start": port.adapter_start_payload,
            "adapter_start_ack": port.adapter_start_ack, "adapter_globals_restored": True,
            "real_resolver_approval_unchanged_none": real_resolver.REAL_APPROVAL is None,
            "binding_calls": port.binding_calls, "actual_factory_and_permit": True,
            "adapter_owned_cleanup": True, "retained_facade_and_stream_refused": True,
            "lifecycle_phase": record.phase.value, "read_set_released": port.read_set.released,
            "pipe_retired": port.pair.closed, "exit_observation": port.exit_observation,
            "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


def _consume_one_then_cancel(port, stream):
    """One fixed cancel-case driver; stop/join remains the adapter's finally."""
    _assert(type(port.operation_mode) is str and port.operation_mode == "cancel",
            "exact_cancel_driver_mode")
    observed = [next(stream)]
    stream.close()
    _assert(port._cursor_state == "cancelled" and port._next_index == 1,
            "adapter_cancel_stops_before_second_generated_segment")
    before = tuple(port.operation_events)
    _assert(before == ("admit_generated_media", "begin_generated_transcription",
                       "next_generated_segment", "cancel_generated_cursor"),
            "exact_adapter_cancel_exchange_order")
    try:
        next(stream)
    except StopIteration:
        pass
    else:
        raise AssertionError("Cancelled adapter stream must not yield another segment")
    _assert(tuple(port.operation_events) == before, "cancelled_adapter_stream_has_no_wire_use")
    return observed


def _bound_cancel_journal(port):
    """Passive serial-probe observation, not a new lifecycle capability."""
    token = port.lifecycle._token(port.key)
    gates = port.reservations.gates
    attempt = gates.attempts.get(token.physical)
    _assert(token.phase == "WORKER_BOUND" and not token.revoked and token.pending is None
            and token.worker is port.worker and token.physical == port._physical
            and token.gate is not None and token.physical in gates._held
            and gates._held.get(token.physical) is token.gate
            and attempt is not None and attempt.token is token.gate
            and attempt.journal is token.journal and attempt.failure is None
            and attempt.handle is token.journal._stream.handle
            and not attempt.handle.closed and not attempt.handle.unconfirmed
            and token.journal.confirmed_bytes == token.raw
            and token.journal.confirmed_revision == token.journal._stream.write_revision
            and not token.journal._poisoned and not token.journal._stream.poisoned,
            "confirmed_bound_journal_held_during_cancel")
    return token, token.raw, attempt.handle


def controller_cancel_flow(port):
    _assert(type(port) is GeneratedLifecyclePort and type(port.operation_mode) is str
            and port.operation_mode == "cancel", "exact_actual_adapter_cancel_port")
    with generated_authority_seams(port):
        with adapter.faster_whisper_session(CHOICE, model_root=port.cwd) as facade:
            _assert(type(facade) is OperationFacade and facade._session._manager is port.lifecycle,
                    "actual_adapter_owned_facade")
            session = facade._session
            record = session._record
            _assert(record.protection is port.read_set and record.permit is port.permit
                    and record.owner is session and port.adapter_startup.policy is port.adapter_profile
                    and port.adapter_startup.binding is port.generated_binding and port.adapter_start_ack is not None,
                    "actual_start_permit_and_worker_ack")
            ticket = port.issue_generated_media_ticket(session)
            request = TranscribeRequest(ticket, language="en")
            stream = facade.transcribe(request)
            _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media", "begin_generated_transcription"],
                    "actual_adapter_start_keeps_segments_lazy")
            token_before, raw_before, handle_before = _bound_cancel_journal(port)
            observed = _consume_one_then_cancel(port, stream)
            token_after, raw_after, handle_after = _bound_cancel_journal(port)
            _assert(token_after is token_before and raw_after == raw_before and handle_after is handle_before
                    and record.phase is Phase.NATIVE_RUNNING and not session._closing
                    and not session._revoked and all(not h.closed for h in port.read_set.members),
                    "cancel_ack_does_not_clear_or_release_owned_lifetime")
            cancellation_journal = {"phase_before": "WORKER_BOUND", "phase_after": "WORKER_BOUND",
                "confirmed_before_sha256": hashlib.sha256(raw_before).hexdigest(),
                "confirmed_after_sha256": hashlib.sha256(raw_after).hexdigest(),
                "same_token_and_handle": True, "gate_held_before_stop": True,
                "journal_open_before_stop": True, "clear_deferred_until_adapter_finally": True}
            for path, expected in port.expectations:
                port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, True))
        # The existing adapter finally alone performs owned close/join and lease exit.
        _assert(record.phase is Phase.RELEASED and session._closed_verified
                and port.read_set.released and port.pair.closed, "actual_adapter_finally_released_after_join")
    before = tuple(port.operation_events)
    operation_flow._require_session_closed(lambda: facade.transcribe(request))
    operation_flow._require_session_closed(lambda: next(stream))
    _assert(tuple(port.operation_events) == before, "actual_adapter_retained_references_have_no_wire_use")
    for path, expected in port.expectations:
        port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, False))
    return {"operation_mode": "cancel", "actual_adapter_context": "faster_whisper_session",
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
            "operation_events": port.operation_events, "cursor_state": port._cursor_state, "cursor_start": port.start_observation,
            "cancellation_journal": cancellation_journal,
            "authority_events": port.authority_events, "adapter_start": port.adapter_start_payload,
            "adapter_start_ack": port.adapter_start_ack, "adapter_globals_restored": True,
            "real_resolver_approval_unchanged_none": real_resolver.REAL_APPROVAL is None,
            "binding_calls": port.binding_calls, "actual_factory_and_permit": True,
            "adapter_owned_cleanup": True, "retained_facade_and_stream_refused": True,
            "lifecycle_phase": record.phase.value, "read_set_released": port.read_set.released,
            "pipe_retired": port.pair.closed, "exit_observation": port.exit_observation,
            "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


def controller_retired_recovery_flow(port):
    _assert(type(port) is GeneratedLifecyclePort and type(port.operation_mode) is str
            and port.operation_mode == "cancel", "exact_actual_adapter_cancel_port")
    probe = port._retired_clear_probe
    _assert(type(probe) is _RetiredClearProbe and probe.port is port and probe.armed
            and not probe.fired, "fixed_recovery_probe_before_actual_adapter_entry")
    try:
        with generated_authority_seams(port):
            with adapter.faster_whisper_session(CHOICE, model_root=port.cwd) as facade:
                _assert(type(facade) is OperationFacade and facade._session._manager is port.lifecycle,
                        "actual_adapter_owned_facade")
                session = facade._session
                record = session._record
                _assert(record.protection is port.read_set and record.permit is port.permit
                        and record.owner is session and port.adapter_startup.policy is port.adapter_profile
                        and port.adapter_startup.binding is port.generated_binding and port.adapter_start_ack is not None,
                        "actual_start_permit_and_worker_ack")
                ticket = port.issue_generated_media_ticket(session)
                request = TranscribeRequest(ticket, language="en")
                stream = facade.transcribe(request)
                _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media", "begin_generated_transcription"],
                        "actual_adapter_start_keeps_segments_lazy")
                token_before, raw_before, handle_before = _bound_cancel_journal(port)
                observed = _consume_one_then_cancel(port, stream)
                token_after, raw_after, handle_after = _bound_cancel_journal(port)
                _assert(token_after is token_before and raw_after == raw_before and handle_after is handle_before
                        and record.phase is Phase.NATIVE_RUNNING and not session._closing
                        and not session._revoked and all(not h.closed for h in port.read_set.members),
                        "cancel_ack_does_not_clear_or_release_owned_lifetime")
                cancellation_journal = {"phase_before": "WORKER_BOUND", "phase_after": "WORKER_BOUND",
                    "confirmed_before_sha256": hashlib.sha256(raw_before).hexdigest(),
                    "confirmed_after_sha256": hashlib.sha256(raw_after).hexdigest(),
                    "same_token_and_handle": True, "gate_held_before_stop": True,
                    "journal_open_before_stop": True, "clear_deferred_until_adapter_finally": True}
                for path, expected in port.expectations:
                    port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, True))
    except KeyboardInterrupt as error:
        if error is not probe.error:
            raise
        # Both the actual adapter context and generated authority seams have
        # unwound before this exact expected object is recognized.
        probe.observe_interruption(error)
    else:
        raise AssertionError("Fixed retired-owner interruption was not observed")
    _assert(record is probe.record and session is probe.owner
            and record.phase is Phase.QUARANTINED and record.protection is None
            and session._revoked and session._closed_verified and session._active == 0,
            "same_retired_owner_quarantined_before_explicit_recovery")
    from snapshot_reservations import ReservationRefused
    try:
        port.reservations.complete(probe.token, None)
    except ReservationRefused as error:
        _assert(str(error) == "ordinary_completion_requires_unrevoked_owner",
                "ordinary_completion_has_exact_revocation_refusal")
    else:
        raise AssertionError("Ordinary completion cannot clear a revoked owner")
    _assert(probe.token.raw == probe.raw and not probe.handle.closed
            and probe.setup.flush_successes == 3, "ordinary_refusal_does_not_write_or_release")
    _assert(port.lifecycle.reconcile_retired_owner(session) is True,
            "manager_owned_retired_reconciliation_confirmed")
    _assert(record.phase is Phase.RELEASED and session._revoked and session._closed_verified
            and port.read_set.released and port.pair.closed and probe.close_observed,
            "same_manager_record_released_without_restoring_old_owner")
    recovery_observation = {"interruption_type": type(probe.error).__name__,
        "interruption_identity_match": probe.observed, "stage": "after_teardown_before_clear",
        "phases_before_recovery": ["INITIALIZED", "RESERVED", "WORKER_BOUND"],
        "before_recovery_sha256": hashlib.sha256(probe.raw).hexdigest(),
        "ordinary_completion_refused": True, "manager_reconciliation_confirmed": True,
        "owner_still_revoked": session._revoked, "token_still_revoked": probe.token.revoked,
        "same_owner_and_record": record is probe.record and session is probe.owner,
        "journal_open_until_recovery_clear": probe.close_observed,
        "native_interrupt_crash_or_restart_claim": False}
    before = tuple(port.operation_events)
    operation_flow._require_session_closed(lambda: facade.transcribe(request))
    operation_flow._require_session_closed(lambda: next(stream))
    _assert(tuple(port.operation_events) == before, "actual_adapter_retained_references_have_no_wire_use")
    for path, expected in port.expectations:
        port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, False))
    return {"operation_mode": "cancel", "actual_adapter_context": "faster_whisper_session",
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
            "operation_events": port.operation_events, "cursor_state": port._cursor_state, "cursor_start": port.start_observation,
            "cancellation_journal": cancellation_journal,
            "retired_owner_recovery": recovery_observation,
            "authority_events": port.authority_events, "adapter_start": port.adapter_start_payload,
            "adapter_start_ack": port.adapter_start_ack, "adapter_globals_restored": True,
            "real_resolver_approval_unchanged_none": real_resolver.REAL_APPROVAL is None,
            "binding_calls": port.binding_calls, "actual_factory_and_permit": True,
            "adapter_owned_cleanup": True, "retained_facade_and_stream_refused": True,
            "lifecycle_phase": record.phase.value, "read_set_released": port.read_set.released,
            "pipe_retired": port.pair.closed, "exit_observation": port.exit_observation,
            "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


class InterruptedCleanupCoordinator:
    """Explicit trusted cleanup coordinator after ASR adapter context unwinds.

    Validates quarantine state after interruption, verifies ordinary completion
    and ordinary retired-owner reconciliation refusals, and drives
    retire_and_reconcile_interrupted_owner.
    """
    def __init__(self, port):
        _assert(type(port) is GeneratedLifecyclePort, "exact_adapter_port_required")
        self.port = port
        self.observed_error = None
        self.quarantine_validated = False
        self.ordinary_completion_refused = False
        self.ordinary_reconciliation_refused = False
        self.interrupted_retirement_confirmed = False

    def coordinate(self, probe, session, record):
        _assert(type(probe) is _InterruptedOperationProbe and probe.port is self.port
                and probe is self.port._interrupted_probe and probe.fired,
                "fixed_fired_interruption_for_cleanup")
        original = probe.error
        self.observed_error = original
        try:
            if not probe.observed:
                probe.observe_interruption(original)
            return self._coordinate_confirmed(probe, session, record)
        except BaseException as cleanup:
            if cleanup is not original:
                BaseException.add_note(original, "Interrupted-owner cleanup remains unconfirmed: "
                                       + type(cleanup).__name__)
            raise original

    def _coordinate_confirmed(self, probe, session, record):
        port = self.port
        _assert(probe.observed and record is probe.record and session is probe.owner
                and record.phase is Phase.QUARANTINED and record.protection is port.read_set
                and session._revoked and not session._closed_verified and session._active == 0,
                "same_interrupted_owner_quarantined_before_explicit_recovery")
        self.quarantine_validated = True

        from snapshot_reservations import ReservationRefused
        try:
            port.reservations.complete(probe.token, None)
        except ReservationRefused as error:
            _assert(str(error) == "ordinary_completion_requires_unrevoked_owner",
                    "ordinary_completion_has_exact_revocation_refusal")
            self.ordinary_completion_refused = True
        else:
            raise AssertionError("Ordinary completion cannot clear a revoked owner")

        try:
            port.lifecycle.reconcile_retired_owner(session)
        except CleanupUnconfirmed:
            self.ordinary_reconciliation_refused = True
        else:
            raise AssertionError("Ordinary retired-owner reconciliation must refuse unretired owner")

        _assert(port.lifecycle.retire_and_reconcile_interrupted_owner(session) is True,
                "manager_owned_interrupted_retirement_confirmed")
        self.interrupted_retirement_confirmed = True
        return True


def controller_interrupted_recovery_flow(port):
    _assert(type(port) is GeneratedLifecyclePort and type(port.operation_mode) is str
            and port.operation_mode == "drain", "exact_actual_adapter_drain_port")
    probe = port._interrupted_probe
    _assert(type(probe) is _InterruptedOperationProbe and probe.port is port and probe.armed
            and not probe.fired, "fixed_interrupted_probe_before_actual_adapter_entry")
    coordinator = InterruptedCleanupCoordinator(port)
    try:
        with generated_authority_seams(port):
            with adapter.faster_whisper_session(CHOICE, model_root=port.cwd) as facade:
                _assert(type(facade) is OperationFacade and facade._session._manager is port.lifecycle,
                        "actual_adapter_owned_facade")
                session = facade._session
                record = session._record
                _assert(record.protection is port.read_set and record.permit is port.permit
                        and record.owner is session and port.adapter_startup.policy is port.adapter_profile
                        and port.adapter_startup.binding is port.generated_binding and port.adapter_start_ack is not None,
                        "actual_start_permit_and_worker_ack")
                ticket = port.issue_generated_media_ticket(session)
                request = TranscribeRequest(ticket, language="en")
                stream = facade.transcribe(request)
                _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media", "begin_generated_transcription"],
                        "actual_adapter_start_keeps_segments_lazy")
                observed = [next(stream)]
                next(stream)
    except KeyboardInterrupt as error:
        if error is not probe.error:
            raise
        # Both the actual adapter context and generated authority seams have
        # unwound before this exact expected object is recognized.
        coordinator.observed_error = error
    else:
        raise AssertionError("Fixed interrupted-owner interruption was not observed")

    try:
        coordinator.coordinate(probe, session, record)
        _assert(record.phase is Phase.RELEASED and session._revoked and session._closed_verified
                and port.read_set.released and port.pair.closed and probe.close_observed,
                "same_manager_record_released_without_restoring_old_owner")
    
        recovery_observation = {"interruption_type": type(probe.error).__name__,
            "interruption_identity_match": probe.observed, "stage": "after_second_segment_exchange",
            "phases_before_recovery": ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"],
            "quarantine_sha256": hashlib.sha256(probe.quarantine_raw).hexdigest(),
            "ordinary_completion_refused": coordinator.ordinary_completion_refused,
            "ordinary_reconciliation_refused": coordinator.ordinary_reconciliation_refused,
            "manager_reconciliation_confirmed": coordinator.interrupted_retirement_confirmed,
            "owner_still_revoked": session._revoked, "token_still_revoked": probe.token.revoked,
            "same_owner_and_record": record is probe.record and session is probe.owner,
            "journal_open_until_recovery_clear": probe.close_observed,
            "native_interrupt_crash_or_restart_claim": False}
    
        before = tuple(port.operation_events)
        operation_flow._require_session_closed(lambda: facade.transcribe(request))
        operation_flow._require_session_closed(lambda: next(stream))
        _assert(tuple(port.operation_events) == before, "actual_adapter_retained_references_have_no_wire_use")
        for path, expected in port.expectations:
            port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, False))
    
        return {"operation_mode": "drain", "actual_adapter_context": "faster_whisper_session",
                "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
                "operation_events": port.operation_events, "cursor_state": port._cursor_state, "cursor_start": port.start_observation,
                "interrupted_owner_recovery": recovery_observation,
                "authority_events": port.authority_events, "adapter_start": port.adapter_start_payload,
                "adapter_start_ack": port.adapter_start_ack, "adapter_globals_restored": True,
                "real_resolver_approval_unchanged_none": real_resolver.REAL_APPROVAL is None,
                "binding_calls": port.binding_calls, "actual_factory_and_permit": True,
                "adapter_owned_cleanup": True, "retained_facade_and_stream_refused": True,
                "lifecycle_phase": record.phase.value, "read_set_released": port.read_set.released,
                "pipe_retired": port.pair.closed, "exit_observation": port.exit_observation,
                "write_access_observations": port.observations,
                "parent_guards_held_through_exit": False,
                "adoption_case": port.case, "adoption_response": port.adoption_response,
                "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
                "controller_handshake_begun": port.handshake._begun, "model_calls": 0}
    except BaseException as cleanup:
        if cleanup is not probe.error:
            BaseException.add_note(probe.error, 'Interrupted-owner result/cleanup validation failed: ' + type(cleanup).__name__)
        raise probe.error


def _bound_worker_operations(pipes, pair, channel, adoption, fixed_root):
    _assert(real_resolver.REAL_APPROVAL is None, "child_real_model_authority_absent")
    original_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
    operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
    expected = policy_payload(fixed_root, channel.binding)
    _assert(operation == "next" and _fixed(payload, expected)
            and adoption.status == "adopted" and not adoption.materialization_started,
            "child_generated_adapter_policy_before_begin")
    acknowledgement = policy_ack(payload)
    pipes.write_bytes(pair, channel.encode("done", acknowledgement), _remaining(pipes.clock))
    result = operation_flow._worker_operations(pipes, pair, channel, adoption)
    _assert(real_resolver.REAL_APPROVAL is None
            and (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == original_functions,
            "child_real_resolver_authority_unchanged")
    return {**result, "adapter_start": payload, "adapter_start_ack": acknowledgement,
            "real_resolver_approval_unchanged_none": True, "real_resolver_functions_unchanged": True}


def child_flow(primitives, pipes, inherited_control_value, expected_child_source_sha256, fixed_root, fixed_case):
    """Same adoption prefix; one explicit generated startup binding before begin."""
    _assert(fixed_case == "positive", "generated_operation_positive_adoption_only")
    fixed_paths(fixed_root)
    pair = pipes.adopt_inherited_client(inherited_control_value)
    channel = None
    adoption = InheritedReadSetAdoption(primitives)
    try:
        binding, key = decode_private_bootstrap(pipes.read_private_bootstrap(pair, _remaining(pipes.clock)))
        _assert(binding.bootstrap_source_sha256 == expected_child_source_sha256
                and binding.namespace_sha256 == namespace_digest(), "fixed_operation_source_and_namespace")
        current = primitives.api.call("GetCurrentProcess")
        values = [primitives.api.structure("FILETIME") for _ in range(4)]
        primitives.api.checked("GetProcessTimes", current, *(primitives.api.ffi.byref(value) for value in values))
        creation = int(values[0].low) | int(values[0].high) << 32
        _assert(creation == binding.process_creation_time, "child_operation_creation_binding")
        channel = GenerationChannel(binding, key, "worker")
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        expected = {"generation": binding.generation_hex, "namespace_sha256": binding.namespace_sha256}
        _assert(operation == "challenge" and payload == expected, "operation_challenge_binding")
        pipes.write_bytes(pair, channel.encode("ready", expected), _remaining(pipes.clock))
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == "adopt_readset", "owned_readset_before_operation")
        adoption.adopt(payload, fixed_root, "positive", inherited_control_value, binding.manifest_sha256)
        _assert(adoption.status == "adopted" and adoption.inheritance_cleared == adoption.identities_checked == 5,
                "complete_adoption_before_operation")
        pipes.write_bytes(pair, channel.encode("readset_ready", operation_flow.adoption_flow.expected_adoption_response("positive")),
                          _remaining(pipes.clock))
        result = _bound_worker_operations(pipes, pair, channel, adoption, fixed_root)
        pipes.retire_endpoint(pair)
        return {"child_flow_return": 0, "adoption": adoption.receipt(), **result, "model_calls": 0}
    except BaseException:
        if adoption.read_set is not None:
            adoption.read_set.unconfirmed = True
        pipes._quarantine(pair)
        raise
    finally:
        if channel is not None:
            channel.revoke()


# Separate route: all preceding drain/cancel/recovery code remains unchanged.
import generated_worker_runtime_bridge as owner_bridge_module

_RETAINED_CHILD_RUNTIME_BRIDGE = None


def child_runtime_owner_flow(primitives, pipes, inherited_control_value,
                             expected_child_source_sha256, fixed_root, fixed_case):
    """One generated native child, using the actual bootstrap and owner.

    The fixed child process retains its bridge until exit, including failures.
    No controller frame supplies a class, factory, PCM decoder or model path.
    """
    global _RETAINED_CHILD_RUNTIME_BRIDGE
    _assert(_RETAINED_CHILD_RUNTIME_BRIDGE is None, 'single_child_runtime_bridge')
    _assert(fixed_case == 'positive', 'generated_operation_positive_adoption_only')
    fixed_paths(fixed_root)
    pair = pipes.adopt_inherited_client(inherited_control_value)
    channel = bridge = None
    first_error = None
    adoption = InheritedReadSetAdoption(primitives)
    try:
        binding, key = decode_private_bootstrap(pipes.read_private_bootstrap(pair, _remaining(pipes.clock)))
        _assert(binding.bootstrap_source_sha256 == expected_child_source_sha256
                and binding.namespace_sha256 == namespace_digest(), 'fixed_operation_source_and_namespace')
        current = primitives.api.call('GetCurrentProcess')
        values = [primitives.api.structure('FILETIME') for _ in range(4)]
        primitives.api.checked('GetProcessTimes', current, *(primitives.api.ffi.byref(value) for value in values))
        creation = int(values[0].low) | int(values[0].high) << 32
        _assert(creation == binding.process_creation_time, 'child_operation_creation_binding')
        channel = GenerationChannel(binding, key, 'worker')
        bridge = owner_bridge_module.GeneratedWorkerRuntimeBridge(channel, adoption)
        _RETAINED_CHILD_RUNTIME_BRIDGE = bridge
        ready = bridge.accept_challenge(pipes.read_frame(pair, _remaining(pipes.clock)))
        pipes.write_bytes(pair, ready, _remaining(pipes.clock))
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == 'adopt_readset', 'owned_readset_before_operation')
        adoption.adopt(payload, fixed_root, 'positive', inherited_control_value, binding.manifest_sha256)
        bridge.adopted()
        pipes.write_bytes(pair, channel.encode('readset_ready',
            operation_flow.adoption_flow.expected_adoption_response('positive')), _remaining(pipes.clock))

        _assert(real_resolver.REAL_APPROVAL is None, 'child_real_model_authority_absent')
        original_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot,
                              real_resolver.bind_for_constructor)
        operation, start_payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == 'next' and _fixed(start_payload, policy_payload(fixed_root, binding))
                and adoption.status == 'adopted' and not adoption.materialization_started,
                'child_generated_adapter_policy_before_begin')
        acknowledgement = policy_ack(start_payload)
        pipes.write_bytes(pair, channel.encode('done', acknowledgement), _remaining(pipes.clock))
        bridge.policy_acknowledged()
        initial = bridge.accept_initial_control(pipes.read_frame(pair, _remaining(pipes.clock)))
        if initial == 'begin':
            bridge.prepare_generated_factory()
            for _ in range(9):
                operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
                if operation == 'cancel':
                    _assert(payload == {}, 'fixed_generated_session_cancel')
                    cursor_state = bridge.state
                    break
                _assert(operation == 'next', 'fixed_generated_request_operation')
                frame = bridge.next_frame(payload)
                pipes.write_bytes(pair, frame, _remaining(pipes.clock))
            else:
                raise AssertionError('Generated operation frame bound exceeded')
        else:
            _assert(initial == 'cancel', 'fixed_initial_control')
            cursor_state = 'not_started'
        closed = bridge.prepare_closed_frame()
        pipes.write_bytes(pair, closed, _remaining(pipes.clock))
        bridge.closed_written()
        pipes.retire_endpoint(pair)
        _assert(real_resolver.REAL_APPROVAL is None and original_functions == (
            real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor),
            'child_real_resolver_authority_unchanged')
        receipt = bridge.receipt()
        return {'child_flow_return': 0, 'adoption': adoption.receipt(),
            'readback': bridge.readback, 'operation_events': list(bridge.actions),
            'cursor_state': cursor_state, 'produced_segments': bridge.index,
            'generated_duration_only': True, 'cursor_start': bridge.start_observation,
            'adapter_start': start_payload, 'adapter_start_ack': acknowledgement,
            'real_resolver_approval_unchanged_none': True, 'real_resolver_functions_unchanged': True,
            'runtime_owner': receipt, 'model_calls': 0}
    except BaseException as original:
        first_error = original
        if bridge is not None:
            bridge.close_preserving(original)
        if adoption.read_set is not None:
            adoption.read_set.unconfirmed = True
        try:
            pipes._quarantine(pair)
        except BaseException as cleanup:
            BaseException.add_note(original, 'Pipe quarantine remains unconfirmed: ' + type(cleanup).__name__)
        raise
    finally:
        if bridge is None and channel is not None:
            try:
                channel.revoke()
            except BaseException as cleanup:
                if first_error is None:
                    raise
                BaseException.add_note(first_error, 'Channel revocation remains unconfirmed: ' + type(cleanup).__name__)
