"""Fixed text-copy preparation only. No candidate imports or execution."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
AUTHOR = ROOT / '_scratch/worker-bootstrap-owner-instrument01'
OWNER = ROOT / '_scratch/worker-runtime-owner-proposal02'
MIGRATION = ROOT / '_scratch/worker-bootstrap-owner-migration01'
PREP = ROOT / '_scratch/worker-bootstrap-owner-confirmation-preparation01'
DEST = ROOT / '_scratch/astra-worker-bootstrap-owner-confirmation01'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def write_json(path, obj):
    with path.open('xb') as stream:
        stream.write((json.dumps(obj, indent=2) + '\n').encode())

template_raw = (AUTHOR / 'ROOT-ADMISSION.template.json').read_bytes()
assert sha(template_raw) == '58968e268fb812fb8c4a0c429e2829adaaf9a3c9db520e802f960852e461d00a'
template = json.loads(template_raw)
assert template['root_reviewed'] is False and len(template['input_sha256']) == 19
assert len(template['expected_cases']) == 17 and template['label'] == 'wbo01'
map_raw = (AUTHOR / 'SOURCE-INPUTS.json').read_bytes()
launcher_raw = (AUTHOR / 'run_bootstrap01.ps1').read_bytes()
assert sha(map_raw) == template['input_sha256']['SOURCE-INPUTS.json'] == '41624afcab27fa350ed91530a3fbd6ae94f8ce0f44e4d0facf465074ec276488'
assert sha(launcher_raw) == template['input_sha256']['run_bootstrap01.ps1'] == '8931a35859bb1dc7e6dba346f966328854ca4068f03769d321bbe050dca4a7d7'
mapping = json.loads(map_raw)
assert len(mapping['sources']) == 17
assert not DEST.exists(), 'Fresh destination required'
DEST.mkdir()
(PREP / 'before').mkdir()
for name, raw in (('run_bootstrap01.ps1', launcher_raw), ('SOURCE-INPUTS.json', map_raw),
                  ('ROOT-ADMISSION.template.json', template_raw)):
    (PREP / 'before' / name).write_bytes(raw)
new_map = json.loads(map_raw)
rows = []
for name, item in mapping['sources'].items():
    source = Path(item['path'])
    assert source.parent in (AUTHOR, OWNER, MIGRATION) and source.name == name
    raw = source.read_bytes()
    digest = sha(raw)
    assert digest == item['sha256'] == template['input_sha256'][name]
    target = DEST / name
    with target.open('xb') as stream: stream.write(raw)
    assert target.read_bytes() == raw
    new_map['sources'][name]['path'] = str(target)
    rows.append({'name': name, 'source': str(source), 'copy': str(target), 'bytes': len(raw),
                 'source_sha256': digest, 'copy_sha256': sha(target.read_bytes())})
substitutions = ((str(AUTHOR).encode(), 3), (str(OWNER).encode(), 11), (str(MIGRATION).encode(), 4))
new_launcher = launcher_raw
for old, count in substitutions:
    assert launcher_raw.count(old) == count
    new_launcher = new_launcher.replace(old, str(DEST).encode())
old_lines, new_lines = launcher_raw.splitlines(keepends=True), new_launcher.splitlines(keepends=True)
assert len(old_lines) == len(new_lines)
for old, new in zip(old_lines, new_lines):
    expected = old
    for prefix, count in substitutions: expected = expected.replace(prefix, str(DEST).encode())
    assert new == expected
(DEST / 'run_bootstrap01.ps1').write_bytes(new_launcher)
write_json(DEST / 'SOURCE-INPUTS.json', new_map)
pins = {row['name']: row['copy_sha256'] for row in rows}
pins['SOURCE-INPUTS.json'] = sha((DEST / 'SOURCE-INPUTS.json').read_bytes())
pins['run_bootstrap01.ps1'] = sha(new_launcher)
write_json(DEST / 'ROOT-ADMISSION.template.json', {'root_reviewed': False,
    'scope': template['scope'], 'label': template['label'], 'input_sha256': pins,
    'expected_cases': template['expected_cases'],
    'notice': 'Independent seventeen-case generated confirmation proposal only. Root review and separate actual admission required. No native/model/runtime authority.'})
(PREP / 'run_bootstrap01.ps1.diff').write_text(''.join(difflib.unified_diff(
    launcher_raw.decode().splitlines(keepends=True), new_launcher.decode().splitlines(keepends=True),
    fromfile='author/run_bootstrap01.ps1', tofile='independent/run_bootstrap01.ps1')), encoding='utf-8', newline='')
for row in rows:
    assert sha(Path(row['source']).read_bytes()) == row['source_sha256']
assert (AUTHOR / 'SOURCE-INPUTS.json').read_bytes() == map_raw
assert (AUTHOR / 'run_bootstrap01.ps1').read_bytes() == launcher_raw
assert (AUTHOR / 'ROOT-ADMISSION.template.json').read_bytes() == template_raw
bindings = {'schema': 'uoink.worker-bootstrap-independent-copy.v1', 'candidate_execution': False,
    'child_input_count': 17, 'outer_input_count': 19, 'case_groups': [11, 6], 'case_count': 17,
    'source_template_sha256': sha(template_raw), 'source_launcher_sha256': sha(launcher_raw),
    'copy_launcher_sha256': sha(new_launcher), 'copy_map_sha256': pins['SOURCE-INPUTS.json'],
    'only_launcher_path_substitutions': True,
    'path_substitution_counts': {'instrument': 3, 'owner_source': 11, 'migration_source': 4},
    'all_original_inputs_unchanged': True, 'files': rows, 'copy_input_sha256': pins}
write_json(DEST / 'COPY-BINDINGS.json', bindings)
(DEST / '.gitattributes').write_bytes(b'* -text\n')
(PREP / '.gitattributes').write_bytes(b'* -text\n')
print(json.dumps({'candidate_execution': False, 'exact_child_copies': len(rows),
    'launcher_sha256': pins['run_bootstrap01.ps1'], 'map_sha256': pins['SOURCE-INPUTS.json'],
    'bindings_sha256': sha((DEST / 'COPY-BINDINGS.json').read_bytes()),
    'template_sha256': sha((DEST / 'ROOT-ADMISSION.template.json').read_bytes())}))
