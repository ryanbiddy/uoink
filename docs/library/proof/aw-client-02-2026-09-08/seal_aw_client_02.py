import datetime as dt, hashlib, json, re, shutil
from pathlib import Path
repo=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
root=repo/'_scratch/aw-client-02';archive=repo/'docs/library/proof/aw-client-02-2026-09-08'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
for rel,h in read(root/'client/supplement-input-seal.json').items():assert sha(root/rel)==h,rel
for rel,h in read(root/'client/recall-launch-seal.json').items():
 p=root/'recall'/rel if rel=='index.db' else root/'client'/rel
 assert sha(p)==h,rel
archive.mkdir(exist_ok=False)
summary=read(root/'receipt-summary-02.json')
for stream in summary['client_streams']:
 p=Path(stream['path']);assert sha(p)==stream['sha256']
 shutil.copyfile(p,archive/('client-stream-'+stream['session_id']+'.jsonl'))
debug=[]
for name in ['claude-debug.log','claude-recall-debug.log']:
 p=root/'client'/name;raw=p.read_text(encoding='utf-8');kept=[]
 for line in raw.splitlines():
  if any(x in line for x in ('MCP server "uoink"','Hook PreToolUse:','Hook PostToolUse:',
   'Hook PostToolUseFailure:','Hook UserPromptSubmit:','[Stall] tool_dispatch_',
   'send set_model model=','permission update:','Replacing all deny rules')):
   if not re.search(r'sk-ant-|Bearer\s|accessToken|refreshToken|authorization',line,re.I):kept.append(line)
 target=archive/(name.replace('.log','-selected.log'))
 target.write_text('\n'.join(kept)+'\n',encoding='utf-8',newline='\n')
 debug.append({'raw_private_path':str(p),'raw_sha256':sha(p),'selection':target.name,'kind':'Selected noncredential lines; raw file retained privately'})
files=[p for p in root.iterdir() if p.is_file() and p.suffix in ('.json','.md','.py','.cjs')]
files += [p for p in (root/'client').rglob('*') if p.is_file() and p.name not in ('claude-debug.log','claude-recall-debug.log')]
files += list((root/'records').glob('*/events.jsonl'))
files += [p for p in (root/'browser-source-01').rglob('*') if p.is_file()]
files += [p for p in (root/'m').rglob('*') if p.is_file() and p.suffix in ('.md','.json')]
files += [p for p in (root/'synthetic-items').rglob('*') if p.is_file()]
files += [root/'recall/corpus.md',root/'guard/sitecustomize.py']
for p in sorted(set(files)):
 target=archive/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
for name in ['inspect_aw_client_02.py','seal_aw_client_02.py']:shutil.copyfile(repo/'_scratch'/name,archive/name)
save(archive/'archive-details.json',{'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'frozen_input_seals_verified':True,'debug':debug,
 'database_archived':False,'credentials_archived':False,'x_error_screenshot_observation':'Visually inspected: Access to x.com was denied, HTTP ERROR 403; no successful destination page',
 'brief_setup_limit':'Synthetic publisher input, not client-authored publication; initial cold standalone setup deadline_exceeded retained with repair note'})
for p in archive.rglob('*'):
 if p.is_file() and p.suffix in ('.json','.jsonl','.log','.md','.py','.cjs','.txt'):
  text=p.read_text(encoding='utf-8-sig')
  assert not re.search(r'sk-ant-[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9_-]{20,}|"(?:accessToken|refreshToken)"\s*:',text),str(p)
manifest={str(p.relative_to(archive)).replace('\\','/'):sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
save(archive/'SHA256.json',manifest)
print(json.dumps({'archive':str(archive),'files':len(manifest),'bytes':sum(p.stat().st_size for p in archive.rglob('*') if p.is_file()),'frozen_inputs_verified':True,'credentials_absent':True}))
