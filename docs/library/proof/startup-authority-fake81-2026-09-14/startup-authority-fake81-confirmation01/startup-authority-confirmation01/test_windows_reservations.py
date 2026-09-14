"""Unexecuted generated controls against the actual retained-handle port."""
from dataclasses import replace
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
import unittest

from win32_worker_connection import FileIdentity, HandleRecord, ReadSet, OwnedWin32Primitives
from windows_reservation_port import (WindowsGateRegistry, DirectoryScope, JournalBinding,
    gate_name, real_windows_reservation_service, MAX_CHUNK)
from snapshot_reservations import PhysicalSnapshot, SnapshotSemantics, ReservationService, ReservationRefused, encode_next, decode_journal
from reservation_file_port import PersistenceUnconfirmed
from durable_lifecycle import DurableOwnedRuntimeFactory
from snapshot_lifecycle import Phase, SessionClosed, OwnedRuntimeFactory, OperationFacade
import test_reservations as reservation_tests
import generated_adapter_flow as actual_flow


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
    # Exercise the retained source's actual read-set retirement algorithm;
    # only its native handle-close boundary remains the fixed fake below.
    release_read_set = OwnedWin32Primitives.release_read_set
    def __init__(self, disk):
        self.read_sets, self.handles, self.metadata = [], [], {}
        self.workers = []
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

    def pin_exact_members(self, expectations):
        assert type(expectations) is tuple and len(expectations) == 5
        owned = ReadSet()
        self.read_sets.append(owned)
        for path, expected in expectations:
            assert type(expected) is FileIdentity and expected.final_path == "\\\\?\\" + path
            handle = self._retain(self.next_handle, "read-member")
            self.next_handle += 1
            self.metadata[handle.value] = expected
            owned.members.append(handle)
            owned.identities.append(expected)
        return owned


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
        return reservation_tests.ConnectionContracts().setup()

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

class ActualAdapterNoWorkerContracts(unittest.TestCase):
    def port(self, fixture=None, generation="1" * 64):
        f = fixture or Fixture()
        paths = actual_flow.fixed_paths(f.snapshot.path)
        expected = tuple((path, FileIdentity("\\\\?\\" + path, 7, bytes([20 + i]) * 16,
                                             len(actual_flow.GENERATED[name]), 1, False))
                         for i, (name, path) in enumerate(zip(actual_flow.NAMES, paths)))
        # The actual constructor and source methods run. These fixed services
        # contain no process/pipe implementation, so any such use would fail.
        port = actual_flow.GeneratedLifecyclePort(f.primitives, SimpleNamespace(), expected,
            "unused-generated-executable", (), f.snapshot.path, (), generation, "a" * 64,
            actual_flow.namespace_digest(), "b" * 64, b"k" * 32, b"p" * 32, "positive")
        creation = f.gates.register_generated_creation(f.physical, f.created) if not f.disk.data else None
        port.connect_durable_registry(f.gates, f.physical, creation)
        return f, port

    def assert_clean_no_worker(self, f, port):
        record = port.lifecycle._records[port.key]
        self.assertIs(record.phase, Phase.RELEASED)
        self.assertIsNone(record.owner)
        self.assertIsNone(record.permit)
        self.assertIsNone(port.worker)
        self.assertIsNone(port.pair)
        self.assertFalse(port._start_attempted)
        self.assertFalse(port._resume_attempted)
        self.assertTrue(port.read_set.released)
        self.assertTrue(all(h.closed for h in port.read_set.members))
        self.assertNotIn(f.physical, f.gates._held)
        self.assertIsNone(f.disk.owner)
        rows, head = decode_journal(bytes(f.disk.data))
        self.assertEqual(rows[-1]["phase"], "CLEARED")
        self.assertTrue(all(row["process"] is None for row in rows))
        self.assertEqual(f.primitives.workers, [])
        self.assertIsNone(port._completion)
        self.assertEqual(port.binding_calls, 0)

    def test_actual_ensure_assets_retires_without_worker_and_allows_fresh_generation(self):
        f, port = self.port()
        with actual_flow.generated_authority_seams(port):
            result = actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
        self.assertTrue(result["ok"])
        self.assertFalse(result["model_constructed"])
        self.assert_clean_no_worker(f, port)
        f, next_port = self.port(f, "2" * 64)
        with actual_flow.generated_authority_seams(next_port):
            self.assertTrue(actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=next_port.cwd)["ok"])
        self.assert_clean_no_worker(f, next_port)
        rows, _ = decode_journal(bytes(f.disk.data))
        self.assertEqual([r["generation"] for r in rows if r["phase"] == "RESERVED"], ["1" * 64, "2" * 64])

    def test_initial_admission_refusal_closes_cleanly_before_consent_error(self):
        f, port = self.port()
        original = actual_flow.real_resolver.AdmissionRefusal("injected local admission failure")
        def fail(*args):
            raise original
        port.generated_admit = fail
        with actual_flow.generated_authority_seams(port):
            with self.assertRaises(actual_flow.adapter.AssetConsentRequired) as caught:
                actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
        self.assertIs(caught.exception.__cause__, original)
        self.assert_clean_no_worker(f, port)

    def test_initial_admission_nonconsent_error_preserves_original_and_retires(self):
        f, port = self.port()
        original = RuntimeError("injected ordinary admission failure")
        def fail(*args):
            raise original
        port.generated_admit = fail
        with actual_flow.generated_authority_seams(port):
            with self.assertRaises(RuntimeError) as caught:
                actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
        self.assertIs(caught.exception, original)
        self.assert_clean_no_worker(f, port)

    def test_no_worker_guard_close_failure_keeps_gate_and_mints_no_witness(self):
        f, port = self.port()
        def admit(*args):
            f.primitives.close_failure = True
            return port.generated_admission
        port.generated_admit = admit
        with actual_flow.generated_authority_seams(port):
            with self.assertRaises(OSError):
                actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
        self.assertIs(port.lifecycle._records[port.key].phase, Phase.QUARANTINED)
        self.assertIn(f.physical, f.gates._held)
        self.assertIsNone(port._no_worker_witness)
        self.assertIsNone(port._completion)
        self.assertTrue(port.read_set.unconfirmed)
        self.assertFalse(port.read_set.released)

    def test_started_or_reserved_native_state_cannot_claim_no_worker_cleanup(self):
        for fault in ("start", "resume", "worker_reserved", "native_permit", "owner", "retained_worker"):
            with self.subTest(fault=fault):
                f, port = self.port()
                def admit(*args):
                    record = port.lifecycle._records[port.key]
                    if fault == "start":
                        port._start_attempted = True
                    elif fault == "resume":
                        port._resume_attempted = True
                    elif fault == "worker_reserved":
                        port.read_set.worker_reserved = True
                    elif fault == "native_permit":
                        record.permit = object()
                    elif fault == "owner":
                        record.owner = SimpleNamespace()
                    else:
                        f.primitives.workers.append(SimpleNamespace(read_set=port.read_set))
                    return port.generated_admission
                port.generated_admit = admit
                with actual_flow.generated_authority_seams(port):
                    with self.assertRaises(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed):
                        actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
                self.assertIn(f.physical, f.gates._held)
                self.assertIsNone(port._no_worker_witness)
                self.assertIsNone(port._completion)
                self.assertFalse(port.read_set.released)

    def test_old_completion_cannot_clear_fresh_lease_record(self):
        f, port = self.port()
        with actual_flow.generated_authority_seams(port):
            actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
        f, next_port = self.port(f, "2" * 64)
        with next_port.lifecycle.read_lease(next_port.cwd, actual_flow.CHOICE, actual_flow.REVISION):
            with self.assertRaisesRegex(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed, "current_retired_lifetime_required"):
                port.completion_evidence(None)
            self.assertFalse(next_port._no_worker_retired())
            self.assertIn(f.physical, f.gates._held)
        self.assert_clean_no_worker(f, next_port)

