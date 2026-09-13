import hashlib, json, shutil, subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\213914a5-528\gemini')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()=='b62aab325ef6b2dfde95e23b97b4b23e263e6e9a'
assert not subprocess.check_output(['git','diff','--name-only'],cwd=w,text=True).strip()
report='docs/library/MIRROR-PROCESS-AUTHORITY-GEMINI-2026-09-13.md'
probe='tests/test_gemini_synthetic_process_authority.py'
out=w/'docs/library/proof/gemini-mirror-authority-2026-09-13'
out.mkdir(exist_ok=False,parents=True)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
for name in [report,probe]:
    shutil.copyfile(w/name,out/Path(name).name)
subprocess.run(['git','add','-N',report,probe],cwd=w,check=True)
(out/'original-worker.diff').write_bytes(subprocess.check_output(['git','diff','--binary','--',report,probe],cwd=w))
subprocess.run(['git','reset','--',probe],cwd=w,check=True)
for label in ['gemini-authority-01','gemini-authority-02','gemini-authority-03','astra-gemini-authority01']:
    for p in (w/'_scratch'/label).rglob('*'):
        if p.is_file() and p.suffix in ('.py','.log','.xml','.json'):
            dest=out/label/p.relative_to(w/'_scratch'/label)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,dest)
for name in ['integrator_verify.py','run_gemini_authority_verification.ps1','archive_gemini_mirror_authority.py']:
    shutil.copyfile(r/'_scratch'/name,out/name)
(out/'review-limits.json').write_text(json.dumps({
 'source':'b62aab325ef6b2dfde95e23b97b4b23e263e6e9a',
 'worker_attempt_counts':[{'passed':4,'failed':2},{'passed':5,'failed':1},{'passed':6,'failed':0}],
 'astra_worker_observation':{'passed':6,'failed':0},
 'meaning':'These probes assert current defects; passing is reproduction, not product clearance.',
 'unverified_claims':['Probe 2 teardown flags assign globals but assert unchanged locals; no real owner/retain is set, so exclusion-held claim is unsupported.','Report opening says 51 mirror failures; actual tree08 has 50 mirror failures plus AT6.','Earlier probe drafts were overwritten by worker; logs remain but exact v1/v2 source bytes were not located.','Tree08 causal link remains unproved.'],
 'product_edits':False,'accepted_regression_tests':False
},indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
subprocess.run(['git','add','-N','-f',str(out)],cwd=w,check=True)
patch=r/'_scratch/gemini-mirror-authority-reviewed.diff'
patch.write_bytes(subprocess.check_output(['git','diff','--binary','--',report,str(out)],cwd=w))
print(json.dumps({'payloads':len(files),'patch':str(patch),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest()}))
