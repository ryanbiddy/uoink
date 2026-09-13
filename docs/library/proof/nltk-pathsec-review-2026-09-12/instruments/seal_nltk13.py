import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
base=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library')
worker=base / 'ecbf6acd-847/gemini'
first=base / '4a939c69-786/gemini'
out=root / 'docs/library/proof/nltk-pathsec-review-2026-09-12'
out.mkdir(exist_ok=False)
def put(name,data):
    path=out / name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(data)
def copy(name,path): put(name,path.read_bytes())
def archive(prefix,directory):
    for path in sorted(directory.rglob('*')):
        if path.is_file(): copy(prefix+'/'+path.relative_to(directory).as_posix(),path)

archive('original-worker',worker / '_scratch/nltk-original')
archive('repair-worker-before-astra',worker / '_scratch/nltk-pre-astra')
bindings={}
for path in (worker / '_scratch/nltk-original').rglob('*'):
    if path.is_file():
        name=path.relative_to(worker / '_scratch/nltk-original')
        assert path.read_bytes()==(first / name).read_bytes(),str(name)
        bindings[name.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()

readme='''# NLTK path-policy source backport

This patch targets the six artifact APIs named by GHSA-8mgp-746c-j5xp in
NLTK 3.10.3. Read docs/library/ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md for
the integration verdict, test counts and limits. It is source preparation,
not a packaged dependency or a cleared installer advisory.

TransitionParser.train/parse and AveragedPerceptron.save/load now check their
paths and use NLTK's guarded file operations. Tagger saves validate filename
components and the destination; they retain POSIX descriptor-based writes.
Maxent output uses the path policy for its four files. Implicitly registering
new caller directories as trusted roots is removed. Existing serialization
code remains downstream; the tests intercept it rather than qualify models.

On Windows, directory creation is checked before and after by pathname. This
does not establish general race protection against another process with the
same user's rights. The Windows symlink test is skipped when the OS refuses
link creation. POSIX-specific behavior was inspected, not executed here.

Prepare into a new directory with:

```powershell
python scripts/prepare_nltk_pathsec_backport.py --src <pristine-nltk-package> --dst <new-destination>
```

The utility checks the exact three input hashes, fixed patch hash, every patch
output and the complete copied file map. The receipt stays inside the new
destination and uses exclusive creation. No expected-hash override is accepted.
No package is imported and no resource is fetched. Retained-byte comparison
does not independently authenticate upstream material or eliminate every
concurrent filesystem race.

The original source files under original/ are portable preparation fixtures,
copied without modification from the staged upstream package. Their copyrights
remain in the files; the upstream distribution licence is in original/LICENSE.txt.
Full import/routing tests require the matching staged Python/native libraries.
UOINK_NLTK_BASE_SOURCE may point to preserved pristine source after the runtime
is patched; it is separate from the runtime used to execute those tests.

Before installer use, build an explicitly labelled local wheel, update its
distribution version/metadata and RECORD, record the wheel hash and notices,
and qualify the staged runtime and full candidate. Keep the original advisory
visible alongside any later backport disposition. Do not patch staging in place.
'''
(root / 'vendor/nltk-pathsec/README.md').write_text(readme,encoding='utf8',newline='\n')
for name in ['NLTK-PATHSEC-BACKPORT-2026-09-12.md','NLTK-PATHSEC-PREPARATION-REVIEW-2026-09-12.md']:
    path=root / 'docs/library' / name
    raw=path.read_text(encoding='utf8')
    prefix='> Retained worker report. Read [Astra\'s verdict](ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md) first; its boundary and test corrections supersede the claims below. Original worker bytes are preserved in the proof archive.\n\n'
    path.write_text(prefix+'\n'.join(line.rstrip() for line in raw.splitlines())+'\n',encoding='utf8')

sources=['scripts/prepare_nltk_pathsec_backport.py','tests/test_nltk_pathsec_backport.py','tests/test_nltk_preparation_boundaries.py',
 'vendor/nltk-pathsec/README.md','vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch',
 'docs/library/ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md','docs/library/NLTK-ASTRA-BOUNDARY-REPAIR-BRIEF-2026-09-12.md']
for name in sources: copy('source/'+name,root / name)
for name in sources[:2]:
    old=(worker / '_scratch/nltk-pre-astra' / name).read_text(encoding='utf8').splitlines(keepends=True)
    new=(root / name).read_text(encoding='utf8').splitlines(keepends=True)
    put('integrator-diffs/'+Path(name).name+'.diff',''.join(difflib.unified_diff(old,new,fromfile='worker/'+name,tofile='astra/'+name)).encode())
counts={}
groups=[('worker',worker,['nltk12-astra-worker01','nltk12-astra-worker02','nltk12-astra-worker03']),
 ('checkout',root,['nltk12-checkout01','nltk12-checkout02']),
 ('original-negative',worker / '_scratch/nltk-pre-astra-probes',['original01'])]
for label,tree,names in groups:
    for name in names:
        directory=tree / '_scratch' / name
        for path in directory.iterdir():
            if path.is_file(): copy('runs/'+label+'/'+name+'/'+path.name,path)
        for path in (directory / 'guard').glob('*.py'): copy('runs/'+label+'/'+name+'/guard/'+path.name,path)
        counts[label+'/'+name]=[n.attrib for n in ET.parse(directory / 'tests.xml').getroot().iter('testsuite')]
archive('integration',root / '_scratch/nltk12-integration01')
archive('dispatch',root / '_scratch/nltk-preparation-repair12-dispatch01')
for name in ['seal_nltk13.py','integrate_nltk13.py','run_media_verify12.py','integrator_verify.py']:
    copy('instruments/'+name,root / '_scratch' / name)
put('review.json',(json.dumps({'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'original_archive_bindings':bindings,'counts_from_original_xml':counts,'production_pins_changed':False,
 'existing_tests_changed':False,'models_loaded':False,'packaged_backport':False,'release_ready':False,
 'worker_report_scope':'27/1 and earlier worker counts remain attributed to the preserved worker reports; Astra did not rerun those uncorrected routing tests.'},indent=2)+'\n').encode())
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(manifest),'original_archive_files_verified':len(bindings),'runs':list(counts)}))