class ActualFactoryMigrationContracts(unittest.TestCase):
    @contextmanager
    def fixture(self, *, old_factory=False):
        f, kernel, manager = reservation_tests.ConnectionContracts().setup()
        module = actual_flow.adapter
        profile = module.RuntimeProfile("generated-profile", "cpu", "int8", None, None)
        authority = SimpleNamespace(runtime_profile_id=profile.profile_id,
                                    manifest_approval=SimpleNamespace(manifest_sha256="a" * 64))
        admission = SimpleNamespace(snapshot="generated")
        binding = actual_flow.real_resolver.LocalBinding("generated", "choice", "revision", "a" * 64, ())
        proxy = SimpleNamespace(LocalBinding=type(binding), AdmissionRefusal=actual_flow.real_resolver.AdmissionRefusal,
            admit_snapshot=lambda *args: admission, bind_for_constructor=lambda value: binding)
        factory = OwnedRuntimeFactory(manager) if old_factory else DurableOwnedRuntimeFactory(manager)
        values = {"_release": lambda *args, **kwargs: (authority, object(), SimpleNamespace(revision="revision"), "generated", "generated"),
                  "resolver": proxy, "SNAPSHOT_LIFECYCLE": manager, "RUNTIME_FACTORY": factory, "RUNTIME_PROFILE": profile}
        with ExitStack() as stack:
            for name, value in values.items():
                stack.enter_context(actual_flow._replace(module, name, value))
            yield f, kernel, manager, module

    def test_exact_migrated_adapter_opens_durable_factory_and_closes_actual_owned_facade(self):
        with self.fixture() as (f, kernel, manager, module):
            with module.faster_whisper_session("choice", model_root="generated") as facade:
                self.assertIs(type(facade), OperationFacade)
                self.assertIs(facade._session._manager, manager)
                self.assertIs(facade._session._record.phase, Phase.NATIVE_RUNNING)
                self.assertIn("finish_start", f.events)
            self.assertIs(facade._session._record.phase, Phase.RELEASED)
            self.assertLess(f.events.index("quiet"), f.events.index("release_guards"))
            self.assertLess(f.events.index("release_guards"), f.events.index("confirm_finish"))
            self.assertEqual(decode_journal(f.stream.getvalue())[0][-1]["phase"], "CLEARED")
            with self.assertRaises(SessionClosed):
                facade._session._require_live()

    def test_old_exact_factory_is_refused_before_native_permit_or_worker_creation(self):
        with self.fixture(old_factory=True) as (f, kernel, manager, module):
            with self.assertRaisesRegex(module.AdapterUnavailable, "Concrete runtime factory"):
                with module.faster_whisper_session("choice", model_root="generated"):
                    self.fail("Old factory must not yield a facade")
            record = next(iter(manager._records.values()))
            self.assertIs(record.phase, Phase.RELEASED)
            self.assertIsNone(record.permit)
            self.assertIsNone(record.owner)
            self.assertNotIn("create", f.events)
            self.assertEqual(decode_journal(f.stream.getvalue())[0][-1]["phase"], "CLEARED")
