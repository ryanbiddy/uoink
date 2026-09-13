import difflib,hashlib,json,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
out=root / 'docs/library/proof/nltk-local-wheel-2026-09-13'
out.mkdir(exist_ok=False)
def put(name,data):
    p=out / name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:stream.write(data)
def copy(name,p):put(name,p.read_bytes())
def archive(name,directory):
    for p in sorted(directory.rglob('*')):
        if p.is_file():copy(name+'/'+p.relative_to(directory).as_posix(),p)
verdict=root/'docs/library/NLTK-LOCAL-WHEEL-REVIEW-2026-09-12.md'
raw=verdict.read_text(encoding='utf8').replace('Checkout verification follows raw diff / three-way integration.',
 'Checkout verification passes the same 43 cases after raw diff / three-way\nintegration: worker 12.04 s, checkout 11.72 s, no failures or skips.')
verdict.write_text(raw,encoding='utf8',newline='\n')
archive('original-worker',root / '_scratch/nltk-wheel-worker-original13')
archive('provisional-artifact',root / '_scratch/nltk-wheel-astra-artifact01')
archive('final-artifact',root / '_scratch/nltk-wheel-astra-artifact02')
archive('compression-repair',root / '_scratch/nltk-wheel-stored-build01')
archive('probe-correction',root / '_scratch/nltk-wheel-probe-correction13')
archive('dispatch',root / '_scratch/nltk-local-wheel13-dispatch01')
archive('integration',root / '_scratch/nltk-wheel13-integration01')
copy('pristine-fixture-receipt.json',root / '_scratch/nltk-upstream-before-local13/receipt.json')
counts={}
for prefix,base,names in [('takeover',tree,['nltk-wheel-astra13-worker01','nltk-wheel-astra13-worker02']),
                         ('checkout',root,['nltk-wheel13-checkout01']),
                         ('negative',root/'_scratch/nltk-wheel-original-probes13',['original01','original02'])]:
    for name in names:
        directory=base / '_scratch' / name
        for p in directory.iterdir():
            if p.is_file():copy('runs/'+prefix+'/'+name+'/'+p.name,p)
        for p in (directory/'guard').glob('*.py'):copy('runs/'+prefix+'/'+name+'/guard/'+p.name,p)
        counts[prefix+'/'+name]=[x.attrib for x in ET.parse(directory/'tests.xml').getroot().iter('testsuite')]
for rel in ['scripts/build_nltk_pathsec_wheel.py','tests/test_nltk_local_wheel.py','tests/test_nltk_wheel_boundaries.py',
            'docs/library/NLTK-LOCAL-WHEEL-REVIEW-2026-09-12.md','docs/library/NLTK-LOCAL-WHEEL-BOUNDARY-REPAIR-BRIEF-2026-09-12.md']:
    copy('source/'+rel,root / rel)
for rel in ['scripts/build_nltk_pathsec_wheel.py','tests/test_nltk_local_wheel.py']:
    old=(root/'_scratch/nltk-wheel-worker-original13'/rel).read_text(encoding='utf8')
    new=(root/rel).read_text(encoding='utf8')
    put('integrator-diffs/'+Path(rel).name+'.diff',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='worker/'+rel,tofile='astra/'+rel)).encode())
for name in ['takeover_wheel13.py','repair_wheel13.py','build_wheel_stored13.py','prepare_wheel_tests13.py','repair_wheel_probe13.py',
             'prepare_wheel_integration13.py','review_nltk_wheel13.py','review_nltk_wheel13_final.py','final_review_wheel13.py',
             'preserve_nltk13.py','seal_wheel13.py','run_media_verify12.py','integrator_verify.py']:
    copy('instruments/'+name,root / '_scratch' / name)
put('review.json',(json.dumps({'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'counts_from_xml':counts,'provider_status':'PARTIAL: print timeout, failed test and missing review; transport completed/zero is not acceptance',
 'patch_instrument_initial_attempt':'No source written: preflight expected earlier out_dir.parent temp block; final snapshot used repo_scratch. Corrected instrument matches preserved source.',
 'wheel_sha256':'969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8','wheel_bytes':6597605,
 'cross_python_wheel_bytes_equal':True,'production_pins_changed':False,'models_loaded':False,'release_ready':False},indent=2)+'\n').encode())
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
attributes=root / '.gitattributes';attrs=attributes.read_text(encoding='utf8');rule='docs/library/proof/nltk-local-wheel-2026-09-13/** -text'
assert rule not in attrs;attributes.write_text(attrs+'\n'+rule+'\n',encoding='utf8',newline='\n')
paths=['.gitattributes','scripts/build_nltk_pathsec_wheel.py','tests/test_nltk_local_wheel.py','tests/test_nltk_wheel_boundaries.py',
       'vendor/nltk-pathsec/dist','docs/library/NLTK-LOCAL-WHEEL-REVIEW-2026-09-12.md','docs/library/proof/nltk-local-wheel-2026-09-13']
subprocess.run(['git','add','-f','--',*paths],cwd=root,check=True,capture_output=True)
mapping={'docs/library/proof/nltk-local-wheel-2026-09-13/'+k:v for k,v in manifest.items()}
mapping.update({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'vendor/nltk-pathsec/dist').iterdir() if p.is_file()})
batch=subprocess.run(['git','cat-file','--batch'],cwd=root,input=''.join(':'+k+'\n' for k in mapping).encode(),capture_output=True,check=True).stdout
offset=0
for name,digest in mapping.items():
    end=batch.index(b'\n',offset);size=int(batch[offset:end].split()[2]);start=end+1
    assert hashlib.sha256(batch[start:start+size]).hexdigest()==digest==hashlib.sha256((root/name).read_bytes()).hexdigest(),name
    assert size<100_000_000;offset=start+size+1
assert not subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=CDMRTUXB','7109182','--','tests','scripts/install_receipt/p4_prepare_fixture.py'],cwd=root)
subprocess.run(['git','diff','--cached','--check','--',*paths[:4],paths[5]],cwd=root,check=True,capture_output=True)
subprocess.run(['git','commit','-m','fix(build): produce a verified reproducible NLTK backport wheel [Astra]'],cwd=root,check=True,capture_output=True)
print(json.dumps({'proof_payloads':len(manifest),'git_and_disk_verified':len(mapping),'counts':counts,'commit':subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=root,text=True).strip()}))
