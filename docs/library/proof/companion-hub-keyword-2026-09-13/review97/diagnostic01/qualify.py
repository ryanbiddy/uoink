"""Exact source-signature contracts with inert Hub and progress seams."""
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert 'site' not in sys.modules
import ast
import hashlib
import importlib.abc
import inspect
import json
import os
from pathlib import Path
import re
import types
import unittest

assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
out = Path(__file__).resolve().parent
label = sys.argv[1]
assert label in ('diagnostic01', 'unused-patched')
run = out / label
run.mkdir(exist_ok=False)
blocked = []
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in sys.stdlib_module_names | set(sys.builtin_module_names):
            blocked.append('import:' + fullname)
            raise ImportError('Non-stdlib import denied')
guard = Guard()
sys.meta_path.insert(0, guard)
def audit(event, values):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system', '_winapi.CreateProcess', 'ctypes.dlopen'}:
        blocked.append(event)
        raise PermissionError(event)
    if event == 'open' and isinstance(values[0], (str, bytes, os.PathLike)):
        path = Path(os.path.abspath(os.fsdecode(values[0])))
        if not (path.is_relative_to(out) or path.is_relative_to(Path(r'C:\Python314'))):
            blocked.append({'event': 'open:outside-scope', 'path': str(path)})
            raise PermissionError('Outside-scoped open')
sys.addaudithook(audit)
manifest = json.loads((out / 'INPUT-DIAGNOSTIC.json').read_bytes())
for row in manifest['payloads']:
    raw = (out / row['file']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
hub = ast.parse((out / 'hub-signature-source.py.txt').read_bytes())
function = [n for n in hub.body if isinstance(n, ast.FunctionDef) and n.name == 'snapshot_download'][-1]
assert not function.args.vararg and not function.args.kwarg and not function.args.posonlyargs
parameters = [inspect.Parameter(arg.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD) for arg in function.args.args]
parameters += [inspect.Parameter(arg.arg, inspect.Parameter.KEYWORD_ONLY, default=None) for arg in function.args.kwonlyargs]
signature = inspect.Signature(parameters)
source_path = out / ('utils-before.py.txt' if label == 'diagnostic01' else 'utils-after.py.txt')
tree = ast.parse(source_path.read_bytes())
download = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'download_model')
download.returns = None
for arg in download.args.args:
    arg.annotation = None
assert not download.decorator_list and not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(download))
models = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_MODELS' for t in n.targets))
calls = []
failure = None
progress = object()
def fake_snapshot(*args, **kwargs):
    bound = signature.bind(*args, **kwargs)
    calls.append(dict(bound.arguments))
    if failure is not None:
        raise failure
    return 'validated-fake-return'
namespace = {'re': re, '_MODELS': ast.literal_eval(models), 'huggingface_hub': types.SimpleNamespace(snapshot_download=fake_snapshot), 'disabled_tqdm': progress}
exec(compile(ast.fix_missing_locations(ast.Module(body=[download], type_ignores=[])), str(source_path), 'exec'), namespace)
call = namespace['download_model']

class Contracts(unittest.TestCase):
    def setUp(self):
        global failure
        failure = None
        calls.clear()
    def expected(self, *, output=False, local=True, mapped=True, extra=False):
        supplied = dict(local_files_only=local)
        if output:
            supplied['output_dir'] = 'local-destination'
        if extra:
            supplied.update(cache_dir='cache-destination', revision='a' * 40, use_auth_token='synthetic-token')
        result = call('small.en' if mapped else 'owner/model', **supplied)
        self.assertEqual(result, 'validated-fake-return')
        expected = dict(repo_id='Systran/faster-whisper-small.en' if mapped else 'owner/model', local_files_only=local,
            allow_patterns=['config.json', 'preprocessor_config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*'],
            tqdm_class=progress, revision='a' * 40 if extra else None)
        if output:
            expected['local_dir'] = 'local-destination'
        if extra:
            expected.update(cache_dir='cache-destination', token='synthetic-token')
        self.assertEqual(calls, [expected])
    def test_output_local_only(self): self.expected(output=True)
    def test_output_fetch_mode(self): self.expected(output=True, local=False)
    def test_output_revision_token_cache(self): self.expected(output=True, mapped=False, extra=True)
    def test_cache_local_only(self): self.expected(extra=True)
    def test_cache_fetch_mode(self): self.expected(local=False, mapped=False)
    def test_false_token_is_forwarded(self):
        call('small.en', use_auth_token=False, local_files_only=True)
        self.assertIs(calls[0]['token'], False)
    def test_invalid_name_does_not_call_hub(self):
        with self.assertRaises(ValueError): call('not-a-supported-size')
        self.assertEqual(calls, [])
    def test_output_error_propagates_unchanged(self):
        global failure
        failure = RuntimeError('synthetic helper refusal')
        with self.assertRaises(RuntimeError) as caught:
            call('small.en', output_dir='local-destination', local_files_only=True)
        self.assertIs(caught.exception, failure)

with (run / 'tests.log').open('x', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
unchanged = all(hashlib.sha256((out / row['file']).read_bytes()).hexdigest() == row['sha256'] for row in manifest['payloads'])
valid = not blocked and guard in sys.meta_path and unchanged
code = 0 if result.wasSuccessful() and valid else 1
receipt = {'label': label, 'tests_run': result.testsRun, 'passed': result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
    'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped), 'exit': code,
    'guard_valid': valid, 'blocked': blocked, 'inputs_unchanged': unchanged, 'packages_or_models_executed': False,
    'scope': 'selected download helper AST only, fake Hub call bound to captured signature'}
(run / 'result.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
raise SystemExit(code)
