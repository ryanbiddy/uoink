"""Focused generated source proposal. No case has been executed."""
import unittest

import generated_adapter_flow as flow
import generated_operation_flow as operations
import generated_worker_runtime_bridge as bridge_module
import generated_worker_factory_inputs as input_module
import owned_generation_protocol as protocol
import owned_cpu_tensor_port as cpu_module
import owned_factory_port as factory_module
import worker_runtime_owner as owner_module
import model_binding_registry as registry_module
import owned_guard as guard
from inherited_readset import InheritedReadSetAdoption, namespace_digest
from generated_native_owner_fixture import fixture, replaced

EXPECTED_CASES = (
    'native_owner_cases.NativeOwnerContracts.test_01_actual_child_build_segment_cancel_retire',
    'native_owner_cases.NativeOwnerContracts.test_02_clean_initial_cancel_allocates_nothing',
    'native_owner_cases.NativeOwnerContracts.test_03_initial_control_requires_ready',
    'native_owner_cases.NativeOwnerContracts.test_04_wrong_initial_manifest_closes_before_allocation',
    'native_owner_cases.NativeOwnerContracts.test_05_consumed_cancel_refuses_both_begin_entries',
    'native_owner_cases.NativeOwnerContracts.test_06_policy_required_before_initial_entry',
    'native_owner_cases.NativeOwnerContracts.test_07_constructor_error_survives_final_revoke',
    'native_owner_cases.NativeOwnerContracts.test_08_partial_generated_input_failure_retained',
    'native_owner_cases.NativeOwnerContracts.test_09_registration_error_retains_actual_product',
    'native_owner_cases.NativeOwnerContracts.test_10_mutated_pcm_blocks_segment_publication',
    'native_owner_cases.NativeOwnerContracts.test_11_revoked_model_lease_blocks_segment_publication',
    'native_owner_cases.NativeOwnerContracts.test_12_unread_release_failure_has_no_closed_write',
    'native_owner_cases.NativeOwnerContracts.test_13_factory_retirement_failure_retains_read_guards',
    'native_owner_cases.NativeOwnerContracts.test_14_closed_write_failure_retains_inputs',
    'native_owner_cases.NativeOwnerContracts.test_15_revoke_failure_after_closed_is_not_clean_return',
    'native_owner_cases.NativeOwnerContracts.test_16_owner_revocation_inside_encode_prevents_send',
)


def bootstrap_pair():
    binding = protocol.GenerationBinding('11' * 32, '22' * 32, namespace_digest(), '44' * 32, 9)
    controller = protocol.GenerationChannel(binding, b'\x55' * 32, 'controller')
    worker = protocol.GenerationChannel(binding, b'\x55' * 32, 'worker')
    b = protocol.WorkerBootstrap(worker, owner_module._WorkerRuntimeOwnerProposal,
                                factory_module._OwnedFactoryPortProposal)
    return b, controller


def ready(b, controller):
    expected = {'generation': controller.binding.generation_hex,
                'namespace_sha256': controller.binding.namespace_sha256}
    assert controller.decode(b.accept_challenge(controller.encode('challenge', expected))) == ('ready', expected)


def retained():
    return flow._RETAINED_CHILD_RUNTIME_BRIDGE


