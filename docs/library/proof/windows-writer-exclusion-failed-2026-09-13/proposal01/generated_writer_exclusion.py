"""Fixed generated contender observation; no native or filesystem work on import."""
import generated_adapter_flow as adapter_flow
import generated_worker_flow as worker_flow
import generated_journal_setup as journal_setup
from snapshot_reservations import PhysicalSnapshot
from snapshot_lifecycle import Phase
from win32_worker_connection import KernelUnconfirmed


def require(value, reason):
    if not value:
        raise KernelUnconfirmed(reason)


class ContenderObservation:
    """Independent path/identity observation. It receives no creation ticket."""
    def __init__(self, primitives, monitor, fixed_root):
        self.primitives, self.monitor = primitives, monitor
        self.directories = journal_setup.GeneratedJournalSetup(primitives, monitor, fixed_root)
        self.physical = self.path = None
        self.attempted = False
        self.attempt_index = None
        self.unexpected_handle = None

    def allow_create(self, args):
        require(len(args) == 7 and args[3] is None and args[6] is None,
                "fixed_contender_create_shape")
        if args[0] in self.directories.directory_paths:
            return self.directories.allow_create(args)
        require(self.path is not None and args[0] == self.path and not self.attempted
                and args[1:3] == (journal_setup.JOURNAL_ACCESS, 0)
                and args[4:6] == (3, journal_setup.JOURNAL_FLAGS),
                "one_existing_physical_journal_attempt")
        self.attempted = True
        self.attempt_index = len(self.monitor.calls)
        return True

    def run(self):
        snapshot = self.directories._scope(self.directories.root)
        self.directories._scope(self.directories.registry_path)
        identity = snapshot.read_set.identities[-1]
        self.physical = PhysicalSnapshot(identity.volume_serial, identity.file_id.hex())
        self.path = self.directories.registry_path + "\\" + journal_setup.journal_port.gate_name(self.physical)
        value = self.monitor.call("CreateFileW", self.path, journal_setup.JOURNAL_ACCESS,
                                  0, None, 3, journal_setup.JOURNAL_FLAGS, None)
        error = self.monitor.ffi.get_last_error()
        invalid = value in (None, 0, self.monitor.ffi.c_void_p(-1).value)
        if not invalid:
            # Unexpected success is failed evidence. Retain this exact handle
            # until current-process death; no content or fallback write occurs.
            self.unexpected_handle = self.primitives._retain(value, "unexpected-contender-journal")
        require(self.attempted and invalid and error == 32, "contender_sharing_refusal_required")
        for read_set in reversed(self.directories.scopes):
            require(self.primitives.release_read_set(read_set) is True,
                    "contender_directory_retirement")
        require(all(scope.released and not scope.unconfirmed
                    and all(handle.closed for handle in scope.members)
                    for scope in self.directories.scopes), "contender_guards_retired")
        return {"status": "sharing_refused", "physical": self.physical.wire(),
                "journal_path": self.path, "attempt_count": 1, "open_call_index": self.attempt_index,
                "winerror": error, "valid_journal_handle_returned": False,
                "journal_content_reads": 0, "journal_writes": 0,
                "own_directory_guards_retired": True,
                "passive_inherited_guard_retired_by_process_exit_only": True,
                "semantic_choice": "independent-contender", "semantic_revision": "different-revision",
                "semantic_labels_are_authority": False, "model_calls": 0}


