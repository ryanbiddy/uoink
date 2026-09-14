"""Dormant D2 conversion child; never invoke during source preparation."""
import sys

BASELINE_WINREG = sys.modules.get("winreg")
assert BASELINE_WINREG is not None
assert getattr(BASELINE_WINREG, "__name__", None) == "winreg"
assert getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
assert not hasattr(BASELINE_WINREG, "__file__")
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
REGISTRY_DENIALS = []

def deny_registry(*args, **kwargs):
    REGISTRY_DENIALS.append("registry_callable")
    raise AssertionError("Registry operations prohibited")

REGISTRY_TRAPS = tuple((name, value, deny_registry) for name, value in sorted(REGISTRY_NAMESPACE.items())
                      if not name.startswith("_") and callable(value))
assert 1 <= len(REGISTRY_TRAPS) <= 64
for name, original, installed in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, installed)

def registry_audit(event, args):
    if event.startswith("winreg."):
        REGISTRY_DENIALS.append(event)
        raise AssertionError("Registry audit prohibited")

REGISTRY_AUDIT = registry_audit
sys.addaudithook(REGISTRY_AUDIT)
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

OWNER_DECISION_SHA256 = 'dbcf0c2abfde5ef7a21482da7358c14361e0195887aa32772f57546c40fc65fa'  # No D2 approval exists.
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
CHECKOUT = r'E:\AI\projects\uoink\checkouts\Yoink-library'
ARTIFACT = CHECKOUT + r'\installer\staging\python\Lib\site-packages\whisperx\assets\pytorch_model.bin'
OUTPUT_ROOT = CHECKOUT + r'\_scratch\vad-fixed-converter-approved-output'
OUTPUT_NAME = 'default-vad-d2-01.safetensors'
OUTPUT = OUTPUT_ROOT + '\\' + OUTPUT_NAME
ARTIFACT_SHA256 = '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'
INVENTORY_SHA256 = '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc'
SCOPE = 'D2_ONE_LOCAL_FIXED54_CONVERSION_ONLY'
MODULES = ('zip_bounds', 'fixed_converter', 'd2_adapter')
SOURCE_NAMES = ('d2_child.py', 'zip_bounds.py', 'fixed_converter.py', 'd2_adapter.py',
                'fixed-plan.json', 'D1-RESULT.json', 'known-inventory.json', 'D2-PROFILE.json')
