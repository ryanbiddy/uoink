"""Six generated-only engine ownership controls; no backend/native execution.

The unchanged bootstrap fixture builds the real fixed factory/owner transaction
over its retained inert tensor and owned-module types. Fault injection changes
only generated object preparation or a cleanup operation; authority checks,
issuance, capability registration and publication predicates are never replaced.
Fixture teardown is generated bookkeeping only, after the custody assertions.
"""
import unittest

from generated_bootstrap_fixture import fixture
from connection_cases import begin, build, replaced
import generated_engine_objects as objects
import model_binding_registry as registry_module
import owned_factory_port as factory_module
import owned_generation_protocol as protocol
import owned_guard as guard
import worker_runtime_owner as owner_module

EXPECTED_CASES = (
    'test_engine_ownership.EngineOwnershipContracts.test_01_actual_generated_sequence_retains_before_preparation',
    'test_engine_ownership.EngineOwnershipContracts.test_02_missing_or_forged_issuance_refuses_before_constructor',
    'test_engine_ownership.EngineOwnershipContracts.test_03_operation_attempt_and_step_order_are_bound',
    'test_engine_ownership.EngineOwnershipContracts.test_04_each_construction_failure_retains_returned_objects',
    'test_engine_ownership.EngineOwnershipContracts.test_05_reentrant_revoke_or_changed_vad_blocks_publication',
    'test_engine_ownership.EngineOwnershipContracts.test_06_secondary_cleanup_failure_preserves_first_error',
)


