"""Eleven proposed generated ownership cases. Guarded execution is not admitted.

fixture() runs the unchanged factory/CPU port with retained inert bytearray
support; no native Tensor, decoder, model or real runtime module is involved.
"""
import unittest

import model_binding_registry as registry_module
import owned_guard as guard
import worker_runtime_owner as proposed
from generated_factory_fixture import fixture

REFUSALS = (proposed.RuntimeOwnerRefusal, registry_module.ModelBindingRefusal)
EXPECTED_CASES = (
    'generated_unit_cases.OwnerContracts.test_01_actual_factory_publication_keeps_registry_identity',
    'generated_unit_cases.OwnerContracts.test_02_foreign_vad_and_namespace_refused',
    'generated_unit_cases.OwnerContracts.test_03_foreign_pcm_and_sample_rate_refused',
    'generated_unit_cases.OwnerContracts.test_04_replaced_mutated_and_expired_pcm_refused',
    'generated_unit_cases.OwnerContracts.test_05_overlapping_operation_and_release_refused',
    'generated_unit_cases.OwnerContracts.test_06_revocation_blocks_publication_and_retains_owners',
    'generated_unit_cases.OwnerContracts.test_07_real_constructor_pcm_and_filter_routes_remain_closed',
    'generated_unit_cases.OwnerContracts.test_08_vad_only_retirement_blocks_publication',
    'generated_unit_cases.OwnerContracts.test_09_replaced_completed_product_blocks_publication',
    'generated_unit_cases.OwnerContracts.test_10_replaced_runtime_module_blocks_publication',
    'generated_unit_cases.OwnerContracts.test_11_revoked_model_lease_blocks_publication',
)


