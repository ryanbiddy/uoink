"""Pure receipt validation for one completed guarded pytest partition.

No pytest, filesystem, process or product imports. A completed failed case stays
failed; inconsistent or incomplete execution raises PartitionContractError.
"""
from collections import Counter, defaultdict
import math
import re
from xml.etree import ElementTree as ET


class PartitionContractError(ValueError):
    """The supplied receipts do not establish a complete pytest partition."""


def _require(condition, message):
    if not condition:
        raise PartitionContractError(message)


def _integer(value, name):
    _require(type(value) is int and value >= 0, name + ' must be a nonnegative integer')
    return value


def _xml_integer(element, name):
    value = element.get(name)
    _require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value) is not None,
             'JUnit ' + name + ' must be a nonnegative integer')
    return int(value)


def _seconds(value, name):
    number = float(value)
    _require(math.isfinite(number) and number >= 0, name + ' must be finite and nonnegative')
    return number


def _xml_name(value):
    # pytest displays invalid XML characters as #xNN in its testcase name.
    def escaped(match):
        code = ord(match.group())
        return '#x%02X' % code if code <= 0xff else '#x%04X' % code
    return re.sub('[^\u0009\u000a\u000d\u0020-\u007e\u0080-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', escaped, value)


def junit_identity(nodeid):
    """pytest's unprefixed classname/name identity, including parameter suffixes."""
    head, bracket, parameter = nodeid.partition('[')
    parts = head.split('::')
    _require(len(parts) >= 2 and all(parts), 'unsupported pytest node identity: ' + nodeid)
    parts[0] = re.sub(r'\.py$', '', parts[0].replace('/', '.'))
    parts[-1] += bracket + parameter
    return '.'.join(parts[:-1]), _xml_name(parts[-1])


def validate_heavy_guard(receipt, pytest_exit):
    """Validate the parent pytest process's explicit import guard receipt."""
    _require(type(receipt) is dict, 'missing heavy-import guard receipt')
    _require(receipt.get('profile') == 'synthetic-import-blocked-no-native-model-credit', 'unexpected heavy-import guard profile')
    _require(receipt.get('already_loaded_at_startup') == [], 'heavy packages loaded before guard startup')
    _require(receipt.get('guard_installed_at_finish') is True, 'heavy-import guard absent at finish')
    _require(type(receipt.get('pytest_exitstatus')) is int and receipt['pytest_exitstatus'] == pytest_exit,
             'heavy-import guard exit differs from actual pytest exit')
    attempts = receipt.get('blocked_import_attempts')
    roots = {'whisperx', 'whisper', 'faster_whisper', 'torch', 'torchaudio', 'pyannote',
             'transformers', 'ctranslate2', 'tokenizers', 'huggingface_hub'}
    _require(type(attempts) is list and all(type(name) is str and name.split('.')[0] in roots for name in attempts),
             'invalid heavy-import attempt receipt')
    return {'validated': True, 'blocked_attempt_count': len(attempts),
            'scope': 'This pytest process only; subprocesses are not covered by this import plugin',
            'native_or_model_qualification': False}


def validate_partition(*, selected, reports, session, verifier_results, outer_exit, junit_xml):
    """Return normalized facts, or reject incomplete/contradictory raw receipts.

    Inputs are parsed JSON values and XML bytes/text. This contract is for the
    existing --runxfail, single-pytest-command guarded verifier, not collection.
    Typed receipts distinguish ordinary phases from subtests and preserve both
    outcomes around logreport hooks. Native pytest can promote a passing parent
    after Session counts failures; JUnit observes the final outcome. Legacy
    untyped receipts remain valid only under the ordinary one-report-per-phase
    contract. Neither JUnit tests nor raw failed reports count unique cases.
    """
    try:
        return _validate(selected, reports, session, verifier_results, outer_exit, junit_xml)
    except PartitionContractError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, ET.ParseError) as error:
        raise PartitionContractError('invalid receipt shape: ' + str(error)) from error


