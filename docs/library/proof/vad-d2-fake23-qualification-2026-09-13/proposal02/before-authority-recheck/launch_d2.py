"""Dormant one-shot D2 parent. No checkpoint path operations in this process."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

OWNER_DECISION_SHA256 = None
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
PYTHON = r'C:\Python314\python.exe'
CHECKOUT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUTPUT_ROOT = CHECKOUT / '_scratch/vad-fixed-converter-approved-output'
OUTPUT_NAME = 'default-vad-d2-01.safetensors'
SCOPE = 'D2_ONE_LOCAL_FIXED54_CONVERSION_ONLY'
PROFILE_SHA256 = 'f0c60e2fa349b945108b4d15dccc8fe2d68ca4cab8588e8c0ff7f2e8762f75d3'
CHILD_SOURCES = ('d2_child.py', 'zip_bounds.py', 'fixed_converter.py', 'd2_adapter.py',
                 'fixed-plan.json', 'D1-RESULT.json', 'known-inventory.json', 'D2-PROFILE.json')
REQUIRED = CHILD_SOURCES + ('INPUTS.json', 'launch_d2.py', 'run-root.ps1')
FIXED_HASHES = {
    'fixed_converter.py': 'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b',
    'zip_bounds.py': 'bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6',
    'fixed-plan.json': '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf',
    'D1-RESULT.json': '754ca6dea6aed81de072940b35ad4c283f270b5770a88236ef55fd0a09d46e75',
    'known-inventory.json': '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc',
    'D2-PROFILE.json': PROFILE_SHA256,
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    with path.open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Short receipt write')
        stream.flush()
        os.fsync(stream.fileno())


def bounded(path, cap=65536):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, 'Regular bounded input required')
        raw = stream.read(cap + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= cap and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while read')
    return raw


def no_links(path, *, final_missing=False):
    # Only source/output/receipt paths, never the checkpoint. Private quiescence is required.
    path = Path(os.path.abspath(path))
    for current in (*reversed(path.parents), path):
        try:
            item = current.lstat()
        except FileNotFoundError:
            require(final_missing and current == path, 'Required private parent missing')
            continue
        require(not stat.S_ISLNK(item.st_mode) and not getattr(item, 'st_file_attributes', 0) & 0x400,
                'Linked/reparse private path refused')
        require(current == path or stat.S_ISDIR(item.st_mode), 'Private ancestor is not a directory')
    return path


def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Use -I -S -B')
    require(os.environ.get('IG_FORBIDDEN_LIVE') == FORBIDDEN, 'Missing lexical live-path binding')
    if OWNER_DECISION_SHA256 is None:
        print(json.dumps({'status': 'dormant_d2_owner_approval_absent', 'child_launched': False,
                          'artifact_path_operation': False, 'actual_launcher_exit': 3}))
        return 3
    require(type(OWNER_DECISION_SHA256) is str and re.fullmatch('[0-9a-f]{64}', OWNER_DECISION_SHA256),
            'Invalid external D2 decision pin')
    here = no_links(Path(__file__).absolute().parent)
    raw_decision = bounded(no_links(here / 'RYAN-D2-DECISION.json'))
    require(sha(raw_decision) == OWNER_DECISION_SHA256, 'Exact recorded D2 decision required')
    decision = json.loads(raw_decision.decode('utf-8-sig'))
    require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
            and decision.get('scope') == SCOPE and decision.get('run_id') == 'd2-real-01'
            and decision.get('profile_sha256') == PROFILE_SHA256
            and decision.get('conversion_authorized') is True, 'No exact D2 approval')
    raw_admission = bounded(no_links(here / 'ROOT-ADMISSION.json'))
    admission = json.loads(raw_admission.decode('utf-8-sig'))
    require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
            and admission.get('run_id') == 'd2-real-01'
            and admission.get('profile_sha256') == PROFILE_SHA256
            and admission.get('owner_decision_sha256') == OWNER_DECISION_SHA256, 'Exact root review required')
    expected = admission['source_hashes']
    require(type(expected) is dict and set(expected) == set(REQUIRED), 'Exact eleven source hashes required')
    inputs = {name: bounded(no_links(here / name)) for name in REQUIRED}
    for name, raw in inputs.items():
        require(sha(raw) == expected[name], 'Root-reviewed source changed: ' + name)
    for name, digest in FIXED_HASHES.items():
        require(sha(inputs[name]) == digest, 'Frozen D2 evidence changed: ' + name)
    run = no_links(here / 'execution-d2-real-01', final_missing=True)
    run.mkdir(exist_ok=False)
    save(run / 'ATTEMPT-CLAIM.json', {'owner_decision_sha256': OWNER_DECISION_SHA256,
         'started_utc': datetime.now(timezone.utc).isoformat(), 'run_id': 'd2-real-01'})
    no_links(OUTPUT_ROOT, final_missing=True)
    OUTPUT_ROOT.mkdir(exist_ok=False)
    for name in CHILD_SOURCES + ('INPUTS.json',):
        with (run / name).open('xb') as stream:
            require(stream.write(inputs[name]) == len(inputs[name]), 'Short child-source copy')
    for name, raw in (('ROOT-ADMISSION.json', raw_admission), ('RYAN-D2-DECISION.json', raw_decision)):
        with (run / name).open('xb') as stream:
            require(stream.write(raw) == len(raw), 'Short decision copy')
    environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR'}}
    environment.update(IG_FORBIDDEN_LIVE=FORBIDDEN, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_DATASETS_OFFLINE='1', PYANNOTE_METRICS_ENABLED='0', TORCH_DEVICE_BACKEND_AUTOLOAD='0',
        PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
        TEMP=str(run), TMP=str(run), HOME=str(run), USERPROFILE=str(run), LOCALAPPDATA=str(run), APPDATA=str(run))
    command = [PYTHON, '-I', '-S', '-B', str(run / 'd2_child.py')]
    save(run / 'launch-plan.json', {'command': command, 'cwd': str(run),
        'environment_variable_names': sorted(environment), 'source_hashes': expected,
        'owner_decision_sha256': OWNER_DECISION_SHA256, 'external_timeout_seconds': 60})
    try:
        with (run / 'stdout.json').open('xb') as stdout, (run / 'stderr.log').open('xb') as stderr:
            child = subprocess.run(command, cwd=run, env=environment, stdout=stdout, stderr=stderr,
                                   timeout=60, close_fds=True)
    except subprocess.TimeoutExpired:
        save(run / 'actual-child-exit.json', {'actual_child_exit': None, 'timed_out': True, 'accepted': False})
        raise
    except OSError as error:
        save(run / 'actual-child-exit.json', {'actual_child_exit': None, 'child_started': False,
             'error_type': type(error).__name__, 'accepted': False})
        raise
    save(run / 'actual-child-exit.json', {'actual_child_exit': child.returncode, 'timed_out': False})
    for name, raw in inputs.items():
        require(bounded(no_links(here / name)) == raw, 'Reviewed input changed during invocation')
    for name in CHILD_SOURCES + ('INPUTS.json',):
        require(bounded(no_links(run / name)) == inputs[name], 'Copied child input changed')
    require(bounded(run / 'ROOT-ADMISSION.json') == raw_admission
            and bounded(run / 'RYAN-D2-DECISION.json') == raw_decision, 'Copied authority changed')
    report = json.loads(bounded(run / 'stdout.json').decode('utf-8'))
    require(not bounded(run / 'stderr.log'), 'Unexpected stderr retained')
    require(report['actual_child_exit'] == child.returncode, 'Child/report exit mismatch')
    guard = report['guard']
    require(guard['valid'] and guard['inputs_unchanged'] and not guard['unexpected_events']
            and not guard['heavy_after'] and guard['conversion_call_wrapper_intact']
            and guard['metadata_wrappers_installed'] and guard['baseline_winreg_identity_unchanged']
            and guard['registry_namespace_unchanged'] and guard['registry_traps_installed']
            and not guard['registry_denials'], 'Invalid D2 child guard')
    require(not report['conversion_profile_active_at_exit'] and report['adapter_owner_pin_unchanged'],
            'D2 profile/pin state changed')
    require(guard['invocations'] <= 1 and guard['artifact_opens'] <= 1 and guard['output_opens'] <= 1,
            'D2 one-shot/open count mismatch')
    operation = report['conversion_operation']
    require(type(operation['file_conversion_calls']) is int
            and type(operation['file_conversion_returns']) is int
            and 0 <= operation['file_conversion_returns'] <= operation['file_conversion_calls'] <= 1,
            'D2 conversion attempt/return count mismatch')
    result = report['conversion_result']
    output_identity_verified = False
    if child.returncode == 0:
        require(guard['invocations'] == guard['artifact_opens'] == guard['output_opens'] == 1
                and operation['file_conversion_calls'] == operation['file_conversion_returns'] == 1
                and result['status'] == 'conversion_bytes_produced_unqualified', 'Incomplete conversion outcome')
        output = bounded(no_links(OUTPUT_ROOT / OUTPUT_NAME), 6 * 1024 * 1024)
        require(len(output) == result['output_bytes'] and sha(output) == result['output_sha256'],
                'Persisted output differs from converter receipt')
        output_identity_verified = True  # Opaque bytes only; no parser/model/tensor construction.
    else:
        require(result is None, 'Failed child cannot publish a conversion result')
    save(run / 'checked-result.json', {'actual_child_exit': child.returncode, 'guard_valid': True,
         'inputs_unchanged': True, 'conversion_result': result,
         'conversion_operation': operation,
         'output_identity_verified': output_identity_verified, 'runtime_or_release_approved': False})
    print(json.dumps({'actual_child_exit': child.returncode, 'guard_valid': True,
        'conversion_result': result, 'output_identity_verified': output_identity_verified,
        'runtime_or_release_approved': False}))
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
