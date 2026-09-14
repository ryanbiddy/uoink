"""Unexecuted fake23 qualifier. No real converter, D2 launcher, or artifact imports."""
import sys

BASELINE_WINREG = sys.modules.get('winreg')
assert BASELINE_WINREG is not None
assert getattr(BASELINE_WINREG, '__name__', None) == 'winreg'
assert getattr(getattr(BASELINE_WINREG, '__spec__', None), 'origin', None) == 'built-in'
assert not hasattr(BASELINE_WINREG, '__file__')
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
REGISTRY_DENIALS = []

def deny_registry(*args, **kwargs):
    REGISTRY_DENIALS.append('registry_callable')
    raise AssertionError('Registry operations prohibited')

REGISTRY_TRAPS = tuple((name, value, deny_registry) for name, value in sorted(REGISTRY_NAMESPACE.items())
                      if not name.startswith('_') and callable(value))
assert 1 <= len(REGISTRY_TRAPS) <= 64
for name, original, installed in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, installed)

def registry_audit(event, args):
    if event.startswith('winreg.'):
        REGISTRY_DENIALS.append(event)
        raise AssertionError('Registry audit prohibited')

REGISTRY_AUDIT = registry_audit
sys.addaudithook(REGISTRY_AUDIT)
import encodings.utf_8_sig
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import time
import types
import unittest

FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
EXPECTED_ROOT = r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d2-dormant-invocation-proposal02'
NAMES = ('d2_adapter.py', 'test_d2_boundaries.py', 'D2-PROFILE.json', 'D1-RESULT.json',
         'known-inventory.json', 'fixed-plan.json', 'EXPECTED-CASES.json', 'qualify_d2.py', 'run_fake23_01.ps1')
READ_NAMES = NAMES + ('QUALIFICATION-INPUTS.json',)
HEAVY = {'torch', 'torchaudio', 'whisper', 'whisperx', 'faster_whisper', 'ctranslate2',
         'pyannote', 'transformers', 'numpy', 'tokenizers', 'safetensors', 'huggingface_hub', 'pickle',
         'fixed_converter', 'zip_bounds', 'd2_child', 'launch_d2'}
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def lexical(path):
    return ntpath.normcase(ntpath.abspath(os.fsdecode(path).replace('/', '\\')))


