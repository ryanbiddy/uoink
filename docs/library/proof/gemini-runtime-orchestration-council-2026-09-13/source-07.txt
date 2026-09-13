"""Dormant D1 child. No active owner pin; never run during source preparation."""
import dataclasses
import encodings.cp437
import encodings.utf_8_sig
import hashlib
import inspect
import io
import json
import math
import ntpath
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
import types
import typing
import zipfile
import zlib

OWNER_DECISION_SHA256 = None  # Requires a separately reviewed future activation.
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
CHECKOUT = r'E:\AI\projects\uoink\checkouts\Yoink-library'
ARTIFACT = CHECKOUT + r'\installer\staging\python\Lib\site-packages\whisperx\assets\pytorch_model.bin'
OUTPUT_ROOT = CHECKOUT + r'\_scratch\vad-buffer-version-approved-output'
OUTPUT_NAME = 'd1-buffer-version-01.json'
OUTPUT = OUTPUT_ROOT + '\\' + OUTPUT_NAME
ARTIFACT_SHA256 = '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'
INVENTORY_SHA256 = '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc'
SCOPE = 'D1_STATIC_VERSION_AND_BUFFERS_ONLY'
MODULES = ('zip_bounds', 'fixed_converter', 'buffer_basis', 'inspect_adapter')
SOURCE_NAMES = ('d1_child.py', 'zip_bounds.py', 'fixed_converter.py', 'buffer_basis.py',
                'inspect_adapter.py', 'known-inventory.json')
READ_NAMES = SOURCE_NAMES + ('INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D1-DECISION.json')
FIXED_HASHES = {
    'inspect_adapter.py': '533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649',
    'fixed_converter.py': 'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b',
    'zip_bounds.py': 'bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6',
    'buffer_basis.py': 'bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373',
    'known-inventory.json': '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc',
}
HEAVY = {'torch', 'torchaudio', 'whisper', 'whisperx', 'faster_whisper', 'ctranslate2',
         'pyannote', 'transformers', 'numpy', 'tokenizers', 'safetensors', 'huggingface_hub', 'pickle'}
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def require(value, reason):
    if not value:
        raise ValueError(reason)

def pairs(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result

def bounded(path, cap=65536):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, 'Text input size/type')
        raw = stream.read(cap+1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= cap and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Text input changed')
    return raw

def decode(raw):
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs)

def lexical(path):
    text = os.fsdecode(path).replace('/', '\\')
    if text.startswith('\\\\?\\') or text.startswith('\\??\\'):
        text = text[4:]
    return ntpath.normcase(ntpath.abspath(text))

