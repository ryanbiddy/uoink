import hashlib, json, shutil, subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

r = Path(__file__).resolve().parents[1]
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=r, text=True).strip()
assert source == 'b62aab325ef6b2dfde95e23b97b4b23e263e6e9a'
out = r/'docs/library/proof/mirror-owner-admission01-2026-09-13'
out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n', encoding='utf8', newline='\n')
names = ['test_mirror_owner_admission_diagnostic.py', 'MIRROR-OWNER-ADMISSION-DIAGNOSTIC-BRIEF-2026-09-13.md', 'mirror-owner-admission01-events.json', 'integrator_verify.py', 'seal_mirror_owner_admission01.py']
for name in names:
    shutil.copyfile(r/'_scratch'/name, out/name)
for name in ['tests.log', 'tests.xml', 'results.json']:
    shutil.copyfile(r/'_scratch/mirror-owner-admission01'/name, out/name)
suites = list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests', 0)) for s in suites) == 1
assert sum(int(s.get('failures', 0)) for s in suites) == 1
events = json.loads((out/'mirror-owner-admission01-events.json').read_text())
assert events[-1] == {'event':'prepared','held':False,'launching':True,'sessions':1}
(out/'summary.json').write_text(json.dumps({'source':source,'passed':0,'failed':1,'skipped':0,'kind':'controlled synthetic interleaving; fake kernel mutex only','original_full_tree_cause':'not established'}, indent=2)+'\n', encoding='utf8')
files = {p.relative_to(out).as_posix():{'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files}, indent=2)+'\n', encoding='utf8')
print(json.dumps({'payloads':len(files),'source':source,'passed':0,'failed':1}))