def bounded(path):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 65536, 'Bounded regular text required')
        raw = stream.read(65537)
        after = os.fstat(stream.fileno())
    require(len(raw) <= 65536 and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Text changed during read')
    return raw


def exception_record(info):
    kind, value, tb = info
    frames = []
    while tb is not None and len(frames) < 16:
        frames.append({'file': tb.tb_frame.f_code.co_filename, 'line': tb.tb_lineno,
                       'function': tb.tb_frame.f_code.co_name})
        tb = tb.tb_next
    return {'type': kind.__name__, 'message': str(value)[:2048], 'frames': frames}


class Result(unittest.TestResult):
    # Do not use linecache or open traceback source files after the read phase closes.
    def __init__(self):
        super().__init__()
        self.subtest_count = 0

    def addError(self, test, error):
        self.errors.append((test._testMethodName, exception_record(error)))

    def addFailure(self, test, error):
        self.failures.append((test._testMethodName, exception_record(error)))

    def addSubTest(self, test, subtest, error):
        self.subtest_count += 1
        if error is not None:
            self.errors.append((test._testMethodName, exception_record(error)))


def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Use -I -S -B')
    require(os.environ.get('IG_FORBIDDEN_LIVE') == FORBIDDEN, 'Explicit startup binding required')
    here = Path(__file__).absolute().parent
    require(lexical(here) == lexical(EXPECTED_ROOT), 'Only the exact reviewed proposal root is allowed')
    reads = {lexical(here / name) for name in READ_NAMES}
    metadata_names = set(reads)
    for item in (here, *here.parents):
        metadata_names.add(lexical(item))
    events = []
    phase = {'read_inputs': True}
    allowed_imports = set(sys.modules) | {'d2_adapter', '_d2_boundary_cases'}
    heavy_before = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    require(not heavy_before, 'Heavy/converter module already loaded')

    def deny(event):
        events.append(event)
        raise AssertionError('Fake23 guard denied ' + event)

    def audit(event, args):
        if event == 'open':
            path, mode, flags = args
            if not isinstance(path, (str, bytes, os.PathLike)):
                deny('open path/descriptor type')
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if not phase['read_inputs'] or writing or lexical(path) not in reads:
                deny('open outside fixed source read phase')
        elif event == 'import' and args[0] not in allowed_imports:
            deny('import:' + str(args[0]))
        elif event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.')) or event in {
                'os.system', 'os.startfile', 'os.startfile/2', 'os.spawn', 'os.posix_spawn',
                'os.fork', 'os.exec', 'os.add_dll_directory', 'os.listdir', 'os.scandir',
                'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime'}:
            deny(event)

    def metadata(path):
        if not isinstance(path, (str, bytes, os.PathLike)) or lexical(path) not in metadata_names:
            deny('metadata outside fixed text namespace')

    wrappers = {}
    for name in ('stat', 'lstat', 'readlink'):
        original = getattr(os, name)
        def wrapper(path, *args, _original=original, **kwargs):
            metadata(path)
            return _original(path, *args, **kwargs)
        wrappers[name] = wrapper
        setattr(os, name, wrapper)
    original_realpath = os.path.realpath
    def realpath(path, *args, **kwargs):
        metadata(path)
        return original_realpath(path, *args, **kwargs)
    os.path.realpath = realpath
    sys.addaudithook(audit)
    raw, cases, result, failure, adapter = {}, [], Result(), None, None
    expected = []
    started = time.monotonic()
    try:
        raw = {name: bounded(here / name) for name in READ_NAMES}
        pins = json.loads(raw['QUALIFICATION-INPUTS.json'].decode('utf-8'))['files']
        require(type(pins) is dict and set(pins) == set(NAMES), 'Exact nine fake23 input pins required')
        require(all(sha(raw[name]) == pins[name] for name in NAMES), 'Fake23 input hash mismatch')
        expected = json.loads(raw['EXPECTED-CASES.json'].decode('utf-8'))
        require(type(expected) is list and len(expected) == len(set(expected)) == 23
                and expected == sorted(expected), 'Exact ordered23 case names required')
        phase['read_inputs'] = False
        for name, filename in (('d2_adapter', 'd2_adapter.py'), ('_d2_boundary_cases', 'test_d2_boundaries.py')):
            module = types.ModuleType(name)
            module.__file__ = str(here / filename)
            sys.modules[name] = module
            exec(compile(raw[filename], module.__file__, 'exec'), module.__dict__)
        adapter = sys.modules['d2_adapter']
        test_module = sys.modules['_d2_boundary_cases']
        require(adapter.OWNER_DECISION_SHA256 is None, 'Real D2 owner pin must stay absent')
        test_module.FIXED_INPUTS = {name: raw[name] for name in (
            'D2-PROFILE.json', 'D1-RESULT.json', 'known-inventory.json', 'fixed-plan.json')}
        case_type = test_module.D2BoundaryCases
        actual_names = unittest.defaultTestLoader.getTestCaseNames(case_type)
        require(actual_names == expected, 'Selected case membership differs')
        for name in expected:
            before = (len(result.failures), len(result.errors), len(result.skipped))
            case_type(name).run(result)
            after = (len(result.failures), len(result.errors), len(result.skipped))
            status = ('failed' if after[0] > before[0] else 'error' if after[1] > before[1]
                      else 'skipped' if after[2] > before[2] else 'passed')
            cases.append({'name': name, 'status': status})
    except Exception as error:
        failure = exception_record(sys.exc_info())
    finally:
        phase['read_inputs'] = True
    unchanged = bool(raw) and all(bounded(here / name) == value for name, value in raw.items())
    phase['read_inputs'] = False
    heavy_after = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    registry_expected = dict(REGISTRY_NAMESPACE)
    for name, original, trap in REGISTRY_TRAPS:
        registry_expected[name] = trap
    guards = {
        'inputs_unchanged': unchanged,
        'source_reads_closed_at_finish': not phase['read_inputs'],
        'metadata_wrappers_installed': all(getattr(os, name) is value for name, value in wrappers.items())
            and os.path.realpath is realpath,
        'baseline_winreg_identity_unchanged': sys.modules.get('winreg') is BASELINE_WINREG
            and getattr(getattr(BASELINE_WINREG, '__spec__', None), 'origin', None) == 'built-in'
            and not hasattr(BASELINE_WINREG, '__file__'),
        'registry_namespace_unchanged': set(vars(BASELINE_WINREG)) == set(registry_expected)
            and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items()),
        'registry_traps_installed': registry_audit is REGISTRY_AUDIT
            and all(getattr(BASELINE_WINREG, name, None) is trap for name, original, trap in REGISTRY_TRAPS),
        'real_owner_pin_absent': adapter is not None and adapter.OWNER_DECISION_SHA256 is None,
        'no_heavy_converter_imports': not heavy_before and not heavy_after,
        'no_audit_or_registry_denials': not events and not REGISTRY_DENIALS,
    }
    counts = {'passed': sum(row['status'] == 'passed' for row in cases),
              'failed': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'subtests': result.subtest_count, 'tests_run': result.testsRun}
    valid = all(guards.values())
    passed = (failure is None and valid and counts == dict(passed=23, failed=0, errors=0,
        skipped=0, subtests=0, tests_run=23) and [row['name'] for row in cases] == expected)
    code = 0 if passed else 1
    print(json.dumps({'scope': 'D2_FAKE23_ONLY_NO_REAL_CONVERSION', 'counts': counts, 'cases': cases,
        'failures': result.failures, 'errors': result.errors, 'skips': result.skipped,
        'instrumentation_failure': failure, 'guard_valid': valid, 'guards': guards,
        'audit_events': events, 'registry_denials': REGISTRY_DENIALS,
        'registry_trap_count': len(REGISTRY_TRAPS), 'heavy_before': heavy_before, 'heavy_after': heavy_after,
        'input_hashes': {name: sha(value) for name, value in raw.items()},
        'elapsed_seconds': time.monotonic() - started, 'qualification_exit': code,
        'actual_converter_or_model_executed': False, 'real_d2_authority': False}, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
