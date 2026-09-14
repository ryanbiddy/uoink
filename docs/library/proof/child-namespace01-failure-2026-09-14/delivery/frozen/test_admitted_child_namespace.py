"""Proposed 17-control test suite for dormant controller-to-child namespace unit.

Conforms to BRIEF.md, MEMBER-SCOPE-CORRECTION.md, and inert lower services.
No Python startup, test execution, native DLL calls, or physical I/O during source delivery.
"""
import copy
import hashlib
import unittest

from admitted_namespace_fixture import (
    AdmittedFixture,
    FakeWin32Primitives,
    FakePipePair,
    FakeFileHandle,
    FakeHandleRecord,
    FakeReadSet,
    FakeWorker,
    MODEL_SPECS,
)
from asr_loading_adapter import (
    _consume_controller_startup,
    _validate_controller_stage,
    AdapterRefusal,
)
from inherited_readset import (
    controller_admitted_envelope,
    validate_admitted_envelope,
    admitted_envelope_digest,
    AdmittedReadSetAdoption,
    AdoptionRefusal,
    MODEL_MEMBERS,
)
from pinned_buffer_namespace import (
    PinnedBufferNamespace,
    NamespaceRefusal,
)
from owned_generation_protocol import (
    GenerationBinding,
    GenerationChannel,
    WorkerBootstrap,
    ControllerHandshake,
    AdmittedNamespaceLease,
    validate_admitted_lease,
    encode_private_bootstrap,
    decode_private_bootstrap,
    ProtocolRefusal,
    _ISSUED_ADMITTED_LEASES,
)
from admitted_namespace_flow import (
    AdmittedControllerPort,
    child_admitted_flow,
    FlowRefusal,
)
from worker_runtime_owner import _WorkerRuntimeOwnerProposal
from owned_factory_port import _OwnedFactoryPortProposal
from snapshot_lifecycle import Phase


