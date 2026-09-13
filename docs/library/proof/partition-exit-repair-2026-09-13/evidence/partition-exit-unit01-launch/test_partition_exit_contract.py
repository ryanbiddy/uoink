"""Pure synthetic receipt cases; no product test, process or filesystem access."""
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from _scratch.partition_exit_contract import PartitionContractError, junit_identity, validate_partition


NODE = 'tests/test_contract.py::test_sample'


def fixture(outcomes=('passed', 'passed', 'passed'), *, xml_groups=None, xml_tests=None):
    phases = ('setup', 'call', 'teardown') if len(outcomes) == 3 else ('setup', 'teardown')
    reports = [{'nodeid': NODE, 'when': phase, 'outcome': outcome, 'duration': 0.01, 'wasxfail': None}
               for phase, outcome in zip(phases, outcomes)]
    failures = [(phase, outcome) for phase, outcome in zip(phases, outcomes) if outcome == 'failed']
    failure_tags = ['failure' if phase == 'call' else 'error' for phase, _ in failures]
    skip_count = outcomes.count('skipped')
    if xml_groups is None:
        tags = [('failure' if phase == 'call' else 'error') if outcome == 'failed' else 'skipped'
                for phase, outcome in zip(phases, outcomes) if outcome != 'passed']
        xml_groups = [tags]
    if xml_tests is None:
        xml_tests = sum(len(tags) or 1 for tags in xml_groups)
    suite = ET.Element('testsuite', name='pytest', tests=str(xml_tests), failures=str(failure_tags.count('failure')),
                       errors=str(failure_tags.count('error')), skipped=str(skip_count), time='0.125')
    for tags in xml_groups:
        item = ET.SubElement(suite, 'testcase', classname='tests.test_contract', name='test_sample', time='0.025')
        for tag in tags:
            ET.SubElement(item, tag, message='synthetic ' + tag)
    exitstatus = int(bool(failures))
    return {'selected': [NODE], 'reports': reports,
            'session': {'exit': exitstatus, 'tests_collected': 1, 'tests_failed': len(failures), 'reports': len(reports)},
            'verifier_results': [{'name': 'tests', 'command': ['inert-python', '-B', '-m', 'pytest', 'synthetic-only'], 'exit': exitstatus}],
            'outer_exit': exitstatus, 'junit_xml': ET.tostring(suite)}


@pytest.mark.parametrize('outcomes,groups,raw_total,status,failed', [
    (('passed', 'passed', 'passed'), [[]], 1, 'passed', []),
    (('passed', 'failed', 'passed'), [['failure']], 1, 'failed', ['call']),
    (('failed', 'passed'), [['error']], 1, 'error', ['setup']),
    (('passed', 'passed', 'failed'), [['error']], 1, 'error', ['teardown']),
    (('passed', 'failed', 'failed'), [['failure'], ['error']], 2, 'error', ['call', 'teardown']),
    (('failed', 'failed'), [['error', 'error']], 1, 'error', ['setup', 'teardown']),
    (('skipped', 'passed'), [['skipped']], 1, 'skipped', []),
    (('passed', 'skipped', 'passed'), [['skipped']], 1, 'skipped', []),
    (('passed', 'skipped', 'failed'), [['skipped', 'error']], 1, 'error', ['teardown']),
    (('passed', 'passed', 'skipped'), [['skipped']], 2, 'skipped', []),
])
def test_completed_outcomes_are_preserved(outcomes, groups, raw_total, status, failed):
    data = fixture(outcomes, xml_groups=groups, xml_tests=raw_total)
    before = deepcopy(data)
    result = validate_partition(**data)
    assert result['counts'] == {status: 1}
    assert result['case_count'] == 1 and result['cases'][NODE]['failed_phases'] == failed
    assert result['failed_phase_count'] == len(failed)
    assert result['result'] == ('FAIL' if failed else 'PASS') and result['complete'] is True
    assert result['junit']['case_elements'] == len(groups)
    assert result['junit']['raw_suite_counts']['tests'] == raw_total
    assert data == before


def test_shutdown_failure_after_green_reports_is_incomplete():
    data = fixture()
    data['verifier_results'][0]['exit'] = 1
    data['outer_exit'] = 1
    with pytest.raises(PartitionContractError, match='actual pytest exit disagrees with session exit'):
        validate_partition(**data)


@pytest.mark.parametrize('exitstatus', [2, 3, 4, 5, -1, True])
def test_abnormal_or_invalid_raw_pytest_exits_are_refused(exitstatus):
    data = fixture()
    data['verifier_results'][0]['exit'] = exitstatus
    data['outer_exit'] = 1
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


@pytest.mark.parametrize('field,value', [('exit', 3), ('tests_collected', 2), ('tests_failed', 1), ('reports', 2), ('reports', True)])
def test_session_receipt_disagreements_are_refused(field, value):
    data = fixture()
    data['session'][field] = value
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


