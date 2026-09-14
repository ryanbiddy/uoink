"""Six unexecuted generated cases through the actual WorkerBootstrap."""
from contextlib import contextmanager
import unittest

import generated_bootstrap_fixture as fixture_module
from generated_bootstrap_fixture import fixture
import model_binding_registry as registry_module
import owned_factory_port as factory_module
import owned_generation_protocol as protocol
import owned_guard as guard
import worker_runtime_owner as owner_module

EXPECTED_CASES = (
    'connection_cases.BootstrapContracts.test_01_actual_bootstrap_build_register_use_release',
    'connection_cases.BootstrapContracts.test_02_missing_guard_refuses_before_constructor',
    'connection_cases.BootstrapContracts.test_03_registration_failure_retains_completed_product',
    'connection_cases.BootstrapContracts.test_04_first_error_survives_both_revocation_failures',
    'connection_cases.BootstrapContracts.test_05_release_cannot_overlap_use',
    'connection_cases.BootstrapContracts.test_06_constructor_error_retains_inputs_before_factory_assignment',
)


@contextmanager
def replaced(instance, name, value):
    namespace = vars(instance)
    existed = name in namespace
    original = namespace.get(name)
    setattr(instance, name, value)
    try:
        yield
    finally:
        if existed:
            setattr(instance, name, original)
        else:
            delattr(instance, name)


def begin(test, f, *, bind_guard=True):
    b = f.bootstrap
    test.assertIsNone(b.registry)
    test.assertIsNone(b._factory)
    test.assertEqual(f.runtime.events, [])
    expected = {'generation': f.generation.generation_hex,
                'namespace_sha256': f.generation.namespace_sha256}
    ready = b.accept_challenge(f.controller.encode('challenge', expected))
    test.assertEqual(f.controller.decode(ready), ('ready', expected))
    test.assertIs(type(b.registry), owner_module._WorkerRuntimeOwnerProposal)
    test.assertIs(b.registry._bootstrap_permit, b._permit)
    test.assertIs(type(b._permit), object)
    b.accept_begin(f.controller.encode('begin', {'manifest_sha256': f.generation.manifest_sha256}))
    test.assertTrue(b._started)
    test.assertIsNone(guard._RUNTIME)
    if bind_guard:
        # This explicit fixture assignment is generated-only and is restored.
        # The actual bootstrap does not install or activate a real runtime.
        guard._RUNTIME = b.registry
    test.assertEqual(b.issue_generated_inputs(
        (b'config', b'generated text', b'preprocessor', b'tokens', b'vocabulary'),
        object(), b'\0' * 16), {'issued_generated_inputs': True})
    test.assertIsNone(b._factory)
    test.assertIsNone(b._product)
    test.assertEqual(f.runtime.events, [])


def build(f):
    return f.bootstrap.build_factory_product(f.fixed, f.port, guard, f.state,
        f.state_binding, registry_module.FIXED_RECIPE_SHA256)


