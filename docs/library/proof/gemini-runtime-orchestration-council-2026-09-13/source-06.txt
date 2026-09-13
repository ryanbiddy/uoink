"""Dormant one-shot D1 launcher. No owner pin or real artifact approval exists."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

OWNER_DECISION_SHA256 = None  # Future activation must be a separately reviewed patch.
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
PYTHON = r'C:\Python314\python.exe'
CHECKOUT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUTPUT_ROOT = CHECKOUT / '_scratch/vad-buffer-version-approved-output'
OUTPUT_NAME = 'd1-buffer-version-01.json'
SCOPE = 'D1_STATIC_VERSION_AND_BUFFERS_ONLY'
CHILD_SOURCES = ('d1_child.py', 'zip_bounds.py', 'fixed_converter.py', 'buffer_basis.py',
                 'inspect_adapter.py', 'known-inventory.json')
REQUIRED = CHILD_SOURCES + ('INPUTS.json', 'launch_d1.py', 'run-root.ps1')
FIXED_HASHES = {
    'inspect_adapter.py': '533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649',
    'fixed_converter.py': 'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b',
    'zip_bounds.py': 'bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6',
    'buffer_basis.py': 'bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373',
    'known-inventory.json': '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc',
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

def bounded(path, cap=65536):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, 'Regular bounded text required')
        raw = stream.read(cap+1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= cap and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Text changed while read')
    return raw

def no_links(path, *, final_missing=False):
    # Path metadata only under private source/receipt roots, never the artifact.
    path = Path(os.path.abspath(path))
    for current in (*reversed(path.parents), path):
        try:
            item = current.lstat()
        except FileNotFoundError:
            require(final_missing and current == path, 'Required private parent missing')
            continue
        require(not stat.S_ISLNK(item.st_mode) and not getattr(item, 'st_file_attributes', 0) & 0x400,
                'Linked/reparse private path refused')
        require(current == path or stat.S_ISDIR(item.st_mode), 'Private parent is not a directory')
    return path

def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Use -I -S -B')
    require(os.environ.get('IG_FORBIDDEN_LIVE') == FORBIDDEN, 'Missing lexical live-path binding')
    if OWNER_DECISION_SHA256 is None:
        print(json.dumps({'status': 'dormant_owner_approval_absent', 'child_launched': False,
                          'artifact_path_operation': False, 'actual_launcher_exit': 3}))
        return 3
    require(type(OWNER_DECISION_SHA256) is str and re.fullmatch('[0-9a-f]{64}', OWNER_DECISION_SHA256),
            'Invalid external owner decision pin')
    here = Path(__file__).absolute().parent
    no_links(here)
    raw_decision = bounded(no_links(here/'RYAN-D1-DECISION.json'))
    require(sha(raw_decision) == OWNER_DECISION_SHA256, 'Recorded Ryan decision differs from reviewed pin')
    decision = json.loads(raw_decision.decode('utf-8-sig'))
    require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
            and decision.get('scope') == SCOPE and decision.get('source_message_id'), 'No recorded Ryan approval')
    require(decision.get('artifact_sha256') == '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'
            and decision.get('artifact_bytes') == 17719103 and decision.get('interpreted_payload_bytes') == 1002
            and decision.get('conversion_authorized') is False
            and decision.get('model_execution_authorized') is False
            and decision.get('network_authorized') is False, 'Owner scope mismatch')
    raw_admission = bounded(no_links(here/'ROOT-ADMISSION.json'))
    admission = json.loads(raw_admission.decode('utf-8-sig'))
    require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
            and admission.get('run_id') == 'd1-real-01'
            and admission.get('owner_decision_sha256') == OWNER_DECISION_SHA256, 'Exact root review required')
    expected = admission['source_hashes']
    require(set(expected) == set(REQUIRED), 'Exact nine input hashes required')
    inputs = {name: bounded(no_links(here/name)) for name in REQUIRED}
    for name, raw in inputs.items():
        require(sha(raw) == expected[name], 'Root-reviewed source changed: '+name)
    for name, digest in FIXED_HASHES.items():
        require(sha(inputs[name]) == digest, 'Qualified helper changed')
    run = here/'execution-d1-real-01'
    no_links(run, final_missing=True)
    run.mkdir(exist_ok=False)  # Persistent one-shot claim, including failed attempts.
    save(run/'ATTEMPT-CLAIM.json', {'owner_decision_sha256': OWNER_DECISION_SHA256,
         'started_utc': datetime.now(timezone.utc).isoformat(), 'run_id': 'd1-real-01'})
    no_links(OUTPUT_ROOT, final_missing=True)
    OUTPUT_ROOT.mkdir(exist_ok=False)  # No existing receipt root may be reused.
    for name in CHILD_SOURCES + ('INPUTS.json',):
        with (run/name).open('xb') as stream:
            stream.write(inputs[name])
    (run/'ROOT-ADMISSION.json').write_bytes(raw_admission)
    (run/'RYAN-D1-DECISION.json').write_bytes(raw_decision)
    environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR'}}
    environment.update(IG_FORBIDDEN_LIVE=FORBIDDEN, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_DATASETS_OFFLINE='1', PYANNOTE_METRICS_ENABLED='0', PYTHONDONTWRITEBYTECODE='1',
        PYTHONUTF8='1', PYTHONIOENCODING='utf-8', TEMP=str(run), TMP=str(run), HOME=str(run),
        USERPROFILE=str(run), LOCALAPPDATA=str(run), APPDATA=str(run))
    command = [PYTHON, '-I', '-S', '-B', str(run/'d1_child.py')]
    save(run/'launch-plan.json', {'command': command, 'cwd': str(run),
        'environment_variable_names': sorted(environment), 'source_hashes': expected,
        'owner_decision_sha256': OWNER_DECISION_SHA256, 'external_timeout_seconds': 60})
    try:
        with (run/'stdout.json').open('xb') as stdout, (run/'stderr.log').open('xb') as stderr:
            child = subprocess.run(command, cwd=run, env=environment, stdout=stdout, stderr=stderr,
                                   timeout=60, close_fds=True)
    except subprocess.TimeoutExpired:
        save(run/'actual-child-exit.json', {'actual_child_exit': None, 'timed_out': True, 'accepted': False})
        raise
    except OSError as error:
        save(run/'actual-child-exit.json', {'actual_child_exit': None, 'child_started': False,
             'error_type': type(error).__name__, 'accepted': False})
        raise
    save(run/'actual-child-exit.json', {'actual_child_exit': child.returncode, 'timed_out': False})
    for name, raw in inputs.items():
        require(bounded(here/name) == raw, 'Reviewed input changed during invocation')
    for name in CHILD_SOURCES + ('INPUTS.json',):
        require(bounded(run/name) == inputs[name], 'Copied child input changed')
    require(bounded(run/'ROOT-ADMISSION.json') == raw_admission
            and bounded(run/'RYAN-D1-DECISION.json') == raw_decision, 'Child decision/admission changed')
    report = json.loads(bounded(run/'stdout.json').decode('utf-8'))
    require(not bounded(run/'stderr.log'), 'Unexpected stderr retained')
    require(report['actual_child_exit'] == child.returncode, 'Child/report exit mismatch')
    guard = report['guard']
    require(guard['valid'] and not guard['unexpected_events'] and not guard['forbidden_conversion_calls']
            and guard['inputs_unchanged'] and guard['metadata_wrappers_installed'], 'Invalid D1 guard')
    require(guard['invocations'] == 1 and guard['artifact_opens'] <= 1 and guard['receipt_opens'] <= 1,
            'D1 invocation/open count mismatch')
    require(not report['conversion_profile_activated'] and report['adapter_owner_gate_reset'], 'Gate state changed')
    result = report['inspection_result']
    if result is not None:
        raw_receipt = bounded(no_links(OUTPUT_ROOT/OUTPUT_NAME), 16384)
        require(sha(raw_receipt) == result['receipt_sha256'] and len(raw_receipt) == result['receipt_bytes'],
                'Adapter receipt identity mismatch')
        with (run/'adapter-receipt.json').open('xb') as stream:
            stream.write(raw_receipt)
        receipt = json.loads(raw_receipt.decode('ascii'))
        require(receipt.get('conversion_profile_activated') is False, 'Receipt activated conversion')
        if child.returncode == 0:
            require(receipt['status'] == 'static_inspection_complete_unqualified'
                    and receipt['interpreted_payload_bytes'] == 1002
                    and receipt['version_actual_hex'] == '330a', 'Incomplete static inspection result')
    save(run/'checked-result.json', {'actual_child_exit': child.returncode, 'guard_valid': True,
         'input_bytes_unchanged': True, 'inspection_result': result,
         'conversion_runtime_or_release_accepted': False})
    print(json.dumps({'actual_child_exit': child.returncode, 'guard_valid': True,
                      'inspection_result': result, 'conversion_runtime_or_release_accepted': False}))
    return child.returncode

if __name__ == '__main__':
    raise SystemExit(main())