def test_failure_exit_with_no_failed_reports_is_refused():
    data = fixture()
    data['session']['exit'] = data['verifier_results'][0]['exit'] = data['outer_exit'] = 1
    with pytest.raises(PartitionContractError, match='failed phase reports'):
        validate_partition(**data)


def test_outer_verifier_failure_cannot_be_hidden_by_green_pytest():
    data = fixture()
    data['outer_exit'] = 1
    with pytest.raises(PartitionContractError, match='outer verifier exit'):
        validate_partition(**data)


@pytest.mark.parametrize('edit', ['drop_setup', 'drop_call', 'drop_teardown', 'reverse', 'duplicate', 'call_after_setup_failure', 'extra_node'])
def test_incomplete_or_duplicate_phase_reports_are_refused(edit):
    data = fixture()
    if edit.startswith('drop_'):
        data['reports'] = [row for row in data['reports'] if row['when'] != edit[5:]]
    elif edit == 'reverse':
        data['reports'].reverse()
    elif edit == 'duplicate':
        data['reports'].append(deepcopy(data['reports'][1]))
    elif edit == 'call_after_setup_failure':
        data['reports'][0]['outcome'] = 'failed'
    else:
        data['reports'][0]['nodeid'] = 'tests/test_other.py::test_other'
    data['session']['reports'] = len(data['reports'])
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


@pytest.mark.parametrize('edit', ['duplicate_member', 'missing_member', 'empty_membership', 'ambiguous_identity'])
def test_membership_must_be_complete_unique_and_unambiguous(edit):
    data = fixture()
    if edit == 'duplicate_member':
        data['selected'].append(NODE)
    elif edit == 'missing_member':
        data['selected'].append('tests/test_missing.py::test_missing')
    elif edit == 'empty_membership':
        data['selected'] = []
    else:
        data['selected'] = ['tests/a.b.py::test_same', 'tests/a/b.py::test_same']
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


@pytest.mark.parametrize('edit', ['missing_element', 'duplicate_element', 'wrong_name', 'wrong_class', 'extra_outcome', 'wrong_counter', 'xfail'])
def test_junit_disagreements_are_refused(edit):
    data = fixture()
    suite = ET.fromstring(data['junit_xml'])
    item = suite.find('testcase')
    if edit == 'missing_element':
        suite.remove(item)
    elif edit == 'duplicate_element':
        suite.append(deepcopy(item))
    elif edit == 'wrong_name':
        item.set('name', 'test_other')
    elif edit == 'wrong_class':
        item.set('classname', 'tests.test_other')
    elif edit == 'extra_outcome':
        ET.SubElement(item, 'failure')
    elif edit == 'wrong_counter':
        suite.set('tests', '2')
    else:
        ET.SubElement(item, 'skipped', type='pytest.xfail')
    data['junit_xml'] = ET.tostring(suite)
    with pytest.raises(PartitionContractError):
        validate_partition(**data)


def test_duplicate_failure_xml_cannot_replace_required_teardown_error():
    data = fixture(('passed', 'failed', 'failed'), xml_groups=[['failure'], ['failure']], xml_tests=2)
    with pytest.raises(PartitionContractError, match='testcase duplication disagree'):
        validate_partition(**data)


def test_double_failure_keeps_two_failed_phases_but_one_case():
    data = fixture(('passed', 'failed', 'failed'), xml_groups=[['failure'], ['error']], xml_tests=2)
    result = validate_partition(**data)
    assert result['case_count'] == 1 and result['failed_phase_count'] == 2
    assert result['failed_phases'] == [{'nodeid': NODE, 'when': 'call', 'outcome': 'failed'},
                                       {'nodeid': NODE, 'when': 'teardown', 'outcome': 'failed'}]


def test_parameter_identity_preserves_colons_slashes_and_control_escape():
    assert junit_identity('tests/test_contract.py::Class::test_sample[a::b/c]') == ('tests.test_contract.Class', 'test_sample[a::b/c]')
    assert junit_identity('tests/test_contract.py::test_sample[\x07]') == ('tests.test_contract', 'test_sample[#x07]')


@pytest.mark.parametrize('edit', ['extra_verifier', 'wrong_command', 'missing_session', 'xfail_report', 'nan_duration', 'bad_xml'])
def test_malformed_or_out_of_scope_receipts_are_refused(edit):
    data = fixture()
    if edit == 'extra_verifier':
        data['verifier_results'].append(deepcopy(data['verifier_results'][0]))
    elif edit == 'wrong_command':
        data['verifier_results'][0]['command'] = ['inert-python', '-m', 'other']
    elif edit == 'missing_session':
        data['session'] = None
    elif edit == 'xfail_report':
        data['reports'][1]['wasxfail'] = 'synthetic expected failure'
    elif edit == 'nan_duration':
        data['reports'][1]['duration'] = float('nan')
    else:
        data['junit_xml'] = '<broken'
    with pytest.raises(PartitionContractError):
        validate_partition(**data)
