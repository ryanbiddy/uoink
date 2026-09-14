"""Proposed source controls only; no observed test result is claimed."""
from dataclasses import replace
import unittest

import asr_loading_adapter as adapter
import trusted_asr_resolver as resolver
from snapshot_lifecycle import OwnedSession, Phase
from startup_authority_fixture import StartupFixture, changed


class ControllerStartupContracts(unittest.TestCase):
    def test_absent_real_approval_refuses_before_services(self):
        with StartupFixture() as f:
            with changed(resolver, "REAL_APPROVAL", None):
                with self.assertRaises(adapter.AdapterUnavailable):
                    with f.scope():
                        self.fail("unapproved startup yielded")
            self.assertEqual(f.f.events, [])
            self.assertEqual(f.admission_reads, 0)

    def test_missing_or_invalid_profile_refuses_before_services(self):
        for value in (None, "shaped", "bad-compute"):
            with self.subTest(value=value), StartupFixture() as f:
                proposed = replace(f.profile, compute_type="auto") if value == "bad-compute" else value
                with changed(adapter, "RUNTIME_PROFILE", proposed):
                    with self.assertRaises(adapter.AdapterUnavailable):
                        with f.scope():
                            self.fail("invalid profile yielded")
                self.assertEqual(f.f.events, [])
                self.assertEqual(f.admission_reads, 0)

    def test_changed_configuration_after_acquire_prevents_admission(self):
        with StartupFixture() as f:
            f.after_acquire = lambda: setattr(adapter, "RUNTIME_PROFILE", replace(f.profile))
            with self.assertRaises(adapter.AdapterUnavailable):
                with f.scope():
                    self.fail("changed configuration yielded")
            self.assertEqual(f.admission_reads, 0)
            self.assertNotIn("controller_start_service", f.f.events)
            self.assertIs(next(iter(f.manager._records.values())).phase, Phase.RELEASED)

    def test_exact_issued_manifest_selection_admission_and_permit_are_retained(self):
        with StartupFixture() as f:
            with f.issued() as start:
                self.assertIs(adapter._validate_controller_startup(start, start.permit), start)
                self.assertIs(start.release, f.release)
                self.assertIs(start.approval, f.approval)
                self.assertEqual(start.manifest, start.admission.manifest)
                self.assertIsNot(start.manifest, start.admission.manifest)
                self.assertIs(start.selected, next(m for m in start.admission.manifest.models if m.choice == f.choice))
                self.assertIs(start.permit, f.custody(start).permit)
                self.assertIs(start.policy, f.profile)
                self.assertEqual(f.admission_reads, len(start.selected.assets) * 2)
            self.assertFalse(f.custody().active)
            self.assertIs(f.custody().primary_error, f.stop)

    def test_copied_startup_and_reconstructed_selection_have_no_authority(self):
        with StartupFixture() as f, f.issued() as start:
            with self.assertRaises(adapter.AdapterUnavailable):
                adapter._validate_controller_startup(replace(start), start.permit)
            original = start.selected
            try:
                object.__setattr__(start, "selected", replace(original))
                with self.assertRaises(adapter.AdapterUnavailable):
                    adapter._validate_controller_startup(start, start.permit)
            finally:
                object.__setattr__(start, "selected", original)

    def test_changed_release_or_profile_identity_refuses_current_startup(self):
        for name in ("RELEASE_AUTHORITY", "RUNTIME_PROFILE"):
            with self.subTest(name=name), StartupFixture() as f, f.issued() as start:
                with changed(adapter, name, replace(getattr(adapter, name))):
                    with self.assertRaises(adapter.AdapterUnavailable):
                        adapter._validate_controller_startup(start, start.permit)

    def test_same_identity_changed_values_are_refused(self):
        for target in ("profile", "release", "asset"):
            with self.subTest(target=target), StartupFixture() as f, f.issued() as start:
                obj, name, value = ((f.profile, "compute_type", "float32") if target == "profile" else
                    (f.release, "data_root", r"E:\different-inert-root") if target == "release" else
                    (start.manifest.models[0].assets[0], "sha256", "9" * 64))
                old = getattr(obj, name)
                try:
                    object.__setattr__(obj, name, value)
                    with self.assertRaises(adapter.AdapterUnavailable):
                        adapter._validate_controller_startup(start, start.permit)
                finally:
                    object.__setattr__(obj, name, old)

    def test_foreign_permit_and_same_value_foreign_record_are_refused(self):
        with StartupFixture() as f, f.issued() as start:
            with self.assertRaises(adapter.AdapterUnavailable):
                adapter._validate_controller_startup(start, replace(start.permit))
            record = start.permit.record
            f.manager._records[record.key] = replace(record)
            try:
                with self.assertRaises(adapter.AdapterUnavailable):
                    adapter._validate_controller_startup(start, start.permit)
            finally:
                f.manager._records[record.key] = record

    def test_revoked_permit_or_reservation_refuses_without_start(self):
        for target in ("permit", "reservation"):
            with self.subTest(target=target), StartupFixture() as f, f.issued() as start:
                custody = f.custody(start)
                if target == "permit":
                    start.permit.record.permit = object()
                else:
                    f.manager._reservations.revoke_local(custody.token)
                with self.assertRaises(adapter.AdapterUnavailable):
                    adapter._validate_controller_startup(start, start.permit)
                self.assertNotIn("controller_start_service", f.f.events)

    def test_selected_model_mismatch_and_same_value_foreign_admission_refuse(self):
        for target in ("selected", "admission"):
            with self.subTest(target=target), StartupFixture() as f, f.issued() as start:
                custody = f.custody(start)
                old = getattr(custody, target)
                value = next(m for m in start.admission.manifest.models if m.choice != f.choice) if target == "selected" else replace(old)
                try:
                    setattr(custody, target, value)
                    with self.assertRaises(adapter.AdapterUnavailable):
                        adapter._validate_controller_startup(start, start.permit)
                finally:
                    setattr(custody, target, old)

    def test_none_foreign_and_repeated_consumption_refuse_with_actual_factory_session(self):
        with StartupFixture() as f:
            def at_start(start, session):
                custody = f.custody(start)
                self.assertIs(type(session), OwnedSession)
                self.assertIs(start.permit.record.owner, session)
                for value in (None, OwnedSession(f.manager, start.permit.record)):
                    with self.subTest(session="none" if value is None else "foreign"):
                        with self.assertRaises(adapter.AdapterUnavailable):
                            adapter._consume_controller_startup(start, start.permit, value)
                        self.assertIsNone(custody.consumed_by)
                self.assertIs(adapter._consume_controller_startup(start, start.permit, session), start)
                self.assertIs(custody.consumed_by, session)
                with self.assertRaises(adapter.AdapterUnavailable):
                    adapter._consume_controller_startup(start, start.permit, session)
                self.assertIs(custody.consumed_by, session)
                raise f.stop
            f.on_start = at_start
            with self.assertRaises(type(f.stop)) as caught:
                with f.scope() as start:
                    f.factory.open_owned_session(start, start.permit)
            self.assertIs(caught.exception, f.stop)
            self.assertIs(f.custody().consumed_by, f.session)
            self.assertIsNone(f.session._worker)

    def test_first_start_error_retains_startup_session_and_cleanup_failure(self):
        with StartupFixture() as f:
            original = RuntimeError("inert first startup failure")
            def at_start(start, session):
                adapter._consume_controller_startup(start, start.permit, session)
                raise original
            def fail_cleanup(*args):
                raise OSError("inert quarantine failure")
            f.on_start = at_start
            f.kernel.quarantine = fail_cleanup
            with self.assertRaises(RuntimeError) as caught:
                with f.scope() as start:
                    f.factory.open_owned_session(start, start.permit)
            self.assertIs(caught.exception, original)
            self.assertIs(f.custody().primary_error, original)
            self.assertIs(f.custody().startup, start)
            self.assertIs(f.custody().consumed_by, f.session)
            self.assertIs(start.permit.record.owner, f.session)
            self.assertFalse(f.custody().active)
            self.assertTrue(any("quarantine" in note.lower() for note in original.__notes__))
            self.assertIs(start.permit.record.phase, Phase.QUARANTINED)

    def test_binding_failure_retains_admission_custody_before_startup_publication(self):
        with StartupFixture() as f:
            original = RuntimeError("inert second admission failure")
            count = len(resolver.MODEL_SPECS[f.choice][2])
            def fail_second_round(current):
                if current == count + 1:
                    raise original
            f.on_hash = fail_second_round
            with self.assertRaises(RuntimeError) as caught:
                with f.scope():
                    self.fail("binding failure yielded")
            self.assertIs(caught.exception, original)
            retained = [owner for owner in adapter._CONTROLLER_STARTUP_ATTEMPTS.values() if owner.manager is f.manager]
            self.assertEqual(len(retained), 1)
            custody = retained[0]
            self.assertIs(custody.primary_error, original)
            self.assertIs(type(custody.admission), resolver.Admission)
            self.assertIsNone(custody.startup)
            self.assertIsNone(custody.binding)
            self.assertIs(custody.record.phase, Phase.QUARANTINED)
            self.assertNotIn("controller_start_service", f.f.events)

    def test_fixed_real_worker_seam_remains_closed_after_valid_controller_checks(self):
        with StartupFixture() as f:
            f.on_start = lambda start, session: adapter._fixed_real_worker_start(start, start.permit, session)
            with self.assertRaisesRegex(adapter.AdapterUnavailable, "Authenticated child transport"):
                with f.scope() as start:
                    f.factory.open_owned_session(start, start.permit)
            self.assertIsNone(f.custody().consumed_by)
            self.assertIsNone(f.session._worker)
            self.assertNotIn("resume", f.f.events)
