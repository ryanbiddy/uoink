"""Unexecuted generated controls against the actual retained-handle port."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from win32_worker_connection import FileIdentity, HandleRecord, ReadSet
from windows_reservation_port import (WindowsGateRegistry, DirectoryScope, JournalBinding,
    gate_name, real_windows_reservation_service, MAX_CHUNK)
from snapshot_reservations import PhysicalSnapshot, SnapshotSemantics, ReservationService, ReservationRefused, encode_next, decode_journal
from reservation_file_port import PersistenceUnconfirmed
from durable_lifecycle import DurableOwnedRuntimeFactory
from snapshot_lifecycle import Phase, SessionClosed
from test_reservations import ConnectionContracts


class Cell:
    def __init__(self, value=0):
        self.value = value


class Buffer:
    def __init__(self, value, count=None):
        self.data = bytearray(value if type(value) is bytes else b"\0" * value)
        if count is not None:
            assert len(self.data) == count
    @property
    def raw(self):
        return bytes(self.data)


class FakeFFI:
    c_uint32 = Cell
    c_int64 = Cell
    def __init__(self):
        self.error = 0
    def c_void_p(self, value=0):
        return Cell(value & ((1 << 64) - 1))
    def byref(self, value):
        return value
    def create_string_buffer(self, value, count=None):
        return Buffer(value, count)
    def get_last_error(self):
        return self.error


class Disk:
    def __init__(self):
        self.data = bytearray()
        self.owner = None


class FakeAPI:
    def __init__(self, owner, disk):
        self.owner, self.disk, self.ffi = owner, disk, FakeFFI()
        self.calls = []
        self.seek_wrong = self.read_wrong = self.write_wrong = self.fail_sync = False
        self.short_write = MAX_CHUNK
        self.position = 0

    def call(self, name, *args):
        self.calls.append((name, args))
        if name == "CreateFileW":
            path, access, share, security, disposition, flags, template = args
            assert path == self.owner.journal_path and access == 0xc0000000 and share == 0
            assert security is None and disposition == 3 and flags == 0x80200000 and template is None
            if self.disk.owner is not None:
                self.ffi.error = 32
                return (1 << 64) - 1
            value = self.owner.next_handle
            self.owner.next_handle += 1
            self.disk.owner = (self, value)
            return value
        handle = args[0]
        assert self.disk.owner == (self, handle)
        if name == "SetFilePointerEx":
            _, offset, output, origin = args
            assert origin == 0
            self.position = offset
            output.value = offset + int(self.seek_wrong)
            return 1
        if name == "ReadFile":
            _, output, requested, actual, overlapped = args
            assert overlapped is None
            value = self.disk.data[self.position:self.position + requested]
            output.data[:len(value)] = value
            actual.value = requested + 1 if self.read_wrong else len(value)
            self.position += len(value)
            return 1
        if name == "WriteFile":
            _, source, requested, actual, overlapped = args
            assert overlapped is None
            count = min(self.short_write, requested)
            self.disk.data[self.position:self.position + count] = source.raw[:count]
            self.position += count
            actual.value = requested + 1 if self.write_wrong else count
            return 1
        if name == "FlushFileBuffers":
            self.ffi.error = 5 if self.fail_sync else 0
            return 0 if self.fail_sync else 1
        raise AssertionError("Unexpected fake native call: " + name)


class FakePrimitives:
    def __init__(self, disk):
        self.read_sets, self.handles, self.metadata = [], [], {}
        self.next_handle = 100
        self.api = FakeAPI(self, disk)
        self.identity_failure = self.close_failure = False
        self.journal_path = self.journal_identity = None
    def _retain(self, value, kind):
        record = HandleRecord(value, kind)
        self.handles.append(record)
        return record
    def _owned(self, handle):
        assert any(item is handle for item in self.handles)
        assert not handle.closed and not handle.unconfirmed
        return handle.value
    def _close(self, handle):
        value = self._owned(handle)
        self.api.calls.append(("CloseHandle", (value,)))
        if self.close_failure:
            handle.unconfirmed = True
            raise OSError("injected close uncertainty")
        if handle.kind == "reservation-journal":
            assert self.api.disk.owner == (self.api, value)
            self.api.disk.owner = None
        handle.closed = True
    def identity(self, handle):
        value = self._owned(handle)
        if self.identity_failure:
            raise OSError("injected identity failure")
        if handle.kind == "reservation-journal":
            return replace(self.journal_identity, size=len(self.api.disk.data))
        return self.metadata[value]
    def scope(self, path, identifiers):
        components = [path[:3]] + [path[:3] + "\\".join(path[3:].split("\\")[:n])
                                  for n in range(1, len(path[3:].split("\\")) + 1)]
        assert len(components) == len(identifiers)
        read_set = ReadSet()
        self.read_sets.append(read_set)
        for component, identifier in zip(components, identifiers):
            handle = self._retain(self.next_handle, "read-member")
            self.next_handle += 1
            observed = FileIdentity("\\\\?\\" + component, 7, bytes([identifier]) * 16, 0, 1, True)
            self.metadata[handle.value] = observed
            read_set.members.append(handle)
            read_set.identities.append(observed)
        return DirectoryScope(path, read_set)


class Fixture:
    def __init__(self, disk=None):
        self.disk = disk or Disk()
        self.primitives = FakePrimitives(self.disk)
        self.registry = self.primitives.scope(r"E:\generated\registry", (1, 2, 3))
        self.snapshot = self.primitives.scope(r"E:\generated\snapshot", (1, 2, 4))
        self.physical = PhysicalSnapshot(7, (bytes([4]) * 16).hex())
        self.semantic = SnapshotSemantics(7, self.physical.file_id, "choice", "revision", "a" * 64)
        self.created = object()
        self.primitives.journal_path = self.registry.path + "\\" + gate_name(self.physical)
        self.primitives.journal_identity = FileIdentity("\\\\?\\" + self.primitives.journal_path,
                                                       7, bytes([9]) * 16, 0, 1, False)
        self.gates = WindowsGateRegistry(self.primitives, self.registry,
            lambda physical, proof: physical == self.physical and proof is self.created,
            lambda *args: False)
        self.binding = JournalBinding(self.physical, self.snapshot, self.primitives.journal_identity)
        self.gates.bind_snapshot(self.binding)
    def opened(self):
        token = self.gates.acquire(self.physical)
        return token, self.gates.open_journal(self.physical)
    def clean(self):
        token, journal = self.opened()
        raw = journal.append_confirmed(b"", encode_next(b"", self.physical, self.semantic, None, "INITIALIZED"))
        return token, journal, decode_journal(raw)[1]


class WindowsPortContracts(unittest.TestCase):
    def test_actual_port_roundtrip_and_release_order(self):
        f = Fixture()
        token, journal, head = f.clean()
        self.assertEqual(journal.read_all(), bytes(f.disk.data))
        self.assertIn("FlushFileBuffers", [row[0] for row in f.primitives.api.calls])
        before = len(f.primitives.api.calls)
        f.gates.release(f.physical, token, head)
        self.assertEqual([row[0] for row in f.primitives.api.calls[before:]], ["CloseHandle"])
        self.assertIsNone(f.disk.owner)
        self.assertNotIn(f.physical, f.gates._held)

    def test_shared_fake_disk_excludes_second_process_registry(self):
        f = Fixture()
        token, journal = f.opened()
        peer = Fixture(f.disk)
        with self.assertRaisesRegex(ReservationRefused, "native_physical_snapshot_busy"):
            peer.gates.acquire(peer.physical)
        self.assertNotIn(peer.physical, peer.gates._held)
        self.assertEqual(peer.gates._known_clean, {})
        self.assertIs(f.gates._held[f.physical], token)
        self.assertEqual(bytes(f.disk.data), b"")

    def test_duplicate_physical_registration_refuses(self):
        f = Fixture()
        with self.assertRaisesRegex(PersistenceUnconfirmed, "duplicate_physical_registration"):
            f.gates.bind_snapshot(f.binding)
        self.assertEqual(len(f.gates.bindings), 1)

    def test_missing_ancestor_or_changed_snapshot_refuses_before_open(self):
        for fault in ("missing", "changed"):
            with self.subTest(fault=fault):
                f = Fixture()
                if fault == "missing":
                    f.snapshot.read_set.members.pop(0)
                else:
                    handle = f.snapshot.read_set.members[-1]
                    f.primitives.metadata[handle.value] = replace(f.primitives.metadata[handle.value], file_id=b"x" * 16)
                with self.assertRaises(PersistenceUnconfirmed):
                    f.gates.acquire(f.physical)
                self.assertEqual(f.primitives.api.calls, [])
                self.assertIn(f.physical, f.gates._held)
                self.assertIsNone(f.disk.owner)

    def test_short_native_writes_complete_exact_journal(self):
        f = Fixture()
        f.primitives.api.short_write = 3
        token, journal, head = f.clean()
        self.assertGreater(sum(name == "WriteFile" for name, args in f.primitives.api.calls), 1)
        self.assertEqual(decode_journal(bytes(f.disk.data))[1], head)
        f.gates.release(f.physical, token, head)

    def test_sync_failure_keeps_exclusive_handle_and_poison(self):
        f = Fixture()
        token, journal, head = f.clean()
        f.primitives.api.fail_sync = True
        with self.assertRaises(OSError):
            journal.confirm_current(bytes(f.disk.data))
        with self.assertRaises(PersistenceUnconfirmed):
            f.gates.release(f.physical, token, head)
        self.assertIsNotNone(f.disk.owner)
        self.assertFalse(f.gates.attempts[f.physical].handle.closed)

    def test_observed_result_or_identity_failure_invalidates_clean_cache(self):
        for fault in ("seek", "read", "identity", "flush", "journal_read"):
            with self.subTest(fault=fault):
                f = Fixture()
                token, journal, head = f.clean()
                stream = f.gates.attempts[f.physical].stream
                if fault == "seek":
                    f.primitives.api.seek_wrong = True
                    action = lambda: stream.seek(0)
                elif fault == "read":
                    f.primitives.api.read_wrong = True
                    action = lambda: stream.read(1)
                else:
                    f.primitives.identity_failure = True
                    action = {"identity": stream.identity, "flush": stream.flush, "journal_read": journal.read_all}[fault]
                with self.assertRaises((PersistenceUnconfirmed, OSError)):
                    action()
                f.primitives.identity_failure = False
                self.assertTrue(stream.poisoned)
                with self.assertRaises(PersistenceUnconfirmed):
                    f.gates.release(f.physical, token, head)
                self.assertFalse(f.gates.attempts[f.physical].handle.closed)
                self.assertIsNotNone(f.disk.owner)

    def test_write_revision_invalidates_previous_confirmation(self):
        f = Fixture()
        token, journal, head = f.clean()
        stream = f.gates.attempts[f.physical].stream
        stream.seek(0)
        stream.write(b"x")
        with self.assertRaisesRegex(PersistenceUnconfirmed, "confirmation_absent"):
            f.gates.release(f.physical, token, head)
        self.assertIsNotNone(f.disk.owner)

    def test_pre_io_argument_refusal_does_not_invent_native_uncertainty(self):
        f = Fixture()
        token, journal, head = f.clean()
        stream = f.gates.attempts[f.physical].stream
        before = len(f.primitives.api.calls)
        for action in (lambda: stream.seek(-1), lambda: stream.read(0), lambda: stream.write(b"")):
            with self.assertRaises(PersistenceUnconfirmed):
                action()
        self.assertEqual(len(f.primitives.api.calls), before)
        self.assertFalse(stream.poisoned)
        f.gates.release(f.physical, token, head)

    def test_close_failure_retains_local_gate_and_no_clean_credit(self):
        f = Fixture()
        token, journal, head = f.clean()
        f.primitives.close_failure = True
        with self.assertRaises(OSError):
            f.gates.release(f.physical, token, head)
        self.assertIs(f.gates._held[f.physical], token)
        self.assertEqual(f.gates._known_clean, {})
        self.assertIsNotNone(f.disk.owner)

    def test_wrong_clean_head_does_not_close_gate(self):
        f = Fixture()
        token, journal, head = f.clean()
        with self.assertRaisesRegex(PersistenceUnconfirmed, "clean_head_mismatch"):
            f.gates.release(f.physical, token, "0" * 64)
        self.assertIsNotNone(f.disk.owner)

    def test_real_entry_remains_closed(self):
        with self.assertRaisesRegex(ReservationRefused, "admission_absent"):
            real_windows_reservation_service(approved=True)


class SplitStartContracts(unittest.TestCase):
    def fixture(self):
        return ConnectionContracts().setup()

    def test_finish_start_runs_after_resume_outside_state_lock_before_publication(self):
        f, kernel, manager = self.fixture()
        observations = []
        def finish(worker, permit, profile):
            self.assertFalse(manager._lock._is_owned())
            record = next(iter(manager._records.values()))
            self.assertIsNone(record.owner._worker)
            self.assertIs(record.phase, Phase.NATIVE_RESERVED)
            self.assertEqual(f.events[-1], "resume")
            observations.append(worker)
            return True
        kernel.finish_start = finish
        with manager.read_lease("generated", "choice", "revision") as lease:
            session = DurableOwnedRuntimeFactory(manager).open_owned_session(object(), lease.begin_native_session())
            self.assertEqual(observations, [f.worker])
            self.assertTrue(session.close_and_join())
            lease.confirm_native_closed()

    def test_finish_failure_stops_exact_worker_and_refuses_publication(self):
        f, kernel, manager = self.fixture()
        original = RuntimeError("injected finish failure")
        def fail(*args):
            raise original
        kernel.finish_start = fail
        with self.assertRaises(RuntimeError) as caught:
            with manager.read_lease("generated", "choice", "revision") as lease:
                DurableOwnedRuntimeFactory(manager).open_owned_session(object(), lease.begin_native_session())
        self.assertIs(caught.exception, original)
        self.assertEqual(f.events.count("stop_exact"), 1)
        self.assertNotIn("release_guards", f.events)
        self.assertIsNone(lease.inner._record.owner._worker)

    def test_revocation_during_finish_refuses_late_publication(self):
        f, kernel, manager = self.fixture()
        def revoke(worker, permit, profile):
            record = next(iter(manager._records.values()))
            with manager._lock:
                manager._quarantine_preserving(record, "finish race", RuntimeError("fixture"))
            return True
        kernel.finish_start = revoke
        with self.assertRaisesRegex(SessionClosed, "revoked before publication"):
            with manager.read_lease("generated", "choice", "revision") as lease:
                DurableOwnedRuntimeFactory(manager).open_owned_session(object(), lease.begin_native_session())
        self.assertEqual(f.events.count("stop_exact"), 1)
        self.assertIsNone(lease.inner._record.owner._worker)
        self.assertNotIn("release_guards", f.events)
