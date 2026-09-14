"""Unexecuted six-case controller retirement proposal; all lower I/O is inert.

Actual adapter/context, durable factory/session, admitted operation, journal,
pipe quarantine, retained handle closure, coordinator and observers are used.
Startup/adoption and frame transport are explicit fixed in-memory seams. These
tests do not qualify child bootstrap, authenticated transport, Win32 or models.
"""
from contextlib import contextmanager
from types import MethodType, SimpleNamespace
import hashlib
import unittest

import generated_adapter_flow as flow
from generated_journal_setup import GeneratedJournalSetup
from snapshot_lifecycle import (Phase, CleanupUnconfirmed, LifecycleUnavailable,
    SessionClosed, OwnedSession, OperationFacade, TranscribeRequest)
from snapshot_reservations import ReservationRefused, decode_journal
from win32_private_pipe import PrivatePipeController, PipePair, PendingIO
from win32_worker_connection import (OwnedWin32Primitives, Win32API, WorkerRecord,
    HandleRecord, KernelUnconfirmed)
import test_windows_reservations as fixtures


@contextmanager
def replaced(owner, name, value):
    prior = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, prior)


class InertChannel:
    """Fixed transport seam; tuples here supply no authentication evidence."""
    def __init__(self, fixture):
        self.fixture = fixture
        self.binding = SimpleNamespace(generation_hex=fixture.port.generation,
            manifest_sha256=fixture.port.manifest,
            namespace_sha256=flow.namespace_digest())
        self._revoked = False

    def encode(self, operation, payload):
        if self._revoked:
            raise SessionClosed("inert channel revoked")
        return operation, payload

    def decode(self, frame):
        if self._revoked:
            raise SessionClosed("inert channel revoked")
        return frame

    def revoke(self):
        self._revoked = True


class InertHandshake:
    def __init__(self, fixture):
        self.fixture, self._begun = fixture, False

    def _owned_phase(self, starting):
        f, port = self.fixture, self.fixture.port
        record = port.lifecycle._records[port.key]
        assert record.owner is f.owner and record.owner._worker is port.worker
        assert record.permit is port.permit and not record.owner._revoked
        assert record.phase is (Phase.NATIVE_RESERVED if starting else Phase.NATIVE_RUNNING)

    def begin(self):
        self._owned_phase(False)
        assert not self._begun
        self._begun = True
        return "begin", {"manifest_sha256": self.fixture.port.manifest}