class BootstrapContracts(unittest.TestCase):
    def test_01_actual_bootstrap_build_register_use_release(self):
        with fixture() as f:
            begin(self, f)
            b = f.bootstrap
            self.assertEqual(build(f), {'built': True})
            factory, product = b._factory, b._product
            complete = factory._completed
            self.assertIs(type(factory), factory_module._OwnedFactoryPortProposal)
            self.assertIs(type(complete), factory_module._FactoryOwner)
            self.assertIs(complete.vad, product)
            self.assertIs(complete.model_lease, b.registry._lease)
            self.assertIs(b.registry._product.vad, product)
            self.assertIs(b.registry._product.model, complete.model)
            self.assertIs(factory._model_capability._registry, b.registry)
            self.assertIs(guard._RUNTIME, b.registry)
            self.assertEqual((complete.model.build_count, complete.model.load_count), (1, 1))
            self.assertEqual(complete.model.load_arguments, (True, False))
            self.assertEqual(len(complete.model_state), 54)
            self.assertEqual(f.controller.decode(b.encode_generated_text('fixture text')),
                             ('done', {'generated_text': 'fixture text'}))
            self.assertIsNone(b.registry._operation)
            self.assertEqual(b.release_factory_product(), {'retired_by_factory': True})
            self.assertIsNone(b._product)
            self.assertIsNone(b.registry._product)
            self.assertIsNone(factory._completed)
            self.assertFalse(b.registry._lease._active)
            b.close_preserving()
            self.assertTrue(b._closed and b._channel._revoked)
            self.assertFalse(b.registry._active)
            self.assertIs(b._factory, factory)
            self.assertIs(b._factory_inputs[2], f.state)
            with self.assertRaises(protocol.ProtocolRefusal):
                protocol.activate_real_worker(b)
            with self.assertRaises(owner_module.RuntimeOwnerRefusal):
                b.registry.assert_load_parameters()

    def test_02_missing_guard_refuses_before_constructor(self):
        with fixture() as f:
            begin(self, f, bind_guard=False)
            b = f.bootstrap
            with self.assertRaisesRegex(protocol.ProtocolRefusal, 'owned_runtime_registry_binding_required'):
                build(f)
            self.assertIsNone(guard._RUNTIME)
            self.assertIsNone(b._factory)
            self.assertIsNone(b._runtime_module)
            self.assertIsNone(b._factory_inputs)
            self.assertFalse(b._factory_attempted)
            self.assertEqual(f.runtime.events, [])
            self.assertTrue(b._closed and b._quarantined and b._channel._revoked)
            self.assertFalse(b.registry._active)

    def test_03_registration_failure_retains_completed_product(self):
        with fixture() as f:
            begin(self, f)
            b = f.bootstrap
            primary = KeyboardInterrupt('generated registration refusal')
            def reject_registration(*args):
                raise primary
            with replaced(b.registry, 'register_vad_product_for_bootstrap', reject_registration):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    build(f)
            self.assertIs(seen.exception, primary)
            self.assertIs(b._factory._completed.vad, b._product)
            self.assertEqual(b._factory._completed.model.load_count, 1)
            self.assertIs(b.registry._retained[3], b._factory._completed.model)
            self.assertIs(b.registry._retained[4], b._factory)
            self.assertIs(b._factory_inputs[2], f.state)
            self.assertIsNone(b.registry._product)
            self.assertTrue(b._closed and b._quarantined and b._channel._revoked)
            self.assertFalse(b.registry._active)
            self.assertIsNone(b.registry._operation)

    def test_04_first_error_survives_both_revocation_failures(self):
        with fixture() as f:
            begin(self, f)
            b = f.bootstrap
            primary = KeyboardInterrupt('first generated registration error')
            calls = []
            def reject_registration(*args):
                raise primary
            def reject_owner(*args):
                calls.append('owner')
                raise RuntimeError('generated owner revoke failure')
            def reject_channel():
                calls.append('channel')
                raise ValueError('generated channel revoke failure')
            with replaced(b.registry, 'register_vad_product_for_bootstrap', reject_registration):
                with replaced(b.registry, 'revoke_generation', reject_owner):
                    with replaced(b._channel, 'revoke', reject_channel):
                        with self.assertRaises(KeyboardInterrupt) as seen:
                            build(f)
            self.assertIs(seen.exception, primary)
            self.assertEqual(calls, ['owner', 'owner', 'channel'])
            self.assertGreaterEqual(len(primary.__notes__), 3)
            self.assertTrue(b._closed and b._quarantined)
            # Both failures are unknown cleanup, not successful revocation.
            self.assertTrue(b.registry._active)
            self.assertFalse(b._channel._revoked)
            self.assertIs(b._factory._completed.vad, b._product)
            self.assertIs(b._factory_inputs[2], f.state)
            self.assertIsNotNone(b._factory._completed.model)
            self.assertIsNone(b.registry._operation)

    def test_05_release_cannot_overlap_use(self):
        with fixture() as f:
            begin(self, f)
            self.assertEqual(build(f), {'built': True})
            b = f.bootstrap
            complete, product = b._factory._completed, b._product
            with self.assertRaises(registry_module.ModelBindingRefusal):
                with b.use_operation():
                    with self.assertRaisesRegex(owner_module.RuntimeOwnerRefusal, 'operation_already_active'):
                        b.release_factory_product()
                    self.assertIs(b._factory._completed, complete)
                    self.assertIs(b._product, product)
            self.assertIs(b._factory._completed, complete)
            self.assertIs(b.registry._retained[0].vad, product)
            self.assertTrue(b._closed and b._quarantined)
            self.assertFalse(b.registry._active)
            self.assertIsNone(b.registry._operation)

    def test_06_constructor_error_retains_inputs_before_factory_assignment(self):
        with fixture() as f:
            begin(self, f)
            b = f.bootstrap
            primary = KeyboardInterrupt('generated factory constructor context')
            def reject_dtype():
                raise primary
            with replaced(f.runtime, 'get_default_dtype', reject_dtype):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    build(f)
            self.assertIs(seen.exception, primary)
            self.assertIsNone(b._factory)
            self.assertIsNone(b._product)
            self.assertIsNone(b.registry._capability)
            self.assertTrue(b._factory_attempted)
            self.assertIs(b._runtime_module, guard)
            self.assertIs(b._factory_inputs[0], f.fixed)
            self.assertIs(b._factory_inputs[1], f.port)
            self.assertIs(b._factory_inputs[2], f.state)
            self.assertIs(b._factory_inputs[3], f.state_binding)
            self.assertEqual(f.runtime.events, [])
            self.assertTrue(b._closed and b._quarantined and b._channel._revoked)
            self.assertFalse(b.registry._active)