class EngineOwnershipContracts(unittest.TestCase):
    def test_01_actual_generated_sequence_retains_before_preparation(self):
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b, seen = f.bootstrap, []
            owner, factory = b.registry, b._factory
            original_model = objects._GeneratedEngineModel.prepare
            original_pipeline = objects._GeneratedEnginePipeline.prepare

            def prepare_model(model):
                attempt = owner._engine_attempt
                self.assertIs(attempt.model, model)
                self.assertIs(attempt.owner, owner)
                self.assertIs(attempt.operation, owner._operation[0])
                self.assertEqual(owner._operation[2], 'engine')
                self.assertTrue(attempt.model_returned)
                self.assertFalse(attempt.pipeline_returned)
                seen.append('model_retained')
                original_model(model)

            def prepare_pipeline(pipeline):
                attempt = owner._engine_attempt
                self.assertEqual(seen, ['model_retained'])
                self.assertIs(attempt.pipeline, pipeline)
                self.assertIs(pipeline.model, attempt.model)
                self.assertTrue(attempt.model.prepared and attempt.pipeline_returned)
                seen.append('pipeline_retained')
                original_pipeline(pipeline)

            with replaced(objects._GeneratedEngineModel, 'prepare', prepare_model):
                with replaced(objects._GeneratedEnginePipeline, 'prepare', prepare_pipeline):
                    self.assertEqual(b._build_generated_engine(), {'generated_engine_constructed': True})
            attempt = owner._engine_attempt
            self.assertEqual(seen, ['model_retained', 'pipeline_retained'])
            self.assertIs(type(factory), factory_module._OwnedFactoryPortProposal)
            self.assertIs(factory._model_capability._registry, owner)
            self.assertIs(attempt.namespace, b._generated_namespace)
            self.assertIs(attempt.product, owner._product)
            self.assertIs(attempt.product.lease, owner._lease)
            self.assertIs(attempt.product.vad.segmentation, factory._completed.model)
            self.assertTrue(attempt.published and attempt.active)
            self.assertIsNone(attempt.failure)
            self.assertIsNone(owner._operation)
            model, pipeline, product = attempt.model, attempt.pipeline, attempt.product
            # These ordinary refusals are unchanged even after inert success.
            with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'real_constructor_policy'):
                owner.assert_load_parameters(model_path=attempt.namespace.label, vad_model=product.vad)
            with self.assertRaises(owner_module.RuntimeOwnerRefusal):
                owner_module.open_real_runtime_owner()
            with self.assertRaises(protocol.ProtocolRefusal):
                protocol.activate_real_worker(b)
            self.assertEqual(b.release_factory_product(), {'retired_by_factory': True})
            self.assertIs(owner._engine_attempt, attempt)
            self.assertIs(attempt.product, product)
            self.assertIs(product.model, model.vad.segmentation)
            b.close_preserving()
            self.assertFalse(attempt.active)
            self.assertIs(owner._engine_attempt, attempt)
            self.assertIs(attempt.model, model)
            self.assertIs(attempt.pipeline, pipeline)
            self.assertIs(attempt.product, product)
            # No logical-close branch clears this engine owner or returns a
            # process/backend retirement receipt.

    def test_02_missing_or_forged_issuance_refuses_before_constructor(self):
        for fault in ('missing_namespace', 'label', 'clone', 'missing_vad', 'foreign_vad'):
            with self.subTest(fault=fault), fixture() as f:
                begin(self, f)
                b = f.bootstrap
                namespace = b._generated_namespace
                if fault == 'foreign_vad':
                    self.assertEqual(build(f), {'built': True})
                    b._product = object()
                elif fault == 'missing_namespace':
                    b._generated_namespace = None
                elif fault == 'label':
                    b._generated_namespace = namespace.label
                elif fault == 'clone':
                    b._generated_namespace = type(namespace)(namespace.label, namespace.members)
                calls = []

                def forbidden_constructor(*args):
                    calls.append('constructor')
                    raise AssertionError('Constructor reached before issued namespace/VAD')

                with replaced(objects._GeneratedEngineModel, '__init__', forbidden_constructor):
                    with self.assertRaises(owner_module.RuntimeOwnerRefusal):
                        b._build_generated_engine()
                self.assertEqual(calls, [])
                self.assertIsNone(b.registry._engine_attempt)
                self.assertTrue(b._closed and b._quarantined)
                self.assertFalse(b.registry._active)
                self.assertIs(b.registry._namespace, namespace)

    def test_03_operation_attempt_and_step_order_are_bound(self):
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b, owner = f.bootstrap, f.bootstrap.registry
            with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'serial_operation_required'):
                owner._begin_generated_engine(b._permit, b._generated_namespace, b._product)
            with owner.operation(b._permit, 'engine'):
                with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'bootstrap_permit_identity'):
                    owner._begin_generated_engine(object(), b._generated_namespace, b._product)
                forged = owner_module._EngineConstructionAttempt(
                    owner, owner._generation, object(), b._generated_namespace, owner._product)
                with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'engine_attempt_identity'):
                    owner._retain_generated_engine_model(forged, object())
                self.assertIsNone(owner._engine_attempt)
                attempt = owner._begin_generated_engine(b._permit, b._generated_namespace, b._product)
            returned = objects._GeneratedEngineModel(attempt.namespace, attempt.product.vad)
            with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'engine_operation_identity'):
                with owner.operation(b._permit, 'engine'):
                    owner._retain_generated_engine_model(attempt, returned)
            self.assertIs(attempt.model, returned)
            self.assertFalse(attempt.active or owner._active)
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b, owner = f.bootstrap, f.bootstrap.registry
            with owner.operation(b._permit, 'use'):
                with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'operation_already_active'):
                    b._build_generated_engine()
            self.assertIsNone(owner._engine_attempt)
            self.assertTrue(b._closed and b._quarantined)
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b, owner = f.bootstrap, f.bootstrap.registry
            pipeline = objects._GeneratedEnginePipeline(object(), b._product)
            with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'engine_model_preparation_order'):
                with owner.operation(b._permit, 'engine'):
                    attempt = owner._begin_generated_engine(b._permit, b._generated_namespace, b._product)
                    owner._retain_generated_engine_pipeline(attempt, pipeline)
            self.assertIs(attempt.pipeline, pipeline)
            self.assertIsNone(attempt.model)
            self.assertFalse(attempt.active or owner._active)

    def test_04_each_construction_failure_retains_returned_objects(self):
        for phase in ('model_constructor', 'model_prepare', 'pipeline_prepare'):
            with self.subTest(phase=phase), fixture() as f:
                begin(self, f)
                self.assertEqual(build(f), {'built': True})
                b, owner = f.bootstrap, f.bootstrap.registry
                original = KeyboardInterrupt('generated ' + phase)
                seen = []
                target = objects._GeneratedEnginePipeline if phase == 'pipeline_prepare' else objects._GeneratedEngineModel
                name = '__init__' if phase == 'model_constructor' else 'prepare'

                def fail(value, *args):
                    attempt = owner._engine_attempt
                    self.assertIs(attempt.owner, owner)
                    self.assertIs(attempt.product, owner._product)
                    self.assertEqual(owner._operation[2], 'engine')
                    if phase != 'model_constructor':
                        self.assertIs(value, attempt.pipeline if phase == 'pipeline_prepare' else attempt.model)
                        seen.append(value)
                    raise original

                with replaced(target, name, fail):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        b._build_generated_engine()
                self.assertIs(caught.exception, original)
                attempt = owner._engine_attempt
                self.assertIs(attempt.failure, original)
                self.assertIs(attempt.namespace, b._generated_namespace)
                self.assertIs(attempt.product.vad, b._product)
                self.assertFalse(attempt.active or attempt.published)
                self.assertTrue(b._closed and b._quarantined)
                self.assertFalse(owner._active)
                self.assertIsNone(owner._operation)
                if phase == 'model_constructor':
                    self.assertFalse(attempt.model_returned or attempt.pipeline_returned)
                    self.assertIsNone(attempt.model)
                    self.assertIsNone(attempt.pipeline)
                    # No claim to own an object its constructor never returned.
                elif phase == 'model_prepare':
                    self.assertIs(attempt.model, seen[0])
                    self.assertTrue(attempt.model_returned)
                    self.assertFalse(attempt.pipeline_returned)
                else:
                    self.assertIs(attempt.pipeline, seen[0])
                    self.assertTrue(attempt.model_returned and attempt.pipeline_returned)
                    self.assertIs(attempt.pipeline.model, attempt.model)
                b.close_preserving()
                self.assertIs(owner._engine_attempt, attempt)

    def test_05_reentrant_revoke_or_changed_vad_blocks_publication(self):
        for fault in ('revoke_after_model', 'changed_vad_link'):
            with self.subTest(fault=fault), fixture() as f:
                begin(self, f)
                self.assertEqual(build(f), {'built': True})
                b, owner = f.bootstrap, f.bootstrap.registry
                target = objects._GeneratedEngineModel if fault == 'revoke_after_model' else objects._GeneratedEnginePipeline
                ordinary = target.prepare

                def prepare(value):
                    ordinary(value)
                    attempt = owner._engine_attempt
                    self.assertIs(attempt.model if fault == 'revoke_after_model' else attempt.pipeline, value)
                    if fault == 'revoke_after_model':
                        owner.revoke_generation(b._permit)
                    else:
                        attempt.product.vad.segmentation = object()

                with replaced(target, 'prepare', prepare):
                    with self.assertRaises((owner_module.RuntimeOwnerRefusal,
                                            registry_module.ModelBindingRefusal)) as caught:
                        b._build_generated_engine()
                attempt = owner._engine_attempt
                self.assertIs(attempt.failure, caught.exception)
                self.assertFalse(attempt.published or attempt.active)
                self.assertIsNotNone(attempt.model)
                self.assertTrue(b._closed and b._quarantined)
                if fault == 'revoke_after_model':
                    self.assertIsNone(attempt.pipeline)
                    self.assertFalse(attempt.pipeline_returned)
                else:
                    self.assertIsNotNone(attempt.pipeline)
                    self.assertIsNot(attempt.product.vad.segmentation, attempt.product.model)
                    self.assertIs(attempt.product.model, owner._retained[0].model)

    def test_06_secondary_cleanup_failure_preserves_first_error(self):
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b, owner = f.bootstrap, f.bootstrap.registry
            original = KeyboardInterrupt('generated model preparation interrupted')
            calls = []

            def fail_model(model):
                self.assertIs(owner._engine_attempt.model, model)
                raise original

            def failed_revoke(*args):
                calls.append('owner_revoke')
                raise RuntimeError('generated revocation unconfirmed')

            # Failure injection only: this never returns a forged live/issued
            # answer or bypasses an admission or publication predicate.
            with replaced(objects._GeneratedEngineModel, 'prepare', fail_model):
                with replaced(owner, 'revoke_generation', failed_revoke):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        b._build_generated_engine()
            self.assertIs(caught.exception, original)
            self.assertEqual(calls, ['owner_revoke', 'owner_revoke'])
            self.assertGreaterEqual(len(original.__notes__), 2)
            attempt = owner._engine_attempt
            self.assertIs(attempt.failure, original)
            self.assertIsNotNone(attempt.model)
            self.assertIsNone(attempt.pipeline)
            self.assertIs(attempt.product, owner._product)
            self.assertIs(attempt.namespace, owner._namespace)
            self.assertTrue(owner._active)  # Cleanup failure is not revocation credit.
            self.assertFalse(attempt.active or attempt.published)
            self.assertTrue(b._closed and b._quarantined and b._channel._revoked)
            self.assertIsNone(owner._operation)
