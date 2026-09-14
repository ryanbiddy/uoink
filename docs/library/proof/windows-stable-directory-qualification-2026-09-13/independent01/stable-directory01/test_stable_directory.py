"""Generated regression controls; no ctypes, filesystem or native execution."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

import test_windows_reservations as fixtures
from reservation_file_port import PersistenceUnconfirmed
from snapshot_reservations import encode_next, decode_journal
from windows_reservation_port import directory_refusal_diagnostic
from win32_worker_connection import (OwnedWin32Primitives, FileIdentity, KernelUnavailable,
    FILE_ATTRIBUTE_REPARSE_POINT, FILE_READ_ATTRIBUTES, GENERIC_READ, FILE_SHARE_READ,
    OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, FILE_FLAG_BACKUP_SEMANTICS)


class WideBuffer:
    def __init__(self, count):
        self.count, self.value = count, ""
    def __len__(self):
        return self.count


class InertFFI(fixtures.FakeFFI):
    def create_unicode_buffer(self, count):
        return WideBuffer(count)
    def sizeof(self, value):
        # This fake covers call ordering and values, not the native ABI layout.
        return 64


class InertIdentityAPI:
    """Fixed query outputs for the actual identity/pin source methods."""
    def __init__(self, expected, observed):
        self.expected, self.observed = expected, observed
        self.ffi, self.calls = InertFFI(), []
        self.attributes = self.reparse_tag = 0
        self.delete_pending = False
    def structure(self, name):
        value = self.observed
        if name == "FILE_ATTRIBUTE_TAG_INFO":
            return SimpleNamespace(attributes=self.attributes, reparse_tag=self.reparse_tag)
        if name == "FILE_STANDARD_INFO":
            return SimpleNamespace(size=value.size, links=value.links,
                                   directory=value.directory, delete_pending=self.delete_pending)
        if name == "FILE_ID_INFO":
            return SimpleNamespace(volume=value.volume_serial, file_id=value.file_id)
        raise AssertionError("Unexpected fixed query structure")
    def call(self, name, *args):
        self.calls.append((name, args))
        if name == "CreateFileW":
            expected = self.expected
            access = FILE_READ_ATTRIBUTES if expected.directory else GENERIC_READ
            flags = FILE_FLAG_OPEN_REPARSE_POINT | (FILE_FLAG_BACKUP_SEMANTICS if expected.directory else 0)
            assert args == (expected.final_path[4:], access, FILE_SHARE_READ, None,
                            OPEN_EXISTING, flags, None)
            return 101
        if name == "GetFileInformationByHandleEx":
            assert args[0] == 101 and args[3] == 64
            return 1
        if name == "GetFinalPathNameByHandleW":
            assert args[0] == 101 and args[2:] == (32768, 0)
            args[1].value = self.observed.final_path
            return len(self.observed.final_path)
        raise AssertionError("Unexpected inert native call")
    def checked(self, name, *args):
        assert self.call(name, *args)


class StableDirectoryContracts(unittest.TestCase):
    def changed(self, expected, fault):
        return replace(expected, **{
            "path": {"final_path": expected.final_path + "-other"},
            "volume": {"volume_serial": expected.volume_serial + 1},
            "file_id": {"file_id": b"z" * 16},
            "links": {"links": expected.links + 1},
            "directory": {"directory": False},
        }[fault])

    def pin(self, expected, observed):
        api = InertIdentityAPI(expected, observed)
        return OwnedWin32Primitives(api), api

    def test_growth_at_each_ancestor_allows_confirmed_clear_and_release(self):
        for scope_name in ("registry", "snapshot"):
            for index in range(3):
                with self.subTest(scope=scope_name, index=index):
                    f = fixtures.Fixture()
                    token, journal, head = f.clean()
                    raw = bytes(f.disk.data)
                    generation = "1" * 64
                    raw = journal.append_confirmed(raw, encode_next(raw, f.physical, f.semantic,
                        generation, "RESERVED"))
                    raw = journal.append_confirmed(raw, encode_next(raw, f.physical, f.semantic,
                        generation, "WORKER_BOUND", process=[100, 200]))
                    scope = getattr(f, scope_name)
                    handle = scope.read_set.members[index]
                    expected = scope.read_set.identities[index]
                    f.primitives.metadata[handle.value] = replace(expected, size=4096)
                    self.assertEqual(journal.confirm_current(raw), raw)
                    f.primitives.metadata[handle.value] = replace(expected, size=8192)
                    raw = journal.append_confirmed(raw, encode_next(raw, f.physical, f.semantic,
                        generation, "CLEARED", process=[100, 200]))
                    rows, head = decode_journal(raw)
                    self.assertEqual([row["phase"] for row in rows],
                                     ["INITIALIZED", "RESERVED", "WORKER_BOUND", "CLEARED"])
                    self.assertEqual(journal.read_all(), raw)
                    self.assertIs(scope.read_set.identities[index], expected)
                    self.assertFalse(journal._stream.poisoned)
                    f.gates.release(f.physical, token, head)
                    self.assertIsNone(f.disk.owner)
                    self.assertNotIn(f.physical, f.gates._held)

    def test_other_directory_fields_refuse_before_journal_open(self):
        for scope_name in ("registry", "snapshot"):
            for fault in ("path", "volume", "file_id", "links", "directory"):
                with self.subTest(scope=scope_name, fault=fault):
                    f = fixtures.Fixture()
                    handle = getattr(f, scope_name).read_set.members[-1]
                    f.primitives.metadata[handle.value] = self.changed(f.primitives.metadata[handle.value], fault)
                    with self.assertRaisesRegex(PersistenceUnconfirmed, "directory_identity_or_final_path_changed"):
                        f.gates.acquire(f.physical)
                    self.assertEqual(f.primitives.api.calls, [])
                    self.assertIn(f.physical, f.gates._held)
                    self.assertIsNone(f.disk.owner)

    def test_other_field_change_after_clean_poisons_and_retains_gate(self):
        for fault in ("path", "volume", "file_id", "links", "directory"):
            with self.subTest(fault=fault):
                f = fixtures.Fixture()
                token, journal, head = f.clean()
                handle = f.registry.read_set.members[-1]
                f.primitives.metadata[handle.value] = self.changed(f.primitives.metadata[handle.value], fault)
                with self.assertRaisesRegex(PersistenceUnconfirmed, "directory_identity_or_final_path_changed"):
                    journal.confirm_current(bytes(f.disk.data))
                with self.assertRaisesRegex(PersistenceUnconfirmed, "confirmation_absent"):
                    f.gates.release(f.physical, token, head)
                self.assertTrue(journal._stream.poisoned)
                self.assertIs(f.gates._held[f.physical], token)
                self.assertFalse(f.gates.attempts[f.physical].handle.closed)
                self.assertIsNotNone(f.disk.owner)

    def test_invalid_directory_size_observations_still_refuse(self):
        for invalid in (-1, 1 << 63, True, "4096", None):
            with self.subTest(invalid=invalid):
                f = fixtures.Fixture()
                handle = f.snapshot.read_set.members[-1]
                f.primitives.metadata[handle.value] = replace(f.primitives.metadata[handle.value], size=invalid)
                with self.assertRaisesRegex(PersistenceUnconfirmed, "directory_identity_or_final_path_changed"):
                    f.gates.acquire(f.physical)
                self.assertEqual(f.primitives.api.calls, [])
                self.assertIn(f.physical, f.gates._held)

    def test_directory_pin_accepts_growth_and_retains_current_observation(self):
        expected = FileIdentity(r"\\?\E:\generated\directory", 7, b"d" * 16, 4096, 1, True)
        observed = replace(expected, size=8192)
        primitives, api = self.pin(expected, observed)
        owned = primitives.pin_exact_members(((expected.final_path[4:], expected),))
        self.assertEqual(owned.identities, [observed])
        self.assertFalse(owned.unconfirmed)
        self.assertFalse(owned.members[0].closed)
        self.assertEqual([name for name, args in api.calls], ["CreateFileW",
            "GetFileInformationByHandleEx", "GetFileInformationByHandleEx",
            "GetFileInformationByHandleEx", "GetFinalPathNameByHandleW"])

    def test_directory_pin_keeps_other_fields_strict(self):
        expected = FileIdentity(r"\\?\E:\generated\directory", 7, b"d" * 16, 4096, 1, True)
        for fault in ("path", "volume", "file_id", "links", "directory"):
            with self.subTest(fault=fault):
                primitives, api = self.pin(expected, self.changed(expected, fault))
                with self.assertRaisesRegex(KernelUnavailable, "Opened identity differs"):
                    primitives.pin_exact_members(((expected.final_path[4:], expected),))
                self.assertTrue(primitives.read_sets[0].unconfirmed)
                self.assertFalse(primitives.handles[0].closed)
                self.assertFalse(any(name == "CloseHandle" for name, args in api.calls))

    def test_regular_file_size_change_refuses_and_retains_handle(self):
        expected = FileIdentity(r"\\?\E:\generated\asset.bin", 7, b"f" * 16, 32, 1, False)
        for size in (31, 33):
            with self.subTest(size=size):
                primitives, api = self.pin(expected, replace(expected, size=size))
                with self.assertRaisesRegex(KernelUnavailable, "Opened identity differs"):
                    primitives.pin_exact_members(((expected.final_path[4:], expected),))
                self.assertTrue(primitives.read_sets[0].unconfirmed)
                self.assertFalse(primitives.handles[0].closed)
                self.assertEqual(primitives.read_sets[0].identities, [])
                self.assertFalse(any(name in ("ReadFile", "CloseHandle") for name, args in api.calls))

    def test_regular_file_exact_identity_still_pins(self):
        expected = FileIdentity(r"\\?\E:\generated\asset.bin", 7, b"f" * 16, 32, 1, False)
        primitives, api = self.pin(expected, expected)
        owned = primitives.pin_exact_members(((expected.final_path[4:], expected),))
        self.assertEqual(owned.identities, [expected])
        self.assertFalse(owned.unconfirmed)

    def test_native_identity_reparse_pending_and_negative_checks_remain(self):
        expected = FileIdentity(r"\\?\E:\generated\directory", 7, b"d" * 16, 4096, 1, True)
        for fault in ("attributes", "tag", "pending", "negative"):
            with self.subTest(fault=fault):
                primitives, api = self.pin(expected, expected)
                if fault == "attributes":
                    api.attributes = FILE_ATTRIBUTE_REPARSE_POINT
                elif fault == "tag":
                    api.reparse_tag = 1
                elif fault == "pending":
                    api.delete_pending = True
                else:
                    api.observed = replace(expected, size=-1)
                with self.assertRaisesRegex(KernelUnavailable, "Reparse, pending deletion or invalid size refused"):
                    primitives.pin_exact_members(((expected.final_path[4:], expected),))
                self.assertTrue(primitives.read_sets[0].unconfirmed)
                self.assertFalse(primitives.handles[0].closed)
                self.assertEqual([name for name, args in api.calls], ["CreateFileW",
                    "GetFileInformationByHandleEx", "GetFileInformationByHandleEx", "GetFileInformationByHandleEx"])

    def test_dataclass_equality_and_refusal_diagnostic_keep_both_sizes(self):
        f = fixtures.Fixture()
        handle = f.snapshot.read_set.members[-1]
        expected = f.primitives.metadata[handle.value]
        observed = replace(expected, size=8192, file_id=b"z" * 16)
        self.assertNotEqual(expected, replace(expected, size=8192))
        f.primitives.metadata[handle.value] = observed
        with self.assertRaisesRegex(PersistenceUnconfirmed, "directory_identity_or_final_path_changed") as caught:
            f.gates.acquire(f.physical)
        diagnostic = directory_refusal_diagnostic(caught.exception)
        self.assertTrue(diagnostic["available"])
        self.assertEqual(diagnostic["stage"], "retained_directory_identity_comparison")
        self.assertEqual((diagnostic["expected"]["size"], diagnostic["observed"]["size"]), (0, 8192))
        self.assertEqual(diagnostic["expected"]["file_id"], expected.file_id.hex())
        self.assertEqual(diagnostic["observed"]["file_id"], observed.file_id.hex())
        self.assertEqual(f.primitives.api.calls, [])

    def test_growth_does_not_grant_release_after_flush_failure(self):
        f = fixtures.Fixture()
        token, journal, head = f.clean()
        handle = f.registry.read_set.members[-1]
        f.primitives.metadata[handle.value] = replace(f.primitives.metadata[handle.value], size=8192)
        f.primitives.api.fail_sync = True
        with self.assertRaises(OSError):
            journal.confirm_current(bytes(f.disk.data))
        with self.assertRaisesRegex(PersistenceUnconfirmed, "confirmation_absent"):
            f.gates.release(f.physical, token, head)
        self.assertIs(f.gates._held[f.physical], token)
        self.assertFalse(f.gates.attempts[f.physical].handle.closed)
        self.assertIsNotNone(f.disk.owner)
