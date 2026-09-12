"""Static evidence only: no dependency imports, model loads or network requests."""
import ast,hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
out=s/'security-backport12-review';out.mkdir(exist_ok=False)
meta=r/'docs/library/proof/security-repair-gemini-2026-09-12'
manifest=json.loads((meta/'SHA256.json').read_text(encoding='utf8'))
for name,row in manifest['files'].items():
    data=(meta/name).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
advisories=[]
for p in sorted((meta/'osv/advisories').glob('*.json')):
    d=json.loads(p.read_text(encoding='utf8'))
    advisories.append({'id':d['id'],'aliases':d.get('aliases',[]),'summary':d.get('summary'),
      'details':d.get('details'),'ranges':[{'package':a['package'],'ranges':a.get('ranges',[])} for a in d.get('affected',[])]})
(out/'retained-advisory-details.json').write_text(json.dumps(advisories,indent=2)+'\n',encoding='utf8',newline='\n')
files=['whisper_runner.py','requirements-installer-lock.txt','tests/test_installer_dependency_lock.py',
 'installer/staging/python/Lib/site-packages/whisperx/asr.py',
 'installer/staging/python/Lib/site-packages/whisperx/vads/pyannote.py',
 'installer/staging/python/Lib/site-packages/whisperx/vads/silero.py',
 'installer/staging/python/Lib/site-packages/whisperx/alignment.py',
 'installer/staging/python/Lib/site-packages/pyannote/audio/core/model.py',
 'installer/staging/python/Lib/site-packages/pyannote/audio/models/segmentation/PyanNet.py',
 'installer/staging/python/Lib/site-packages/nltk/data.py',
 'installer/staging/python/Lib/site-packages/torch/nn/modules/rnn.py',
 'installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py',
 'installer/staging/python/Lib/site-packages/lightning/fabric/utilities/cloud_io.py']
bindings=[]
for name in files:
    p=r/name;data=p.read_bytes();target=out/'inspected-source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    bindings.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(out/'source-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf8',newline='\n')
# Preserve the worker's exact documentary diff without applying it to frozen candidate source.
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\940c7fc1-f40\gemini')
name='docs/library/SECURITY-BACKPORT-FEASIBILITY-2026-09-12.md'
subprocess.run(['git','add','-N','--',name],cwd=w,check=True)
(out/'worker-original.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=w))
shutil.copyfile(w/name,out/'worker-report-original.md.txt')
print(json.dumps({'primary_metadata_payloads_verified':len(manifest['files']),'source_files_retained':len(bindings),'advisories':len(advisories),'executed_model_code':False}))
