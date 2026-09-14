"""Unexecuted transfer controls; the native CREATE_NEW claim is not mocked proven.

Use the reviewed fake services from the source proposal with this derivative's
actual windows_reservation_port. The test setup supplies an already retained
fake handle, as a bootstrap would. No native API or existing65 body is executed
or altered by writing this file. A runner/admission is still required.
"""
from dataclasses import replace
import unittest
import test_windows_reservations as fixtures
from win32_worker_connection import HandleRecord
from reservation_file_port import PersistenceUnconfirmed
from snapshot_reservations import ReservationService, ReservationRefused, encode_next, decode_journal


class CreationTransferContracts(unittest.TestCase):
    def setup(self):
        f = fixtures.Fixture()
        handle = f.primitives._retain(200, "reservation-journal")
        f.disk.owner = (f.primitives.api, handle.value)
        return f, handle

    def test_same_retained_handle_moves_without_reopen_and_closes_once(self):
        f, handle = self.setup()
        f.gates.stage_created_handle(f.binding, handle)
        before = len(f.primitives.api.calls)
        token = f.gates.acquire(f.physical)
        self.assertIs(f.gates.attempts[f.physical].handle, handle)
        self.assertNotIn(f.physical, f.gates._created_handles)
        self.assertEqual(f.primitives.api.calls[before:], [])
        journal = f.gates.open_journal(f.physical)
        raw = journal.append_confirmed(b"", encode_next(b"", f.physical, f.semantic, None, "INITIALIZED"))
        f.gates.release(f.physical, token, decode_journal(raw)[1])
        self.assertTrue(handle.closed)
        self.assertEqual([args for name, args in f.primitives.api.calls if name == "CloseHandle"], [(handle.value,)])
        self.assertFalse(any(name == "CreateFileW" for name, args in f.primitives.api.calls))

    def test_identity_failure_after_transfer_retains_attempt_handle_and_gate(self):
        f, handle = self.setup()
        f.gates.stage_created_handle(f.binding, handle)
        f.primitives.identity_failure = True
        with self.assertRaisesRegex(OSError, "injected identity failure"):
            f.gates.acquire(f.physical)
        attempt = f.gates.attempts[f.physical]
        self.assertIs(attempt.handle, handle)
        self.assertIs(f.gates._held[f.physical], attempt.token)
        self.assertNotIn(f.physical, f.gates._created_handles)
        self.assertEqual(attempt.failure, "OSError")
        self.assertFalse(handle.closed)
        self.assertEqual(f.disk.owner, (f.primitives.api, handle.value))
        self.assertEqual(f.primitives.api.calls, [])

    def test_duplicate_and_foreign_handle_transfers_refuse(self):
        f, handle = self.setup()
        f.gates.stage_created_handle(f.binding, handle)
        with self.assertRaisesRegex(PersistenceUnconfirmed, "one_registered_creation_transfer"):
            f.gates.stage_created_handle(f.binding, handle)
        g, owned = self.setup()
        foreign = HandleRecord(owned.value, owned.kind)
        # This exact AssertionError belongs to the reviewed FakePrimitives
        # identity trap; it is not the production KernelUnconfirmed hierarchy.
        with self.assertRaises(AssertionError):
            g.gates.stage_created_handle(g.binding, foreign)
        self.assertIs(f.gates._created_handles[f.physical], handle)
        self.assertEqual(g.gates._created_handles, {})
        self.assertFalse(owned.closed)

    def test_changed_or_nonempty_identity_cannot_stage_handle(self):
        for fault in ("identity", "nonempty"):
            with self.subTest(fault=fault):
                f, handle = self.setup()
                if fault == "identity":
                    f.primitives.journal_identity = replace(f.primitives.journal_identity, file_id=b"x" * 16)
                else:
                    f.disk.data.extend(b"x")
                with self.assertRaisesRegex(PersistenceUnconfirmed, "created_empty_identity_changed"):
                    f.gates.stage_created_handle(f.binding, handle)
                self.assertEqual(f.gates._created_handles, {})
                self.assertFalse(handle.closed)
                self.assertEqual(f.disk.owner, (f.primitives.api, handle.value))

    def test_handle_transfer_does_not_issue_creation_authority(self):
        f, handle = self.setup()
        f.gates.stage_created_handle(f.binding, handle)
        service = ReservationService(f.gates, f.gates.open_journal, lambda *args: None, lambda *args: False)
        with self.assertRaisesRegex(ReservationRefused, "new_snapshot_creation_evidence_required"):
            service.begin(f.physical, f.semantic, "1" * 64)
        self.assertEqual(bytes(f.disk.data), b"")
        self.assertIs(f.gates.attempts[f.physical].handle, handle)
        self.assertIn(f.physical, f.gates._held)
        self.assertFalse(handle.closed)