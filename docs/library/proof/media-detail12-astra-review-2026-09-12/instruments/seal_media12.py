import hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
p=r/'docs/library/proof/media-detail12-astra-review-2026-09-12';p.mkdir(exist_ok=False)
(p/'.gitattributes').write_text('* -text\n',encoding='utf8')
def copy(src,dest):
    q=p/dest;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,q)
for f in (r/'_scratch/media-detail12-review').iterdir():
    if f.is_file():copy(f,'transport/'+f.name)
attempts=[]
for root in (w,r):
    for folder in sorted((root/'_scratch').iterdir()):
        if not folder.is_dir() or not folder.name.startswith(('astra-media12-','gemini-media-','gemini-baseline-')):continue
        if not (folder/'results.json').exists():continue
        for f in folder.iterdir():
            if f.is_file() and f.suffix in ('.json','.log','.xml'):copy(f,'attempts/'+folder.name+'/'+f.name)
        suites=list(ET.parse(folder/'tests.xml').getroot().iter('testsuite')) if (folder/'tests.xml').exists() else []
        attempts.append({'label':folder.name,'root':'worker' if root==w else 'checkout','exit_codes':[x['exit'] for x in json.loads((folder/'results.json').read_text(encoding='utf8'))], 'tests':sum(int(x.get('tests',0)) for x in suites),'failures':sum(int(x.get('failures',0)) for x in suites),'errors':sum(int(x.get('errors',0)) for x in suites),'skipped':sum(int(x.get('skipped',0)) for x in suites),'seconds':sum(float(x.get('time',0)) for x in suites)})
(p/'attempts-summary.json').write_text(json.dumps(attempts,indent=2)+'\n',encoding='utf8')
for name in ('prepare_media_review12.py','prepare_media_review12_initial.py.txt','media-review12-preparation-failure.json','fix_media_boundary_setup12.py','fix_media_boundary_setup12_02.py','fix_media_boundary_setup12_03.py','repair_media_source12.py','repair_media_depth12.py','run_media_verify12.py','integrator_verify.py','integrate_media12.py','media_alias_preflight12.py','repair_media_alias12.py','integrate_media_alias12.py','seal_media12.py'):
    copy(r/'_scratch'/name,'instruments/'+name)
bindings=[]
for name in ('server.py','assets/dashboard/index.html','tests/test_dashboard_media_detail_truth.py','tests/test_media_detail_boundaries.py'):
    data=subprocess.check_output(['git','show',':'+name],cwd=r)
    assert data==(r/name).read_bytes().replace(b'\r\n',b'\n')==(w/name).read_bytes().replace(b'\r\n',b'\n')
    bindings.append({'path':name,'git_sha256':hashlib.sha256(data).hexdigest(),'both_roots_match':True})
(p/'final-source-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf8')
name='docs/library/DASHBOARD-MEDIA-DETAIL-WORKER-2026-09-12.md'
patch=subprocess.check_output(['git','diff','--binary','--',name],cwd=w);(p/'worker-documentary.patch').write_bytes(patch)
result=subprocess.run(['git','apply','--3way',str(p/'worker-documentary.patch')],cwd=r,capture_output=True)
(p/'worker-documentary-apply.stdout').write_bytes(result.stdout);(p/'worker-documentary-apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
report=r/name;report.write_text('> Integrator notice: this retained worker report describes the initial patch.\n> Its byte-bound, nested-field and race claims were incomplete. Read\n> ASTRA-MEDIA-DETAIL-REVIEW-2026-09-12.md for the accepted source and results.\n\n'+report.read_text(encoding='utf8'),encoding='utf8',newline='\n')
for name in ('DASHBOARD-MEDIA-DETAIL-REPAIR-BRIEF-2026-09-12.md','MEDIA-DETAIL-INTEGRATOR-REPAIR-2026-09-12.md'):
    shutil.copyfile(r/'_scratch'/name,r/'docs/library'/name)
files={q.relative_to(p).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(p.rglob('*')) if q.is_file()}
(p/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'attempts':attempts},indent=2))