class OwnedContender:
    """One generated observation before the actual durable worker is created."""
    def __init__(self, primitives, monitor, primary_setup, bootstrap_path):
        self.primitives, self.monitor = primitives, monitor
        self.primary, self.bootstrap = primary_setup, bootstrap_path
        self.port = self.read_set = self.worker = None
        self.entered = self.creating = self.resuming = self.completed = False
        self.creation_returned = False
        self.start_index = None
        self.observation = None
        self.failure_type = None
        self.stop_attempted = False
        self.stop_wait_observed = None
        self.milestones = []

    def before_process(self, name, args):
        require(self.entered and not self.completed and self.port is not None,
                "active_owned_contender_scope")
        token, head = self.primary._confirmed_phase("RESERVED")
        require(token.worker is None and self.port.worker is None
                and self.primary.flush_successes == 2 and not self.primary.milestones,
                "primary_journal_remains_reserved_during_contender")
        if name == "CreateProcessW":
            require(self.creating and not self.resuming and self.worker is None
                    and len(self.primitives.workers) == self.start_index + 1,
                    "exact_contender_create_slot")
            pending = self.primitives.workers[-1]
            require(pending.read_set is self.read_set and len(pending.child_read_handles) == 1
                    and pending.child_control_handle is None
                    and len(self.read_set.members) == 1
                    and all(handle is not self.primary.created_handle for handle in self.read_set.members)
                    and self.read_set.identities == [self.port.expectations[0][1]],
                    "contender_inherits_only_its_passive_fixture_guard")
        elif name == "ResumeThread":
            require(self.resuming and not self.creating and self.worker is not None
                    and args[0] == self.primitives._owned(self.worker.thread),
                    "exact_contender_resume_slot")
        else:
            raise KernelUnconfirmed("Unexpected contender process operation")
        self.milestones.append({"api": name, "phase": "RESERVED", "head": head,
                                "call_index": len(self.monitor.calls), "flush_successes": 2})

    def run(self, port, protection, permit, profile):
        require(not self.entered and self.monitor.contender is self and port.worker is None
                and not port._start_attempted and not port._resume_attempted,
                "one_contender_before_primary_start")
        record = port._record(protection, permit)
        require(record.phase is Phase.NATIVE_RESERVED and profile is port.profile,
                "contender_requires_existing_primary_reservation")
        self.entered, self.port = True, port
        token, before_head = self.primary._confirmed_phase("RESERVED")
        before_raw = token.raw
        self.start_index = len(self.primitives.workers)
        require(self.start_index == 0, "contender_is_first_owned_process")
        try:
            # One distinct guard; primary journal/ancestor ownership is not
            # handed off or marked worker_reserved by this auxiliary lifetime.
            self.read_set = self.primitives.pin_exact_members((port.expectations[0],))
            self.creating = True
            try:
                self.worker = self.primitives.create_suspended_worker(self.read_set, port.executable,
                    ("-I", "-S", "-B", self.bootstrap, "contender"), port.cwd, port.environment)
                self.creation_returned = True
            finally:
                self.creating = False
            require(self.worker.read_set is self.read_set and self.worker.assigned
                    and len(self.worker.child_read_handles) == 1
                    and self.worker.child_control_handle is None,
                    "exact_contender_owned_lifetime")
            self.resuming = True
            try:
                self.primitives._resume_after_future_admission(self.worker)
            finally:
                self.resuming = False
            self.observation = worker_flow._observe_graceful_exit(self.primitives, self.worker, 0)
            require(all(not handle.closed for handle in self.read_set.members),
                    "contender_parent_guard_held_through_exit")
            self.primitives.close_quiescent_worker_handles(self.worker)
            require(self.primitives.release_read_set(self.read_set) is True,
                    "contender_guard_release_after_exit")
            current, after_head = self.primary._confirmed_phase("RESERVED")
            require(current is token and current.raw == before_raw and after_head == before_head
                    and not self.primary.created_handle.closed and self.primary.flush_successes == 2
                    and len(self.milestones) == 2,
                    "contender_cannot_change_primary_journal_or_owner")
            self.completed = True
        except BaseException as error:
            self.failure_type = type(error).__name__
            # A constructor failure already attempts exact native cleanup in
            # the preserved primitive. Recover its retained record, not a PID.
            if self.worker is None and len(self.primitives.workers) == self.start_index + 1:
                self.worker = self.primitives.workers[-1]
            if self.worker is not None and not self.worker.quiescent:
                if self.creation_returned:
                    self.stop_attempted = True
                    try:
                        self.stop_wait_observed = self.primitives._stop_partial_worker(self.worker, 5000)
                    except BaseException as cleanup:
                        error.add_note("Contender stop unconfirmed: " + type(cleanup).__name__)
                self.worker.unconfirmed = True
            if self.read_set is not None:
                self.read_set.unconfirmed = True
            raise

    def receipt(self):
        worker = self.worker
        return {"completed": self.completed, "failure_type": self.failure_type,
                "milestones": self.milestones, "exit_observation": self.observation,
                "stop_attempted": self.stop_attempted, "stop_wait_observed": self.stop_wait_observed,
                "guard_released": self.read_set is not None and self.read_set.released,
                "worker_handles_closed": worker is not None and all(h is not None and h.closed
                    for h in (worker.process, worker.thread, worker.job)),
                "worker_unconfirmed": worker is not None and worker.unconfirmed,
                "observed_pid": None if worker is None or worker.creation_info is None else int(worker.creation_info.pid),
                "observed_creation_time": None if worker is None else worker.creation_time,
                "passive_inherited_guard_count": 0 if worker is None else len(worker.child_read_handles),
                "inherited_control_handle_absent": worker is not None and worker.child_control_handle is None,
                "primary_journal_held_through_contender_exit": self.completed,
                "model_calls": 0}


class GeneratedExclusionPort(adapter_flow.GeneratedLifecyclePort):
    def bind_contender(self, contender):
        require(type(contender) is OwnedContender and not hasattr(self, "_contender"),
                "one_fixed_contender_port_binding")
        self._contender = contender

    def create_suspended(self, protection, permit, profile):
        self._contender.run(self, protection, permit, profile)
        return super().create_suspended(protection, permit, profile)
