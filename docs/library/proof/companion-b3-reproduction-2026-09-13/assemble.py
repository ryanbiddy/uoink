"""Verify and archive exact B3 text evidence; reject every binary input."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

out = Path(__file__).absolute().parent
scratch = out.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
copies = []
forbidden = {'.whl', '.zip', '.onnx', '.exe', '.dll', '.pyd', '.bin', '.pt', '.pth', '.safetensors', '.db'}
def read_text_bytes(path, expected=None, size=None):
    if path.suffix.lower() in forbidden:
        raise ValueError('Binary/runtime/model input forbidden')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, 'st_reparse_tag', 0) or before.st_size > 1024 * 1024:
        raise ValueError('Regular bounded text input required')
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if identity(opened) != identity(before):
            raise ValueError('Text input identity changed')
        raw = stream.read(before.st_size + 1)
        if identity(os.fstat(stream.fileno())) != identity(opened):
            raise ValueError('Text changed while reading')
    if len(raw) != before.st_size or identity(path.lstat()) != identity(before):
        raise ValueError('Text input changed')
    raw.decode('utf-8')
    if expected is not None:
        assert sha(raw) == expected
    if size is not None:
        assert len(raw) == size
    return raw
def copy(source, name, expected=None, size=None):
    raw = read_text_bytes(source, expected, size)
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    copies.append({'source': str(source), 'target': name, 'bytes': len(raw), 'sha256': sha(raw)})
    return raw
archives = [
    ('companion-b3-combined-review01', 'synthetic95', '2e982651021232121fd87d058b02b75c2361ff985af230695921397f101bd127', 95),
    ('b3-real-wheel-preparation01', 'preparation32', '36141cdd7a2bec9014985bbe860eacc60d4c265e68a6591e3c3659dbd195678a', 32),
]
for folder, prefix, expected, count in archives:
    source = scratch / folder
    raw = copy(source / 'SHA256.json', prefix + '/SHA256.json', expected)
    manifest = json.loads(raw)
    assert manifest['payload_count'] == len(manifest['payloads']) == count
    for row in manifest['payloads']:
        assert 'original63/' not in row['file'] and 'original97/' not in row['file']
        copy(source / row['file'], prefix + '/' + row['file'], row['sha256'], row['bytes'])
copy(scratch / 'B3-REAL-WHEEL-ROOT-DECISION-2026-09-13.md', 'ROOT-DECISION.md')
names = ['build-result.json', 'launch-plan.json', 'launch-result.json', 'console.log', 'root-outer-exit.json', 'artifact/provenance.json']
for label in ('py314-01', 'py313-01'):
    source = scratch / ('b3-real-wheel-' + label)
    for name in names:
        copy(source / name, 'actual/' + label + '/' + name)

def read_json(name):
    return json.loads(read_text_bytes(out / name))
recipe = read_json('preparation32/inputs/recipe/member-manifest.json')
expected_output = {'filename': 'faster_whisper-1.2.1+uoink.localassets2-py3-none-any.whl',
    'version': '1.2.1+uoink.localassets2', 'size': 1388022,
    'sha256': '97bdde2d33fe71660b4cf8a318853e2e1b647ad900918e7e24397990162f29e4'}
expected_builder = 'f25530a3ee58169c049e63c2e6bfff444061f2c04c9a87ec2af43c8850b81892'
expected_recipes = {path.name: sha(read_text_bytes(path)) for path in sorted((out / 'preparation32/inputs/recipe').iterdir())}
checks = []
for label, python, epoch in [('py314-01', '3.14.6', '1'), ('py313-01', '3.13.15', '2000000000')]:
    prefix = 'actual/' + label + '/'
    result, plan, actual, outer, provenance = [read_json(prefix + name) for name in
        ['build-result.json', 'launch-plan.json', 'launch-result.json', 'root-outer-exit.json', 'artifact/provenance.json']]
    assert result['status'] == provenance['status'] == 'BUILT_AND_BYTE_VERIFIED'
    assert result['exit'] == actual['actual_child_exit'] == actual['launcher_return_code'] == outer['actual_outer_exit'] == 0
    assert result['builder_sha256'] == provenance['builder_sha256'] == expected_builder
    assert result['recipe_hashes'] == provenance['recipe_hashes'] == expected_recipes
    assert result['output'] == provenance['output']
    assert {key: result['output'][key] for key in expected_output} == expected_output
    assert Path(result['output']['path']) == scratch / ('b3-real-wheel-' + label) / 'artifact' / expected_output['filename']
    assert result['python'].startswith(python + ' ') and provenance['python'] == result['python']
    assert result['flags'] == {'isolated': 1, 'no_site': 1, 'dont_write_bytecode': 1}
    assert result['guard'] == {'preloaded_heavy': [], 'postloaded_heavy': [], 'violations': [], 'finder_installed_at_finish': True, 'valid': True}
    assert result['member_count'] == 16 and result['manifest_and_record_verified'] and result['opaque_asset_and_license_unchanged']
    assert result['actual_wheel_read_attempted'] and result['actual_wheel_read']
    assert actual['inputs_unchanged'] and result['model_execution'] is False and result['runtime_acceptance'] is False and result['release_ready'] is False
    assert provenance['model_execution'] is False and provenance['dependencies_imported'] is False and provenance['release_ready'] is False
    assert provenance['output_members'] == recipe['members'] and provenance['zip'] == recipe['zip']
    assert len(provenance['input_members']) == 15 and len(provenance['output_members']) == 16
    assert provenance['upstream']['filename'] == 'faster_whisper-1.2.1-py3-none-any.whl'
    assert provenance['upstream']['size'] == 1118909 and provenance['upstream']['sha256'] == '79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7'
    member_map = {row['member']: row for row in provenance['output_members']}
    asset = 'faster_whisper/assets/silero_vad_v6.onnx'
    assert result['opaque_asset_sha256'] == member_map[asset]['sha256'] == provenance['input_members'][asset]['sha256'] == '4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2'
    assert member_map['faster_whisper-1.2.1+uoink.localassets2.dist-info/LICENSE']['sha256'] == provenance['input_members']['faster_whisper-1.2.1.dist-info/LICENSE']['sha256']
    assert plan['manifest_sha256'] == '36141cdd7a2bec9014985bbe860eacc60d4c265e68a6591e3c3659dbd195678a'
    assert plan['source_date_epoch'] == epoch
    assert plan['command'][1:4] == ['-I', '-S', '-B']
    expected_exe = Path(r'C:\Python314\python.exe') if label == 'py314-01' else scratch / 'b2-stdlib313-runtime01/python.exe'
    assert Path(plan['command'][0]) == expected_exe
    if label == 'py314-01':
        assert result['reproducibility_python313'] == 'PENDING_B3_REPRODUCTION'
        assert actual['runtime_unchanged'] is None and plan['comparison_sha256'] is None and plan['comparison_size'] is None
    else:
        assert result['reproducibility_python313'] == 'BYTE_IDENTICAL'
        assert result['comparison_wheel_sha256'] == plan['comparison_sha256'] == expected_output['sha256']
        assert result['comparison_wheel_bytes'] == plan['comparison_size'] == expected_output['size']
        assert result['private_runtime_verified'] and result['private_runtime_file_count'] == 34 and actual['runtime_unchanged']
        assert plan['runtime_plan_sha256'] == '8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b'
        assert set(map(Path, result['sys_path'])) == {scratch / 'b2-stdlib313-runtime01', scratch / 'b2-stdlib313-runtime01/python313.zip'} and len(result['sys_path']) == 2
    checks.append({'label': label, 'output': expected_output, 'actual_child_exit': 0, 'launcher_return_code': 0,
        'actual_outer_exit': 0, 'guard_valid': True, 'source_date_epoch': epoch,
        'original_reproduction_field': result['reproducibility_python313'], 'result_sha256': sha(read_text_bytes(out / (prefix + 'build-result.json'))),
        'receipt_and_protocol_review_only': True})

verification = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PACKAGING_RECEIPTS_CONSISTENT',
    'checks': checks, 'preserved_original_archive_counts': [95, 32], 'raw_actual_text_receipts': 12,
    'first_receipt_not_rewritten': True, 'proposal_basis_prose_preserved': True,
    'binary_payloads_included': False, 'wheel_or_runtime_or_model_accessed_by_reviewer': False,
    'no_execution_or_build_during_review': True, 'migration_installation_market_acceptance': False}
(out / 'REVIEW-CHECKS.json').write_text(json.dumps(verification, indent=2)+'\n', encoding='utf-8', newline='\n')
(out / 'COPY-RECEIPT.json').write_text(json.dumps({'copies': copies}, indent=2)+'\n', encoding='utf-8', newline='\n')
payloads = []
for source in sorted(out.rglob('*')):
    if source.is_file() and source != out / 'SHA256.json':
        raw = read_text_bytes(source)
        payloads.append({'file': str(source.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
raw = (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(payloads), 'payloads': payloads}, indent=2)+'\n').encode()
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(payloads), 'manifest_sha256': sha(raw), 'actual_build_receipts_verified': 2,
    'wheel_bytes_recorded': expected_output['size'], 'wheel_sha256_recorded': expected_output['sha256'], 'binary_accessed': False}))
