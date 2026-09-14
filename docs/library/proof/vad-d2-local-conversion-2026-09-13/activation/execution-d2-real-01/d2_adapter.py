"""Dormant D2 adapter. No imports from data, filesystem API, or reader activation.

Only the hash-bound child may call run_once with the frozen converter module.
Private validators/port orchestration are test seams, not caller authority.
"""
import hashlib
import json
import re

OWNER_DECISION_SHA256 = 'dbcf0c2abfde5ef7a21482da7358c14361e0195887aa32772f57546c40fc65fa'
SCOPE = 'D2_ONE_LOCAL_FIXED54_CONVERSION_ONLY'
RUN_ID = 'd2-real-01'
PROFILE_SHA256 = 'f0c60e2fa349b945108b4d15dccc8fe2d68ca4cab8588e8c0ff7f2e8762f75d3'
D1_SHA256 = '754ca6dea6aed81de072940b35ad4c283f270b5770a88236ef55fd0a09d46e75'
INVENTORY_SHA256 = '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc'
PLAN_SHA256 = '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf'
ARTIFACT_SHA256 = '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'
ARTIFACT_SIZE = 17719103
ROOT = r'E:\AI\projects\uoink\checkouts\Yoink-library'
INPUT = ROOT + r'\installer\staging\python\Lib\site-packages\whisperx\assets\pytorch_model.bin'
OUTPUT_ROOT = ROOT + r'\_scratch\vad-fixed-converter-approved-output'
OUTPUT_NAME = 'default-vad-d2-01.safetensors'
PREREQUISITES = (
    'accept_uniform_raw_storage_writer_assumption',
    'accept_IEEE754_binary32_interpretation',
    'accept_dense_fixed_ranges_and_omitted_legacy_metadata',
    'accept_local_conversion_only_with_model_notice_unresolved',
)


class Refusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Refusal(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(rows):
    result = {}
    for key, value in rows:
        require(type(key) is str and key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, 'Bounded decision/evidence bytes required')
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refusal('Malformed decision/evidence JSON') from error


def _evidence(profile_raw, d1_raw, inventory_raw, plan_raw):
    for raw, digest in ((profile_raw, PROFILE_SHA256), (d1_raw, D1_SHA256),
                        (inventory_raw, INVENTORY_SHA256), (plan_raw, PLAN_SHA256)):
        require(type(raw) is bytes and 0 < len(raw) <= 65536 and sha(raw) == digest,
                'Exact fixed D2 evidence required')
    profile, d1, inventory = decode(profile_raw), decode(d1_raw), decode(inventory_raw)
    require(profile['status'] == 'proposal_no_execution_authority' and profile['scope'] == SCOPE
            and tuple(profile['owner_prerequisites']) == PREREQUISITES, 'Fixed profile scope mismatch')
    require(d1['status'] == 'static_inspection_complete_unqualified'
            and d1['version_actual_hex'] == profile['archive_version_hex'] == '330a'
            and d1['input']['sha256'] == ARTIFACT_SHA256
            and d1['input']['bytes'] == ARTIFACT_SIZE, 'D1 input/version binding mismatch')
    basis = d1['buffer_basis']
    require(basis['orientation'] == 'little' and basis['ulp_limit'] == 8
            and basis['word_count'] == 250 and basis['orientations']['little']['matches_both'] is True
            and basis['orientations']['big']['matches_both'] is False
            and basis['real_profile_approved'] is False and basis['other_storages_validated'] is False,
            'D1 consistency scope mismatch')
    require(type(inventory) is list and len(inventory) == 131, 'Fixed inventory count mismatch')
    names = tuple(row[0] for row in inventory)
    require(len(set(names)) == 131, 'Fixed inventory names ambiguous')
    return profile, names


def _decision(decision_raw, expected_digest):
    require(type(expected_digest) is str and re.fullmatch('[0-9a-f]{64}', expected_digest),
            'D2 owner approval remains absent')
    require(type(decision_raw) is bytes and sha(decision_raw) == expected_digest,
            'Exact D2 owner decision required')
    decision = decode(decision_raw)
    require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
            and decision.get('scope') == SCOPE and decision.get('profile_sha256') == PROFILE_SHA256
            and decision.get('run_id') == RUN_ID and decision.get('output_basename') == OUTPUT_NAME,
            'D2 decision scope mismatch')
    require(type(decision.get('decision_text')) is str and 0 < len(decision['decision_text']) <= 2048
            and type(decision.get('source_note_sha256')) is str
            and re.fullmatch('[0-9a-f]{64}', decision['source_note_sha256']),
            'Recorded D2 decision text/source binding required')
    require(all(decision.get(name) is True for name in PREREQUISITES),
            'D2 interpretation/migration/notice disposition remains unaccepted')
    require(decision.get('conversion_authorized') is True
            and all(decision.get(name) is False for name in (
                'model_execution_authorized', 'network_authorized', 'redistribution_authorized',
                'real_reader_authorized', 'release_authorized')), 'D2 authority exceeds fixed scope')
    return decision


