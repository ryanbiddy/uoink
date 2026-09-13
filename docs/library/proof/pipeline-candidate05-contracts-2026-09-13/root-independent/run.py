"""Run only captured selected AST bodies under stdlib fake seams and guards."""
import ast
import collections
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest

out = Path(__file__).resolve().parent
label = sys.argv[1]
if label != 'pc01': raise ValueError('Unbriefed label')
run = out / 'runs' / label
run.mkdir(parents=True, exist_ok=False)
assert sys.version_info[:2] == (3, 14)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert 'site' not in sys.modules
assert os.environ['IG_FORBIDDEN_LIVE'] == r'C:\Users\hello\AppData\Local\Uoink\index.db'
heavy = {'whisper_runner', 'server', 'whisper', 'whisperx', 'faster_whisper', 'ctranslate2', 'torch', 'torchaudio',
         'pyannote', 'tokenizers', 'transformers', 'huggingface_hub', 'safetensors', 'numpy', 'scipy'}
preloaded = sorted(name for name in sys.modules if name.split('.')[0] in heavy)
assert not preloaded
violations, observations, diagnostics = [], [], []
calls, forbidden_initializer_calls = {}, []
selected_codes = {}
forbidden_code = None

def inside(path, root):
    try: path.relative_to(root); return True
    except ValueError: return False

stdlib = Path(sys.base_prefix).resolve()
class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        name = fullname.split('.')[0]
        if name in heavy or name not in sys.stdlib_module_names and name not in sys.builtin_module_names:
            violations.append({'event': 'import', 'name': fullname})
            raise ImportError('Only stdlib imports are allowed')
finder = Finder()
sys.meta_path.insert(0, finder)

def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system', 'ctypes.dlopen', 'sqlite3.connect'}:
        violations.append({'event': event})
        raise PermissionError('Network, subprocess, native library and database access forbidden')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        mode, flags = args[1], args[2]
        writing = isinstance(mode, str) and any(char in mode for char in 'wax+') or isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        forbidden_suffix = path.suffix.lower() in {'.whl', '.onnx', '.safetensors', '.pt', '.pth', '.pkl', '.pickle', '.db', '.dll', '.pyd', '.bin'}
        allowed = inside(path, run) if writing else inside(path, out) or inside(path, stdlib)
        if not allowed or forbidden_suffix:
            violations.append({'event': event, 'path': str(path), 'writing': bool(writing)})
            raise PermissionError('File access outside scoped source, stdlib, or fresh receipts')
    if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink'}:
        targets = args[:2] if event in {'os.rename', 'os.link', 'os.symlink'} else args[:1]
        for value in targets:
            if isinstance(value, (str, bytes, os.PathLike)) and not inside(Path(os.fsdecode(value)).absolute(), run):
                violations.append({'event': event, 'path': os.fsdecode(value)})
                raise PermissionError('Mutation outside fresh run forbidden')
sys.addaudithook(audit)

def profile(frame, event, arg):
    if event == 'call':
        code = frame.f_code
        if code is forbidden_code:
            forbidden_initializer_calls.append({'file': code.co_filename, 'line': code.co_firstlineno})
            raise RuntimeError('Captured Pipeline initializer execution prohibited')
        if code in selected_codes:
            name = selected_codes[code]
            calls[name] = calls.get(name, 0) + 1

class Result(unittest.TextTestResult):
    def _exc_info_to_string(self, error, test):
        kind, value, trace = error
        frames = []
        while trace is not None:
            code = trace.tb_frame.f_code
            frames.append({'file': code.co_filename, 'line': trace.tb_lineno, 'function': code.co_name})
            trace = trace.tb_next
        return json.dumps({'type': kind.__name__, 'message': str(value), 'frames': frames}, indent=2)
    def addSuccess(self, test):
        super().addSuccess(test)
        observations.append({'id': test.id(), 'status': 'passed'})
    def addFailure(self, test, error):
        super().addFailure(test, error)
        observations.append({'id': test.id(), 'status': 'failed', 'trace': self._exc_info_to_string(error, test)})
    def addError(self, test, error):
        super().addError(test, error)
        observations.append({'id': test.id(), 'status': 'error', 'trace': self._exc_info_to_string(error, test)})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        observations.append({'id': test.id(), 'status': 'skipped', 'reason': reason})