def _validate(selected, reports, session, verifier_results, outer_exit, junit_xml):
    _require(type(selected) is list and selected and all(type(node) is str and node for node in selected),
             'selected membership must be a nonempty list of node ids')
    _require(len(selected) == len(set(selected)), 'duplicate selected node id')
    identities = {}
    for node in selected:
        identity = junit_identity(node)
        _require(identity not in identities, 'ambiguous selected JUnit identity: ' + str(identity))
        identities[identity] = node
    _require(type(reports) is list and all(type(row) is dict for row in reports), 'reports must be a list of objects')
    typed = any('report_type' in row for row in reports)
    _require(not typed or all('report_type' in row for row in reports), 'mixed typed and legacy reports')
    grouped = defaultdict(list)
    for index, row in enumerate(reports):
        _require(row['nodeid'] in selected, 'unexpected report node id: ' + str(row['nodeid']))
        _require(row['when'] in ('setup', 'call', 'teardown'), 'unexpected report phase')
        _require(row['outcome'] in ('passed', 'failed', 'skipped'), 'unexpected report outcome')
        _require(row.get('wasxfail') is None, 'xfail receipt is outside the --runxfail contract')
        _seconds(row['duration'], 'report duration')
        if typed:
            _require(_integer(row['report_index'], 'report_index') == index, 'duplicate, missing or out-of-order report index')
            _require(row['report_type'] in ('TestReport', 'SubtestReport'), 'unknown report type')
            expected_class = '_pytest.subtests.SubtestReport' if row['report_type'] == 'SubtestReport' else '_pytest.reports.TestReport'
            _require(row['report_class'] == expected_class, 'report class disagrees with report type')
            _require(row['outcome_before_hooks'] in ('passed', 'failed', 'skipped'), 'invalid before-hooks outcome')
            if row['report_type'] == 'SubtestReport':
                _require(row['when'] == 'call', 'subtest report outside native call reporting')
                subtest = row['subtest']
                _require(type(subtest) is dict and set(subtest) == {'ordinal', 'context'}, 'missing or invalid subtest evidence')
                _integer(subtest['ordinal'], 'subtest ordinal')
                context = subtest['context']
                _require(type(context) is dict and set(context) == {'msg', 'kwargs'}, 'invalid subtest context')
                _require(context['msg'] is None or type(context['msg']) is str, 'invalid subtest message')
                _require(type(context['kwargs']) is dict and all(type(k) is str and type(v) is str for k, v in context['kwargs'].items()), 'invalid serialized subtest parameters')
            else:
                _require(row['subtest'] is None, 'ordinary report carries subtest context')
        grouped[row['nodeid']].append(row)
    _require(set(grouped) == set(selected), 'missing execution reports for selected cases')

    cases = {}
    failed_phases = []
    failed_subtests = []
    subtest_counts = Counter({'passed': 0, 'failed': 0, 'skipped': 0})
    promoted_parents = []
    raw_failed_phases = 0
    expected_xml = {}
    expected_stats = Counter({'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0})
    for node in selected:
        events = grouped[node]
        ordinary = [row for row in events if row.get('report_type', 'TestReport') == 'TestReport']
        subs = [row for row in events if row.get('report_type') == 'SubtestReport']
        phases = [row['when'] for row in ordinary]
        _require(len(phases) == len(set(phases)), 'duplicate phase report for ' + node)
        _require(phases and phases[0] == 'setup', 'missing initial setup report for ' + node)
        expected_phases = ['setup', 'call', 'teardown'] if ordinary[0]['outcome'] == 'passed' else ['setup', 'teardown']
        _require(phases == expected_phases, 'incomplete or out-of-order phase reports for ' + node)
        _require(events[-1] is ordinary[-1], 'subtest report after completed teardown for ' + node)
        if typed:
            _require([row['subtest']['ordinal'] for row in subs] == list(range(1, len(subs) + 1)), 'duplicate, missing or out-of-order subtest ordinal')
            prior_sub_failures = 0
            for row in events:
                before = row['outcome_before_hooks']
                after = row['outcome']
                if before != after:
                    expected_reason = 'contains %d failed subtest%s' % (prior_sub_failures, 's' if prior_sub_failures != 1 else '')
                    _require(row['report_type'] == 'TestReport' and row['when'] == 'call'
                             and before == 'passed' and after == 'failed' and prior_sub_failures > 0
                             and row['outcome_transition_reason'] == expected_reason,
                             'unexplained report outcome mutation for ' + node)
                    promoted_parents.append({'nodeid': node, 'report_index': row['report_index'], 'failed_subtests_before_parent': prior_sub_failures})
                else:
                    _require(row['outcome_transition_reason'] is None, 'spurious outcome transition reason')
                if row['report_type'] == 'SubtestReport' and before == 'failed':
                    prior_sub_failures += 1
        failures = [row['when'] for row in ordinary if row['outcome'] == 'failed']
        skipped = [row['when'] for row in ordinary if row['outcome'] == 'skipped']
        subfailures = [row for row in subs if row['outcome'] == 'failed']
        status = ('error' if any(phase != 'call' for phase in failures) else 'failed') if failures or subfailures else ('skipped' if skipped else 'passed')
        raw_failed_phases += sum(row.get('outcome_before_hooks', row['outcome']) == 'failed' for row in ordinary)
        normalized_subs = [{'report_index': row['report_index'], 'ordinal': row['subtest']['ordinal'],
                            'outcome': row['outcome'], 'context': row['subtest']['context']} for row in subs]
        subtest_counts.update(row['outcome'] for row in subs)
        failed_subtests.extend({'nodeid': node, **row} for row in normalized_subs if row['outcome'] == 'failed')
        cases[node] = {'status': status, 'failed_phases': failures,
                       'phase_outcomes': [{'when': row['when'], 'outcome': row['outcome']} for row in ordinary],
                       'subtests': normalized_subs, 'failed_subtest_count': len(subfailures)}
        failed_phases.extend({'nodeid': node, 'when': phase, 'outcome': 'failed'} for phase in failures)
        tags = []
        xml_groups = []
        passed_calls = 0
        has_call_failure = False
        double_count_correction = 0
        for row in events:
            if row['outcome'] == 'failed':
                if row['when'] == 'teardown':
                    if has_call_failure:
                        xml_groups.append(tags)
                        tags = []
                    else:
                        double_count_correction = 1
                tag = 'failure' if row['when'] == 'call' else 'error'
                tags.append(tag)
                expected_stats['failures' if tag == 'failure' else 'errors'] += 1
                has_call_failure = has_call_failure or row['when'] == 'call'
            elif row['outcome'] == 'skipped':
                tags.append('skipped')
                expected_stats['skipped'] += 1
            elif row['when'] == 'call':
                passed_calls += 1
        # Native JUnit counts every passing call (including subtests), places
        # subtest tags on the parent's element, and splits on failed teardown
        # after any failed call report, including a failed subtest.
        xml_groups.append(tags)
        expected_xml[node] = xml_groups
        expected_stats['tests'] += passed_calls + sum(map(len, xml_groups)) - double_count_correction

    _require(type(session) is dict, 'missing session receipt')
    session_exit = _integer(session['exit'], 'session exit')
    _require(session_exit in (0, 1), 'abnormal pytest session exit')
    _require(_integer(session['tests_collected'], 'session tests_collected') == len(selected), 'session collection count mismatch')
    _require(_integer(session['reports'], 'session reports') == len(reports), 'session report count mismatch')
    raw_failed_reports = raw_failed_phases + len(failed_subtests)
    _require(_integer(session['tests_failed'], 'session tests_failed') == raw_failed_reports, 'session failed-phase/subtest count mismatch')
    _require(type(verifier_results) is list and len(verifier_results) == 1 and type(verifier_results[0]) is dict,
             'verifier must record exactly one pytest command')
    verifier = verifier_results[0]
    _require(verifier['name'] == 'tests', 'unexpected verifier result name')
    command = verifier['command']
    _require(type(command) is list and all(type(part) is str for part in command), 'invalid verifier command')
    _require(command.count('-m') == 1 and command.index('-m') + 1 < len(command)
             and command[command.index('-m') + 1] == 'pytest', 'verifier command is not pytest')
    _require('--runxfail' in command, 'verifier command does not establish --runxfail policy')
    raw_exit = _integer(verifier['exit'], 'actual pytest exit')
    _require(raw_exit in (0, 1), 'abnormal actual pytest exit')
    _require(raw_exit == session_exit, 'actual pytest exit disagrees with session exit')
    _require(raw_exit == int(bool(raw_failed_reports)), 'actual pytest exit disagrees with failed phase reports or subtests')
    _require(_integer(outer_exit, 'outer verifier exit') == raw_exit, 'outer verifier exit disagrees with actual pytest exit')

    _require(type(junit_xml) in (str, bytes), 'JUnit input must be XML text or bytes')
    root = ET.fromstring(junit_xml)
    if root.tag == 'testsuites':
        _require(all(child.tag == 'testsuite' for child in root), 'unexpected JUnit root child')
        suites = list(root)
    else:
        _require(root.tag == 'testsuite', 'unexpected JUnit root')
        suites = [root]
    _require(len(suites) == 1, 'expected one pytest JUnit suite')
    suite = suites[0]
    _require(all(child.tag in ('testcase', 'properties') for child in suite), 'unexpected JUnit suite child')
    observed_xml = defaultdict(list)
    xml_elements = 0
    for element in suite.findall('testcase'):
        identity = element.get('classname'), element.get('name')
        _require(identity in identities, 'unexpected JUnit testcase identity: ' + str(identity))
        node = identities[identity]
        _require(all(child.tag in ('failure', 'error', 'skipped', 'properties', 'system-out', 'system-err') for child in element),
                 'unexpected JUnit testcase child')
        tags = []
        for child in element:
            if child.tag in ('failure', 'error', 'skipped'):
                _require(child.get('type') != 'pytest.xfail', 'xfail XML is outside the --runxfail contract')
                tags.append(child.tag)
        observed_xml[node].append({'outcomes': tags, 'seconds': _seconds(element.get('time'), 'JUnit testcase time')})
        xml_elements += 1
    _require(set(observed_xml) == set(selected), 'JUnit membership mismatch')
    for node in selected:
        _require([row['outcomes'] for row in observed_xml[node]] == expected_xml[node],
                 'JUnit outcomes or testcase duplication disagree for ' + node)
        cases[node]['junit_elements'] = observed_xml[node]
    xml_stats = {name: _xml_integer(suite, name) for name in ('tests', 'failures', 'errors', 'skipped')}
    _require(xml_stats == dict(expected_stats), 'JUnit suite totals disagree with phase reports')
    seconds = _seconds(suite.get('time'), 'JUnit suite time')
    counts = dict(Counter(case['status'] for case in cases.values()))
    return {'result': 'FAIL' if failed_phases or failed_subtests else 'PASS', 'complete': True,
            'cases': cases, 'counts': counts, 'case_count': len(selected),
            'failed_phases': failed_phases, 'failed_phase_count': len(failed_phases),
            'subtest_counts': dict(subtest_counts), 'subtest_count': sum(subtest_counts.values()),
            'failed_subtests': failed_subtests, 'failed_subtest_count': len(failed_subtests),
            'raw_failed_phase_count': raw_failed_phases, 'raw_failed_report_count': raw_failed_reports,
            'reported_failed_report_count': len(failed_phases) + len(failed_subtests),
            'promoted_parent_failures': promoted_parents, 'promoted_parent_failure_count': len(promoted_parents),
            'report_count': len(reports), 'pytest_exit': raw_exit, 'outer_exit': outer_exit,
            'junit': {'case_elements': xml_elements, 'raw_suite_counts': xml_stats, 'seconds': seconds}}
