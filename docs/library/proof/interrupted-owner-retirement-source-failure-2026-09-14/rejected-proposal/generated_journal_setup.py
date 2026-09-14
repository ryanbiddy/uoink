"""One generated retained journal setup; no native load or call at import."""
import hashlib
import windows_reservation_port as journal_port
import snapshot_reservations as reservations
from win32_worker_connection import ReadSet, FileIdentity, _absolute_local_path

CREATE_NEW = 1
DIRECTORY_ACCESS = 0x80
DIRECTORY_FLAGS = 0x02200000
JOURNAL_ACCESS = 0xc0000000
JOURNAL_FLAGS = 0x80200000
MAX_EVENTS = 256


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


class GeneratedJournalSetup:
    def __init__(self, primitives, monitor, fixed_root):
        _absolute_local_path(fixed_root)
        self.primitives, self.monitor, self.root = primitives, monitor, fixed_root
        self.registry_path = fixed_root + "\\registry"
        self.directory_paths = tuple(dict.fromkeys(journal_port._prefixes(fixed_root)
                                                   + journal_port._prefixes(self.registry_path)))
        require(len(self.directory_paths) <= 16, "fixed_generated_directory_depth")
        self.scopes = []
        self.registry_scope = self.snapshot_scope = None
        self.journal_path = self.created_handle = self.journal_identity = None
        self.physical = self.gates = self.port = self.creation_ticket = None
        self.creating = self.create_call_used = self.create_succeeded = False
        self.opened = False
        self.events, self.milestones = [], []
        self.flush_successes = 0
        self._recovery_probe = None
        self._interrupted_probe = None

    def _scope(self, path):
        read_set = ReadSet()
        self.primitives.read_sets.append(read_set)
        self.scopes.append(read_set)  # Retain partial setup before native work.
        for member in journal_port._prefixes(path):
            value = self.monitor.call("CreateFileW", member, DIRECTORY_ACCESS, 1, None,
                                      3, DIRECTORY_FLAGS, None)
            handle = self.primitives._retain(value, "read-member")
            read_set.members.append(handle)
            identity = self.primitives.identity(handle)
            require(type(identity) is FileIdentity and identity.directory
                    and identity.final_path.casefold() == ("\\\\?\\" + member).casefold(),
                    "retained_generated_directory_identity")
            read_set.identities.append(identity)
        return journal_port.DirectoryScope(path, read_set)

    def open(self):
        require(not self.opened and not self.scopes, "single_generated_registry_setup")
        self.opened = True
        self.snapshot_scope = self._scope(self.root)
        self.registry_scope = self._scope(self.registry_path)
        snapshot = self.snapshot_scope.read_set.identities[-1]
        self.physical = reservations.PhysicalSnapshot(snapshot.volume_serial, snapshot.file_id.hex())
        self.journal_path = self.registry_path + "\\" + journal_port.gate_name(self.physical)
        self.creating = True
        try:
            value = self.monitor.call("CreateFileW", self.journal_path, JOURNAL_ACCESS, 0, None,
                                      CREATE_NEW, JOURNAL_FLAGS, None)
            self.created_handle = self.primitives._retain(value, "reservation-journal")
        finally:
            self.creating = False
        self.journal_identity = self.primitives.identity(self.created_handle)
        require(self.create_succeeded and self.journal_identity.size == 0
                and not self.journal_identity.directory and self.journal_identity.links == 1
                and self.journal_identity.final_path.casefold() == ("\\\\?\\" + self.journal_path).casefold(),
                "exact_empty_created_journal")
        self.gates = journal_port.WindowsGateRegistry(self.primitives, self.registry_scope,
                                                      self.confirm_creation, lambda *args: False)
        binding = journal_port.JournalBinding(self.physical, self.snapshot_scope, self.journal_identity)
        self.gates.bind_snapshot(binding)
        self.gates.stage_created_handle(binding, self.created_handle)
        self.creation_ticket = self.gates.register_generated_creation(self.physical, self.created_handle)
        return self

    def confirm_creation(self, physical, evidence):
        return (self.create_succeeded and evidence is self.created_handle and physical == self.physical
                and not self.created_handle.closed and not self.created_handle.unconfirmed
                and self.primitives.identity(self.created_handle) == self.journal_identity
                and self.journal_identity.size == 0)

    def connect(self, port):
        require(self.port is None and self.gates is not None and port.primitives is self.primitives
                and port.cwd == self.root, "exact_generated_durable_port")
        self.port = port
        port.connect_durable_registry(self.gates, self.physical, self.creation_ticket)

    def _journal_handle(self, value):
        handle = self.created_handle
        return (handle is not None and handle.value == value and not handle.closed and not handle.unconfirmed
                and any(item is handle for item in self.primitives.handles))

    def allow_create(self, args):
        require(len(args) == 7 and args[3] is None and args[6] is None, "fixed_generated_create_shape")
        if args[0] in self.directory_paths:
            require(args[1:3] == (DIRECTORY_ACCESS, 1) and args[4:6] == (3, DIRECTORY_FLAGS),
                    "fixed_retained_directory_open")
            return True
        if args[0] == self.journal_path:
            require(self.creating and not self.create_call_used and self.created_handle is None
                    and args[1:3] == (JOURNAL_ACCESS, 0) and args[4:6] == (CREATE_NEW, JOURNAL_FLAGS),
                    "one_retained_generated_journal_creation")
            self.create_call_used = True
            return True
        return False

    def journal_scope(self, name, args):
        if name not in ("SetFilePointerEx", "ReadFile", "WriteFile", "FlushFileBuffers"):
            return False
        if not args or not self._journal_handle(args[0]):
            require(name not in ("SetFilePointerEx", "FlushFileBuffers"), "controller_journal_owner_required")
            require(name not in ("ReadFile", "WriteFile") or len(args) != 5 or args[4] is not None,
                    "controller_synchronous_io_requires_journal")
            return False
        ffi = self.monitor.ffi
        if name == "SetFilePointerEx":
            require(len(args) == 4 and type(args[1]) is int and 0 <= args[1] <= reservations.MAX_JOURNAL
                    and args[3] == 0 and type(getattr(args[2], "_obj", None)) is ffi.c_int64,
                    "bounded_retained_journal_seek")
        elif name in ("ReadFile", "WriteFile"):
            require(len(args) == 5 and args[4] is None and type(args[2]) is int and 0 < args[2] <= 65536
                    and isinstance(args[1], ffi.Array) and args[1]._type_ is ffi.c_char
                    and ffi.sizeof(args[1]) == args[2]
                    and type(getattr(args[3], "_obj", None)) is ffi.c_uint32,
                    "bounded_retained_journal_io")
        else:
            require(len(args) == 1, "exact_retained_journal_flush")
        return True

    def _confirmed_phase(self, expected):
        require(self.port is not None and self.gates is not None, "connected_durable_start")
        token = self.port.lifecycle._token(self.port.key)
        rows, head = reservations.decode_journal(token.raw)
        attempt = self.gates.attempts.get(self.physical)
        require(attempt is not None and attempt.handle is self.created_handle and attempt.journal is token.journal
                and token.journal.confirmed_bytes == token.raw
                and token.journal.confirmed_revision == token.journal._stream.write_revision
                and not token.journal._poisoned and not token.journal._stream.poisoned
                and rows[-1]["phase"] == expected and not token.revoked,
                "current_confirmed_journal_phase")
        return token, head

    def before_process(self, name):
        if name not in ("CreateProcessW", "ResumeThread"):
            return
        expected = "RESERVED" if name == "CreateProcessW" else "WORKER_BOUND"
        token, head = self._confirmed_phase(expected)
        if name == "CreateProcessW":
            require(token.worker is None and self.flush_successes == 2 and not self.milestones,
                    "reserved_before_generated_process")
        else:
            require(token.worker is self.port.worker and self.flush_successes == 3
                    and [event["api"] for event in self.milestones] == ["CreateProcessW"],
                    "bound_before_generated_resume")
        self.milestones.append({"api": name, "phase": expected, "head": head,
                                "call_index": len(self.monitor.calls), "flush_successes": self.flush_successes})

    def before_close(self, args):
        if args and self._journal_handle(args[0]):
            token, head = self._confirmed_phase("CLEARED")
            require(token.phase == "CLEAR_PENDING" and self.port._retired(token.worker)
                    and self.flush_successes == 4, "retired_native_lifetime_before_journal_close")
            self.milestones.append({"api": "CloseHandle", "phase": "CLEARED", "head": head,
                                    "call_index": len(self.monitor.calls), "flush_successes": self.flush_successes})

    def before_recovery_close(self, args):
        # Separate observer: ordinary before_close still requires an unrevoked
        # token and is never relaxed for this deliberately interrupted case.
        if args and self._journal_handle(args[0]):
            from generated_adapter_flow import _RetiredClearProbe
            probe = self._recovery_probe
            require(type(probe) is _RetiredClearProbe and probe.setup is self
                    and probe.port is self.port, "fixed_recovery_close_observer")
            token = self.port.lifecycle._token(self.port.key)
            head = probe.before_recovery_close(token)
            self.milestones.append({"api": "CloseHandle", "phase": "CLEARED", "head": head,
                                    "call_index": len(self.monitor.calls), "flush_successes": self.flush_successes})

    def before_interrupted_close(self, args):
        # Separate observer for interrupted-owner route with 5 frames.
        if args and self._journal_handle(args[0]):
            from generated_adapter_flow import _InterruptedOperationProbe
            probe = self._interrupted_probe
            require(type(probe) is _InterruptedOperationProbe and probe.setup is self
                    and probe.port is self.port, "fixed_interrupted_close_observer")
            token = self.port.lifecycle._token(self.port.key)
            head = probe.before_interrupted_close(token)
            self.milestones.append({"api": "CloseHandle", "phase": "CLEARED", "head": head,
                                    "call_index": len(self.monitor.calls), "flush_successes": self.flush_successes})

    def complete_recovery(self):
        from generated_adapter_flow import _RetiredClearProbe
        from snapshot_lifecycle import Phase
        probe = self._recovery_probe
        require(type(probe) is _RetiredClearProbe and probe.setup is self and probe.observed
                and probe.close_observed and probe.service_attempt is not None,
                "observed_retired_recovery_before_completion")
        token, owner, record = probe.token, probe.owner, probe.record
        rows, head = reservations.decode_journal(token.raw)
        require(self.port.lifecycle._records.get(self.port.key) is record and record.owner is owner
                and record.phase is Phase.RELEASED and owner._revoked is True
                and owner._closed_verified is True and owner._active == 0
                and self.port.key not in self.port.lifecycle._retired_recoveries
                and self.port.lifecycle._token(self.port.key) is token and token.revoked is True
                and head == probe.close_head and self.port._retired(probe.worker),
                "manager_published_same_retired_owner_after_recovery")
        # Original completion assertions still check all four phases, confirmed
        # gate/handle retirement and ancestor release. They contain no token
        # unrevocation requirement and remain unchanged.
        result = self.complete()
        return {**result, "explicit_retired_owner_recovery": True,
                "old_owner_still_revoked": owner._revoked,
                "old_token_still_revoked": token.revoked,
                "injected_interrupt_type": type(probe.error).__name__,
                "injected_interrupt_identity_observed": probe.observed,
                "injected_stage": "after_teardown_before_clear",
                "before_clear_phases": ["INITIALIZED", "RESERVED", "WORKER_BOUND"],
                "before_clear_sha256": hashlib.sha256(probe.raw).hexdigest(),
                "same_manager_and_service_attempt": probe.close_observed,
                "fresh_process_query_after_retirement": False,
                "os_interrupt_or_crash_claim": False}

    def complete_interrupted_recovery(self):
        from generated_adapter_flow import _InterruptedOperationProbe
        from snapshot_lifecycle import Phase
        probe = self._interrupted_probe
        require(type(probe) is _InterruptedOperationProbe and probe.setup is self and probe.observed
                and probe.close_observed and probe.service_attempt is not None,
                "observed_interrupted_recovery_before_completion")
        token, owner, record = probe.token, probe.owner, probe.record
        rows, head = reservations.decode_journal(token.raw)
        require(self.port.lifecycle._records.get(self.port.key) is record and record.owner is owner
                and record.phase is Phase.RELEASED and owner._revoked is True
                and owner._closed_verified is True and owner._active == 0
                and self.port.key not in self.port.lifecycle._interrupted_retirements
                and self.port.lifecycle._token(self.port.key) is token and token.revoked is True
                and head == probe.close_head
                and [row["phase"] for row in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"]
                and token.phase == "CLEARED" and self.physical not in self.gates._held
                and self.physical not in self.gates.attempts and self.created_handle.closed
                and not self.created_handle.unconfirmed and self.flush_successes == 5
                and [event["api"] for event in self.milestones] == ["CreateProcessW", "ResumeThread", "CloseHandle"],
                "complete_interrupted_generated_journal")
        for read_set in reversed(self.scopes):
            require(self.primitives.release_read_set(read_set) is True, "retire_registry_ancestor_guards")
        require(all(scope.released and not scope.unconfirmed and all(h.closed for h in scope.members)
                    for scope in self.scopes), "all_directory_guards_retired")
        return {"physical": self.physical.wire(), "journal_path": self.journal_path,
                "journal_bytes": len(token.raw), "journal_sha256": hashlib.sha256(token.raw).hexdigest(),
                "journal_hex": token.raw.hex(), "head": head, "phases": [row["phase"] for row in rows],
                "flush_successes": self.flush_successes, "milestones": self.milestones,
                "io_events": self.events, "creation_handle_transferred_without_close": True,
                "journal_handle_closed": self.created_handle.closed, "directory_guards_retired": True,
                "explicit_interrupted_owner_recovery": True,
                "old_owner_still_revoked": owner._revoked,
                "old_token_still_revoked": token.revoked,
                "injected_interrupt_type": type(probe.error).__name__,
                "injected_interrupt_identity_observed": probe.observed,
                "injected_stage": "after_next_segment_before_return",
                "before_recovery_phases": ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"],
                "before_recovery_sha256": hashlib.sha256(probe.raw).hexdigest(),
                "same_manager_and_service_attempt": probe.close_observed,
                "fresh_process_query_after_retirement": False,
                "native_power_loss_or_restart_claim": False}

    def observe(self, name, args, result, is_journal):
        if name == "CreateFileW" and args[0] == self.journal_path:
            self.create_succeeded = result not in (None, 0, self.monitor.ffi.c_void_p(-1).value)
        if not is_journal:
            return
        require(len(self.events) < MAX_EVENTS, "bounded_journal_events")
        event = {"api": name, "call_index": len(self.monitor.calls) - 1, "result": bool(result)}
        if name == "SetFilePointerEx":
            event.update(requested_offset=args[1], actual_offset=args[2]._obj.value)
        elif name in ("ReadFile", "WriteFile"):
            event.update(requested_bytes=args[2], actual_bytes=args[3]._obj.value)
        elif result:
            self.flush_successes += 1
        self.events.append(event)

    def complete(self):
        require(self.port is not None, "connected_completion")
        token = self.port.lifecycle._token(self.port.key)
        rows, head = reservations.decode_journal(token.raw)
        require([row["phase"] for row in rows] == ["INITIALIZED", "RESERVED", "WORKER_BOUND", "CLEARED"]
                and token.phase == "CLEARED" and self.physical not in self.gates._held
                and self.physical not in self.gates.attempts and self.created_handle.closed
                and not self.created_handle.unconfirmed and self.flush_successes == 4
                and [event["api"] for event in self.milestones] == ["CreateProcessW", "ResumeThread", "CloseHandle"],
                "complete_normal_generated_journal")
        for read_set in reversed(self.scopes):
            require(self.primitives.release_read_set(read_set) is True, "retire_registry_ancestor_guards")
        require(all(scope.released and not scope.unconfirmed and all(h.closed for h in scope.members)
                    for scope in self.scopes), "all_directory_guards_retired")
        return {"physical": self.physical.wire(), "journal_path": self.journal_path,
                "journal_bytes": len(token.raw), "journal_sha256": hashlib.sha256(token.raw).hexdigest(),
                "journal_hex": token.raw.hex(), "head": head, "phases": [row["phase"] for row in rows],
                "flush_successes": self.flush_successes, "milestones": self.milestones,
                "io_events": self.events, "creation_handle_transferred_without_close": True,
                "journal_handle_closed": self.created_handle.closed, "directory_guards_retired": True,
                "native_power_loss_or_restart_claim": False}