class InterruptedFixture:
    def __init__(self):
        self.f = f = fixtures.Fixture()
        self.events, self.transport_actions, self.pending_frames = [], [], []
        self.owner = self.record = self.facade = self.stream = self.request = None
        self.token = self.original_error = None
        self.stop_requests = 0
        self.wait_result, self.exit_code, self.job_active = 0, 1, 0
        self.creation_time = 456
        self.during_sync = self.before_close = None
        self.fail_handle = None
        p = f.primitives
        # Bind actual retained-owner/close/stop algorithms, not duplicate logic.
        for name in ("_owned", "_close", "_stop_partial_worker", "_creation_time"):
            setattr(p, name, MethodType(getattr(OwnedWin32Primitives, name), p))
        p.api.checked = MethodType(Win32API.checked, p.api)
        p.api.structure = self.structure
        p.api.ffi.sizeof = lambda value: value._inert_size
        self.journal_call = p.api.call
        p.api.call = self.call
        self.pipes = pipes = PrivatePipeController(p, lambda: 1.0)
        # Actual _frame_operation and _quarantine remain installed.
        pipes.write_bytes, pipes.read_frame = self.write_frame, self.read_frame
        expected = tuple((path, fixtures.FileIdentity("\\\\?\\" + path, 7,
            bytes([20 + i]) * 16, len(flow.GENERATED[name]), 1, False))
            for i, (name, path) in enumerate(zip(flow.NAMES, flow.fixed_paths(f.snapshot.path))))
        self.port = port = flow.GeneratedLifecyclePort(p, pipes, expected,
            "unused-generated-executable", (), f.snapshot.path, (), "1" * 64,
            "a" * 64, flow.namespace_digest(), "b" * 64, b"k" * 32, b"p" * 32,
            "positive", operation_mode="drain")
        self.setup = setup = GeneratedJournalSetup(p, SimpleNamespace(calls=p.api.calls), port.cwd)
        setup.gates, setup.physical = f.gates, f.physical
        setup.scopes = [f.snapshot.read_set, f.registry.read_set]
        setup.journal_path = p.journal_path
        # Explicit lower startup/adoption seam. Actual ASR adapter and durable
        # factory still create, validate and retain their exact startup/permit.
        port.create_suspended = self.create_suspended
        port.resume, port.finish_start = self.resume, self.finish_start
        creation = f.gates.register_generated_creation(f.physical, f.created)
        port.connect_durable_registry(f.gates, f.physical, creation)
        setup.port = port
        self.probe = flow._InterruptedOperationProbe(port, setup)
        port._bind_interrupted_probe(self.probe)

    def structure(self, name):
        if name == "FILETIME":
            return SimpleNamespace(low=0, high=0, _inert_size=8)
        if name == "JOBOBJECT_BASIC_ACCOUNTING_INFORMATION":
            return SimpleNamespace(active_processes=0, _inert_size=48)
        raise AssertionError("unlisted inert structure: " + name)

    def call(self, name, *args):
        p, port = self.f.primitives, self.port
        if name in ("CreateFileW", "SetFilePointerEx", "ReadFile", "WriteFile", "FlushFileBuffers"):
            assert not port.lifecycle._lock._is_owned(), "journal seam called under manager lock"
            result = self.journal_call(name, *args)
            if name == "FlushFileBuffers" and result:
                self.setup.flush_successes += 1
                gate_attempt = self.f.gates.attempts[self.f.physical]
                self.setup.created_handle = gate_attempt.handle
                self.events.append("flush")
                if self.during_sync is not None:
                    self.during_sync()
            return result
        assert not port.lifecycle._lock._is_owned(), "native seam called under manager lock"
        p.api.calls.append((name, args))
        self.events.append(name)
        worker = port.worker
        if name == "GetProcessTimes":
            assert worker is not None and args[0] == p._owned(worker.process)
            args[1].low, args[1].high = self.creation_time, 0
            return 1
        if name == "TerminateJobObject":
            assert worker is not None and args == (p._owned(worker.job), 1)
            self.stop_requests += 1
            return 1
        if name == "TerminateProcess":
            raise AssertionError("published assigned worker must use its owned job")
        if name == "WaitForSingleObject":
            assert args[0] == p._owned(worker.process) and 0 <= args[1] <= 5000
            return self.wait_result
        if name == "GetExitCodeProcess":
            assert args[0] == p._owned(worker.process)
            args[1].value = self.exit_code
            return 1
        if name == "QueryInformationJobObject":
            assert args[0] == p._owned(worker.job) and args[1] == 1
            assert args[3] == 48
            args[2].active_processes = self.job_active
            args[4].value = 48
            return 1
        if name == "CloseHandle":
            matches = [h for h in p.handles if h.value == args[0] and not h.closed]
            assert len(matches) == 1 and not matches[0].unconfirmed
            handle = matches[0]
            if self.before_close is not None:
                self.before_close(handle)
            if handle is self.fail_handle:
                p.api.ffi.error = 5
                return 0
            if handle is self.setup.created_handle:
                self.setup.before_interrupted_close(args)
                assert self.f.disk.owner == (p.api, handle.value)
                self.f.disk.owner = None
            return 1
        raise AssertionError("unlisted inert native call: " + name)

    def create_suspended(self, protection, permit, startup):
        port, p = self.port, self.f.primitives
        record = port.lifecycle._records[port.key]
        assert type(startup) is flow.adapter._OwnedASRStart
        assert startup.policy is port.adapter_profile and startup.binding is port.generated_binding
        assert startup.usage == "reliability" and permit is record.permit
        assert record.protection is protection and record.phase is Phase.NATIVE_RESERVED
        assert type(record.owner) is OwnedSession and record.owner._manager is port.lifecycle
        assert port.binding_calls == 1 and port.adapter_startup is None
        port.adapter_startup, port.permit, port._start_attempted = startup, permit, True
        port.authority_events.append("inert_start_after_actual_adapter_binding")
        self.owner, self.record = record.owner, record
        self.token = port.lifecycle._token(port.key)
        self.setup.before_process("CreateProcessW")
        process, thread, job = [p._retain(9000 + i, name)
            for i, name in enumerate(("process", "thread", "job"))]
        worker = WorkerRecord(process=process, thread=thread, job=job,
            read_set=protection, creation_time=self.creation_time, assigned=True,
            creation_info=SimpleNamespace(pid=123))
        port.worker = worker
        p.workers.append(worker)
        protection.worker_reserved = True
        pair = PipePair(server=p._retain(9010, "pipe-server"),
            client=p._retain(9011, "pipe-client"), worker=worker, read_set=protection)
        port.pair = pair
        self.pipes.pairs.append(pair)
        # Simulates confirmed parent-side retirement of the inherited endpoint.
        p._close(pair.client)
        # The fixed native boundary contains five read duplicates plus control.
        # These are inert retained owners, not an observation of inheritance.
        worker.inherited_copies = [p._retain(9020 + i, "inert-inherited-copy") for i in range(6)]
        for duplicate in worker.inherited_copies:
            p._close(duplicate)
        port.channel = InertChannel(self)
        port.handshake = InertHandshake(self)
        return worker

    def resume(self, worker):
        assert worker is self.port.worker and not worker.resumed
        assert self.token.phase == "WORKER_BOUND" and not self.token.revoked
        self.setup.before_process("ResumeThread")
        self.port._resume_attempted = worker.resumed = True
        return True

    def finish_start(self, worker, permit, startup):
        assert worker is self.port.worker and permit is self.port.permit
        assert startup is self.port.adapter_startup and worker.resumed
        assert self.record.phase is Phase.NATIVE_RESERVED
        self.port.adapter_start_payload = {"inert_adoption_and_policy": True}
        self.port.adapter_start_ack = {"inert_adoption_and_policy": True}
        self.events.append("inert_finish_start")
        return True

    def write_frame(self, pair, frame, expires):
        assert pair is self.port.pair and expires == 11.0
        with self.pipes._frame_operation(pair):
            assert self.owner._active == 1 and not self.owner._revoked
            operation, payload = frame
            if operation == "begin":
                assert payload == {"manifest_sha256": self.port.manifest}
                self.events.append("inert_begin")
                return
            assert operation == "next"
            action = payload["action"]
            self.transport_actions.append(action)
            op = flow.operation_flow
            if action == "admit_generated_media":
                assert payload == {"action": action, "media_id": op.MEDIA_ID}
                response = "done", op.contract_payload(self.port.channel.binding)
            elif action == "begin_generated_transcription":
                assert payload["media_id"] == op.MEDIA_ID
                assert payload["options"] == op.fixed_options(self.request)
                response = "done", {"cursor_id": op.CURSOR_ID, "started": True, "produced_segments": 0}
            elif action == "next_generated_segment":
                index = payload["index"]
                assert payload == {"action": action, "cursor_id": op.CURSOR_ID, "index": index}
                assert index in (0, 1)
                response = "segment", {"cursor_id": op.CURSOR_ID, "index": index, "segment": op.SEGMENTS[index]}
            else:
                raise AssertionError("unexpected extra wire request: " + action)
            self.pending_frames.append(response)

    def read_frame(self, pair, expires):
        assert pair is self.port.pair and expires == 11.0
        with self.pipes._frame_operation(pair):
            assert self.owner._active == 1 and len(self.pending_frames) == 1
            return self.pending_frames.pop(0)

    def interrupted(self, *, observe=True):
        try:
            with flow.generated_authority_seams(self.port):
                with flow.adapter.faster_whisper_session(flow.CHOICE, model_root=self.port.cwd) as facade:
                    self.facade = facade
                    assert type(facade) is OperationFacade and facade._session is self.owner
                    ticket = self.port.issue_generated_media_ticket(self.owner)
                    self.request = TranscribeRequest(ticket, language="en")
                    self.stream = facade.transcribe(self.request)
                    self.first_segment = next(self.stream)
                    next(self.stream)
        except KeyboardInterrupt as error:
            assert error is self.probe.error
            self.original_error = error
            if observe:
                self.probe.observe_interruption(error)
        else:
            raise AssertionError("actual admitted second next must raise the fixed interruption")
        return self

    def coordinate(self):
        return flow.InterruptedCleanupCoordinator(self.port).coordinate(self.probe, self.owner, self.record)

    def raw(self):
        return bytes(self.f.disk.data)

    def phases(self):
        return [row["phase"] for row in decode_journal(self.raw())[0]]


