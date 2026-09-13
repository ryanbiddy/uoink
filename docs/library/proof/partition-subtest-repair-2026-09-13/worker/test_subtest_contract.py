"""Pure synthetic subtest receipt contracts and retained inert-preflight replay."""
from copy import deepcopy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from _scratch.partition_exit_contract import PartitionContractError, validate_partition
from _scratch.test_partition_exit_contract import fixture, NODE


def receipt(subs=('passed',), parent='passed', before=None, teardown='passed', groups=None, xml_tests=2):
    data = fixture()
    ordinary = data['reports']
    ordinary[1]['outcome'] = parent
    ordinary[2]['outcome'] = teardown
    for row in ordinary:
        row.update(report_type='TestReport', report_class='_pytest.reports.TestReport',
                   outcome_before_hooks=row['outcome'], outcome_transition_reason=None, subtest=None)
    ordinary[1]['outcome_before_hooks'] = before or parent
    if ordinary[1]['outcome_before_hooks'] != parent:
        count = subs.count('failed')
        ordinary[1]['outcome_transition_reason'] = 'contains %d failed subtest%s' % (count, 's' if count != 1 else '')
    children = [dict(nodeid=NODE, when='call', outcome=outcome, duration=0.01, wasxfail=None,
                     report_type='SubtestReport', report_class='_pytest.subtests.SubtestReport',
                     outcome_before_hooks=outcome, outcome_transition_reason=None,
                     subtest={'ordinal': i + 1, 'context': {'msg': 'same context', 'kwargs': {'value': "'repeat'"}}})
                for i, outcome in enumerate(subs)]
    data['reports'] = [ordinary[0], *children, *ordinary[1:]]
    for i, row in enumerate(data['reports']):
        row['report_index'] = i
    failed = sum(row['outcome_before_hooks'] == 'failed' for row in data['reports'])
    data['session'].update(exit=int(bool(failed)), tests_failed=failed, reports=len(data['reports']))
    data['verifier_results'][0]['exit'] = data['outer_exit'] = int(bool(failed))
    groups = groups if groups is not None else [[]]
    tags = [tag for group in groups for tag in group]
    suite = ET.Element('testsuite', name='pytest', tests=str(xml_tests), failures=str(tags.count('failure')),
                       errors=str(tags.count('error')), skipped=str(tags.count('skipped')), time='0.15')
    for group in groups:
        case = ET.SubElement(suite, 'testcase', classname='tests.test_contract', name='test_sample', time='0.1')
        for tag in group:
            ET.SubElement(case, tag, message='synthetic ' + tag)
    data['junit_xml'] = ET.tostring(suite)
    return data


@pytest.mark.parametrize('subs,parent,before,teardown,groups,total,status,raw,promoted', [
    (('passed',), 'passed', None, 'passed', [[]], 2, 'passed', 0, 0),
    (('passed','passed'), 'passed', None, 'passed', [[]], 3, 'passed', 0, 0),
    (('failed',), 'passed', None, 'passed', [['failure']], 2, 'failed', 1, 0),
    (('failed',), 'failed', 'passed', 'passed', [['failure','failure']], 2, 'failed', 1, 1),
    (('skipped',), 'passed', None, 'passed', [['skipped']], 2, 'passed', 0, 0),
    (('failed',), 'skipped', None, 'passed', [['failure','skipped']], 2, 'failed', 1, 0),
    (('failed',), 'failed', None, 'failed', [['failure','failure'],['error']], 3, 'error', 3, 0),
    (('failed',), 'passed', None, 'failed', [['failure'],['error']], 3, 'error', 2, 0),
    (('passed',), 'passed', None, 'failed', [['error']], 2, 'error', 1, 0),
    (('failed','failed'), 'failed', 'passed', 'failed', [['failure','failure','failure'],['error']], 4, 'error', 3, 1),
])
def test_native_top_level_and_subtest_counts_remain_distinct(subs, parent, before, teardown, groups, total, status, raw, promoted):
    data = receipt(subs, parent, before, teardown, groups, total)
    original = deepcopy(data)
    result = validate_partition(**data)
    assert data == original
    assert result['case_count'] == 1 and result['counts'] == {status: 1}
    assert result['subtest_count'] == len(subs)
    assert result['failed_subtest_count'] == subs.count('failed')
    assert result['raw_failed_report_count'] == raw
    assert result['promoted_parent_failure_count'] == promoted
    assert result['reported_failed_report_count'] == raw + promoted
    assert result['junit']['raw_suite_counts']['tests'] == total
    assert result['result'] == ('FAIL' if raw else 'PASS')


