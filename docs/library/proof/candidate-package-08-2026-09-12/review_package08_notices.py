"""Documentary review: fill UNKNOWN only from exact staged License-Expression."""
import email
import hashlib
import json
import re
import shutil
from pathlib import Path

r = Path(__file__).resolve().parents[1]
out = r / '_scratch/package08-notices-review-01'
out.mkdir(exist_ok=False)
path = r / 'THIRD-PARTY-NOTICES.md'
before = path.read_text(encoding='utf8')
shutil.copyfile(path, out / 'generated-notices.md')
metadata = {}
norm = lambda s: re.sub(r'[-_.]+', '-', s.lower())
for source in (r / 'installer/staging/python/Lib/site-packages').glob('*.dist-info/METADATA'):
    data = email.message_from_bytes(source.read_bytes())
    metadata[norm(data['Name'])] = (source, data)
changes = []
remaining = []
lines = []
for line in before.splitlines():
    cells = [x.strip() for x in line.split('|')]
    if len(cells) == 6 and cells[3] == 'UNKNOWN':
        source, data = metadata[norm(cells[1])]
        assert data['Version'] == cells[2]
        expression = data['License-Expression']
        if expression:
            assert '\n' not in expression and '|' not in expression
            line = line.replace(' | UNKNOWN | ', ' | ' + expression + ' | ')
            relative = Path('metadata') / source.parent.name / source.name
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            changes.append({'package': cells[1], 'version': cells[2], 'old': 'UNKNOWN',
                            'license_expression': expression, 'metadata': relative.as_posix(),
                            'metadata_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        else:
            remaining.append(cells[1])
    lines.append(line)
note = ('\nSPDX expressions below fill the generator\'s UNKNOWN fields only where the\n'
        'exact packaged wheel declares License-Expression. This September 12 review\n'
        'does not infer missing metadata or replace the packaged license files.\n')
after = '\n'.join(lines) + '\n'
anchor = '\n| Package | Version | License | Project |'
assert anchor in after and changes
after = after.replace(anchor, note + anchor, 1)
path.write_text(after, encoding='utf8', newline='\n')
shutil.copyfile(path, out / 'reviewed-notices.md')
record = {'scope': 'Documentation only; no generator or installed source change.',
          'reason': 'pip-licenses 5 omits modern License-Expression values; preserve its raw output and copy exact staged fields.',
          'changed_rows': len(changes), 'changes': changes, 'remaining_unknown': remaining,
          'generated_sha256': hashlib.sha256((out / 'generated-notices.md').read_bytes()).hexdigest(),
          'reviewed_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
(out / 'review.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(json.dumps({k: v for k, v in record.items() if k != 'changes'}, indent=2))
