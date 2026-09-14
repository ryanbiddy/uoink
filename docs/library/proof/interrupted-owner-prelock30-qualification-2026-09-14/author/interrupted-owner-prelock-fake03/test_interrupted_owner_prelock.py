"""Two proposed controller pre-lock controls; lower APIs remain inert.

Call the actual interrupted controller, ASR context, facade, retained cleanup
and write-access probe. Reuse the unchanged InterruptedFixture for in-memory
startup, transport, journal and native result cells. No OS protection is claimed.
"""
from contextlib import ExitStack
import unittest

import generated_adapter_flow as flow
from snapshot_lifecycle import OwnedSession, Phase
from win32_worker_connection import KernelUnconfirmed
from test_interrupted_owner_retirement import InterruptedFixture, replaced


class PrelockFixture(InterruptedFixture):
    """Add only the missing write-open API seam and delegating observations."""
    def __init__(self, refusal_failure=None):
        self.refusal_failure = refusal_failure
        self.boundary = []
        self.write_attempts = []
        self.unexpected_write_handles = []
        self.context_cleanup = []
        super().__init__()

    def call(self, name, *args):
        # The original fixture handles only its journal's CreateFileW. This
        # separate exact call shape is the unchanged generated write probe.
        if name == "CreateFileW" and len(args) == 7 and args[1] == 0x40000000:
            p, port = self.f.primitives, self.port
            path, access, share, security, disposition, flags, template = args
            paths = tuple(value for value, expected in port.expectations)
            assert path in paths and share == 7 and security is None
            assert disposition == 3 and flags == 0x00200000 and template is None
            assert not port.lifecycle._lock._is_owned()
            index = paths.index(path)
            p.api.calls.append((name, args))
            if not port.read_set.released:
                assert self.record.phase is Phase.NATIVE_RUNNING
                assert self.record.protection is port.read_set
                assert self.record.permit is port.permit and self.record.owner is self.owner
                assert port.adapter_start_ack is not None and port.worker.resumed
                assert not self.owner._revoked and not self.owner._closed_verified
                assert len(port.read_set.members) == 5
                assert all(not h.closed and not h.unconfirmed for h in port.read_set.members)
                assert port._ticket is None and not port.operation_events
                assert not self.probe.fired and not port.pair.active and not port.pair.operations
                assert index == len(self.write_attempts)
                self.boundary.append(("locked", index))
                self.write_attempts.append((path, True))
                if index == self.refusal_failure:
                    # A handle returned instead of ERROR_SHARING_VIOLATION
                    # must be closed by the actual helper before it refuses.
                    value = 20000 + index
                    self.unexpected_write_handles.append(value)
                    p.api.ffi.error = 0
                    return value
                p.api.ffi.error = 32
                return (1 << 64) - 1
            assert self.record.phase is Phase.RELEASED
            assert self.owner._closed_verified and self.owner._revoked
            assert self.token.revoked and port.pair.closed
            assert all(h.closed and not h.unconfirmed for h in port.read_set.members)
            assert self.setup.created_handle.closed
            assert self.f.physical not in self.f.gates._held
            assert index == len(self.write_attempts) - 5
            self.boundary.append(("opened", index))
            self.write_attempts.append((path, False))
            p.api.ffi.error = 0
            return 21000 + index
        return super().call(name, *args)

    def run_controller(self):
        port = self.port
        actual_ticket = port.issue_generated_media_ticket
        actual_begin = port.begin_transcription
        actual_next = port.next_segment
        actual_close = OwnedSession.close_and_join

        def ticket(session):
            self.boundary.append(("ticket", None))
            return actual_ticket(session)

        def begin(worker, contract, request):
            # The controller owns this request; the inherited transport seam
            # needs its exact value instead of old interrupted()'s local setup.
            self.request = request
            self.boundary.append(("transcribe", None))
            return actual_begin(worker, contract, request)

        def advance(worker, cursor):
            self.boundary.append(("segment", port._next_index))
            return actual_next(worker, cursor)

        def close(owner):
            assert owner is self.owner
            self.context_cleanup.append(owner)
            self.boundary.append(("context_cleanup", None))
            return actual_close(owner)

        with ExitStack() as stack:
            stack.enter_context(replaced(port, "issue_generated_media_ticket", ticket))
            stack.enter_context(replaced(port, "begin_transcription", begin))
            stack.enter_context(replaced(port, "next_segment", advance))
            stack.enter_context(replaced(OwnedSession, "close_and_join", close))
            return flow.controller_interrupted_recovery_flow(port)