@pytest.mark.parametrize('edit', [
    'missing_type','unknown_type','wrong_class','missing_context','context_on_parent',
    'nonstring_message','nonstring_parameter','missing_ordinal','duplicate_index','missing_index',
    'wrong_ordinal','wrong_subtest_phase','subtest_after_teardown','duplicate_parent_call',
    'missing_parent_call','unexplained_parent_promotion','changed_subtest_outcome',
    'spurious_transition','extra_context_field','mixed_legacy','extra_duplicate_child',
])
def test_incomplete_ambiguous_or_unexplained_reports_are_refused(edit):
    data = receipt()
    child = data['reports'][1]
    if edit == 'missing_type': del child['report_type']
    elif edit == 'unknown_type': child['report_type'] = 'OtherReport'
    elif edit == 'wrong_class': child['report_class'] = '_pytest.reports.TestReport'
    elif edit == 'missing_context': child['subtest'] = None
    elif edit == 'context_on_parent': data['reports'][0]['subtest'] = child['subtest']
    elif edit == 'nonstring_message': child['subtest']['context']['msg'] = 5
    elif edit == 'nonstring_parameter': child['subtest']['context']['kwargs']['value'] = 5
    elif edit == 'missing_ordinal': del child['subtest']['ordinal']
    elif edit == 'duplicate_index': child['report_index'] = 0
    elif edit == 'missing_index': del child['report_index']
    elif edit == 'wrong_ordinal': child['subtest']['ordinal'] = 2
    elif edit == 'wrong_subtest_phase': child['when'] = 'setup'
    elif edit == 'subtest_after_teardown': data['reports'].append(data['reports'].pop(1))
    elif edit == 'duplicate_parent_call': data['reports'].insert(3, deepcopy(data['reports'][2]))
    elif edit == 'missing_parent_call': del data['reports'][2]
    elif edit == 'unexplained_parent_promotion':
        data['reports'][2].update(outcome='failed', outcome_transition_reason='contains 0 failed subtests')
    elif edit == 'changed_subtest_outcome': child.update(outcome='failed', outcome_transition_reason='contains 1 failed subtest')
    elif edit == 'spurious_transition': child['outcome_transition_reason'] = 'not a transition'
    elif edit == 'extra_context_field': child['subtest']['context']['unknown'] = True
    elif edit == 'mixed_legacy': del data['reports'][0]['report_type']
    elif edit == 'extra_duplicate_child':
        duplicate = deepcopy(child)
        duplicate['subtest']['ordinal'] = 2
        data['reports'].insert(2, duplicate)
    if edit in ('subtest_after_teardown','duplicate_parent_call','missing_parent_call','extra_duplicate_child'):
        for i, row in enumerate(data['reports']): row['report_index'] = i
        data['session']['reports'] = len(data['reports'])
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


@pytest.mark.parametrize('edit', ['raw_count_uses_promoted','raw_exit_green','outer_exit_green','xml_top_level_total','xml_drops_subfailure','extra_xml_case','promotion_reason','missing_subfailure'])
def test_failure_and_xml_disagreements_cannot_be_normalized_away(edit):
    data = receipt(('failed',), 'failed', 'passed', groups=[['failure','failure']])
    if edit == 'raw_count_uses_promoted': data['session']['tests_failed'] = 2
    elif edit == 'raw_exit_green': data['verifier_results'][0]['exit'] = 0
    elif edit == 'outer_exit_green': data['outer_exit'] = 0
    elif edit == 'promotion_reason': data['reports'][2]['outcome_transition_reason'] = 'contains 2 failed subtests'
    elif edit == 'missing_subfailure':
        data['reports'][1].update(outcome='passed', outcome_before_hooks='passed')
    else:
        xml = ET.fromstring(data['junit_xml'])
        if edit == 'xml_top_level_total': xml.set('tests', '1')
        elif edit == 'xml_drops_subfailure':
            xml[0].remove(xml[0][0])
            xml.set('failures', '1')
            xml.set('tests', '1')
        elif edit == 'extra_xml_case': xml.append(deepcopy(xml[0]))
        data['junit_xml'] = ET.tostring(xml)
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


def test_actual_native02_receipts_reconcile_without_relabeling_intentional_failure():
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    folder = here / 'native02-partition'
    result = validate_partition(
        selected=json.loads((folder/'membership.json').read_bytes()),
        reports=[json.loads(line) for line in (folder/'reports.jsonl').read_text().splitlines()],
        session=json.loads((folder/'session.json').read_bytes()),
        verifier_results=json.loads((root/'_scratch/partition-subtest-native02/results.json').read_bytes()),
        outer_exit=1, junit_xml=(root/'_scratch/partition-subtest-native02/tests.xml').read_bytes())
    assert result['result'] == 'FAIL' and result['complete']
    assert result['counts'] == {'passed': 4, 'failed': 6, 'error': 3}
    assert result['case_count'] == 13 and result['report_count'] == 57
    assert result['subtest_counts'] == {'passed': 8, 'failed': 8, 'skipped': 2}
    assert result['raw_failed_report_count'] == 14 and result['reported_failed_report_count'] == 16
    assert result['junit']['raw_suite_counts'] == {'tests': 33, 'failures': 13, 'errors': 3, 'skipped': 3}
    assert result['junit']['case_elements'] == 15


def guard_receipt():
    return {'profile':'synthetic-import-blocked-no-native-model-credit',
            'already_loaded_at_startup':[], 'blocked_import_attempts':['whisperx'],
            'pytest_exitstatus':1, 'guard_installed_at_finish':True}


def test_parent_process_guard_receipt_preserves_failed_exit_and_scope():
    from _scratch.partition_exit_contract import validate_heavy_guard
    result = validate_heavy_guard(guard_receipt(), 1)
    assert result['validated'] and result['blocked_attempt_count'] == 1
    assert 'subprocesses are not covered' in result['scope']
    assert result['native_or_model_qualification'] is False


@pytest.mark.parametrize('edit',['missing','preloaded','removed','wrong_exit','wrong_profile','unknown_attempt','missing_attempts'])
def test_absent_or_unhealthy_guard_receipts_are_refused(edit):
    from _scratch.partition_exit_contract import validate_heavy_guard
    data = guard_receipt()
    if edit == 'missing': data = None
    elif edit == 'preloaded': data['already_loaded_at_startup'] = ['torch']
    elif edit == 'removed': data['guard_installed_at_finish'] = False
    elif edit == 'wrong_exit': data['pytest_exitstatus'] = 0
    elif edit == 'wrong_profile': data['profile'] = 'unqualified'
    elif edit == 'unknown_attempt': data['blocked_import_attempts'] = ['other_module']
    elif edit == 'missing_attempts': del data['blocked_import_attempts']
    with pytest.raises(PartitionContractError): validate_heavy_guard(data, 1)
