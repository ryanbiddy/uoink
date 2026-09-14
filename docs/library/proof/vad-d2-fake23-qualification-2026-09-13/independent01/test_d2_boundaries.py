"""Unexecuted new boundary cases. A reviewed inert runner supplies FIXED_INPUTS.

No filesystem calls, real converter import, model reader, or actual approval.
Decision bytes below are generated test records, never owner evidence.
"""
import json
from types import SimpleNamespace
import unittest
import d2_adapter as adapter

FIXED_INPUTS = None


def encoded(value):
    return json.dumps(value, sort_keys=True).encode('ascii')


def generated_decision():
    return dict(owner='Ryan', approved=True, scope=adapter.SCOPE,
        profile_sha256=adapter.PROFILE_SHA256, run_id=adapter.RUN_ID,
        output_basename=adapter.OUTPUT_NAME, decision_text='GENERATED TEST RECORD ONLY',
        source_note_sha256='9' * 64, conversion_authorized=True,
        model_execution_authorized=False, network_authorized=False,
        redistribution_authorized=False, real_reader_authorized=False, release_authorized=False,
        **{name: True for name in adapter.PREREQUISITES})


def generated_admission(owner_digest):
    return dict(root_reviewed=True, scope=adapter.SCOPE, run_id=adapter.RUN_ID,
        owner_decision_sha256=owner_digest, profile_sha256=adapter.PROFILE_SHA256)


class FakeConverter:
    """Private orchestration port only. It never invokes a filesystem or converter."""
    REAL_PROFILE = None
    REAL_INPUT = adapter.INPUT
    REAL_OUTPUT_ROOT = adapter.OUTPUT_ROOT
    PLAN_SHA256 = adapter.PLAN_SHA256
    ORIGINAL_SHA256 = adapter.ARTIFACT_SHA256
    ORIGINAL_SIZE = adapter.ARTIFACT_SIZE

    def __init__(self, *, error=None, change=None):
        self.REAL_PROFILE = None
        self.calls = []
        self.error = error
        self.change = change

    @staticmethod
    def ProtocolProfile(*args):
        return SimpleNamespace(args=args)

    def convert_reviewed_real_file(self, name, plan):
        self.calls.append((name, plan, self.REAL_PROFILE))
        if self.error is not None:
            raise self.error
        result = dict(status='conversion_bytes_produced_unqualified',
            profile_id='reviewed-d2-existing-f32-v1', input_sha256=adapter.ARTIFACT_SHA256,
            input_bytes=17719103, output_sha256='8' * 64, output_bytes=5896708,
            tensor_entries=54, selected_storages=23, dense_data_bytes=5891996,
            model_or_tensor_constructed=False, pickle_interpreted=False,
            model_compatibility_qualified=False, release_approved=False)
        if self.change is not None:
            self.change(self, result)
        return result


