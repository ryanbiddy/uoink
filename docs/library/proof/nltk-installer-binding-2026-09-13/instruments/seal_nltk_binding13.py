import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root/'_scratch/wheel-integrator13'
out=root/'docs/library/proof/nltk-installer-binding-2026-09-13';out.mkdir(exist_ok=False)
def copy(name,path):
    p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(path.read_bytes())
counts={}
for prefix,base,names in [('worktree',tree,['nltk-binding13-worker01','nltk-binding13-worker02']),('checkout',root,['nltk-binding13-checkout01'])]:
    for name in names:
        folder=base/'_scratch'/name
        for p in folder.iterdir():
            if p.is_file():copy('runs/'+prefix+'/'+name+'/'+p.name,p)
        for p in (folder/'guard').glob('*.py'):copy('runs/'+prefix+'/'+name+'/guard/'+p.name,p)
        counts[prefix+'/'+name]=[e.attrib for e in ET.parse(folder/'tests.xml').getroot().iter('testsuite')] if (folder/'tests.xml').exists() else []
for p in (root/'_scratch/nltk-binding13-integration01').iterdir():copy('integration/'+p.name,p)
paths=['build.ps1','requirements-installer-lock.txt','THIRD-PARTY-NOTICES.md','scripts/gen_third_party_notices.py','docs/build-installer.md','docs/security.md']
for name in paths:copy('source/'+name,root/name)
for name in ['integrate_nltk_binding13.py','seal_nltk_binding13.py','run_media_verify12.py','integrator_verify.py']:copy('instruments/'+name,root/'_scratch'/name)
build=(root/'build.ps1').read_text(encoding='utf8')
hash_literal=re.search(r"\$NLTK_PATHSEC_SHA256 = '([0-9a-f]{64})'",build)[1]
artifact=root/'vendor/nltk-pathsec/dist/nltk-3.10.3+uoink.pathsec1-py3-none-any.whl'
assert hashlib.sha256(artifact.read_bytes()).hexdigest()==hash_literal=='969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8'
assert 'nltk==3.10.3+uoink.pathsec1' in (root/'requirements-installer-lock.txt').read_text()
assert build.index('Confirm-Hash $NltkPathsecWheel')<build.index('& $embedPython -m pip install')
note='''# Installer selects the reviewed NLTK backport

The candidate build now verifies and explicitly installs the local
3.10.3+uoink.pathsec1 wheel under the matching lock constraint. The committed
artifact matches the fixed build hash. Other pins, including Torch/WhisperX,
remain unchanged. Notices name the local modification and retain its licence.
Staging and installed qualification are still pending.

The six named build/signing/notices suites pass 51 cases in each root, after
raw diff / three-way integration: worker 12.92 seconds, checkout 12.49 seconds.
The first launcher named a nonexistent guide test and exited 4 with zero tests
run; the corrected filename and fresh label are documented in the package brief.
No existing test or assertion changed. A full combined tree and replacement
package must follow. Source binding alone does not clear the original advisory.
'''
verdict=root/'docs/library/NLTK-INSTALLER-BINDING-VERDICT-2026-09-13.md';verdict.write_text(note,encoding='utf8',newline='\n')
copy('source/docs/library/NLTK-INSTALLER-BINDING-VERDICT-2026-09-13.md',verdict)
(out/'review.json').write_text(json.dumps({'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'counts':counts,'fixed_build_hash_matches_vendor_wheel':True,'installer_built':False,'installed':False,'release_ready':False},indent=2)+'\n',encoding='utf8')
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
attr=root/'.gitattributes';text=attr.read_text(encoding='utf8');rule='docs/library/proof/nltk-installer-binding-2026-09-13/** -text';assert rule not in text
attr.write_text(text+'\n'+rule+'\n',encoding='utf8',newline='\n')
paths+=['.gitattributes','docs/library/PACKAGE-09-INTEGRATION-BRIEF-2026-09-12.md',str(verdict.relative_to(root)),str(out.relative_to(root))]
subprocess.run(['git','add','-f','--',*paths],cwd=root,check=True,capture_output=True)
for name,digest in manifest.items():
    blob=subprocess.check_output(['git','show',':'+(out/name).relative_to(root).as_posix()],cwd=root)
    assert hashlib.sha256(blob).hexdigest()==digest
assert not subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=CDMRTUXB','7109182','--','tests','scripts/install_receipt/p4_prepare_fixture.py'],cwd=root)
subprocess.run(['git','diff','--cached','--check','--',*paths[:-1]],cwd=root,check=True,capture_output=True)
subprocess.run(['git','commit','-m','fix(build): bind the installer to the reviewed NLTK security wheel [Astra]'],cwd=root,check=True,capture_output=True)
print(json.dumps({'proof_payloads':len(manifest),'commit':subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=root,text=True).strip(),'counts':counts}))