def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Use -I -S -B')
    require(os.environ.get('IG_FORBIDDEN_LIVE') == FORBIDDEN, 'Missing lexical live-path binding')
    if OWNER_DECISION_SHA256 is None:
        print(json.dumps({'status': 'dormant_owner_approval_absent', 'artifact_access': False,
                          'helper_execution': False, 'actual_child_exit': 3}))
        return 3
    require(type(OWNER_DECISION_SHA256) is str and re.fullmatch('[0-9a-f]{64}', OWNER_DECISION_SHA256),
            'Invalid externally reviewed owner pin')
    here = Path(__file__).absolute().parent
    reads = {lexical(here/name) for name in READ_NAMES}
    live = ntpath.dirname(lexical(FORBIDDEN))
    artifact, output = lexical(ARTIFACT), lexical(OUTPUT)
    source_metadata = reads | {lexical(here)}
    real_metadata = set()
    for name in (ARTIFACT, OUTPUT):
        current = ntpath.abspath(name)
        while True:
            real_metadata.add(lexical(current))
            parent = ntpath.dirname(current)
            if parent == current:
                break
            current = parent
    events, trapped = [], []
    access = {'active': False, 'artifact_opens': 0, 'receipt_opens': 0, 'invocations': 0}
    preloaded = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    require(not preloaded, 'Model/pickle module already loaded')
    allowed_imports = set(sys.modules) | set(MODULES)

    def deny(event):
        events.append(event)
        raise RuntimeError('D1 guard denied ' + event)

    def audit(event, args):
        if event == 'open':
            path, mode, flags = args
            if not isinstance(path, (str, bytes, os.PathLike)):
                deny('open descriptor/path type')
            name = lexical(path)
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if name in reads and not writing:
                return
            if name == artifact and access['active'] and not writing and access['artifact_opens'] == 0:
                access['artifact_opens'] += 1
                return
            if (name == output and access['active'] and access['receipt_opens'] == 0
                    and flags & os.O_EXCL and flags & os.O_CREAT and flags & os.O_WRONLY
                    and not flags & (os.O_RDWR | os.O_TRUNC | os.O_APPEND)):
                access['receipt_opens'] += 1
                return
            deny('open outside exact D1 allowance')
        elif event == 'import' and args[0] not in allowed_imports:
            deny('import:' + str(args[0]))
        elif event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.')) or event in {
                'os.system', 'os.startfile', 'os.startfile/2', 'os.spawn', 'os.posix_spawn',
                'os.fork', 'os.exec', 'os.add_dll_directory', 'os.listdir', 'os.scandir',
                'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime'}:
            deny(event)

    def metadata(path):
        if not isinstance(path, (str, bytes, os.PathLike)):
            deny('metadata descriptor/path type')
        name = lexical(path)
        if name == live or name.startswith(live+'\\'):
            deny('live metadata')
        if name not in source_metadata and not (access['active'] and name in real_metadata):
            deny('metadata outside exact D1 allowance')

    wrappers = {}
    for name in ('stat', 'lstat', 'readlink'):
        original = getattr(os, name)
        def wrapper(path, *args, _original=original, **kwargs):
            metadata(path)
            return _original(path, *args, **kwargs)
        wrappers[name] = wrapper
        setattr(os, name, wrapper)
    old_realpath = os.path.realpath
    def realpath(path, *args, **kwargs):
        metadata(path)
        return old_realpath(path, *args, **kwargs)
    os.path.realpath = realpath
    sys.addaudithook(audit)
    raw, adapter, archive, result, failure, code = {}, None, None, None, None, 1
    try:
        raw = {name: bounded(here/name) for name in READ_NAMES}
        require(sha(raw['RYAN-D1-DECISION.json']) == OWNER_DECISION_SHA256, 'Owner decision hash mismatch')
        decision = decode(raw['RYAN-D1-DECISION.json'])
        require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
                and decision.get('scope') == SCOPE and decision.get('source_message_id'), 'No recorded Ryan decision')
        require(decision.get('artifact_sha256') == ARTIFACT_SHA256
                and decision.get('artifact_bytes') == 17719103
                and decision.get('interpreted_payload_bytes') == 1002
                and decision.get('conversion_authorized') is False
                and decision.get('model_execution_authorized') is False
                and decision.get('network_authorized') is False, 'Owner scope mismatch')
        admission = decode(raw['ROOT-ADMISSION.json'])
        require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
                and admission.get('owner_decision_sha256') == OWNER_DECISION_SHA256
                and admission.get('run_id') == 'd1-real-01', 'Missing exact root admission')
        bindings = decode(raw['INPUTS.json'])['child_files']
        require(set(bindings) == set(SOURCE_NAMES), 'Exact child input membership required')
        for name, digest in bindings.items():
            require(sha(raw[name]) == digest and admission['source_hashes'].get(name) == digest,
                    'Child source hash mismatch')
        for name, digest in FIXED_HASHES.items():
            require(sha(raw[name]) == digest, 'Qualified helper changed')
        require(admission['source_hashes'].get('INPUTS.json') == sha(raw['INPUTS.json']), 'Input binding changed')
        require(sha(raw['known-inventory.json']) == INVENTORY_SHA256, 'Known inventory changed')
        inventory = decode(raw['known-inventory.json'])
        for name in MODULES:
            module = types.ModuleType(name)
            module.__file__ = str(here/(name+'.py'))
            sys.modules[name] = module
            exec(compile(raw[name+'.py'], module.__file__, 'exec'), module.__dict__)
        adapter, archive = sys.modules['inspect_adapter'], sys.modules['fixed_converter']
        require(adapter.D1_OWNER_APPROVAL is None and archive.REAL_PROFILE is None, 'Helper gate unexpectedly active')
        require(lexical(adapter.REAL_INPUT) == artifact and lexical(adapter.REAL_OUTPUT_ROOT) == lexical(OUTPUT_ROOT),
                'Qualified adapter fixed paths differ')
        def no_conversion(*args, **kwargs):
            trapped.append('conversion or other-storage interpretation')
            raise RuntimeError('D1 conversion trap')
        for name in ('convert_bytes', 'convert_reviewed_real_file', 'load_fixed_plan', 'reject_nonfinite', 'encode_safetensors'):
            setattr(archive, name, no_conversion)
        profile = adapter.InspectionProfile('real', 'reviewed-d1-existing-v1', ARTIFACT_SHA256,
            17719103, tuple(tuple(row) for row in inventory))
        adapter.D1_OWNER_APPROVAL = adapter.InspectionApproval(profile, OWNER_DECISION_SHA256)
        access['active'] = True
        access['invocations'] += 1
        result = adapter.inspect_reviewed_real_file(OUTPUT_NAME)
        code = result['inspection_exit']
        require(type(code) is int and code in (0, 1, 2), 'Unexpected inspection exit')
    except Exception as error:
        failure = {'error_type': type(error).__name__, 'reason': str(error)[:180]}
        code = 1
    finally:
        access['active'] = False
        if adapter is not None:
            adapter.D1_OWNER_APPROVAL = None
    unchanged = bool(raw) and all(bounded(here/name) == value for name, value in raw.items())
    installed = all(getattr(os, name) is value for name, value in wrappers.items()) and os.path.realpath is realpath
    heavy_after = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    valid = not events and not trapped and not heavy_after and unchanged and installed
    if not valid:
        code = 1
    print(json.dumps({'scope': SCOPE, 'actual_child_exit': code, 'inspection_result': result,
        'failure': failure, 'guard': {'valid': valid, 'unexpected_events': events,
            'forbidden_conversion_calls': trapped, 'heavy_preloaded': preloaded, 'heavy_after': heavy_after,
            'inputs_unchanged': unchanged, 'metadata_wrappers_installed': installed, **access},
        'owner_decision_sha256': OWNER_DECISION_SHA256,
        'input_sha256': {name: sha(value) for name, value in raw.items()},
        'conversion_profile_activated': archive is not None and archive.REAL_PROFILE is not None,
        'adapter_owner_gate_reset': adapter is None or adapter.D1_OWNER_APPROVAL is None,
        'runtime_or_release_approved': False}, indent=2))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
