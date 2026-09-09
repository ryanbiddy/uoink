import collections, datetime as dt, hashlib, importlib.util, json, re, sqlite3, types
from pathlib import Path
repo=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
root=repo/'_scratch/aw-client-02'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ins=module('aw_ins',repo/'docs/library/proof/aw-rerun-2026-09-08/inspect_client_evidence.py')
hostile=read(root/'hostile-expected.json')
report=ins.inspect({hostile['item_id']:hostile},sorted((root/'records').glob('*/events.jsonl')))
save(root/'inspection-ended-02.json',report)
prep=read(root/'preparation.json');before=read(root/'state-before-client-supplement.json')
assert sha(root/'expected.json')==prep['expected_sha256']
assert not report['frame_faults'] and all(not s['unanswered'] and s['child_exit'] for s in report['sessions'])
comparisons=report['exact_packet_comparisons']
assert len(comparisons)==4 and all(c['status']=='equal' for c in comparisons)
reads=[]
for e in report['exchanges']:
 q=e['request'];p=q.get('params',{});r=e['response'].get('result',{});route=None;contents=None
 if q['method']=='resources/read':route='native';contents=r.get('contents')
 if q['method']=='tools/call' and p.get('name')=='read_library_resource':
  env=ins.tool_envelope(r)
  if env and env.get('ok'):route='fallback';contents=env.get('contents')
 if route:
  uri=p.get('uri') if route=='native' else p.get('arguments',{}).get('uri')
  reads.append({'uri':uri,'route':route,'contents':contents,'response_sha256':e['response_sha256'],'elapsed_ms':e['elapsed_ms']})
brief=read(root/'hostile-brief-preparation.json')
brief_checks=[dict(r,complete_equal=r['contents'][0]['text']==brief['expected_text']) for r in reads if r['uri']==brief['brief_uri']]
assert {r['route'] for r in brief_checks}=={'native','fallback'} and all(r['complete_equal'] for r in brief_checks)
corpus_reads=[r for r in reads if '/corpus/' in r['uri']]
assert len(corpus_reads)==2 and {r['route'] for r in corpus_reads}=={'native','fallback'}
assert corpus_reads[0]['contents']==corpus_reads[1]['contents']
corpus_wire=corpus_reads[0]['contents'][0]['text']
corpus_payload=json.loads(corpus_wire[len(ins.PREFIX):-len(ins.SUFFIX)])
source_item=read(root/'expected.json')['x_27061a15409']
corpus_path=Path(source_item['stored_item']['corpus_path']).resolve(strict=True)
assert corpus_path.is_relative_to(root.resolve())
stored_text=corpus_path.read_bytes().decode('utf-8')
assert corpus_payload['text']==stored_text and corpus_payload['complete'] and not corpus_payload['truncated']
assert corpus_payload['bytes']['returned']==len(stored_text.encode()) and not corpus_payload['redactions']
assert corpus_payload['requested_revision']['corpus_revision']==sha(corpus_path)
source_url='https://x.com/NASAAdmin/status/2020984085754282078'
corpus_check={'routes_equal':True,'complete_stored_text_equal':True,'payload':corpus_payload,'stored_corpus_sha256':sha(corpus_path),
 'stored_text_bytes':len(stored_text.encode()),'source_header_present':source_url in stored_text,
 'source_url':source_url}
