"""Generated journal/fake kernel controls; no process, model or filesystem use.

Actual manager, owner, lease, service, Windows journal, probe and observer run.
Process start/join and pipe retirement below are explicit in-memory seams. They
do not qualify native startup, authenticated IPC or observed Windows teardown.
"""
from types import SimpleNamespace
import unittest

import generated_adapter_flow as flow
from generated_journal_setup import GeneratedJournalSetup
from durable_lifecycle import DurableOwnedRuntimeFactory
from snapshot_lifecycle import Phase, CleanupUnconfirmed, LifecycleUnavailable, SessionClosed, TranscribeRequest
from snapshot_reservations import ReservationRefused, decode_journal
from reservation_file_port import PersistenceUnconfirmed
import test_windows_reservations as fixtures

KernelUnconfirmed = flow.operation_flow.adoption_flow.KernelUnconfirmed


class RecoveryFixture:
    def __init__(self, *, armed=True):
        self.f = fixtures.Fixture()
        f = self.f
        paths = flow.fixed_paths(f.snapshot.path)
        expected = tuple((path, fixtures.FileIdentity("\\\\?\\" + path, 7, bytes([20 + i]) * 16,
                    len(flow.GENERATED[name]), 1, False))
                    for i, (name, path) in enumerate(zip(flow.NAMES, paths)))
        self.port = port = flow.GeneratedLifecyclePort(f.primitives, SimpleNamespace(), expected,
            "unused-generated-executable", (), f.snapshot.path, (), "1" * 64, "a" * 64,
            flow.namespace_digest(), "b" * 64, b"k" * 32, b"p" * 32, "positive", operation_mode="cancel")
        self.setup = setup = GeneratedJournalSetup(f.primitives, SimpleNamespace(calls=f.primitives.api.calls), port.cwd)
        # Existing Fixture owns generated directory/journal metadata. open() and
        # its real CREATE_NEW path are deliberately not invoked in this harness.
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
                if setup._recovery_probe is None:
                    setup.before_close((handle.value,))
                else:
                    setup.before_recovery_close((handle.value,))
            return close(handle)
        f.primitives._close = fake_close

        def create(protection, permit, profile):
            assert protection is port.read_set and permit is port.lifecycle._records[port.key].permit
            setup.before_process("CreateProcessW")
            port.permit = permit
            handles = [f.primitives._retain(9000 + i, kind)
                       for i, kind in enumerate(("process", "thread", "job"))]
            port.worker = SimpleNamespace(read_set=protection, creation_time=456, assigned=True,
                resumed=False, unconfirmed=False, quiescent=False,
                process=handles[0], thread=handles[1], job=handles[2], creation_info=SimpleNamespace(pid=123))
            f.primitives.workers.append(port.worker)
            port.pair = SimpleNamespace(worker=port.worker, operations=[], closed=False, unconfirmed=False)
            return port.worker
        def observe(worker):
            assert worker is port.worker and worker.assigned and not worker.resumed
            return [123, worker.creation_time]
        def resume(worker):
            assert worker is port.worker
            setup.before_process("ResumeThread")
            worker.resumed = True
            return True
        def join(worker, permit):
            assert worker is port.worker and permit is port.permit
            worker.quiescent = True
            port.exit_observation = {"child_native_exit": 0, "process_wait_observed": True, "job_active_processes": 0}
            return True
        def retire_pair(pair):
            assert pair is port.pair and pair.worker.quiescent and not pair.operations and not pair.unconfirmed
            pair.closed = True
            return True
        def close_worker(worker):
            assert worker is port.worker and worker.quiescent and port.pair.closed
            for handle in (worker.process, worker.thread, worker.job):
                f.primitives._close(handle)
        port.create_suspended, port.observe_owned_worker, port.resume = create, observe, resume
        port.finish_start = lambda worker, permit, profile: worker is port.worker and permit is port.permit
        port.close_and_join = join
        port.pipes.retire_endpoint = retire_pair
        f.primitives.close_quiescent_worker_handles = close_worker
        creation = f.gates.register_generated_creation(f.physical, f.created)
        port.connect_durable_registry(f.gates, f.physical, creation)
        setup.port = port
        self.probe = flow._RetiredClearProbe(port, setup)
        if armed:
            port._bind_retired_clear_probe(self.probe)

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

    def exit_retired(self):
        assert self.owner.close_and_join() is True
        self.lease.confirm_native_closed()
        return self.lease.__exit__(None, None, None)

    def interrupted(self):
        self.start()
        try:
            self.exit_retired()
        except KeyboardInterrupt as error:
            if error is not self.probe.error:
                raise
            self.probe.observe_interruption(error)
        else:
            raise AssertionError("Expected fixed pre-clear interruption")
        return self

    def raw(self):
        return bytes(self.f.disk.data)