fatal = None
result = None
try:
    spec = importlib.util.spec_from_file_location('synthetic_pipeline_seams', out / 'seams.py')
    seams = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seams)
    selected = seams.load_selected(out)
    forbidden_code = selected['Pipeline'].__init__.__code__
    for class_name, name in selected['selected_methods']:
        method = getattr(selected[class_name], name)
        method = getattr(method, '__wrapped__', method)
        selected_codes[method.__code__] = class_name + '.' + name
    selected_codes[selected['_reform_generator'].__code__] = '_reform_generator'
    sys.setprofile(profile)
    namespace = {'__name__': 'synthetic_pipeline_contracts', '__file__': str(out / 'tests.py'), 'S': seams, 'N': selected}
    exec(compile((out / 'tests.py').read_bytes(), str(out / 'tests.py'), 'exec'), namespace)
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(namespace[name])
        for name in ('PipelineContracts', 'ParameterContracts', 'IteratorContracts'))
    with (run / 'tests.log').open('x', encoding='utf-8', newline='\n') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    pipeline = namespace['make_pipeline']()[0]
    try:
        actual = pipeline([])
        diagnostic = {'input': 'direct empty list', 'expected_if_supported': [], 'actual': repr(actual), 'status': 'RETURNED_DIAGNOSTIC_ONLY'}
    except Exception as error:
        diagnostic = {'input': 'direct empty list', 'expected_if_supported': [], 'exception_type': type(error).__name__,
            'message': str(error), 'status': 'UNACCEPTED_OPTIONAL_API_DEFECT', 'source': 'base.py.txt', 'line': 1242}
    diagnostics.append(diagnostic)
except Exception as error:
    fatal = {'type': type(error).__name__, 'message': str(error)}

postloaded = sorted(name for name in sys.modules if name.split('.')[0] in heavy)
guard_valid = not preloaded and not postloaded and not violations and not forbidden_initializer_calls and finder in sys.meta_path and sys.getprofile() is profile
status = 0 if result is not None and result.wasSuccessful() and guard_valid and fatal is None else 1
receipt = {'label': label, 'tests_run': result.testsRun if result else 0,
    'passed': sum(row['status'] == 'passed' for row in observations), 'failed': len(result.failures) if result else 0,
    'errors': len(result.errors) if result else 0, 'skipped': len(result.skipped) if result else 0,
    'exit': status, 'fatal': fatal, 'observations': observations, 'diagnostics': diagnostics,
    'selected_method_call_counts': calls, 'input_hashes': {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in ('seams.py', 'tests.py', 'run.py', 'launch.py', 'SOURCE-BINDINGS.json')},
    'guard': {'preloaded_heavy': preloaded, 'postloaded_heavy': postloaded, 'violations': violations,
        'forbidden_pipeline_initializer_calls': forbidden_initializer_calls, 'finder_installed_at_finish': finder in sys.meta_path,
        'profile_installed_at_finish': sys.getprofile() is profile, 'valid': guard_valid},
    'python': sys.version, 'flags': {'isolated': sys.flags.isolated, 'no_site': sys.flags.no_site, 'dont_write_bytecode': sys.flags.dont_write_bytecode},
    'scope': 'Exact selected captured AST bodies with stdlib fake tensor, array, loader, device, mel, model, non-chat and parameter-spy seams only; no package/model/native execution or stack acceptance.',
    'finished_utc': datetime.now(timezone.utc).isoformat()}
(run / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({key: receipt[key] for key in ('label', 'tests_run', 'passed', 'failed', 'errors', 'skipped', 'exit', 'fatal', 'guard', 'diagnostics')}))
raise SystemExit(status)
