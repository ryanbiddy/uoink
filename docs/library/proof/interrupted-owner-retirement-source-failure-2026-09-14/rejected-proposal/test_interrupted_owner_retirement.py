"""Unexecuted proposed tests for interrupted owned-session retirement.

Actual manager, owner, lease, service, Windows journal, probe, witness and
cleanup coordinator methods run against explicit in-memory seams. No process,
model, Python startup or filesystem execution occurs.
"""
from types import SimpleNamespace
import unittest

import generated_adapter_flow as flow
from generated_journal_setup import GeneratedJournalSetup
from durable_lifecycle import DurableOwnedRuntimeFactory, _InterruptedRetirement
from snapshot_lifecycle import Phase, CleanupUnconfirmed, LifecycleUnavailable, SessionClosed, TranscribeRequest
from snapshot_reservations import ReservationRefused, decode_journal
from reservation_file_port import PersistenceUnconfirmed
import test_windows_reservations as fixtures

KernelUnconfirmed = flow.operation_flow.adoption_flow.KernelUnconfirmed


class InterruptedFixture:
    def __init__(self, *, armed=True):
        self.f = fixtures.Fixture()
        f = self.f
        paths = flow.fixed_paths(f.snapshot.path)
        expected = tuple((path, fixtures.FileIdentity("\\\\?\\" + path, 7, bytes([20 + i]) * 16,
                    len(flow.GENERATED[name]), 1, False))
                    for i, (name, path) in enumerate(zip(flow.NAMES, paths)))
        self.port = port = flow.GeneratedLifecyclePort(f.primitives, SimpleNamespace(), expected,
            "unused-generated-executable", (), f.snapshot.path, (), "1" * 64, "a" * 64,
            flow.namespace_digest(), "b" * 64, b"k" * 32, b"p" * 32, "positive", operation_mode="drain")
        self.setup = setup = GeneratedJournalSetup(f.primitives, SimpleNamespace(calls=f.primitives.api.calls), port.cwd)
        setup.gates, setup.physical = f.gates, f.physical
        setup.scopes = [f.snapshot.read_set, f.registry.read_set]
        setup.journal_path = f.primitives.journal_path
        self.during_sync = None
        call = f.primitives.api.call
        def fake_call(name, *args):
            result = call(name, *args)
            if name == "FlushFileBuffers" and result:
                setup.flush_successes += 1
                if self.during_sync is not None:
                    self.during_sync()
            return result
        f.primitives.api.call = fake_call
        close = f.primitives._close
        def fake_close(handle):
            if handle is setup.created_handle:
                if setup._interrupted_probe is not None and setup._interrupted_probe.armed:
                    setup.before_interrupted_close((handle.value,))
                elif setup._recovery_probe is not None:
                    setup.before_recovery_close((handle.value,))
                else:
                    setup.before_close((handle.value,))
            return close(handle)
        f.primitives._close = fake_close

        def create(protection, permit, profile):
            assert protection is port.read_set and permit is port.lifecycle._records[port.key].permit
            setup.before_process("CreateProcessW")
            port.permit = permit
            handles = [f.primitives._retain(9000 + i, kind)
                       for i, kind in enumerate(("process", "thread", "job"))]
            port.worker = SimpleNamespace(read_set=protection, creation_time=456, assigned=True,
                resumed=False, unconfirmed=False, shutdown_started=False, quiescent=False,
                process=handles[0], thread=handles[1], job=handles[2], creation_info=SimpleNamespace(pid=123))
            f.primitives.workers.append(port.worker)
            server_handle = f.primitives._retain(9010, "pipe_server")
            client_handle = f.primitives._retain(9011, "pipe_client")
            port.pair = SimpleNamespace(worker=port.worker, operations=[], closed=False, unconfirmed=False,
                                        active=False, role="controller", server=server_handle, client=client_handle)
            return port.worker

        def observe(worker):
            assert worker is port.worker and worker.assigned and not worker.resumed
            return [123, worker.creation_time]

        def resume(worker):
            assert worker is port.worker
            setup.before_process("ResumeThread")
            worker.resumed = True
            return True

        port.create_suspended, port.observe_owned_worker, port.resume = create, observe, resume
        port.finish_start = lambda worker, permit, profile: worker is port.worker and permit is port.permit

        if not hasattr(f.primitives, "_creation_time"):
            f.primitives._creation_time = lambda proc: 456
        if not hasattr(f.primitives.api, "checked"):
            def fake_checked(name, *args):
                f.primitives.api.calls.append((name, args))
                return 1
            f.primitives.api.checked = fake_checked
        if not hasattr(f.primitives.api, "structure"):
            def fake_structure(name):
                if name == "JOBOBJECT_BASIC_ACCOUNTING_INFORMATION":
                    return SimpleNamespace(active_processes=self.active_processes_value)
                return SimpleNamespace()
            f.primitives.api.structure = fake_structure
        if not hasattr(f.primitives.api.ffi, "sizeof"):
            f.primitives.api.ffi.sizeof = lambda s: 1
        if not hasattr(f.primitives.api.ffi, "byref"):
            f.primitives.api.ffi.byref = lambda s: s

        self.exit_code_value = 0
        self.active_processes_value = 0
        self.wait_result = 0

        orig_call = f.primitives.api.call
        def extended_call(name, *args):
            if name == "WaitForSingleObject":
                return self.wait_result
            return orig_call(name, *args)
        f.primitives.api.call = extended_call

        orig_checked = f.primitives.api.checked
        def extended_checked(name, *args):
            if name == "GetExitCodeProcess":
                exit_code_ptr = args[1]
                if hasattr(exit_code_ptr, "value"):
                    exit_code_ptr.value = self.exit_code_value
                return 1
            if name == "QueryInformationJobObject":
                accounting_ptr = args[2]
                if hasattr(accounting_ptr, "active_processes"):
                    accounting_ptr.active_processes = self.active_processes_value
                returned_ptr = args[4]
                if hasattr(returned_ptr, "value"):
                    returned_ptr.value = f.primitives.api.ffi.sizeof(accounting_ptr)
                return 1
            return orig_checked(name, *args)
        f.primitives.api.checked = extended_checked

        creation = f.gates.register_generated_creation(f.physical, f.created)
        port.connect_durable_registry(f.gates, f.physical, creation)
        setup.port = port
        self.probe = flow._InterruptedOperationProbe(port, setup)
        if armed:
            port._bind_interrupted_probe(self.probe)

    def start(self):
        port, setup = self.port, self.setup
        self.lease = port.lifecycle.read_lease(port.cwd, flow.CHOICE, flow.REVISION)
        self.lease.__enter__()
        attempt = self.f.gates.attempts[self.f.physical]
        setup.created_handle = attempt.handle
        self.token = self.lease.token
        self.owner = DurableOwnedRuntimeFactory(port.lifecycle).open_owned_session(object(), self.lease.begin_native_session())
        self.facade = self.owner.operations()
        return self

    def interrupted(self):
        self.start()
        port = self.port
        port._next_index = 2
        try:
            self.probe.interrupt_after_exchange(port.worker)
        except KeyboardInterrupt as error:
            with port.lifecycle._lock:
                port.lifecycle._quarantine_preserving(self.owner._record, "Owned operation interrupted", error)
            self.lease.__exit__(type(error), error, None)
            self.probe.observe_interruption(error)
            self.interrupted_error = error
        return self

    def raw(self):
        return bytes(self.f.disk.data)