READ_NAMES = SOURCE_NAMES + ('INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D2-DECISION.json')
FIXED_HASHES = {
    'fixed_converter.py': 'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b',
    'zip_bounds.py': 'bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6',
    'fixed-plan.json': '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf',
    'D1-RESULT.json': '754ca6dea6aed81de072940b35ad4c283f270b5770a88236ef55fd0a09d46e75',
    'known-inventory.json': '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc',
    'D2-PROFILE.json': 'f0c60e2fa349b945108b4d15dccc8fe2d68ca4cab8588e8c0ff7f2e8762f75d3',
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
    events = []
    access = {'active': False, 'artifact_opens': 0, 'output_opens': 0, 'invocations': 0}
    operation = {'file_conversion_calls': 0, 'file_conversion_returns': 0}
    preloaded = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    require(not preloaded, 'Model/pickle module already loaded')
    allowed_imports = set(sys.modules) | set(MODULES)

    def deny(event):
        events.append(event)
        raise RuntimeError('D2 guard denied ' + event)

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
            if (name == output and access['active'] and access['output_opens'] == 0
                    and flags & os.O_EXCL and flags & os.O_CREAT and flags & os.O_WRONLY
                    and not flags & (os.O_RDWR | os.O_TRUNC | os.O_APPEND)):
                access['output_opens'] += 1
                return
            deny('open outside exact D2 allowance')
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
            deny('metadata outside exact D2 allowance')

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
    conversion_wrapper = None
    try:
        raw = {name: bounded(here/name) for name in READ_NAMES}
        require(sha(raw['RYAN-D2-DECISION.json']) == OWNER_DECISION_SHA256, 'Owner decision hash mismatch')
        decision = decode(raw['RYAN-D2-DECISION.json'])
        require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
                and decision.get('scope') == SCOPE and decision.get('conversion_authorized') is True,
                'No exact D2 owner decision')
        admission = decode(raw['ROOT-ADMISSION.json'])
        require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
                and admission.get('owner_decision_sha256') == OWNER_DECISION_SHA256
                and admission.get('run_id') == 'd2-real-01', 'Missing exact root admission')
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
        adapter, archive = sys.modules['d2_adapter'], sys.modules['fixed_converter']
        require(adapter.OWNER_DECISION_SHA256 == OWNER_DECISION_SHA256
                and archive.REAL_PROFILE is None, 'D2 adapter pin/profile mismatch')
        # All decision, admission and evidence gates precede active artifact allowances.
        adapter._decision(raw['RYAN-D2-DECISION.json'], OWNER_DECISION_SHA256)
        adapter._admission(raw['ROOT-ADMISSION.json'], OWNER_DECISION_SHA256)
        adapter._evidence(raw['D2-PROFILE.json'], raw['D1-RESULT.json'],
                          raw['known-inventory.json'], raw['fixed-plan.json'])
        original_conversion = archive.convert_reviewed_real_file
        def count_conversion(*args, **kwargs):
            operation['file_conversion_calls'] += 1
            require(operation['file_conversion_calls'] == 1, 'Repeated file conversion refused')
            returned = original_conversion(*args, **kwargs)
            operation['file_conversion_returns'] += 1
            return returned
        conversion_wrapper = count_conversion
        archive.convert_reviewed_real_file = conversion_wrapper
        access['active'] = True
        access['invocations'] += 1
        result = adapter.run_once(archive, profile_raw=raw['D2-PROFILE.json'],
            d1_raw=raw['D1-RESULT.json'], inventory_raw=raw['known-inventory.json'],
            plan_raw=raw['fixed-plan.json'], decision_raw=raw['RYAN-D2-DECISION.json'],
            admission_raw=raw['ROOT-ADMISSION.json'])
        code = 0
    except Exception as error:
        failure = {'error_type': type(error).__name__, 'reason': str(error)[:180]}
        code = 2 if ((adapter is not None and isinstance(error, adapter.Refusal))
                     or (archive is not None and isinstance(error, archive.Refusal))) else 1
    finally:
        access['active'] = False
        if archive is not None:
            archive.REAL_PROFILE = None
    unchanged = bool(raw) and all(bounded(here/name) == value for name, value in raw.items())
    installed = all(getattr(os, name) is value for name, value in wrappers.items()) and os.path.realpath is realpath
    heavy_after = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
    registry_expected = dict(REGISTRY_NAMESPACE)
    for name, original, installed_trap in REGISTRY_TRAPS:
        registry_expected[name] = installed_trap
    registry_guards = {
        'baseline_winreg_identity_unchanged': sys.modules.get('winreg') is BASELINE_WINREG
            and getattr(getattr(BASELINE_WINREG, '__spec__', None), 'origin', None) == 'built-in'
            and not hasattr(BASELINE_WINREG, '__file__'),
        'registry_namespace_unchanged': set(vars(BASELINE_WINREG)) == set(registry_expected)
            and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items()),
        'registry_traps_installed': registry_audit is REGISTRY_AUDIT
            and all(getattr(BASELINE_WINREG, name, None) is installed_trap
                    for name, original, installed_trap in REGISTRY_TRAPS),
    }
    call_wrapper_intact = (archive is None or (conversion_wrapper is not None
                           and archive.convert_reviewed_real_file is conversion_wrapper))
    valid = (not events and not heavy_after and unchanged and installed and call_wrapper_intact
             and all(registry_guards.values()) and not REGISTRY_DENIALS)
    if not valid:
        code = 1
    print(json.dumps({'scope': SCOPE, 'actual_child_exit': code, 'conversion_result': result,
        'failure': failure, 'guard': {'valid': valid, 'unexpected_events': events,
            'heavy_preloaded': preloaded, 'heavy_after': heavy_after,
            'inputs_unchanged': unchanged, 'metadata_wrappers_installed': installed,
            'conversion_call_wrapper_intact': call_wrapper_intact,
            'registry_denials': REGISTRY_DENIALS, 'registry_trap_count': len(REGISTRY_TRAPS),
            **registry_guards, **access},
        'conversion_operation': operation,
        'owner_decision_sha256': OWNER_DECISION_SHA256,
        'input_sha256': {name: sha(value) for name, value in raw.items()},
        'conversion_profile_active_at_exit': archive is not None and archive.REAL_PROFILE is not None,
        'adapter_owner_pin_unchanged': adapter is None or adapter.OWNER_DECISION_SHA256 == OWNER_DECISION_SHA256,
        'runtime_or_release_approved': False}, indent=2))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