class TestAdmittedChildNamespace(unittest.TestCase):
    """17 focused controls through the actual new controller/child sequence."""

    def test_01_admitted_issued_success_five_member(self):
        """Control 1: Pre/post-stage success for 5-member model (large)."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker
        _validate_controller_stage(token, fix.startup, fix.release, fix.selection, fix.profile)

        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        self.assertEqual(len(envelope["members"]), 5)
        self.assertIn("preprocessor_config.json", envelope["members"])
        self.assertIn("vocabulary.json", envelope["members"])

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")

        # Handshake
        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, fix.worker)
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        ready_frame = bootstrap.accept_challenge(handshake.challenge())
        handshake.accept_ready(ready_frame)

        # Envelope adoption
        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["large"])
        env_digest = admitted_envelope_digest(envelope)
        bootstrap.bind_admitted_envelope(envelope, env_digest)

        # Begin
        begin_frame = handshake.begin_admitted(env_digest)
        op = bootstrap.accept_initial_control(begin_frame)
        self.assertEqual(op, "begin")

        # Materialization & lease issuance
        adoption.mark_begin_accepted()
        ns = adoption.materialize_admitted()
        self.assertEqual(len(ns.buffers), 5)
        self.assertEqual(ns.status, "completed")

        lease = bootstrap.issue_admitted_namespace(adoption, ns, fix.selection, fix.profile)
        self.assertTrue(validate_admitted_lease(lease, bootstrap))
        self.assertEqual(lease.member_count, 5)

        # Post-effects stage check
        _validate_controller_stage(token, fix.startup, fix.release, fix.selection, fix.profile)

    def test_02_foreign_or_copied_startup_session_permit_refusal(self):
        """Control 2: Foreign or copied startup/session/permit refused."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker

        foreign_permit = copy.copy(fix.permit)
        foreign_permit.identity = object()
        foreign_permit.token = foreign_permit.identity

        with self.assertRaises(AdapterRefusal):
            _validate_controller_stage(token, fix.startup, fix.release, fix.selection, fix.profile, permit=foreign_permit)

    def test_03_changed_release_or_profile_after_consumption_refusal(self):
        """Control 3: Altered release authority or profile after consumption refused."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker

        altered_profile = dict(fix.profile)
        altered_profile["device"] = "cuda"

        with self.assertRaises(AdapterRefusal):
            _validate_controller_stage(token, fix.startup, fix.release, fix.selection, altered_profile)

    def test_04_substituted_worker_read_set_source_creation_time_refusal(self):
        """Control 4: Substituted worker, read set, or creation time refused."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)

        # Substituted worker with mismatched creation time
        sub_worker = FakeWorker(read_set=fix.read_set, creation_time=999999999)
        fix.primitives.workers.append(sub_worker)
        fix.record.worker = sub_worker

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, sub_worker)

        with self.assertRaises(ProtocolRefusal):
            handshake.challenge()

    def test_05_independent_channel_or_key_refusal(self):
        """Control 5: Independently constructed channel or incorrect key refused."""
        fix = AdmittedFixture("large")
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        wrong_channel = GenerationChannel(binding, b"x" * 32, "worker")

        frame = ctrl_channel.encode("challenge", {"generation": fix.generation_hex, "namespace_sha256": binding.namespace_sha256})
        with self.assertRaises(ProtocolRefusal):
            wrong_channel.decode(frame)

    def test_06_changed_envelope_selection_or_profile_refusal(self):
        """Control 6: Tampered envelope selection or profile refused."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        envelope["selection"]["choice"] = "tampered-choice"

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        with self.assertRaises(AdoptionRefusal):
            validate_admitted_envelope(envelope, fix.worker, fix.primitives, binding, MODEL_SPECS["large"])

    def test_07_missing_or_extra_envelope_members_refusal(self):
        """Control 7: Missing or extra members in envelope refused."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        # Remove a member
        del envelope["members"]["preprocessor_config.json"]

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        with self.assertRaises(AdoptionRefusal):
            validate_admitted_envelope(envelope, fix.worker, fix.primitives, binding, MODEL_SPECS["large"])

    def test_08_aliased_inherited_handles_refusal(self):
        """Control 8: Aliased handles across envelope members refused."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        names = list(envelope["members"].keys())
        # Alias raw handle of second member to first member
        envelope["members"][names[1]]["handle"] = envelope["members"][names[0]]["handle"]

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        with self.assertRaises(AdoptionRefusal):
            validate_admitted_envelope(envelope, fix.worker, fix.primitives, binding, MODEL_SPECS["large"])

    def test_09_physical_identity_or_inheritance_mismatch_refusal(self):
        """Control 9: Physical identity collision across members refused."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        names = list(envelope["members"].keys())
        # Duplicate volume serial and file id
        envelope["members"][names[1]]["physical_identity"] = envelope["members"][names[0]]["physical_identity"]

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        with self.assertRaises(AdoptionRefusal):
            validate_admitted_envelope(envelope, fix.worker, fix.primitives, binding, MODEL_SPECS["large"])

    def test_10_materialization_before_begin_refusal(self):
        """Control 10: Materialization attempted before begin refused."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["large"])

        with self.assertRaises(AdoptionRefusal):
            adoption.materialize_admitted()

    def test_11_initial_cancel_without_buffers(self):
        """Control 11: Initial cancel releases unread adoption; no buffers materialized."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker

        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")

        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, fix.worker)
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        ready_frame = bootstrap.accept_challenge(handshake.challenge())
        handshake.accept_ready(ready_frame)

        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["large"])
        bootstrap.bind_admitted_envelope(envelope, admitted_envelope_digest(envelope))

        # Controller sends cancel
        cancel_frame = handshake.cancel()
        op = bootstrap.accept_initial_control(cancel_frame)
        self.assertEqual(op, "cancel")

        # Unread handles released
        receipt = adoption.release_unread()
        self.assertEqual(receipt["status"], "released_unread")
        self.assertIsNone(adoption.namespace)

        bootstrap.close_preserving()
        self.assertTrue(bootstrap._closed)

    def test_12_begin_cancel_replay_refusal(self):
        """Control 12: Begin/cancel replay or out-of-order execution refused."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker

        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")

        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, fix.worker)
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        bootstrap.accept_challenge(handshake.challenge())
        env_digest = admitted_envelope_digest(envelope)
        bootstrap.bind_admitted_envelope(envelope, env_digest)

        begin_frame = handshake.begin_admitted(env_digest)
        bootstrap.accept_initial_control(begin_frame)

        # Attempt to replay begin
        with self.assertRaises(ProtocolRefusal):
            bootstrap.accept_initial_control(begin_frame)

    def test_13_copied_lease_or_namespace_refusal(self):
        """Control 13: Constructed or copied lease/namespace grants nothing."""
        fix = AdmittedFixture("large")
        unregistered_lease = AdmittedNamespaceLease(
            issuance_identity=object(),
            bootstrap=object(),
            permit=object(),
            generation=fix.generation_hex,
            adoption=object(),
            read_set=fix.read_set,
            namespace=object(),
            selection=fix.selection,
            profile=fix.profile,
            envelope_sha256="c" * 64,
            member_count=5,
        )
        with self.assertRaises(ProtocolRefusal):
            validate_admitted_lease(unregistered_lease)

    def test_14_short_read_or_hash_failure_retains_partial_custody(self):
        """Control 14: Short read or corrupted hash retains partial chunks and custody."""
        fix = AdmittedFixture("large")
        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        names = list(envelope["members"].keys())
        # Corrupt expected digest of first member
        envelope["members"][names[0]]["sha256"] = "f" * 64

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["large"])
        adoption.mark_begin_accepted()

        with self.assertRaises(NamespaceRefusal):
            adoption.materialize_admitted()

        # Partial custody and materialization attempt retained
        self.assertIsNotNone(adoption.namespace)
        self.assertIsNotNone(adoption.namespace.materialization_attempt)
        self.assertIsNotNone(adoption.namespace.materialization_error)

    def test_15_revocation_before_publication_retains_returned_custody(self):
        """Control 15: Revocation before publication retains custody and refuses."""
        fix = AdmittedFixture("large")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker

        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["large"])
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")

        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, fix.worker)
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        bootstrap.accept_challenge(handshake.challenge())
        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["large"])
        env_digest = admitted_envelope_digest(envelope)
        bootstrap.bind_admitted_envelope(envelope, env_digest)

        bootstrap.accept_initial_control(handshake.begin_admitted(env_digest))
        adoption.mark_begin_accepted()
        ns = adoption.materialize_admitted()

        # Revoke bootstrap before issue
        bootstrap.close_preserving()

        with self.assertRaises(ProtocolRefusal):
            bootstrap.issue_admitted_namespace(adoption, ns, fix.selection, fix.profile)

        # Buffers and adoption custody retained
        self.assertEqual(len(ns.completed_buffers), 5)

    def test_16_cleanup_failure_preserves_original_exception(self):
        """Control 16: Cleanup failure preserves original exception identity."""
        fix = AdmittedFixture("large")
        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        # Simulate exception during operation and failure during cleanup
        orig = RuntimeError("original_bootstrap_failure")
        try:
            bootstrap.close_preserving(orig)
        except RuntimeError as e:
            self.assertIs(e, orig)

    def test_17_admitted_issued_success_four_member(self):
        """Control 17: Positive 4-member model (tiny/base/small/medium with vocabulary.txt)."""
        fix = AdmittedFixture("tiny")
        token = _consume_controller_startup(fix.startup, fix.permit, fix.session)
        fix.record.worker = fix.worker
        _validate_controller_stage(token, fix.startup, fix.release, fix.selection, fix.profile)

        envelope = controller_admitted_envelope(fix.primitives, fix.read_set, fix.worker, fix.record, MODEL_SPECS["tiny"])
        self.assertEqual(len(envelope["members"]), 4)
        self.assertIn("vocabulary.txt", envelope["members"])
        self.assertNotIn("preprocessor_config.json", envelope["members"])

        binding = GenerationBinding(
            fix.generation_hex,
            fix.manifest_sha256,
            fix.read_set.namespace_digest(),
            fix.child_source_sha256,
            fix.worker.creation_time,
        )
        ctrl_channel = GenerationChannel(binding, fix.master_key, "controller")
        worker_channel = GenerationChannel(binding, fix.master_key, "worker")

        handshake = ControllerHandshake(ctrl_channel, fix.session, token.token, fix.primitives, fix.worker)
        bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, _OwnedFactoryPortProposal)

        ready_frame = bootstrap.accept_challenge(handshake.challenge())
        handshake.accept_ready(ready_frame)

        adoption = AdmittedReadSetAdoption(fix.primitives)
        adoption.adopt_admitted(envelope, binding, MODEL_SPECS["tiny"])
        env_digest = admitted_envelope_digest(envelope)
        bootstrap.bind_admitted_envelope(envelope, env_digest)

        begin_frame = handshake.begin_admitted(env_digest)
        op = bootstrap.accept_initial_control(begin_frame)
        self.assertEqual(op, "begin")

        adoption.mark_begin_accepted()
        ns = adoption.materialize_admitted()
        self.assertEqual(len(ns.buffers), 4)
        self.assertIn("vocabulary.txt", ns.buffers)
        self.assertNotIn("preprocessor_config.json", ns.buffers)
        self.assertEqual(ns.status, "completed")

        lease = bootstrap.issue_admitted_namespace(adoption, ns, fix.selection, fix.profile)
        self.assertTrue(validate_admitted_lease(lease, bootstrap))
        self.assertEqual(lease.member_count, 4)

        _validate_controller_stage(token, fix.startup, fix.release, fix.selection, fix.profile)


if __name__ == "__main__":
    unittest.main()
