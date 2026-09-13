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


def validate_partition(*, selected, reports, session, verifier_results, outer_exit, junit_xml):
    """Return normalized facts, or reject incomplete/contradictory raw receipts.

    Inputs are parsed JSON values and XML bytes/text. This contract is for the
    existing --runxfail, single-pytest-command guarded verifier, not collection.
    ``tests_failed`` is a count of failed phase reports, not unique failed cases.
    JUnit may emit two elements for one call-failure-plus-teardown-error case.
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
    grouped = defaultdict(list)
    for row in reports:
        _require(row['nodeid'] in selected, 'unexpected report node id: ' + str(row['nodeid']))
        _require(row['when'] in ('setup', 'call', 'teardown'), 'unexpected report phase')
        _require(row['outcome'] in ('passed', 'failed', 'skipped'), 'unexpected report outcome')
        _require(row.get('wasxfail') is None, 'xfail receipt is outside the --runxfail contract')
        _seconds(row['duration'], 'report duration')
        grouped[row['nodeid']].append(row)
    _require(set(grouped) == set(selected), 'missing execution reports for selected cases')

    cases = {}
    failed_phases = []
    expected_xml = {}
    expected_stats = Counter({'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0})
    for node in selected:
        events = grouped[node]
        phases = [row['when'] for row in events]
        _require(len(phases) == len(set(phases)), 'duplicate phase report for ' + node)
        _require(phases and phases[0] == 'setup', 'missing initial setup report for ' + node)
        expected_phases = ['setup', 'call', 'teardown'] if events[0]['outcome'] == 'passed' else ['setup', 'teardown']
        _require(phases == expected_phases, 'incomplete or out-of-order phase reports for ' + node)
        failures = [row['when'] for row in events if row['outcome'] == 'failed']
        skipped = [row['when'] for row in events if row['outcome'] == 'skipped']
        status = ('error' if any(phase != 'call' for phase in failures) else 'failed') if failures else ('skipped' if skipped else 'passed')
        cases[node] = {'status': status, 'failed_phases': failures,
                       'phase_outcomes': [{'when': row['when'], 'outcome': row['outcome']} for row in events]}
        failed_phases.extend({'nodeid': node, 'when': phase, 'outcome': 'failed'} for phase in failures)
        tags = []
        passed_call = False
        for row in events:
            if row['outcome'] == 'failed':
                tag = 'failure' if row['when'] == 'call' else 'error'
                tags.append(tag)
                expected_stats['failures' if tag == 'failure' else 'errors'] += 1
            elif row['outcome'] == 'skipped':
                tags.append('skipped')
                expected_stats['skipped'] += 1
            elif row['when'] == 'call':
                passed_call = True
        # In current pytest, a failed call followed by failed teardown opens a
        # second XML testcase. Other failed teardowns reuse the first element.
        expected_xml[node] = [['failure'], ['error']] if failures == ['call', 'teardown'] else [tags]
        raw_total = int(passed_call) + len(tags)
        if 'teardown' in failures and 'call' not in failures:
            raw_total -= 1
        expected_stats['tests'] += raw_total

    _require(type(session) is dict, 'missing session receipt')
    session_exit = _integer(session['exit'], 'session exit')
    _require(session_exit in (0, 1), 'abnormal pytest session exit')
    _require(_integer(session['tests_collected'], 'session tests_collected') == len(selected), 'session collection count mismatch')
    _require(_integer(session['reports'], 'session reports') == len(reports), 'session report count mismatch')
    _require(_integer(session['tests_failed'], 'session tests_failed') == len(failed_phases), 'session failed-phase count mismatch')
    _require(type(verifier_results) is list and len(verifier_results) == 1 and type(verifier_results[0]) is dict,
             'verifier must record exactly one pytest command')
    verifier = verifier_results[0]
    _require(verifier['name'] == 'tests', 'unexpected verifier result name')
    command = verifier['command']
    _require(type(command) is list and all(type(part) is str for part in command), 'invalid verifier command')
    _require(command.count('-m') == 1 and command[command.index('-m') + 1] == 'pytest', 'verifier command is not pytest')
    raw_exit = _integer(verifier['exit'], 'actual pytest exit')
    _require(raw_exit in (0, 1), 'abnormal actual pytest exit')
    _require(raw_exit == session_exit, 'actual pytest exit disagrees with session exit')
    _require(raw_exit == int(bool(failed_phases)), 'actual pytest exit disagrees with failed phase reports')
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
    return {'result': 'FAIL' if failed_phases else 'PASS', 'complete': True,
            'cases': cases, 'counts': counts, 'case_count': len(selected),
            'failed_phases': failed_phases, 'failed_phase_count': len(failed_phases),
            'report_count': len(reports), 'pytest_exit': raw_exit, 'outer_exit': outer_exit,
            'junit': {'case_elements': xml_elements, 'raw_suite_counts': xml_stats, 'seconds': seconds}}