class D2BoundaryCases(unittest.TestCase):
    def setUp(self):
        self.assertIsNone(adapter.OWNER_DECISION_SHA256)
        self.assertIs(type(FIXED_INPUTS), dict)
        self.profile_raw = FIXED_INPUTS['D2-PROFILE.json']
        self.d1_raw = FIXED_INPUTS['D1-RESULT.json']
        self.inventory_raw = FIXED_INPUTS['known-inventory.json']
        self.plan_raw = FIXED_INPUTS['fixed-plan.json']
        self.profile, self.names = adapter._evidence(
            self.profile_raw, self.d1_raw, self.inventory_raw, self.plan_raw)

    def tearDown(self):
        self.assertIsNone(adapter.OWNER_DECISION_SHA256)

    def execute_fake(self, port):
        return adapter._execute(port, self.profile, self.names, self.plan_raw)

    def test_closed_public_entry_precedes_converter_and_evidence_access(self):
        class Trap:
            def __getattr__(self, name):
                raise AssertionError('No converter attribute may be accessed')
        with self.assertRaisesRegex(adapter.Refusal, 'owner approval remains absent'):
            adapter.run_once(Trap(), profile_raw=object(), d1_raw=object(),
                inventory_raw=object(), plan_raw=object(), decision_raw=object(), admission_raw=object())

    def test_exact_evidence_preserves_measured_d1_and_all_inventory_names(self):
        self.assertEqual(self.profile['archive_version_hex'], '330a')
        self.assertEqual(len(self.names), 131)
        self.assertIn('archive/data/128', self.names)
        self.assertEqual(self.profile['source_byte_order'], 'little')
        self.assertEqual(self.profile['status'], 'proposal_no_execution_authority')

    def test_changed_each_evidence_input_refuses(self):
        original = [self.profile_raw, self.d1_raw, self.inventory_raw, self.plan_raw]
        for position in range(4):
            changed = list(original)
            changed[position] += b' '
            with self.assertRaisesRegex(adapter.Refusal, 'Exact fixed D2 evidence'):
                adapter._evidence(*changed)

    def test_none_owner_digest_refuses_generated_approval(self):
        with self.assertRaisesRegex(adapter.Refusal, 'owner approval remains absent'):
            adapter._decision(encoded(generated_decision()), None)

    def test_wrong_owner_digest_refuses(self):
        with self.assertRaisesRegex(adapter.Refusal, 'Exact D2 owner decision'):
            adapter._decision(encoded(generated_decision()), '0' * 64)

    def test_generated_private_decision_predicate_accepts_only_fixed_scope(self):
        record = generated_decision()
        raw = encoded(record)
        self.assertEqual(adapter._decision(raw, adapter.sha(raw)), record)
        self.assertIsNone(adapter.OWNER_DECISION_SHA256)

    def test_missing_each_assumption_or_notice_disposition_refuses(self):
        for key in adapter.PREREQUISITES:
            record = generated_decision()
            record[key] = False
            raw = encoded(record)
            with self.assertRaisesRegex(adapter.Refusal, 'remains unaccepted'):
                adapter._decision(raw, adapter.sha(raw))

    def test_broader_reader_native_network_or_release_claim_refuses(self):
        for key in ('model_execution_authorized', 'network_authorized',
                    'redistribution_authorized', 'real_reader_authorized', 'release_authorized'):
            record = generated_decision()
            record[key] = True
            raw = encoded(record)
            with self.assertRaisesRegex(adapter.Refusal, 'authority exceeds fixed scope'):
                adapter._decision(raw, adapter.sha(raw))

    def test_wrong_profile_run_or_output_in_decision_refuses(self):
        for key in ('profile_sha256', 'run_id', 'output_basename'):
            record = generated_decision()
            record[key] = 'wrong'
            raw = encoded(record)
            with self.assertRaisesRegex(adapter.Refusal, 'decision scope mismatch'):
                adapter._decision(raw, adapter.sha(raw))

    def test_missing_source_note_or_decision_text_refuses(self):
        for key in ('source_note_sha256', 'decision_text'):
            record = generated_decision()
            record[key] = None
            raw = encoded(record)
            with self.assertRaisesRegex(adapter.Refusal, 'text/source binding required'):
                adapter._decision(raw, adapter.sha(raw))

    def test_duplicate_json_and_oversized_input_refuse(self):
        for raw in (b'{"x":1,"x":2}', b' ' * 65537):
            with self.assertRaises(adapter.Refusal):
                adapter.decode(raw)

    def test_root_unreviewed_wrong_owner_or_wrong_profile_refuses(self):
        for key, value in (('root_reviewed', False), ('owner_decision_sha256', '1' * 64),
                           ('profile_sha256', '1' * 64), ('run_id', 'other')):
            record = generated_admission('0' * 64)
            record[key] = value
            with self.assertRaisesRegex(adapter.Refusal, 'Exact D2 root admission'):
                adapter._admission(encoded(record), '0' * 64)

    def test_private_generated_admission_does_not_activate_owner_pin(self):
        record = generated_admission('0' * 64)
        self.assertEqual(adapter._admission(encoded(record), '0' * 64), record)
        self.assertIsNone(adapter.OWNER_DECISION_SHA256)

    def test_fake_port_receives_exact_real_profile_and_frozen_plan_once(self):
        port = FakeConverter()
        result = self.execute_fake(port)
        self.assertEqual(len(port.calls), 1)
        name, plan, issued = port.calls[0]
        self.assertEqual(name, 'default-vad-d2-01.safetensors')
        self.assertIs(plan, self.plan_raw)
        self.assertEqual(issued.args, ('real', 'reviewed-d2-existing-f32-v1',
            adapter.ARTIFACT_SHA256, 17719103, 'little', 'IEEE754-binary32', b'3\n',
            self.names, adapter.PROFILE_SHA256))
        self.assertFalse(result['release_approved'])
        self.assertIsNone(port.REAL_PROFILE)

    def test_existing_active_profile_refuses_without_overwriting_it(self):
        port = FakeConverter()
        active = object()
        port.REAL_PROFILE = active
        with self.assertRaisesRegex(adapter.Refusal, 'unexpectedly active'):
            self.execute_fake(port)
        self.assertIs(port.REAL_PROFILE, active)
        self.assertEqual(port.calls, [])

    def test_wrong_input_or_output_port_path_refuses_before_call(self):
        for key in ('REAL_INPUT', 'REAL_OUTPUT_ROOT'):
            port = FakeConverter()
            setattr(port, key, 'outside')
            with self.assertRaisesRegex(adapter.Refusal, 'paths differ'):
                self.execute_fake(port)
            self.assertEqual(port.calls, [])
            self.assertIsNone(port.REAL_PROFILE)

    def test_changed_plan_refuses_before_port_call(self):
        port = FakeConverter()
        with self.assertRaisesRegex(adapter.Refusal, 'Fixed plan changed'):
            adapter._execute(port, self.profile, self.names, self.plan_raw + b' ')
        self.assertEqual(port.calls, [])
        self.assertIsNone(port.REAL_PROFILE)

    def test_port_write_failure_propagates_same_error_and_resets_profile(self):
        original = OSError('generated short/failed-write control')
        port = FakeConverter(error=original)
        with self.assertRaises(OSError) as raised:
            self.execute_fake(port)
        self.assertIs(raised.exception, original)
        self.assertEqual(len(port.calls), 1)
        self.assertIsNone(port.REAL_PROFILE)

    def test_port_deadline_refusal_propagates_same_error_and_resets_profile(self):
        original = adapter.Refusal('generated deadline control')
        port = FakeConverter(error=original)
        with self.assertRaises(adapter.Refusal) as raised:
            self.execute_fake(port)
        self.assertIs(raised.exception, original)
        self.assertIsNone(port.REAL_PROFILE)

    def test_replaced_profile_is_refused_and_cleared(self):
        def change(port, result):
            port.REAL_PROFILE = object()
        port = FakeConverter(change=change)
        with self.assertRaisesRegex(adapter.Refusal, 'profile replaced'):
            self.execute_fake(port)
        self.assertIsNone(port.REAL_PROFILE)

    def test_incomplete_count_input_or_status_report_refuses(self):
        for key, value in (('tensor_entries', 53), ('selected_storages', 22),
                           ('input_sha256', '0' * 64), ('status', 'accepted')):
            port = FakeConverter(change=lambda port, result, k=key, v=value: result.update({k: v}))
            with self.assertRaisesRegex(adapter.Refusal, 'Incomplete fixed conversion report'):
                self.execute_fake(port)
            self.assertIsNone(port.REAL_PROFILE)

    def test_invalid_output_hash_size_and_boolean_size_refuse(self):
        for key, value in (('output_sha256', 'wrong'), ('output_bytes', 6291457),
                           ('output_bytes', 0), ('output_bytes', True)):
            port = FakeConverter(change=lambda port, result, k=key, v=value: result.update({k: v}))
            with self.assertRaisesRegex(adapter.Refusal, 'Invalid conversion output identity'):
                self.execute_fake(port)
            self.assertIsNone(port.REAL_PROFILE)

    def test_model_pickle_compatibility_or_release_report_refuses(self):
        for key in ('model_or_tensor_constructed', 'pickle_interpreted',
                    'model_compatibility_qualified', 'release_approved'):
            port = FakeConverter(change=lambda port, result, k=key: result.update({k: True}))
            with self.assertRaisesRegex(adapter.Refusal, 'claims broader authority'):
                self.execute_fake(port)
            self.assertIsNone(port.REAL_PROFILE)