class NativeOwnerContracts(unittest.TestCase):
    def test_01_actual_child_build_segment_cancel_retire(self):
        with fixture() as f:
            result = f.run()
            r = retained()
            self.assertEqual(result['cursor_state'], 'cancelled')
            self.assertEqual(result['operation_events'], ['admit_generated_media', 'begin_generated_transcription',
                'next_generated_segment', 'cancel_generated_cursor'])
            self.assertEqual([row for row in f.writes if row[0] == 'segment'], [('segment', {
                'cursor_id': operations.CURSOR_ID, 'index': 0, 'segment': operations.SEGMENTS[0]})])
            self.assertEqual(result['produced_segments'], 1)
            self.assertIs(type(r.bootstrap._factory), factory_module._OwnedFactoryPortProposal)
            self.assertTrue(r.bootstrap._factory_attempted)
            self.assertIs(r.bootstrap._factory_inputs[2], r.inputs.state)
            self.assertEqual(len(r.inputs.state), 54)
            self.assertEqual(r.inputs.runtime.events.count('strict_load'), 1)
            self.assertIsNone(r.bootstrap._factory._completed)
            self.assertIsNone(r.bootstrap._product)
            self.assertFalse(r.bootstrap.registry._lease._active)
            self.assertFalse(r.bootstrap.registry._active)
            self.assertTrue(r.channel._revoked and r.clean_closed and f.pair.closed)
            self.assertTrue(f.read_set.released)
            self.assertIsNone(guard._RUNTIME)
            events = r.events
            self.assertLess(events.index('actual_factory_registered'), events.index('segment_committed'))
            self.assertLess(events.index('actual_factory_retired'), events.index('child_readset_released'))
            self.assertLess(events.index('closed_frame_written'), events.index('owner_and_channel_revoked'))
            self.assertEqual(r.channel._receive_sequence, f.controller._send_sequence)
            self.assertEqual(r.channel._send_sequence, f.controller._receive_sequence)
            self.assertFalse(result['runtime_owner']['real_runtime_approved'])
            self.assertEqual(result['model_calls'], 0)

    def test_02_clean_initial_cancel_allocates_nothing(self):
        with fixture(early_cancel=True) as f:
            result = f.run()
            r = retained()
            self.assertEqual(result['cursor_state'], 'not_started')
            self.assertEqual(result['operation_events'], [])
            self.assertIsNone(r.inputs)
            self.assertIsNone(r.bootstrap._generated_pcm)
            self.assertIsNone(r.bootstrap._factory)
            self.assertIsNone(r.bootstrap._factory_inputs)
            self.assertFalse(r.bootstrap._started or r.bootstrap._factory_attempted)
            self.assertNotIn('fake_materialize', f.events)
            self.assertEqual(f.writes[-1], ('closed', {}))
            self.assertLess(f.events.index('release_read_set'), f.events.index('write:closed'))
            self.assertTrue(r.clean_closed and f.pair.closed and f.read_set.released)
            self.assertEqual(r.channel._receive_sequence, f.controller._send_sequence)

    def test_03_initial_control_requires_ready(self):
        b, c = bootstrap_pair()
        with self.assertRaisesRegex(protocol.ProtocolRefusal, 'initial_control_order'):
            b.accept_initial_control(c.encode('cancel', {}))
        self.assertIsNone(b.registry)
        self.assertTrue(b._closed and b._channel._revoked)
        self.assertFalse(b._started)

    def test_04_wrong_initial_manifest_closes_before_allocation(self):
        b, c = bootstrap_pair()
        ready(b, c)
        with self.assertRaisesRegex(protocol.ProtocolRefusal, 'initial_control_binding'):
            b.accept_initial_control(c.encode('begin', {'manifest_sha256': '33' * 32}))
        self.assertFalse(b._started or b.registry._active)
        self.assertIsNone(b._factory_inputs)
        self.assertIsNone(b._generated_pcm)
        self.assertTrue(b._closed and b._channel._revoked)

    def test_05_consumed_cancel_refuses_both_begin_entries(self):
        b, c = bootstrap_pair()
        ready(b, c)
        self.assertEqual(b.accept_initial_control(c.encode('cancel', {})), 'cancel')
        self.assertFalse(b._started or b._ready)
        self.assertTrue(b._initial_control_consumed)
        frame = c.encode('begin', {'manifest_sha256': c.binding.manifest_sha256})
        with self.assertRaisesRegex(protocol.ProtocolRefusal, 'begin_order'):
            b.accept_begin(frame)
        with self.assertRaisesRegex(protocol.ProtocolRefusal, 'initial_control_order'):
            b.accept_initial_control(frame)
        self.assertFalse(b.registry._active)
        self.assertIsNone(b._factory_inputs)

    def test_06_policy_required_before_initial_entry(self):
        b, c = bootstrap_pair()
        adoption = InheritedReadSetAdoption(object())
        r = bridge_module.GeneratedWorkerRuntimeBridge(b._channel, adoption)
        with self.assertRaisesRegex(bridge_module.GeneratedBridgeRefusal, 'initial_after_policy'):
            r.accept_initial_control(c.encode('cancel', {}))
        self.assertIsNone(r.inputs)
        self.assertIsNone(r.bootstrap.registry)
        self.assertEqual(r.channel._receive_sequence, 0)
        r.close_preserving()

    def test_07_constructor_error_survives_final_revoke(self):
        primary = KeyboardInterrupt('generated bridge constructor')
        def fail_construct(*args): raise primary
        def fail_revoke(self): raise ValueError('generated final channel revoke')
        with fixture(early_cancel=True) as f:
            with replaced(bridge_module, 'GeneratedWorkerRuntimeBridge', fail_construct):
                with replaced(protocol.GenerationChannel, 'revoke', fail_revoke):
                    with self.assertRaises(KeyboardInterrupt) as seen:
                        f.run()
            self.assertIs(seen.exception, primary)
            self.assertIsNone(retained())
            self.assertIn('quarantine', f.events)
            self.assertEqual(f.writes, [])
            self.assertTrue(any('Channel revocation' in note for note in primary.__notes__))

    def test_08_partial_generated_input_failure_retained(self):
        primary = KeyboardInterrupt('generated second allocation')
        allocate = cpu_module._OwnedCPUTorchPortProposal.allocate_owned_cpu_f32
        count = []
        def fail_second(port, shape):
            count.append(shape)
            if len(count) == 2: raise primary
            return allocate(port, shape)
        with fixture() as f:
            with replaced(cpu_module._OwnedCPUTorchPortProposal, 'allocate_owned_cpu_f32', fail_second):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    f.run()
            r = retained()
            self.assertIs(seen.exception, primary)
            self.assertIs(r.failure, primary)
            self.assertEqual(len(r.inputs.state), 1)
            self.assertFalse(r.inputs.prepared)
            self.assertIsNotNone(r.inputs.port)
            self.assertIsNone(r.bootstrap._factory_inputs)
            self.assertFalse(f.read_set.released or r.clean_closed)

    def test_09_registration_error_retains_actual_product(self):
        primary = KeyboardInterrupt('generated registration')
        def fail_registration(*args): raise primary
        with fixture() as f:
            with replaced(owner_module._WorkerRuntimeOwnerProposal,
                          'register_vad_product_for_bootstrap', fail_registration):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    f.run()
            r = retained()
            self.assertIs(seen.exception, primary)
            self.assertIs(r.bootstrap._factory._completed.vad, r.bootstrap._product)
            self.assertIs(r.bootstrap._factory_inputs[2], r.inputs.state)
            self.assertEqual(r.bootstrap._factory._completed.model.load_count, 1)
            self.assertFalse(r.clean_closed or f.read_set.released)
            self.assertFalse(any(op == 'segment' for op, payload in f.writes))

    def test_10_mutated_pcm_blocks_segment_publication(self):
        with fixture() as f:
            def mutate(op, payload):
                if payload.get('action') == 'next_generated_segment':
                    retained().bootstrap._generated_pcm._storage[0] = 1
            f.before_read = mutate
            with self.assertRaises(owner_module.RuntimeOwnerRefusal):
                f.run()
            self.assertFalse(any(op == 'segment' for op, payload in f.writes))
            self.assertFalse(retained().clean_closed or f.read_set.released)
            self.assertEqual(retained().index, 0)

    def test_11_revoked_model_lease_blocks_segment_publication(self):
        with fixture() as f:
            def revoke(op, payload):
                if payload.get('action') == 'next_generated_segment':
                    retained().bootstrap.registry._lease.revoke()
            f.before_read = revoke
            with self.assertRaises(registry_module.ModelBindingRefusal):
                f.run()
            self.assertFalse(any(op == 'segment' for op, payload in f.writes))
            self.assertFalse(retained().clean_closed or f.read_set.released)
            self.assertIsNotNone(retained().bootstrap._factory._completed)

    def test_12_unread_release_failure_has_no_closed_write(self):
        primary = KeyboardInterrupt('generated unread release')
        with fixture(early_cancel=True) as f:
            def fail_release(read_set): raise primary
            f.release_hook = fail_release
            with self.assertRaises(KeyboardInterrupt) as seen:
                f.run()
            self.assertIs(seen.exception, primary)
            self.assertIs(retained().failure, primary)
            self.assertIsNone(retained().inputs)
            self.assertFalse(any(op == 'closed' for op, payload in f.writes))
            self.assertTrue(f.read_set.unconfirmed)
            self.assertFalse(f.read_set.released or retained().clean_closed)

    def test_13_factory_retirement_failure_retains_read_guards(self):
        primary = KeyboardInterrupt('generated factory release')
        def fail_release(*args): raise primary
        with fixture() as f:
            with replaced(factory_module._OwnedFactoryPortProposal, 'release_product', fail_release):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    f.run()
            self.assertIs(seen.exception, primary)
            self.assertIsNotNone(retained().bootstrap._product)
            self.assertIsNotNone(retained().bootstrap._factory._completed)
            self.assertFalse(f.read_set.released or retained().clean_closed)
            self.assertFalse(any(op == 'closed' for op, payload in f.writes))

    def test_14_closed_write_failure_retains_inputs(self):
        primary = KeyboardInterrupt('generated closed write')
        with fixture() as f:
            def fail_write(op, payload):
                if op == 'closed': raise primary
            f.before_write = fail_write
            with self.assertRaises(KeyboardInterrupt) as seen:
                f.run()
            r = retained()
            self.assertIs(seen.exception, primary)
            self.assertTrue(f.read_set.released and f.read_set.unconfirmed)
            self.assertIsNone(r.bootstrap._product)
            self.assertIs(r.bootstrap._factory_inputs[2], r.inputs.state)
            self.assertFalse(r.clean_closed or f.pair.closed)
            self.assertFalse(any(op == 'closed' for op, payload in f.writes))

    def test_15_revoke_failure_after_closed_is_not_clean_return(self):
        primary = KeyboardInterrupt('generated owner revoke')
        def fail_revoke(*args): raise primary
        with fixture(early_cancel=True) as f:
            with replaced(owner_module._WorkerRuntimeOwnerProposal, 'revoke_generation', fail_revoke):
                with self.assertRaises(KeyboardInterrupt) as seen:
                    f.run()
            r = retained()
            self.assertIs(seen.exception, primary)
            self.assertEqual(f.writes[-1], ('closed', {}))
            self.assertFalse(r.clean_closed or f.pair.closed)
            self.assertTrue(r.bootstrap.registry._active and r.channel._revoked)
            self.assertTrue(f.read_set.released and f.read_set.unconfirmed)
            self.assertIsNone(r.inputs)

    def test_16_owner_revocation_inside_encode_prevents_send(self):
        encode = protocol.GenerationChannel.encode
        def revoke_on_segment(channel, op, payload):
            if op == 'segment':
                b = retained().bootstrap
                b.registry.revoke_generation(b._permit)
            return encode(channel, op, payload)
        with fixture() as f:
            with replaced(protocol.GenerationChannel, 'encode', revoke_on_segment):
                with self.assertRaises(registry_module.ModelBindingRefusal):
                    f.run()
            self.assertFalse(any(op == 'segment' for op, payload in f.writes))
            self.assertFalse(retained().clean_closed or f.read_set.released)
            self.assertFalse(retained().bootstrap.registry._active)