class InterruptedOwnerRetirementContracts(unittest.TestCase):
    def test_actual_adapter_interruption_preserves_error_and_quarantine(self):
        f = InterruptedFixture().interrupted()
        self.assertIsNone(f.port._completion)
        self.assertTrue(f.probe.observed)
        self.assertEqual(f.raw(), f.probe.quarantine_raw)
        self.assertEqual([r["phase"] for r in decode_journal(f.raw())[0]],
                         ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])
        self.assertEqual(f.setup.flush_successes, 4)
        self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
        self.assertIs(f.owner._record.protection, f.port.read_set)
        self.assertTrue(f.owner._revoked)
        self.assertFalse(f.owner._closed_verified)
        self.assertEqual(f.owner._active, 0)
        self.assertTrue(f.token.revoked)
        self.assertEqual(f.token.phase, "QUARANTINED")
        self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
        self.assertFalse(f.setup.created_handle.closed)
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaisesRegex(ReservationRefused, "ordinary_completion_requires_unrevoked_owner"):
            f.port.reservations.complete(f.token, None)
        self.assertEqual(tuple(f.f.primitives.api.calls), before)
        with self.assertRaises(SessionClosed):
            f.facade.transcribe(TranscribeRequest(object()))

    def test_confirmed_idle_owner_retires_and_reconciles_once(self):
        f = InterruptedFixture().interrupted()
        self.assertTrue(f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner))
        self.assertIs(f.owner._record.phase, Phase.RELEASED)
        self.assertIsNone(f.owner._record.protection)
        self.assertTrue(f.owner._revoked)
        self.assertTrue(f.token.revoked)
        self.assertTrue(f.owner._closed_verified)
        self.assertTrue(f.port.read_set.released)
        self.assertTrue(f.port.pair.closed)
        self.assertTrue(f.port.worker.quiescent)
        self.assertTrue(all(h.closed for h in (f.port.worker.process, f.port.worker.thread, f.port.worker.job)))
        self.assertTrue(all(h.closed for h in f.port.read_set.members))
        self.assertTrue(f.port.pair.server.closed)
        self.assertTrue(f.port.pair.client.closed)
        self.assertEqual(f.setup.flush_successes, 5)
        self.assertEqual([r["phase"] for r in decode_journal(f.raw())[0]],
                         ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"])
        self.assertTrue(f.setup.created_handle.closed)
        self.assertNotIn(f.f.physical, f.f.gates._held)
        self.assertNotIn(f.f.physical, f.f.gates.attempts)
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaises(CleanupUnconfirmed):
            f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
        with self.assertRaises(CleanupUnconfirmed):
            f.port.lifecycle.reconcile_retired_owner(f.owner)
        self.assertEqual(tuple(f.f.primitives.api.calls), before)
        with self.assertRaises(SessionClosed):
            f.facade.transcribe(TranscribeRequest(object()))
        coordinator = flow.InterruptedCleanupCoordinator(f.port)
        self.assertFalse(coordinator.quarantine_validated)

    def test_foreign_stale_active_or_pending_attempt_refuses(self):
        faults = ("foreign", "record", "token", "service", "delegate", "worker", "permit",
                  "active", "unrevoked", "unquarantined", "already_verified", "already_closing",
                  "no_protection", "pending_recovery", "pending_interrupted", "pending_entering")
        for fault in faults:
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                manager, owner = f.port.lifecycle, f.owner
                if fault == "foreign":
                    owner = object()
                elif fault == "record":
                    manager._records[f.port.key] = object()
                elif fault == "token":
                    manager._tokens[f.port.key] = object()
                elif fault == "service":
                    manager._reservations = object()
                elif fault == "delegate":
                    manager._delegate = None
                elif fault == "worker":
                    f.token.worker = object()
                elif fault == "permit":
                    f.owner._record.permit = None
                elif fault == "active":
                    f.owner._active = 1
                elif fault == "unrevoked":
                    f.owner._revoked = False
                elif fault == "unquarantined":
                    f.owner._record.phase = Phase.NATIVE_RUNNING
                elif fault == "already_verified":
                    f.owner._closed_verified = True
                elif fault == "already_closing":
                    f.owner._closing = True
                elif fault == "no_protection":
                    f.owner._record.protection = None
                elif fault == "pending_recovery":
                    manager._retired_recoveries[f.port.key] = object()
                elif fault == "pending_interrupted":
                    manager._interrupted_retirements[f.port.key] = object()
                elif fault == "pending_entering":
                    manager._entering[f.port.key] = object()

                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises((LifecycleUnavailable, CleanupUnconfirmed)):
                    manager.retire_and_reconcile_interrupted_owner(owner)
                self.assertEqual(tuple(f.f.primitives.api.calls), before)
                self.assertEqual(f.raw(), f.probe.quarantine_raw)
                self.assertFalse(f.setup.created_handle.closed)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)

    def test_retained_io_or_uncertain_handle_refuses_without_retirement(self):
        faults = ("pair_none", "pair_active", "pair_operations", "pair_closed", "pair_unconfirmed",
                  "no_primitives", "process_none", "process_unconfirmed", "process_closed",
                  "thread_unconfirmed", "job_unconfirmed", "server_unconfirmed", "client_unconfirmed",
                  "member_unconfirmed", "foreign_handle")
        for fault in faults:
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                if fault == "pair_none":
                    f.port.pair = None
                elif fault == "pair_active":
                    f.port.pair.active = True
                elif fault == "pair_operations":
                    f.port.pair.operations.append(object())
                elif fault == "pair_closed":
                    f.port.pair.closed = True
                elif fault == "pair_unconfirmed":
                    f.port.pair.unconfirmed = True
                elif fault == "no_primitives":
                    f.port.primitives = None
                elif fault == "process_none":
                    f.port.worker.process = None
                elif fault == "process_unconfirmed":
                    f.port.worker.process.unconfirmed = True
                elif fault == "process_closed":
                    f.port.worker.process.closed = True
                elif fault == "thread_unconfirmed":
                    f.port.worker.thread.unconfirmed = True
                elif fault == "job_unconfirmed":
                    f.port.worker.job.unconfirmed = True
                elif fault == "server_unconfirmed":
                    f.port.pair.server.unconfirmed = True
                elif fault == "client_unconfirmed":
                    f.port.pair.client.unconfirmed = True
                elif fault == "member_unconfirmed":
                    f.port.read_set.members[0].unconfirmed = True
                elif fault == "foreign_handle":
                    f.port.worker.process = flow.operation_flow.adoption_flow.win32_conn.HandleRecord(99999, "process")

                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises(CleanupUnconfirmed):
                    f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
                self.assertEqual(tuple(f.f.primitives.api.calls), before)
                self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
                self.assertFalse(f.owner._closed_verified)
                self.assertIsNotNone(f.owner._record.protection)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
                self.assertEqual([r["phase"] for r in decode_journal(f.raw())[0]],
                                 ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])

    def test_unobserved_exit_nonempty_job_or_close_failure_retains_custody(self):
        faults = ("creation_time_changed", "wait_timeout", "exit_still_active", "job_not_empty", "close_failure")
        for fault in faults:
            with self.subTest(fault=fault):
                f = InterruptedFixture().interrupted()
                if fault == "creation_time_changed":
                    f.port.worker.creation_time += 1
                elif fault == "wait_timeout":
                    f.wait_result = 258
                elif fault == "exit_still_active":
                    f.exit_code_value = 259
                elif fault == "job_not_empty":
                    f.active_processes_value = 1
                elif fault == "close_failure":
                    f.f.primitives.close_failure = True

                with self.assertRaises((CleanupUnconfirmed, KernelUnconfirmed, AssertionError, OSError)):
                    f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)

                self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
                self.assertFalse(f.owner._closed_verified)
                self.assertIsNotNone(f.owner._record.protection)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
                self.assertFalse(f.setup.created_handle.closed)
                self.assertEqual([r["phase"] for r in decode_journal(f.raw())[0]],
                                 ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"])

    def test_reentrant_or_clear_failure_preserves_first_error_and_gate(self):
        # Part A: Reentrancy check during sync
        f = InterruptedFixture().interrupted()
        observations = []
        def during_sync():
            self.assertFalse(f.port.lifecycle._lock._is_owned())
            with self.assertRaises(CleanupUnconfirmed):
                f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner)
            observations.append(f.owner._record.phase)
        f.during_sync = during_sync
        self.assertTrue(f.port.lifecycle.retire_and_reconcile_interrupted_owner(f.owner))
        self.assertEqual(observations, [Phase.QUARANTINED])
        self.assertEqual(f.setup.flush_successes, 5)
        self.assertIs(f.owner._record.phase, Phase.RELEASED)

        # Part B: Flush failure during journal write
        g = InterruptedFixture().interrupted()
        g.f.primitives.api.fail_sync = True
        with self.assertRaises(PersistenceUnconfirmed):
            g.port.lifecycle.retire_and_reconcile_interrupted_owner(g.owner)
        self.assertIs(g.owner._record.phase, Phase.QUARANTINED)
        self.assertIs(g.f.gates._held[g.f.physical], g.token.gate)
        self.assertFalse(g.setup.created_handle.closed)

        # Part C: Revocation during sync refuses release
        h = InterruptedFixture().interrupted()
        h.during_sync = lambda: h.port.reservations.revoke_local(h.token)
        with self.assertRaisesRegex(ReservationRefused, "completion_revoked_before_release"):
            h.port.lifecycle.retire_and_reconcile_interrupted_owner(h.owner)
        self.assertIs(h.owner._record.phase, Phase.QUARANTINED)
        self.assertIs(h.f.gates._held[h.f.physical], h.token.gate)
        self.assertFalse(h.setup.created_handle.closed)

        # Part D: State changed before final publication
        k = InterruptedFixture().interrupted()
        original = k.port.reservations.reconcile_live
        def changed_after_success(token):
            result = original(token)
            k.owner._record.permit = object()
            return result
        k.port.reservations.reconcile_live = changed_after_success
        with self.assertRaisesRegex(CleanupUnconfirmed, "changed before manager publication"):
            k.port.lifecycle.retire_and_reconcile_interrupted_owner(k.owner)
        self.assertIs(k.owner._record.phase, Phase.QUARANTINED)
        self.assertTrue(k.owner._revoked)
