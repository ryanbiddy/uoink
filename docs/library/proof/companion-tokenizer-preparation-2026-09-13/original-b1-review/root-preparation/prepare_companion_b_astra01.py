"""Copy exact reviewed synthetic inputs for an independent constructor check."""
import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
original=root/'_scratch/companion-b-static-qualification01'
out=root/'_scratch/astra-companion-b01'
out.mkdir(exist_ok=False)
mapping=json.loads((original/'source-mapping.json').read_bytes())
names=['harness.py','launch.py','source-mapping.json','constructor-contracts.py.txt',
       'BASELINE-REPAIR-REASON-2026-09-13.md',mapping['input_relative_path'],
       mapping['derivative_relative_path'],mapping['patch_relative_path']]
bindings={}
for name in names:
    source=(original/name).resolve(strict=True)
    target=out/name
    assert source.is_relative_to(original) and target.resolve().is_relative_to(out)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    raw=source.read_bytes()
    assert target.read_bytes()==raw
    bindings[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
(out/'ROOT-REVIEW.json').write_text(json.dumps({
    'purpose':'Independent candidate verification after complete source/harness/assertion review',
    'scope':'Only selected constructor prefix with fake seams; no model/dependency import, application or build',
    'original_baseline_result':{'passed':1,'failed':5,'errors':0,'exit':1},
    'source_inputs':bindings,'existing_tests_changed':False,
    'candidate_harness_and_tests_unchanged':True},indent=2)+'\n',encoding='utf8')
print(json.dumps({'directory':str(out),'exact_copied_inputs':len(bindings)}))