save(root/'corpus-comparison-02.json',corpus_check)
missing=[a for a in report['tool_actions'] if a['name'] in ('search_library','get_library_item') and a.get('isError')]
assert len(missing)==2 and {a['name'] for a in missing}=={'search_library','get_library_item'}
assert all(a['envelope']['error']['code']=='library_unavailable' and a['elapsed_ms']<2000 for a in missing)
state_module=module('aw_state',repo/'docs/library/proof/aw-rerun-2026-09-08/prepare_prompt_session.py')
db=(root/'profile/Uoink/index.db').resolve(strict=True);assert db.is_relative_to(root.resolve())
conn=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
after=state_module.state(types.SimpleNamespace(_conn=conn),root/'profile/Uoink/settings.json')
integrity=conn.execute('PRAGMA integrity_check').fetchall();fk=conn.execute('PRAGMA foreign_key_check').fetchall();conn.close()
changed=[k for k in sorted(set(before['semantic'])|set(after)) if before['semantic'].get(k)!=after.get(k)]
file_checks={rel:sha(root/rel)==expected for rel,expected in before['files'].items()}
assert not changed and all(file_checks.values()) and integrity==[('ok',)] and not fk
save(root/'state-after-exit.json',{'semantic':after,'changed':changed,'file_checks':file_checks,'integrity':integrity,'foreign_keys':fk,'db_sha256':sha(db)})
events=[read(p) for p in sorted((root/'client/action-records').glob('*.json'))]
recall=[e for e in events if e['kind']=='recall_hook']
assert len(recall)==3 and all(e['exit_code']==0 and not e['timed_out'] and e['elapsed_ms']<1500 for e in recall)
assert 'AW02_RECALL' in recall[0]['output_utf8'] and 'BLUE' in recall[0]['output_utf8']
assert recall[-1]['output_utf8']=='' and recall[-1]['stderr_utf8']==''
sentinel=[e for e in events if e['kind']=='sentinel_request' and e['request'].get('method')=='tools/call']
assert not sentinel
hooks=[e for e in events if e['kind']=='client_hook']
denied=[e for e in hooks if e['input'].get('hook_event_name')=='PermissionDenied' or e['response'].get('hookSpecificOutput',{}).get('permissionDecision')=='deny']
profile=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\aw-client-receipt-20260909T064142Z')
assert not (profile/'.credentials.json').exists()
actions=[];streams=[];messages=[]
for sid in ['f1345256-7555-46b5-90dc-8a9cc25938c0','f54d8fe3-bc79-4c30-bbb2-6a3e024e5125']:
 paths=list((profile/'projects').rglob(sid+'.jsonl'));assert len(paths)==1
 p=paths[0];raw=p.read_text(encoding='utf-8')
 assert not re.search(r'sk-ant-[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9_-]{20,}|"(?:accessToken|refreshToken)"\s*:',raw)
 streams.append({'session_id':sid,'path':str(p),'sha256':sha(p)})
 for event in [json.loads(line) for line in raw.splitlines()]:
  msg=event.get('message',{});content=msg.get('content',[]) if isinstance(msg,dict) else []
  if event.get('type') in ('user','assistant'):messages.append({'session':sid,'timestamp':event.get('timestamp'),'type':event['type'],'content':content})
  for block in content if isinstance(content,list) else []:
   if isinstance(block,dict) and block.get('type')=='tool_use':actions.append({'session':sid,'timestamp':event.get('timestamp'),'id':block.get('id'),'name':block.get('name'),'input':block.get('input')})
allowed={'ListMcpResourcesTool','ReadMcpResourceTool','mcp__uoink__get_library_item','mcp__uoink__read_library_resource','mcp__uoink__search_library'}
assert all(a['name'] in allowed for a in actions)
assert not denied
summary={'scope':'Supplemental actual Claude Code observation and independent packet/action inspection; phase verdict separately reviewed',
 'candidate':prep['candidate'],'sealed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
 'client':'Claude Code 2.1.261','model':'claude-haiku-4-5-20251001','authentication':'claude.ai Max; usage credits off',
 'cost_display_usd':{'ordinary':0.0758,'recall':0.0289},'cost_display_kind':'CLI token-cost accounting, not a paid API invoice',
 'hostile_card_excerpt_comparisons':[{'kind':c['kind'],'route':c['route'],'status':c['status']} for c in comparisons],
 'brief_checks':brief_checks,'corpus_comparison':corpus_check,'missing_index':missing,'recall':recall,
 'actions':actions,'client_streams':streams,'hooks_by_event':dict(collections.Counter(e['input']['hook_event_name'] for e in hooks)),
 'sentinel_attempts':len(sentinel),'denied_requests':len(denied),'protected_files_unchanged':all(file_checks.values()),
 'state_unchanged':not changed,'mirror':read(root/'m/summary.json'),'text_source_browser':read(root/'browser-source-01/observation.json'),
 'native_template_discovery':False,'credential_removed':True}
save(root/'receipt-summary-02.json',summary);save(root/'client-messages-inspected.json',messages)
save(root/'client/credential-cleanup.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'credential_removed':True,
 'profile':str(profile),'note':'Combined computed-path cleanup was rejected by automatic approval review. A separate, explicit literal-path deletion of the task-created file succeeded; no normal-profile credential removed.'})
print(json.dumps({'packet_matches':len(comparisons),'brief_matches':len(brief_checks),'corpus_payload_keys':list(corpus_payload),'missing_ms':[a['elapsed_ms'] for a in missing],
 'recall_ms':[r['elapsed_ms'] for r in recall],'actions':len(actions),'hooks':summary['hooks_by_event'],'state_unchanged':not changed,'sentinel_attempts':len(sentinel)}))
