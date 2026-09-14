"""Unexecuted actual-adapter/generated-worker bridge. No real authority.

Only a separately reviewed generated bootstrap may invoke this module. Import
executes definitions and hashes fixed generated text; it performs no I/O.
"""
from contextlib import contextmanager, ExitStack
from types import SimpleNamespace
import hashlib
import json
import asr_loading_adapter as adapter
import trusted_asr_resolver as real_resolver
import generated_operation_flow as operation_flow
from snapshot_lifecycle import OperationFacade, TranscribeRequest, Phase
from durable_lifecycle import DurableSnapshotLifecycle, DurableOwnedRuntimeFactory, _RetiredRecovery
from snapshot_reservations import ReservationService, SnapshotSemantics, decode_journal
import generated_journal_setup as journal_setup_module
from windows_reservation_port import WindowsGateRegistry
from owned_generation_protocol import GenerationChannel, decode_private_bootstrap
from inherited_readset import InheritedReadSetAdoption, GENERATED, NAMES, namespace_digest, fixed_paths
from generated_writer_exclusion import OwnedContender

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
        self._reconciliation_attempts = set()
        self._contender = None
        self._retired_clear_probe = None

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
                and (self._no_worker_retired(reconciling=True) if worker is None else self._retired(worker)),
                "current_exact_retired_generation_required")
        self._reconciliation_attempts.add(attempt)
        if self._retired_clear_probe is not None:
            self._retired_clear_probe.bind_service_attempt(worker, physical, generation, head, attempt)
        # Fresh inspection of exact retired guards and either never-started
        # state or the observed-dead lifetime; never a recorded-PID reopen/kill.
        return True

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
