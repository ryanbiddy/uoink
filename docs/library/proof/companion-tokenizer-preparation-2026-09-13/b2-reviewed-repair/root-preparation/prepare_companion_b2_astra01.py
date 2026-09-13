"""Copy the exact reviewed B2 inputs for independent synthetic qualification."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
original = root / '_scratch/companion-b2-empty-buffer01'
out = root / '_scratch/astra-companion-b2-01'
out.mkdir(exist_ok=False)
mapping = json.loads((original / 'source-mapping.json').read_bytes())
names = ['harness.py', 'launch.py', 'source-mapping.json',
         'constructor-contracts.py.txt', 'B1-BOUNDARY-REPAIR-REASON-2026-09-13.md',
         'BRIEF.md', mapping['input_relative_path'], mapping['derivative_relative_path'],
         'B1-to-B2.patch.txt']
bindings = {}
for name in names:
    source = (original / name).resolve(strict=True)
    target = out / name
    assert source.is_relative_to(original) and target.resolve().is_relative_to(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    raw = source.read_bytes()
    assert target.read_bytes() == raw
    bindings[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
(out / 'ROOT-REVIEW.json').write_text(json.dumps({
    'purpose': 'Independent B2 qualification after review of the source delta, all ten assertions, helper and launcher',
    'scope': 'Selected constructor prefix with inert fakes; no dependency package import, model load, installation or build',
    'prior_B1_boundary': {'passed': 6, 'failed': 4, 'errors': 0, 'exit': 1},
    'inputs': bindings, 'original_six_assertions_unchanged': True,
    'existing_acceptance_tests_changed': False,
    'B2_harness_and_tests_copied_exactly': True}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'directory': str(out), 'exact_copied_inputs': len(bindings)}))