class InterruptedOwnerRetirementContracts(unittest.TestCase):
    def assert_quarantine(self, f):
        self.assertIs(f.record.phase, Phase.QUARANTINED)
        self.assertTrue(f.owner._revoked and f.token.revoked)
        self.assertTrue(f.port.pair.unconfirmed and f.port.worker.unconfirmed and f.port.read_set.unconfirmed)
        self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
        self.assertFalse(f.setup.created_handle.closed)

    def assert_no_new_effects(self, f, before):
        self.assertEqual(tuple(f.f.primitives.api.calls), before)
        self.assertEqual(f.phases(), ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])
        self.assert_quarantine(f)

    def test_actual_adapter_interruption_preserves_error_and_quarantine(self):
        f = InterruptedFixture().interrupted()
        self.assertIs(f.original_error, f.probe.error)
        self.assertTrue(any("Owned ASR cleanup remains unconfirmed" in note for note in f.original_error.__notes__))
        self.assertIs(type(f.owner), OwnedSession)
        self.assertIs(type(f.facade), OperationFacade)
        self.assertEqual(f.owner._active, 0)
        self.assertFalse(f.stream._next_active or f.port._operation_active or f.port.pair.active)
        self.assertEqual(f.port.pair.operations, [])
        self.assertEqual(f.pending_frames, [])
        self.assertEqual(f.stream._segments, 1)
        self.assertEqual(f.port._next_index, 2)
        self.assertEqual(f.transport_actions, ["admit_generated_media", "begin_generated_transcription",
            "next_generated_segment", "next_generated_segment"])
        self.assertEqual(f.port.operation_events, f.transport_actions)
        self.assertEqual(f.setup.flush_successes, 4)
        self.assertGreater(f.probe.quarantine_revision, f.probe.revision)
        self.assertEqual(f.probe.quarantine_revision, f.token.revision)
        self.assertEqual(f.probe.quarantine_raw, f.token.raw)
        self.assertEqual(len(decode_journal(f.probe.raw)[0]), 3)
        self.assertEqual(len(decode_journal(f.probe.quarantine_raw)[0]), 4)
        self.assertTrue(f.port.pair.forced_stop_attempted and f.port.pair.forced_process_stop_observed)
        self.assertEqual(f.stop_requests, 1)
        self.assertFalse(f.port.worker.shutdown_started)
        self.assert_quarantine(f)
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaisesRegex(ReservationRefused, "ordinary_completion_requires_unrevoked_owner"):
            f.port.reservations.complete(f.token, None)
        with self.assertRaises(CleanupUnconfirmed):
            f.port.lifecycle.reconcile_retired_owner(f.owner)
        with self.assertRaises(SessionClosed):
            f.facade.transcribe(f.request)
        with self.assertRaises(SessionClosed):
            next(f.stream)
        self.assert_no_new_effects(f, before)

    def test_confirmed_idle_owner_retires_and_reconciles_once(self):
        f = InterruptedFixture().interrupted()
        self.assertTrue(f.coordinate())
        self.assertEqual(f.stop_requests, 1)
        self.assertIs(f.record.phase, Phase.RELEASED)
        self.assertIsNone(f.record.protection)
        self.assertTrue(f.owner._revoked and f.token.revoked and f.owner._closed_verified)
        self.assertTrue(f.port.pair.unconfirmed and f.port.worker.unconfirmed and f.port.read_set.unconfirmed)
        self.assertTrue(f.port.pair.closed and f.port.read_set.released)
        self.assertTrue(all(h.closed and not h.unconfirmed for h in
            (f.port.pair.server, f.port.pair.client, f.port.worker.process,
             f.port.worker.thread, f.port.worker.job, *f.port.read_set.members)))
        self.assertFalse(f.port._retired(f.port.worker))
        self.assertTrue(f.port._interrupted_retired(f.port.worker))
        self.assertEqual(f.setup.flush_successes, 5)
        self.assertEqual(f.phases(), ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"])
        self.assertTrue(f.setup.created_handle.closed)
        self.assertNotIn(f.f.physical, f.f.gates._held)
        result = f.setup.complete_interrupted_recovery()
        self.assertEqual(result["before_recovery_sha256"], hashlib.sha256(f.probe.quarantine_raw).hexdigest())
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaises(CleanupUnconfirmed):
            f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
        with self.assertRaises(SessionClosed):
            next(f.stream)
        self.assertEqual(tuple(f.f.primitives.api.calls), before)

    def test_foreign_stale_active_or_pending_attempt_refuses(self):
        for fault in ("foreign", "record", "token", "delegate", "active", "pending", "reentrant", "worker",
                      "primitives", "pair_registration", "protection", "permit", "revision", "head"):
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                manager, owner = f.port.lifecycle, f.owner
                if fault == "foreign": owner = object()
                elif fault == "record": manager._records[f.port.key] = object()
                elif fault == "token": manager._tokens[f.port.key] = object()
                elif fault == "delegate": manager._delegate = object()
                elif fault == "active": owner._active = 1
                elif fault == "pending": f.token.pending = object()
                elif fault == "reentrant": manager._interrupted_retirements[f.port.key] = object()
                elif fault == "worker": f.token.worker = object()
                elif fault == "primitives": f.port.primitives = object()
                elif fault == "pair_registration": f.pipes.pairs.clear()
                elif fault == "protection": f.record.protection = object()
                elif fault == "permit": f.port.permit = object()
                elif fault == "revision": f.token.revision += 1
                else: f.probe.quarantine_head = "0" * 64
                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises((CleanupUnconfirmed, LifecycleUnavailable, KernelUnconfirmed)):
                    manager.retire_and_reconcile_interrupted_owner(owner)
                self.assert_no_new_effects(f, before)
        # The retained bound method cannot be replaced after the fixed boundary.
        f = InterruptedFixture().interrupted()
        called = []
        def substitute(attempt):
            called.append(attempt)
            return object()
        before = tuple(f.f.primitives.api.calls)
        with replaced(f.port, "retire_interrupted_worker", substitute):
            with self.assertRaises((CleanupUnconfirmed, KernelUnconfirmed)):
                f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
        self.assertEqual(called, [])
        self.assert_no_new_effects(f, before)
        self.assertFalse(f.owner._closed_verified)
        self.assertIs(f.record.protection, f.port.read_set)
        # A foreign value and a real witness from an already completed owner are
        # both refused before any retirement or persistence for the next owner.
        prior = InterruptedFixture().interrupted()
        self.assertTrue(prior.coordinate())
        for label, witness in (("foreign_witness", object()), ("stale_witness", prior.port._interrupted_witness)):
            with self.subTest(fault=label):
                g = InterruptedFixture().interrupted()
                g.port._interrupted_witness = witness
                before = tuple(g.f.primitives.api.calls)
                with self.assertRaises(CleanupUnconfirmed):
                    g.port.lifecycle.retire_and_reconcile_interrupted_owner(g.owner)
                self.assert_no_new_effects(g, before)
                self.assertFalse(g.owner._closed_verified)
        # A lower close callback changes an identity after work has begun. The
        # manager must refuse publication; actual partial closures stay visible.
        h = InterruptedFixture().interrupted()
        def change_permit_at_last_member(handle):
            if handle is h.port.read_set.members[0]:
                h.port.permit = object()
        h.before_close = change_permit_at_last_member
        with self.assertRaises((CleanupUnconfirmed, KernelUnconfirmed)):
            h.port.lifecycle.retire_and_reconcile_interrupted_owner(h.owner)
        self.assertTrue(all(member.closed for member in h.port.read_set.members))
        self.assertFalse(h.owner._closed_verified)
        self.assertIs(h.record.protection, h.port.read_set)
        self.assert_quarantine(h)
        self.assertEqual(h.phases(), ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])

    def test_retained_io_or_uncertain_handle_refuses_without_retirement(self):
        for fault in ("active_pair", "retained_io", "process", "thread", "job", "server",
                      "closed_client_uncertain", "closed_client_foreign", "closed_client_reopened",
                      "member", "inherited"):
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                held_buffer = None
                if fault == "active_pair": f.port.pair.active = True
                elif fault == "retained_io":
                    held_buffer = bytearray(b"retained generated pending bytes")
                    f.port.pair.operations.append(PendingIO(f.port.pair.server, buffer=held_buffer, submitted=True))
                elif fault in ("process", "thread", "job"): getattr(f.port.worker, fault).unconfirmed = True
                elif fault == "server": f.port.pair.server.unconfirmed = True
                elif fault == "closed_client_uncertain": f.port.pair.client.unconfirmed = True
                elif fault == "closed_client_foreign":
                    f.port.pair.client = HandleRecord(99999, "pipe-client", closed=True)
                elif fault == "closed_client_reopened": f.port.pair.client.closed = False
                elif fault == "member": f.port.read_set.members[0].unconfirmed = True
                else: f.port.worker.inherited_copies[0].unconfirmed = True
                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises((CleanupUnconfirmed, KernelUnconfirmed)):
                    f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
                self.assert_no_new_effects(f, before)
                if held_buffer is not None:
                    self.assertIs(f.port.pair.operations[0].buffer, held_buffer)
                self.assertFalse(f.owner._closed_verified)
                self.assertEqual(f.stop_requests, 1)

    def test_unobserved_exit_nonempty_job_or_close_failure_retains_custody(self):
        for fault in ("creation", "wait", "still_active", "job", "close"):
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                if fault == "creation": f.creation_time += 1
                elif fault == "wait": f.wait_result = 258
                elif fault == "still_active": f.exit_code = 259
                elif fault == "job": f.job_active = 1
                else: f.fail_handle = f.port.pair.server
                with self.assertRaises((CleanupUnconfirmed, KernelUnconfirmed, OSError)):
                    f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
                self.assert_quarantine(f)
                self.assertFalse(f.owner._closed_verified)
                self.assertIs(f.record.protection, f.port.read_set)
                self.assertEqual(f.stop_requests, 1)
                self.assertEqual(f.phases(), ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])
                if fault == "close":
                    self.assertTrue(f.port.pair.server.unconfirmed)
                    self.assertFalse(f.port.worker.process.closed)

    def test_reentrant_or_clear_failure_preserves_first_error_and_gate(self):
        f = InterruptedFixture().interrupted()
        observations = []
        def during_sync():
            self.assertFalse(f.port.lifecycle._lock._is_owned())
            with self.assertRaises(CleanupUnconfirmed):
                f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
            observations.append(f.record.phase)
        f.during_sync = during_sync
        self.assertTrue(f.coordinate())
        self.assertEqual(observations, [Phase.QUARANTINED])
        for fault in ("flush", "revision", "head", "observer"):
            with self.subTest(fault=fault):
                g = InterruptedFixture().interrupted(observe=fault != "observer")
                if fault == "flush": g.f.primitives.api.fail_sync = True
                elif fault == "revision": g.during_sync = lambda: g.port.reservations.revoke_local(g.token)
                elif fault == "head": g.probe.quarantine_head = "0" * 64
                else: g.setup.flush_successes = 3
                with self.assertRaises(KeyboardInterrupt) as seen:
                    g.coordinate()
                self.assertIs(seen.exception, g.original_error)
                self.assertTrue(any("cleanup" in note.lower() or "reconcil" in note.lower()
                    for note in seen.exception.__notes__))
                self.assert_quarantine(g)
                self.assertEqual(g.stop_requests, 1)