def _admission(admission_raw, owner_digest):
    admission = decode(admission_raw)
    require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
            and admission.get('run_id') == RUN_ID
            and admission.get('owner_decision_sha256') == owner_digest
            and admission.get('profile_sha256') == PROFILE_SHA256, 'Exact D2 root admission required')
    return admission


def _execute(converter, profile, names, plan_raw):
    # Private fake-port seam. Only run_once is the invocation entry point.
    require(converter.REAL_PROFILE is None, 'Converter profile unexpectedly active')
    require(str(converter.REAL_INPUT) == INPUT and str(converter.REAL_OUTPUT_ROOT) == OUTPUT_ROOT,
            'Frozen converter paths differ')
    require(converter.PLAN_SHA256 == PLAN_SHA256 and converter.ORIGINAL_SHA256 == ARTIFACT_SHA256
            and converter.ORIGINAL_SIZE == ARTIFACT_SIZE, 'Frozen converter identity differs')
    require(sha(plan_raw) == PLAN_SHA256, 'Fixed plan changed before conversion')
    runtime_profile = converter.ProtocolProfile('real', profile['profile_id'], ARTIFACT_SHA256,
        ARTIFACT_SIZE, 'little', 'IEEE754-binary32', bytes.fromhex('330a'), names, PROFILE_SHA256)
    converter.REAL_PROFILE = runtime_profile
    try:
        report = converter.convert_reviewed_real_file(OUTPUT_NAME, plan_raw)
        require(converter.REAL_PROFILE is runtime_profile, 'Converter profile replaced during conversion')
        require(type(report) is dict and report.get('status') == 'conversion_bytes_produced_unqualified'
                and report.get('profile_id') == profile['profile_id']
                and report.get('input_sha256') == ARTIFACT_SHA256
                and report.get('input_bytes') == ARTIFACT_SIZE
                and report.get('tensor_entries') == 54 and report.get('selected_storages') == 23
                and report.get('dense_data_bytes') == 5891996, 'Incomplete fixed conversion report')
        require(type(report.get('output_sha256')) is str
                and re.fullmatch('[0-9a-f]{64}', report['output_sha256'])
                and type(report.get('output_bytes')) is int
                and 5891996 < report['output_bytes'] <= 6291456, 'Invalid conversion output identity')
        require(all(report.get(name) is False for name in ('model_or_tensor_constructed',
                'pickle_interpreted', 'model_compatibility_qualified', 'release_approved')),
                'Conversion report claims broader authority')
        return report
    finally:
        converter.REAL_PROFILE = None


def run_once(converter, *, profile_raw, d1_raw, inventory_raw, plan_raw, decision_raw, admission_raw):
    # This remains before converter attributes, evidence parsing and every file path operation.
    require(OWNER_DECISION_SHA256 is not None, 'D2 owner approval remains absent')
    _decision(decision_raw, OWNER_DECISION_SHA256)
    _admission(admission_raw, OWNER_DECISION_SHA256)
    profile, names = _evidence(profile_raw, d1_raw, inventory_raw, plan_raw)
    return _execute(converter, profile, names, plan_raw)