class OwnerContracts(unittest.TestCase):
    def test_01_actual_factory_publication_keeps_registry_identity(self):
        with fixture() as f:
            owner, complete = f.registry, f.factory._completed
            self.assertIs(guard._RUNTIME, owner)
            self.assertIs(type(f.capability), registry_module._FactoryModelCapability)
            self.assertIs(f.capability._registry, owner)
            self.assertIs(type(owner).assert_vad_model_binding,
                          registry_module._WorkerModelRegistryProposal.assert_vad_model_binding)
            self.assertIs(type(owner)._issue_for_bootstrap,
                          registry_module._WorkerModelRegistryProposal._issue_for_bootstrap)
            self.assertIs(complete.vad, f.product)
            self.assertIs(complete.model_lease, owner._lease)
            self.assertEqual((complete.model.build_count, complete.model.load_count), (1, 1))
            self.assertEqual(complete.model.load_arguments, (True, False))
            self.assertEqual(len(complete.model_state), 54)
            self.assertTrue(complete.model.evaluated)
            self.assertIsNone(f.factory._quarantined_owner)
            f.capability.assert_factory_and_runtime(f.factory, guard)
            owner.assert_vad_model_binding(complete.model)
            with owner.operation(f.bootstrap, 'use'):
                owner.assert_vad_binding(f.product)
                owner.assert_model_binding(f.namespace.label, f.product)
                owner.assert_waveform_binding(f.pcm, sample_rate=16000)

    def test_02_foreign_vad_and_namespace_refused(self):
        with fixture() as f:
            clone = type(f.namespace)(f.namespace.label, f.namespace.members)
            self.assertEqual(clone, f.namespace)
            self.assertIsNot(clone, f.namespace)
            with f.registry.operation(f.bootstrap, 'use'):
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_generated_namespace_binding(clone)
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_vad_binding(object())
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_model_binding(f.namespace.label + '-foreign', f.product)
                f.registry.assert_generated_namespace_binding(f.namespace)
                f.registry.assert_model_binding(f.namespace.label, f.product)

    def test_03_foreign_pcm_and_sample_rate_refused(self):
        with fixture() as f:
            foreign = type(f.pcm)(bytes(f.pcm._storage))
            self.assertEqual(foreign._storage, f.pcm._storage)
            with f.registry.operation(f.bootstrap, 'use'):
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_waveform_binding(foreign, sample_rate=16000)
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_waveform_binding(f.pcm, sample_rate=8000)
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_waveform_binding(f.pcm, sample_rate=16000.0)
                f.registry.assert_waveform_binding(f.pcm, sample_rate=16000)

    def test_04_replaced_mutated_and_expired_pcm_refused(self):
        with fixture() as f:
            retained = f.registry._pcm_owner
            with f.registry.operation(f.bootstrap, 'use'):
                f.pcm._storage = bytearray(f.pcm._storage)
                with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'owned_pcm_storage_changed'):
                    f.registry.assert_waveform_binding(f.pcm, sample_rate=16000)
                with self.assertRaises(registry_module.ModelBindingRefusal):
                    f.registry.assert_active()
            self.assertIs(f.registry._retained[1], retained)
            self.assertIsNot(retained.storage, f.pcm._storage)
        with fixture() as f:
            with f.registry.operation(f.bootstrap, 'use'):
                f.pcm._storage[0] ^= 1
                with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'owned_pcm_storage_changed'):
                    f.registry.assert_waveform_binding(f.pcm, sample_rate=16000)
            self.assertFalse(f.registry._active)
        with fixture() as f:
            with f.registry.operation(f.bootstrap, 'release'):
                f.registry.retire_generated_pcm(f.bootstrap, f.pcm)
            with f.registry.operation(f.bootstrap, 'use'):
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.assert_waveform_binding(f.pcm, sample_rate=16000)
            with f.registry.operation(f.bootstrap, 'issue'):
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.issue_generated_pcm(f.bootstrap, object(), b'\0' * 4)

    def test_05_overlapping_operation_and_release_refused(self):
        with fixture() as f:
            pcm_owner, vad_owner = f.registry._pcm_owner, f.registry._product
            with f.registry.operation(f.bootstrap, 'use'):
                with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'operation_already_active'):
                    with f.registry.operation(f.bootstrap, 'release'):
                        self.fail('Nested operation entered')
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.retire_generated_pcm(f.bootstrap, f.pcm)
                with self.assertRaises(proposed.RuntimeOwnerRefusal):
                    f.registry.retire_vad_product_for_bootstrap(f.bootstrap, f.factory, f.product)
                self.assertIs(f.registry._pcm_owner, pcm_owner)
                self.assertIs(f.registry._product, vad_owner)
                self.assertTrue(pcm_owner.active and vad_owner.active)
            with f.registry.operation(f.bootstrap, 'release'):
                f.registry.retire_generated_pcm(f.bootstrap, f.pcm)
                f.registry.retire_vad_product_for_bootstrap(f.bootstrap, f.factory, f.product)
            self.assertIsNone(f.registry._pcm_owner)
            self.assertIsNone(f.registry._product)
            self.assertIsNone(f.factory._completed)
            self.assertFalse(f.registry._lease._active)

    def test_06_revocation_blocks_publication_and_retains_owners(self):
        with fixture() as f:
            owner = f.registry
            vad_owner, pcm_owner = owner._product, owner._pcm_owner
            model = f.factory._completed.model
            with owner.operation(f.bootstrap, 'use') as token:
                self.assertEqual(owner.publish_generated_text(token, f.pcm, 'generated'), 'generated')
                owner.revoke_generation(f.bootstrap)
                with self.assertRaises(registry_module.ModelBindingRefusal):
                    owner.publish_generated_text(token, f.pcm, 'too late')
                self.assertIs(owner._retained[0], vad_owner)
                self.assertIs(owner._retained[1], pcm_owner)
                self.assertIs(owner._retained[3], model)
                self.assertIs(vad_owner.model, model)
                self.assertIs(pcm_owner.storage, f.pcm._storage)
                self.assertFalse(vad_owner.active or pcm_owner.active)
            self.assertIsNone(owner._operation)
            with self.assertRaises(registry_module.ModelBindingRefusal):
                with owner.operation(f.bootstrap, 'use'):
                    self.fail('Revoked generation entered')
        with fixture() as f:
            interrupted = KeyboardInterrupt('generated interruption')
            with self.assertRaises(KeyboardInterrupt) as observed:
                with f.registry.operation(f.bootstrap, 'use'):
                    raise interrupted
            self.assertIs(observed.exception, interrupted)
            self.assertFalse(f.registry._active)
            self.assertIsNotNone(f.registry._retained[0])
            self.assertIsNotNone(f.registry._retained[1])
            self.assertIsNone(f.registry._operation)

    def test_07_real_constructor_pcm_and_filter_routes_remain_closed(self):
        with fixture() as f:
            options = {'beam_size': 5}
            with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'real_constructor_policy'):
                f.registry.assert_load_parameters(model_path=f.namespace.label, vad_model=f.product,
                    local_files_only=True, device='cpu', compute_type='float32', asr_options=options)
            self.assertEqual(options, {'beam_size': 5})
            with self.assertRaises(proposed.RuntimeOwnerRefusal):
                proposed.open_real_runtime_owner(f.bootstrap, type(f.factory))
            with self.assertRaises(proposed.RuntimeOwnerRefusal):
                f.registry.issue_real_pcm(f.bootstrap, f.pcm)
            with self.assertRaises(proposed.RuntimeOwnerRefusal):
                f.registry.issue_real_filter_record(f.bootstrap, object())
            with self.assertRaises(proposed.RuntimeOwnerRefusal):
                f.registry.get_mel_filters(80)
            with self.assertRaises(proposed.RuntimeOwnerRefusal):
                f.registry.get_mel_filters(128)
            self.assertEqual(f.registry.max_audio_samples, 64)
            with self.assertRaises(AttributeError):
                f.registry.max_audio_samples = 1

    def test_08_vad_only_retirement_blocks_publication(self):
        with fixture() as f:
            with f.registry.operation(f.bootstrap, 'release'):
                f.registry.retire_vad_product_for_bootstrap(f.bootstrap, f.factory, f.product)
            self.assertTrue(f.registry._active)
            self.assertTrue(f.registry._pcm_owner.active)
            self.assertFalse(f.registry._lease._active)
            with f.registry.operation(f.bootstrap, 'use') as token:
                f.registry.assert_waveform_binding(f.pcm, sample_rate=16000)
                with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'vad_product_required_at_publication'):
                    f.registry.publish_generated_text(token, f.pcm, 'retired product')

    def test_09_replaced_completed_product_blocks_publication(self):
        with fixture() as f:
            original = f.product
            with f.registry.operation(f.bootstrap, 'use') as token:
                f.factory._completed.vad = object()
                with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'factory_product_or_runtime_changed'):
                    f.registry.publish_generated_text(token, f.pcm, 'replaced product')
            self.assertFalse(f.registry._active)
            self.assertIs(f.registry._retained[0].vad, original)
            self.assertIs(f.registry._retained[1].pcm, f.pcm)

    def test_10_replaced_runtime_module_blocks_publication(self):
        with fixture() as f:
            original = f.factory._owned_runtime_module
            try:
                with f.registry.operation(f.bootstrap, 'use') as token:
                    f.factory._owned_runtime_module = object()
                    with self.assertRaisesRegex(proposed.RuntimeOwnerRefusal, 'factory_product_or_runtime_changed'):
                        f.registry.publish_generated_text(token, f.pcm, 'replaced runtime module')
                self.assertFalse(f.registry._active)
                self.assertIs(f.registry._retained[0].owned_module, original)
            finally:
                # Restore only the inert fixture field for its inherited cleanup.
                # This cannot reactivate the revoked generation or create a pass.
                f.factory._owned_runtime_module = original

    def test_11_revoked_model_lease_blocks_publication(self):
        with fixture() as f:
            with f.registry.operation(f.bootstrap, 'use') as token:
                f.capability.revoke(f.factory)
                self.assertTrue(f.registry._active)
                self.assertTrue(f.registry._pcm_owner.active)
                self.assertIs(f.registry._product.vad, f.product)
                self.assertFalse(f.registry._lease._active)
                with self.assertRaises(registry_module.ModelBindingRefusal):
                    f.registry.publish_generated_text(token, f.pcm, 'revoked model lease')
