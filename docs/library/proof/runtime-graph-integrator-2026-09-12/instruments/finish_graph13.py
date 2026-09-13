import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\6c96f0a3-c02\gemini')
before=worker / '_scratch/graph-pre-astra-probes'
before.mkdir(exist_ok=False)
for rel, original in [('scripts/check_runtime_graph.py',True),('tests/test_runtime_graph_boundaries.py',False)]:
    dst=before / rel
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile((worker / '_scratch/graph-pre-astra' if original else worker) / rel,dst)
command=[sys.executable,'-I','-S','-B',str(root / '_scratch/run_media_verify12.py'),
         '--root',str(before),'--label','original01','tests/test_runtime_graph_boundaries.py']
observed=subprocess.run(command,cwd=root)
print('Archived-checker negative cases exit:',observed.returncode,flush=True)
out=worker / 'docs/library/proof/runtime-graph-astra-review-2026-09-12'
assert (out / 'input-lock-02e06db.txt').is_file()
bootstrap='''import runpy,sys
sys.path.append(r'C:\\Users\\hello\\AppData\\Roaming\\Python\\Python314\\site-packages')
def guard(event,args):
    if event.startswith('socket.') or event=='subprocess.Popen': raise PermissionError('Offline metadata check')
sys.addaudithook(guard)
path=sys.argv.pop(1)
runpy.run_path(path,run_name='__main__')
'''
env=os.environ.copy()
for key in list(env):
    upper=key.upper()
    if any(s in upper for s in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL','OAUTH_TOKEN')) or upper.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_')): env.pop(key,None)
rows=[]
for name,selection in [('current',out / 'input-lock-02e06db.txt'),('proposal',worker / 'docs/library/proof/runtime-graph-review-2026-09-12/proposal_selection.json')]:
    target=out / (name+'.json')
    assert not target.exists()
    cmd=[sys.executable,'-I','-S','-B','-c',bootstrap,str(worker / 'scripts/check_runtime_graph.py'),
         '--selection',str(selection),'--evidence-dir',str(worker / 'docs/library/proof/runtime-graph-01-2026-09-12'),
         '--output-json',str(target)]
    result=subprocess.run(cmd,cwd=worker,env=env,capture_output=True)
    (out / (name+'.stdout')).write_bytes(result.stdout)
    (out / (name+'.stderr')).write_bytes(result.stderr)
    data=json.loads(target.read_text(encoding='utf8'))
    row={'name':name,'exit':result.returncode,'command':cmd,'passed':data['passed'],
         'edges':len(data['active_edges']),'wheel_failures':data['wheel_failures'],
         'conflicts':data['conflicting_constraints'],'missing':data['missing_packages'],
         'incomplete':data['incomplete_evidence'],'manifest_errors':data['manifest_errors']}
    rows.append(row)
    print(json.dumps({k:v for k,v in row.items() if k!='command'}),flush=True)
(out / 'execution.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