class InterruptedOwnerPrelockContracts(unittest.TestCase):
    def assert_authority_restored(self):
        self.assertIsNone(flow.real_resolver.REAL_APPROVAL)
        self.assertIs(flow.adapter.resolver, flow.real_resolver)
        for name in ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE",
                     "RUNTIME_FACTORY", "ACQUISITION_SERVICE"):
            self.assertIsNone(getattr(flow.adapter, name))

    def test_actual_controller_probes_before_media_and_after_retirement(self):
        f = PrelockFixture()
        close_before = OwnedSession.close_and_join
        probe_before = flow.operation_flow.adoption_flow._write_access_probe
        result = f.run_controller()
        self.assertIs(OwnedSession.close_and_join, close_before)
        self.assertIs(flow.operation_flow.adoption_flow._write_access_probe, probe_before)
        self.assert_authority_restored()
        paths = tuple(path for path, expected in f.port.expectations)
        self.assertEqual(f.write_attempts, [(path, True) for path in paths] +
                         [(path, False) for path in paths])
        self.assertEqual(f.boundary,
            [("locked", i) for i in range(5)] +
            [("ticket", None), ("transcribe", None), ("segment", 0),
             ("segment", 1), ("context_cleanup", None)] +
            [("opened", i) for i in range(5)])
        self.assertEqual(f.context_cleanup, [f.owner])
        self.assertEqual(result["write_access_observations"],
            [{"write_open_refused": True, "winerror": 32} for _ in paths] +
            [{"write_open_succeeded": True, "bytes_written": 0} for _ in paths])
        self.assertEqual(result["operation_events"], [
            "admit_generated_media", "begin_generated_transcription",
            "next_generated_segment", "next_generated_segment"])
        self.assertEqual(len(result["segments"]), 1)
        self.assertIs(f.record.phase, Phase.RELEASED)
        self.assertTrue(f.owner._closed_verified and f.owner._revoked and f.token.revoked)
        self.assertTrue(f.port.read_set.released and f.port.pair.closed)
        self.assertFalse(result["parent_guards_held_through_exit"])
        self.assertEqual(f.phases(),
            ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"])
        self.assertEqual(f.setup.flush_successes, 5)

    def test_refusal_error_stops_media_and_reaches_context_cleanup(self):
        for failing_index in range(5):
            with self.subTest(failing_index=failing_index):
                f = PrelockFixture(refusal_failure=failing_index)
                close_before = OwnedSession.close_and_join
                probe_before = flow.operation_flow.adoption_flow._write_access_probe
                with self.assertRaisesRegex(KernelUnconfirmed,
                        "^generated_file_write_share_guard_not_observed$") as caught:
                    f.run_controller()
                self.assertIs(OwnedSession.close_and_join, close_before)
                self.assertIs(flow.operation_flow.adoption_flow._write_access_probe, probe_before)
                self.assert_authority_restored()
                self.assertEqual(f.boundary,
                    [("locked", i) for i in range(failing_index + 1)] +
                    [("context_cleanup", None)])
                paths = tuple(path for path, expected in f.port.expectations)
                self.assertEqual(f.write_attempts,
                    [(path, True) for path in paths[:failing_index + 1]])
                self.assertEqual(f.port.observations,
                    [{"write_open_refused": True, "winerror": 32}
                     for _ in range(failing_index)])
                self.assertIsNone(f.port._ticket)
                self.assertIsNone(f.request)
                self.assertEqual(f.transport_actions, [])
                self.assertEqual(f.port.operation_events, [])
                self.assertEqual(f.port._next_index, 0)
                self.assertEqual(f.context_cleanup, [f.owner])
                self.assertFalse(f.probe.fired)
                self.assertIs(f.record.phase, Phase.QUARANTINED)
                self.assertFalse(f.owner._closed_verified)
                self.assertTrue(f.owner._revoked and f.token.revoked)
                self.assertIs(f.record.protection, f.port.read_set)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
                self.assertFalse(f.setup.created_handle.closed)
                self.assertTrue(any("Owned ASR cleanup remains unconfirmed" in note
                                    for note in caught.exception.__notes__))
                self.assertEqual(len(f.unexpected_write_handles), 1)
                handle = [h for h in f.f.primitives.handles
                          if h.value == f.unexpected_write_handles[0]]
                self.assertEqual(len(handle), 1)
                self.assertEqual(handle[0].kind, "dummy-unexpected-write-access")
                self.assertTrue(handle[0].closed and not handle[0].unconfirmed)
