"""Root byte/receipt check. Never import a wheel member or execute a model."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tomllib

assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
BASE = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
SOURCE = BASE / 'whisperx-owned-builder-proposal01'
PREP = BASE / 'whisperx-owned-build-launch-proposal01'
LAUNCH = PREP / 'launch-build01'
RUN = SOURCE / 'runs/build01'
before = {}

def read(path, limit=1048576):
    assert path.is_relative_to(BASE)
    for p in reversed((path,) + tuple(path.parents)):
        info = p.lstat()
        assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400
        assert stat.S_ISREG(info.st_mode) if p == path else stat.S_ISDIR(info.st_mode)
    info = path.stat()
    assert info.st_size <= limit
    with path.open('rb') as f:
        raw = f.read(limit + 1)
    assert len(raw) == info.st_size <= limit
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    assert all(getattr(info, n) == getattr(after, n) for n in fields)
    before[path] = (hashlib.sha256(raw).hexdigest(), tuple(getattr(after, n) for n in fields))
    return raw

def doc(path):
    return json.loads(read(path))

actual = doc(PREP / 'ACTUAL-BUILD01-OUTER-TOOL.json')
assert actual['exit_code'] == 0 and actual['chunk_id'] == '405e18'
launch = doc(LAUNCH / 'result.json')
assert launch['status'] == 'BYTE_BUILD_VERIFIED' and launch['intended_outer_exit'] == 0
assert launch['instrumentation_error'] is None and launch['before'] == launch['after']
assert [p['mode'] for p in launch['phases']] == ['build', 'verify']
assert len(launch['before']['instruments']) == 5 and len(launch['before']['inputs']) == 46
assert len(launch['before']['runtime']) == 34
for group, directory in (('instruments', PREP), ('inputs', SOURCE)):
    for row in launch['before'][group]:
        assert row['path'] and not row['path'].startswith('/') and ':' not in row['path'] and '..' not in Path(row['path']).parts
        raw = read(directory / row['path'])
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
runtime_plan_raw = read(PREP / 'runtime-copy-plan.json')
assert hashlib.sha256(runtime_plan_raw).hexdigest() == '8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b'
rp = json.loads(runtime_plan_raw)
assert launch['before']['runtime'] == [dict(path=r['filename'], bytes=r['bytes'], sha256=r['sha256']) for r in rp['files'] + [rp['private_pth']]]
for phase in launch['phases']:
    mode = phase['mode']
    assert phase['actual_native_exit'] == 0
    native = doc(LAUNCH / (mode + '-actual-native-exit.json'))
    assert native['actual_native_exit'] == 0 and native['native_type'] == 'System.Int32'
    guard = doc(LAUNCH / (mode + '-guard.json'))
    assert guard['exit'] == 0 and guard['error'] is None
    assert all(guard[k] is True for k in ('guard_valid', 'metadata_wrappers_installed', 'finder_installed', 'startup_binding'))
    assert guard['preloaded_heavy'] == guard['postloaded_heavy'] == guard['violations'] == []
    assert 0 <= guard['elapsed_seconds'] <= 30
    for log in phase['logs']:
        raw = read(LAUNCH / (mode + '-' + log['kind'] + '.log'))
        assert len(raw) == log['bytes'] and hashlib.sha256(raw).hexdigest() == log['sha256']
        if log['kind'] == 'stderr': assert raw == b''
build = doc(RUN / 'result.json')
verify = doc(RUN / 'independent-verification.json')
assert build['exit'] == verify['exit'] == 0 and build['inputs_unchanged'] is verify['inputs_unchanged'] is True
verifier_raw = read(SOURCE / 'verify_wheel.py')
assert hashlib.sha256(verifier_raw).hexdigest() == 'e2dd54c9001ceeb00e54d2b1c9c333ffab3976002438fc86a1ea8b073682ed6e'
recipe_raw = read(SOURCE / 'inputs/WHEEL-RECIPE.json')
assert hashlib.sha256(recipe_raw).hexdigest() == 'a30b6ca4b87b9317d8232a284434c069b91ff0fe6d1874e903de1bfafb947581'
recipe = json.loads(recipe_raw)
names = {row['input'] for row in recipe['fixed_members']} | {'after/pyproject.toml', 'after/README-UOINK.md'}
sources = {n: read(SOURCE / 'inputs' / n, 262144) for n in names}
wheel = read(RUN / 'whisperx-3.8.6+uoink.owned1-py3-none-any.whl')
assert len(wheel) == 134793 and hashlib.sha256(wheel).hexdigest() == '0c23ec175b663eaafe9955ff93b1ccc6e93ed66a61665951baac5799a75c92d4'
for path, identity in tuple(before.items()):
    read(path)
    assert before[path] == identity
heavy = ('torch', 'torchaudio', 'whisperx', 'faster_whisper', 'ctranslate2', 'pyannote', 'numpy')
assert not any(n.split('.')[0] in heavy for n in sys.modules)
def deny_io(event, args):
    if event == 'open' or event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.')):
        raise AssertionError('Read-only byte calculation attempted external operation: ' + event)
sys.addaudithook(deny_io)
namespace = {'__name__': 'root_reviewed_byte_verifier', '__file__': str(SOURCE / 'verify_wheel.py')}
exec(compile(verifier_raw, '<reviewed independent verifier>', 'exec'), namespace)
result = namespace['verify_bytes'](wheel, recipe_raw, sources)
assert all(result[k] == verify[k] for k in result)
assert build['sha256'] == result['sha256'] and build['bytes'] == result['bytes'] and build['members'] == 22
assert not any(n.split('.')[0] in heavy for n in sys.modules)
print(json.dumps({'status': 'ROOT_BYTE_VERIFIED', 'byte_verification': result,
                  'source_files_rechecked': 46, 'instruments_rechecked': 5,
                  'runtime_identity_rows_compared': 34, 'runtime_files_read_by_root': 0,
                  'bound_files_unchanged': len(before), 'actual_outer_exit': actual['exit_code'],
                  'native_phases': 2, 'wheel_imported_or_installed': False, 'model_executed': False}))
