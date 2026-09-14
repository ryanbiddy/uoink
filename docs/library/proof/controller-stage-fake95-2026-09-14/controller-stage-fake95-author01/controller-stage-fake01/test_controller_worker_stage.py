"""Unexecuted stage controls using actual startup, lease and factory paths."""
from dataclasses import replace
import unittest

from startup_authority_fixture import adapter, changed
from worker_stage_fixture import WorkerStageFixture
from snapshot_lifecycle import OwnedSession, Phase, CleanupUnconfirmed


class ControllerWorkerStageContracts(unittest.TestCase):
    def check(self, f, startup, session, worker, stage):
        events = list(f.f.events)
        result = adapter._validate_controller_worker_stage(
            startup, startup.permit, session, worker, stage)
        self.assertIs(result, startup)
        self.assertEqual(f.f.events, events)

    def refused(self, f, startup, session, worker, stage, permit=None):
        events = list(f.f.events)
        with self.assertRaises(adapter.AdapterUnavailable):
            adapter._validate_controller_worker_stage(
                startup, startup.permit if permit is None else permit, session, worker, stage)
        self.assertEqual(f.f.events, events)

    def test_actual_finish_start_and_factory_publication(self):
        with WorkerStageFixture() as f:
            def at_finish(startup, session, worker):
                token = f.custody(startup).token
                self.assertIs(startup.permit.record.phase, Phase.NATIVE_RESERVED)
                self.assertEqual(token.phase, "WORKER_BOUND")
                self.assertTrue(token.resume_attempted)
                self.assertIs(token.worker, worker)
                self.assertIs(f.manager._kernel._starts[startup.permit.identity], worker)
                self.assertIsNone(session._worker)
                self.check(f, startup, session, worker, "finish_start")
            f.on_finish = at_finish
            with f.published() as (startup, session, worker):
                self.assertIs(type(session), OwnedSession)
                self.assertIs(session, startup.permit.record.owner)
                self.assertIs(session._worker, worker)
                self.assertIs(worker, f.f.worker)
                self.assertIs(startup.permit.record.phase, Phase.NATIVE_RUNNING)
                self.check(f, startup, session, worker, "published")
                self.assertEqual(f.finish_checks, [(startup, session, worker)])
                self.assertLess(f.f.events.index("create"), f.f.events.index("observe"))
                self.assertLess(f.f.events.index("observe"), f.f.events.index("resume"))
                self.assertLess(f.f.events.index("resume"), f.f.events.index("finish_start"))
            self.assertTrue(f.kernel.joined and f.kernel.released)

    def test_explicit_stage_and_non_none_worker_are_required(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                for stage in (None, "", "reserved", "FINISH_START", object()):
                    with self.subTest(stage=type(stage).__name__ if not isinstance(stage, str) else stage):
                        self.refused(f, startup, session, worker, stage)
                self.refused(f, startup, session, None, "published")
                with self.assertRaises(TypeError):
                    adapter._validate_controller_worker_stage(startup, startup.permit, session, worker)

    def test_finish_and_published_labels_cannot_be_interchanged(self):
        with WorkerStageFixture() as f:
            f.on_finish = lambda start, session, worker: self.refused(
                f, start, session, worker, "published")
            with f.published() as (startup, session, worker):
                self.refused(f, startup, session, worker, "finish_start")

    def test_actual_created_but_unbound_worker_is_refused(self):
        with WorkerStageFixture() as f:
            def at_created(startup, session, worker):
                token = f.custody(startup).token
                self.assertEqual(token.phase, "RESERVED")
                self.assertFalse(token.resume_attempted)
                self.assertIsNone(token.worker)
                self.assertNotIn(startup.permit.identity, f.manager._kernel._starts)
                for stage in ("finish_start", "published"):
                    with self.subTest(stage=stage):
                        self.refused(f, startup, session, worker, stage)
            f.on_created = at_created
            with f.published() as (startup, session, worker):
                self.check(f, startup, session, worker, "published")

    def test_copied_startup_permit_and_foreign_session_refuse(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                self.refused(f, replace(startup), session, worker, "published")
                self.refused(f, startup, session, worker, "published",
                             permit=replace(startup.permit))
                foreign = OwnedSession(f.manager, startup.permit.record)
                self.refused(f, startup, foreign, worker, "published")
                self.refused(f, startup, None, worker, "published")
                self.check(f, startup, session, worker, "published")

    def test_changed_record_phase_is_refused_at_each_real_stage(self):
        with WorkerStageFixture() as f:
            def at_finish(startup, session, worker):
                for phase in Phase:
                    if phase is not Phase.NATIVE_RESERVED:
                        with self.subTest(stage="finish_start", phase=phase.name):
                            with changed(startup.permit.record, "phase", phase):
                                self.refused(f, startup, session, worker, "finish_start")
            f.on_finish = at_finish
            with f.published() as (startup, session, worker):
                for phase in Phase:
                    if phase is not Phase.NATIVE_RUNNING:
                        with self.subTest(stage="published", phase=phase.name):
                            with changed(startup.permit.record, "phase", phase):
                                self.refused(f, startup, session, worker, "published")

    def test_pending_revoked_failed_and_not_resumed_reservations_refuse(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                token = f.custody(startup).token
                values = (("phase", "RESERVED"), ("phase", "QUARANTINED"),
                          ("phase", "CLEARED"), ("pending", object()),
                          ("revoked", True), ("persistence_failure", "unconfirmed"),
                          ("resume_attempted", False))
                for name, value in values:
                    with self.subTest(field=name, value=value if type(value) in (str, bool) else "object"):
                        with changed(token, name, value):
                            self.refused(f, startup, session, worker, "published")

    def test_all_three_worker_bindings_must_be_exact(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                token = f.custody(startup).token
                for foreign in (object(), type(worker)()):
                    with self.subTest(worker=type(foreign).__name__):
                        self.refused(f, startup, session, foreign, "published")
                for owner, name in ((token, "worker"), (session, "_worker")):
                    for value in (None, object()):
                        with self.subTest(binding=name, value="none" if value is None else "foreign"):
                            with changed(owner, name, value):
                                self.refused(f, startup, session, worker, "published")
                starts = f.manager._kernel._starts
                identity = startup.permit.identity
                for value in (None, object()):
                    with self.subTest(binding="retained_start", value="none" if value is None else "foreign"):
                        try:
                            if value is None:
                                del starts[identity]
                            else:
                                starts[identity] = value
                            self.refused(f, startup, session, worker, "published")
                        finally:
                            starts[identity] = worker
                with changed(f.manager, "_kernel", object()):
                    self.refused(f, startup, session, worker, "published")

    def test_changed_configuration_identity_or_values_refuse(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                for name, value in (("RELEASE_AUTHORITY", replace(f.release)),
                                    ("RUNTIME_PROFILE", replace(f.profile)),
                                    ("SNAPSHOT_LIFECYCLE", object()),
                                    ("RUNTIME_FACTORY", object())):
                    with self.subTest(configuration=name):
                        with changed(adapter, name, value):
                            self.refused(f, startup, session, worker, "published")
                previous = f.profile.compute_type
                try:
                    object.__setattr__(f.profile, "compute_type", "float32")
                    self.refused(f, startup, session, worker, "published")
                finally:
                    object.__setattr__(f.profile, "compute_type", previous)
                self.check(f, startup, session, worker, "published")

    def test_live_lease_protection_and_consuming_owner_cannot_be_replaced(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                custody = f.custody(startup)
                substitutions = ((startup.permit.record, "protection", object()),
                                 (startup.permit.record, "owner", object()),
                                 (custody, "consumed_by", object()),
                                 (custody.lease, "_finalization_started", True),
                                 (custody.lease.inner, "_exited", True),
                                 (session, "_active", 1),
                                 (session, "_closing", True))
                for owner, name, value in substitutions:
                    with self.subTest(binding=name):
                        with changed(owner, name, value):
                            self.refused(f, startup, session, worker, "published")
                self.check(f, startup, session, worker, "published")

    def test_actual_reservation_revocation_refuses_and_retains_worker(self):
        with WorkerStageFixture() as f:
            with f.issued() as startup:
                session = f.factory.open_owned_session(startup, startup.permit)
                worker = f.returned_worker
                custody = f.custody(startup)
                f.manager._reservations.revoke_local(custody.token)
                self.refused(f, startup, session, worker, "published")
                self.assertIs(custody.token.worker, worker)
                self.assertIs(f.manager._kernel._starts[startup.permit.identity], worker)
                self.assertIs(session._worker, worker)
            self.assertIs(startup.permit.record.phase, Phase.QUARANTINED)
            self.assertFalse(f.kernel.released)

    def test_actual_close_and_scope_exit_refuse_reuse(self):
        with WorkerStageFixture() as f:
            with f.published() as (startup, session, worker):
                self.assertTrue(session.close_and_join())
                self.refused(f, startup, session, worker, "published")
            self.refused(f, startup, session, worker, "published")
            self.assertTrue(f.kernel.released)
            self.assertNotIn(id(startup), adapter._CONTROLLER_STARTUPS)

    def test_first_finish_error_survives_failed_stop_with_custody_retained(self):
        with WorkerStageFixture() as f:
            original = RuntimeError("inert finish failure")
            def fail_finish(startup, session, worker):
                raise original
            def fail_stop(worker):
                self.assertIs(worker, f.returned_worker)
                raise OSError("inert exact-stop failure")
            f.on_finish = fail_finish
            f.kernel.stop_start_failure = fail_stop
            with self.assertRaises(RuntimeError) as caught:
                with f.scope() as startup:
                    f.factory.open_owned_session(startup, startup.permit)
            self.assertIs(caught.exception, original)
            custody = f.custody(startup)
            self.assertIs(custody.primary_error, original)
            self.assertIs(custody.consumed_by, f.session)
            self.assertIs(custody.token.worker, f.returned_worker)
            self.assertIs(f.manager._kernel._starts[startup.permit.identity], f.returned_worker)
            self.assertIsNone(f.session._worker)
            self.assertFalse(custody.active)
            self.assertIs(startup.permit.record.phase, Phase.QUARANTINED)
            self.assertTrue(any("Exact worker stop raised: OSError" in note for note in original.__notes__))

    def test_actual_lease_exit_during_finish_prevents_publication(self):
        with WorkerStageFixture() as f:
            failures = []
            def exit_lease(startup, session, worker):
                try:
                    f.custody(startup).lease.__exit__(None, None, None)
                except CleanupUnconfirmed as original:
                    failures.append(original)
                    raise
            f.on_finish = exit_lease
            with self.assertRaises(CleanupUnconfirmed) as caught:
                with f.scope() as startup:
                    f.factory.open_owned_session(startup, startup.permit)
            self.assertEqual(len(failures), 1)
            self.assertIs(caught.exception, failures[0])
            self.assertIs(f.custody(startup).primary_error, caught.exception)
            self.assertIsNone(f.session._worker)
            self.assertIs(f.custody(startup).token.worker, f.returned_worker)
            self.assertIn("stop_exact", f.f.events)
            self.refused(f, startup, f.session, f.returned_worker, "finish_start")
