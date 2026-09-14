"""Copy/hash text inputs only; never import or execute the qualification."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
PREP = ROOT / '_scratch/worker-runtime-owner-confirmation-preparation01'
AUTHOR = ROOT / '_scratch/worker-runtime-owner-instrument01'
SOURCE = ROOT / '_scratch/worker-runtime-owner-proposal02'
DEST = ROOT / '_scratch/astra-worker-runtime-owner-confirmation01'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def save_json(path, data):
    with path.open('xb') as stream:
        stream.write((json.dumps(data, indent=2) + '\n').encode('utf-8'))

admission_raw = (AUTHOR / 'ROOT-ADMISSION.json').read_bytes()
assert digest(admission_raw) == '6947fb2cda180fefd17b8fb5cdcc64216bc45569cf96a46238236256b8921f44'
admission = json.loads(admission_raw)
assert admission['root_reviewed'] is True
assert len(admission['input_sha256']) == 15
assert len(admission['expected_cases']) == 11
map_raw = (AUTHOR / 'SOURCE-INPUTS.json').read_bytes()
assert digest(map_raw) == admission['input_sha256']['SOURCE-INPUTS.json']
mapping = json.loads(map_raw)
assert len(mapping['sources']) == 13
launcher_raw = (AUTHOR / 'run_owner01.ps1').read_bytes()
assert digest(launcher_raw) == admission['input_sha256']['run_owner01.ps1']
assert not DEST.exists(), 'Fresh confirmation copy required'
DEST.mkdir()
(PREP / 'before').mkdir()
(PREP / 'before/run_owner01.ps1').write_bytes(launcher_raw)
(PREP / 'before/SOURCE-INPUTS.json').write_bytes(map_raw)
records = []
new_map = json.loads(map_raw)
for name, row in mapping['sources'].items():
    source = Path(row['path'])
    assert source.parent in (AUTHOR, SOURCE)
    assert source.name == name
    raw = source.read_bytes()
    original_hash = digest(raw)
    assert original_hash == row['sha256'] == admission['input_sha256'][name]
    target = DEST / name
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw
    new_map['sources'][name]['path'] = str(target)
    records.append({'name': name, 'author_path': str(source), 'copy_path': str(target),
                    'bytes': len(raw), 'author_sha256': original_hash,
                    'copy_sha256': digest(target.read_bytes())})

author_literal = str(AUTHOR).encode()
source_literal = str(SOURCE).encode()
dest_literal = str(DEST).encode()
assert launcher_raw.count(author_literal) == 3
assert launcher_raw.count(source_literal) == 11
copied_launcher = launcher_raw.replace(author_literal, dest_literal).replace(source_literal, dest_literal)
# Verify every changed line is exactly one of those literal path substitutions.
old_lines = launcher_raw.splitlines(keepends=True)
new_lines = copied_launcher.splitlines(keepends=True)
assert len(old_lines) == len(new_lines)
assert all(new == old.replace(author_literal, dest_literal).replace(source_literal, dest_literal)
           for old, new in zip(old_lines, new_lines))
with (DEST / 'run_owner01.ps1').open('xb') as stream:
    stream.write(copied_launcher)
save_json(DEST / 'SOURCE-INPUTS.json', new_map)
pins = {row['name']: row['copy_sha256'] for row in records}
pins['SOURCE-INPUTS.json'] = digest((DEST / 'SOURCE-INPUTS.json').read_bytes())
pins['run_owner01.ps1'] = digest(copied_launcher)
save_json(DEST / 'ROOT-ADMISSION.template.json', {
    'root_reviewed': False,
    'scope': admission['scope'],
    'label': admission['label'],
    'input_sha256': pins,
    'expected_cases': admission['expected_cases'],
    'notice': 'Independent confirmation proposal only. Same eleven generated cases; root must review these copy bindings and issue separate admission. No native/model/runtime authority.'
})
(PREP / 'run_owner01.ps1.diff').write_text(''.join(difflib.unified_diff(
    launcher_raw.decode().splitlines(keepends=True), copied_launcher.decode().splitlines(keepends=True),
    fromfile='author/run_owner01.ps1', tofile='confirmation/run_owner01.ps1')), encoding='utf-8', newline='')
for row in records:
    assert digest(Path(row['author_path']).read_bytes()) == row['author_sha256']
assert digest((AUTHOR / 'run_owner01.ps1').read_bytes()) == admission['input_sha256']['run_owner01.ps1']
assert digest((AUTHOR / 'SOURCE-INPUTS.json').read_bytes()) == admission['input_sha256']['SOURCE-INPUTS.json']
assert digest((AUTHOR / 'ROOT-ADMISSION.json').read_bytes()) == digest(admission_raw)
bindings = {'schema': 'uoink.runtime-owner-independent-copy.v1',
    'candidate_execution': False, 'case_count': 11, 'exact_child_copies': records,
    'original_admission_sha256': digest(admission_raw),
    'launcher_original_sha256': digest(launcher_raw),
    'launcher_copy_sha256': digest(copied_launcher),
    'source_map_copy_sha256': pins['SOURCE-INPUTS.json'],
    'path_substitution_counts': {'instrument_directory': 3, 'proposal_directory': 11},
    'only_launcher_path_substitutions': True, 'all_original_inputs_unchanged': True,
    'new_input_sha256': pins}
save_json(DEST / 'COPY-BINDINGS.json', bindings)
(DEST / '.gitattributes').write_bytes(b'* -text\n')
(PREP / '.gitattributes').write_bytes(b'* -text\n')
print(json.dumps({'candidate_execution': False, 'exact_child_copies': len(records),
    'launcher_sha256': pins['run_owner01.ps1'], 'source_map_sha256': pins['SOURCE-INPUTS.json'],
    'copy_bindings_sha256': digest((DEST / 'COPY-BINDINGS.json').read_bytes()),
    'admission_template_sha256': digest((DEST / 'ROOT-ADMISSION.template.json').read_bytes())}))