class RetiredOwnerRecoveryContracts(unittest.TestCase):
    def test_fixed_interruption_consumes_witness_without_clear_or_release(self):
        f = RecoveryFixture().interrupted()
        self.assertIsNone(f.port._completion)
        self.assertTrue(f.probe.observed)
        self.assertEqual(f.raw(), f.probe.raw)
        self.assertEqual([r["phase"] for r in decode_journal(f.raw())[0]], ["INITIALIZED", "RESERVED", "WORKER_BOUND"])
        self.assertEqual(f.setup.flush_successes, 3)
        self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
        self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
        self.assertFalse(f.setup.created_handle.closed)
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaisesRegex(ReservationRefused, "ordinary_completion_requires_unrevoked_owner"):
            f.port.reservations.complete(f.token, None)
        self.assertEqual(tuple(f.f.primitives.api.calls), before)

    def test_explicit_manager_clear_once_keeps_retained_authority_revoked(self):
        f = RecoveryFixture().interrupted()
        self.assertTrue(f.port.lifecycle.reconcile_retired_owner(f.owner))
        self.assertIs(f.owner._record.phase, Phase.RELEASED)
        self.assertTrue(f.owner._revoked and f.token.revoked)
        self.assertEqual(f.setup.flush_successes, 4)
        self.assertTrue(f.setup.created_handle.closed)
        self.assertNotIn(f.f.physical, f.f.gates._held)
        self.assertNotIn(f.f.physical, f.f.gates.attempts)
        before = tuple(f.f.primitives.api.calls)
        with self.assertRaises(SessionClosed):
            f.facade.transcribe(TranscribeRequest(object()))
        with self.assertRaises(CleanupUnconfirmed):
            f.port.lifecycle.reconcile_retired_owner(f.owner)
        self.assertFalse(f.lease.__exit__(None, None, None))
        self.assertEqual(tuple(f.f.primitives.api.calls), before)
        self.assertTrue(f.setup.complete_recovery()["old_owner_still_revoked"])

    def test_foreign_changed_or_active_owner_refuses_before_clear(self):
        for fault in ("foreign", "record", "token", "service", "worker", "permit", "active", "protection", "verified"):
            with self.subTest(fault=fault):
                f = RecoveryFixture().interrupted()
                manager, owner = f.port.lifecycle, f.owner
                if fault == "foreign": owner = object()
                elif fault == "record": manager._records[f.port.key] = object()
                elif fault == "token": manager._tokens[f.port.key] = object()
                elif fault == "service": manager._reservations = object()
                elif fault == "worker": f.token.worker = object()
                elif fault == "permit": f.owner._record.permit = None
                elif fault == "active": f.owner._active = 1
                elif fault == "protection": f.owner._record.protection = object()
                else: f.owner._closed_verified = False
                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises((LifecycleUnavailable, CleanupUnconfirmed)):
                    manager.reconcile_retired_owner(owner)
                self.assertEqual(tuple(f.f.primitives.api.calls), before)
                self.assertEqual(f.raw(), f.probe.raw)
                self.assertFalse(f.setup.created_handle.closed)

    def test_retirement_uncertainty_refuses_fresh_service_observation(self):
        for fault in ("pending", "pipe", "worker", "guards", "handle", "creation"):
            with self.subTest(fault=fault):
                f = RecoveryFixture().interrupted()
                if fault == "pending": f.port.pair.operations.append(object())
                elif fault == "pipe": f.port.pair.unconfirmed = True
                elif fault == "worker": f.port.worker.unconfirmed = True
                elif fault == "guards": f.port.read_set.released = False
                elif fault == "handle": f.port.worker.process.unconfirmed = True
                else: f.port.worker.creation_time += 1
                before = tuple(f.f.primitives.api.calls)
                with self.assertRaises(KernelUnconfirmed):
                    f.port.lifecycle.reconcile_retired_owner(f.owner)
                self.assertEqual(tuple(f.f.primitives.api.calls), before)
                self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)

    def test_reentrant_recovery_is_refused_without_manager_lock_over_io(self):
        f = RecoveryFixture().interrupted()
        observations = []
        def during_sync():
            self.assertFalse(f.port.lifecycle._lock._is_owned())
            with self.assertRaises(CleanupUnconfirmed):
                f.port.lifecycle.reconcile_retired_owner(f.owner)
            observations.append(f.owner._record.phase)
        f.during_sync = during_sync
        self.assertTrue(f.port.lifecycle.reconcile_retired_owner(f.owner))
        self.assertEqual(observations, [Phase.QUARANTINED])
        self.assertEqual(f.setup.flush_successes, 4)

    def test_fake_flush_and_identity_failures_keep_quarantine_without_retry(self):
        for fault in ("flush", "identity"):
            with self.subTest(fault=fault):
                f = RecoveryFixture().interrupted()
                if fault == "flush": f.f.primitives.api.fail_sync = True
                else: f.f.primitives.identity_failure = True
                with self.assertRaises((OSError, PersistenceUnconfirmed)):
                    f.port.lifecycle.reconcile_retired_owner(f.owner)
                self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
                self.assertFalse(f.setup.created_handle.closed)
                before = tuple(f.f.primitives.api.calls)
                self.assertFalse(f.lease.__exit__(None, None, None))
                self.assertEqual(tuple(f.f.primitives.api.calls), before)

    def test_revocation_during_fake_flush_refuses_gate_release(self):
        f = RecoveryFixture().interrupted()
        f.during_sync = lambda: f.port.reservations.revoke_local(f.token)
        with self.assertRaisesRegex(ReservationRefused, "completion_revoked_before_release"):
            f.port.lifecycle.reconcile_retired_owner(f.owner)
        self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
        self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
        self.assertFalse(f.setup.created_handle.closed)
        self.assertEqual(decode_journal(f.raw())[0][-1]["phase"], "CLEARED")

    def test_changed_manager_publication_retains_block_without_recreating_gate(self):
        f = RecoveryFixture().interrupted()
        original = f.port.reservations.reconcile_live
        def changed_after_success(token):
            result = original(token)
            f.owner._record.permit = object()
            return result
        f.port.reservations.reconcile_live = changed_after_success
        with self.assertRaisesRegex(CleanupUnconfirmed, "changed before manager publication"):
            f.port.lifecycle.reconcile_retired_owner(f.owner)
        self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
        self.assertTrue(f.owner._revoked)
        self.assertNotIn(f.f.physical, f.f.gates._held)
        self.assertTrue(f.setup.created_handle.closed)

    def test_probe_and_observer_refuse_unarmed_premature_or_wrong_attempt(self):
        f = RecoveryFixture(armed=False).start()
        with self.assertRaises(KernelUnconfirmed):
            f.port._bind_retired_clear_probe(f.probe)
        with self.assertRaisesRegex(KernelUnconfirmed, "fixed_recovery_close_observer"):
            f.setup.before_recovery_close((f.setup.created_handle.value,))
        with self.assertRaises(RuntimeError):
            f.setup.complete_recovery()
        f.exit_retired()
        self.assertEqual(f.setup.complete()["phases"], ["INITIALIZED", "RESERVED", "WORKER_BOUND", "CLEARED"])
        g = RecoveryFixture().interrupted()
        g.probe.service_attempt = object()
        with self.assertRaises(KernelUnconfirmed):
            g.port.lifecycle.reconcile_retired_owner(g.owner)
        self.assertFalse(g.setup.created_handle.closed)

    def test_changed_head_and_stale_confirmation_refuse_before_release(self):
        for fault in ("head", "confirmation"):
            with self.subTest(fault=fault):
                f = RecoveryFixture().interrupted()
                if fault == "head": f.probe.head = "0" * 64
                else: f.token.journal.confirmed_revision = -1
                with self.assertRaises((KernelUnconfirmed, PersistenceUnconfirmed)):
                    f.port.lifecycle.reconcile_retired_owner(f.owner)
                self.assertIs(f.owner._record.phase, Phase.QUARANTINED)
                self.assertIs(f.f.gates._held[f.f.physical], f.token.gate)
                self.assertFalse(f.setup.created_handle.closed)
