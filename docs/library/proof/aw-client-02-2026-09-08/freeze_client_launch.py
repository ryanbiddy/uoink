import copy, datetime as dt, hashlib, importlib.util, json, os, sys
from pathlib import Path
root=Path(__file__).resolve().parent;repo=root.parent.parent;client=root/'client'
env=json.loads((root/'mcp.json').read_text(encoding='utf-8'))['mcpServers']['uoink']['env']
os.environ.pop('ANTHROPIC_API_KEY',None);os.environ.update(env);sys.path[:0]=env['PYTHONPATH'].split(os.pathsep)
g=root/'guard/sitecustomize.py';exec(compile(g.read_text(),str(g),'exec'),{})
def module(name,file):
 spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,j):
 with p.open('x',encoding='utf-8') as f:json.dump(j,f,ensure_ascii=False,indent=2);f.write('\n')
import index
prep=module('aw_expected',repo/'docs/library/proof/aw-rerun-2026-09-08/prepare_fixture.py')
state=module('aw_state',repo/'docs/library/proof/aw-rerun-2026-09-08/prepare_prompt_session.py')
idx=index.Index.open(root/'profile/Uoink/index.db')
try:
 hostile=prep.expected_item(idx,'aw02-hostile-orbit')
 before=state.state(idx,root/'profile/Uoink/settings.json')
finally:idx.close()
save(root/'hostile-expected.json',hostile)
file_roots=[root/'profile/Uoink/reach/briefs',root/'synthetic-items',root/'recall',root/'prompt-store']
files={str(p.relative_to(root)):sha(p) for top in file_roots for p in sorted(top.rglob('*')) if p.is_file()}
files['client/protected-sentinel.txt']=sha(client/'protected-sentinel.txt')
save(root/'state-before-client-supplement.json',{'semantic':before,'files':files,'created_at':dt.datetime.now(dt.timezone.utc).isoformat()})
j=json.loads((client/'launch.json').read_text(encoding='utf-8'));profile=json.loads((client/'isolated-profile-preparation.json').read_text(encoding='utf-8'))
j['environment']['CLAUDE_CONFIG_DIR']=profile['profile']
j['args']+=['--model','haiku']+j['interactive_extra_args']
j['executable']=profile['executable'];j['actual_launch_frozen_at']=dt.datetime.now(dt.timezone.utc).isoformat()
j['original_launch_sha256']=sha(client/'launch.json');j['profile_preparation_sha256']=sha(client/'isolated-profile-preparation.json')
save(client/'launch-isolated.json',j)
save(client/'supplement-input-seal.json',{str(p.relative_to(root)):sha(p) for p in [client/'launch-isolated.json',root/'adversarial-input-preparation.json',root/'hostile-expected.json',root/'hostile-brief-preparation.json',root/'state-before-client-supplement.json']})
print(json.dumps({'session_id':j['session_id'],'profile':profile['profile'],'hostile_card_uri':hostile['card_uri'],'launch_sha256':sha(client/'launch-isolated.json')}))
