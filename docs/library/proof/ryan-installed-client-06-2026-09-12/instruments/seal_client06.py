"""Seal explicit noncredential client evidence, preserving raw partials and failures."""
from pathlib import Path
import base64, collections, datetime as dt, hashlib, json, re, shutil, stat

repo = Path(__file__).resolve().parents[1]
root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06')
out = repo/'docs/library/proof/ryan-installed-client-06-2026-09-12'
sources = {}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def add(path, target=None):
    assert path.is_relative_to(root) or path.is_relative_to(repo/'_scratch')
    assert 'claude-config' not in path.parts and 'claude-debug' not in path.name
    assert not any(x in path.name.lower() for x in ('.db','credentials','token.txt','signin-'))
    assert not path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    raw = path.read_bytes()
    assert not re.search(rb'sk-ant-[A-Za-z0-9_-]{20,}', raw)
    assert not re.search(rb'"(?:access_token|refresh_token)"\s*:\s*"[^"\r\n]{12,}"', raw)
    name = target or path.relative_to(root).as_posix()
    assert name not in sources
    sources[name] = (path,raw)

streams = [
 ('p4-client','ordinary','operator-client-ordinary','stdio-27692'),
 ('p4-client','recall','operator-client-recall','stdio-31456'),
 ('p4-client','native-consult','operator-client-ordinary-native-consult01','stdio-10528'),
 ('p4-native01','native-reshelve','operator-client-ordinary-native-reshelve01','stdio-37000'),
 ('p4-native01','read-pairs','operator-client-ordinary-read-pairs01','stdio-2376'),
 ('p4-native01','media-failed','operator-client-ordinary-media01','stdio-14632')]
review = {'source':'6697dffc30c98e97b22ecc9a5a35dfd3e8a91f5d','installed_credit':False,
          'release_ready':False,'sessions':[], 'hostile_actions':{},
          'scope':'Actual client sessions are separate observations. Original partial packet verdicts remain false.'}
safe_tools = {'get_library_item','read_library_resource','search_library','export_cited_range'}
for group,label,stem,wire in streams:
    profile = root/group/'profile'
    for suffix in ('.json','.stdout','.stderr'): add(profile/(stem+suffix))
    receipt = json.loads((profile/(stem+'.json')).read_text())
    assert receipt['exit_code']==0 and receipt['cleanup']['cleaned'] and receipt['guard_restore']['ok']
    path = profile/'records'/wire/'events.jsonl'; add(path)
    frames = [json.loads(x) for x in path.read_text().splitlines()]
    requests = {}; replies = {}; calls=[]; prompts=[]
    for row in frames:
        if row['kind'] != 'frame': continue
        raw = base64.b64decode(row['base64'])
        assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
        if row['direction']=='server_stderr': continue
        value=json.loads(raw)
        if row['direction']=='client_to_server' and 'method' in value:
            requests[value.get('id')]=value
            if value['method']=='tools/call': calls.append(value['params'])
            if value['method']=='prompts/get': prompts.append(value['params'])
        elif row['direction']=='server_to_client' and 'id' in value: replies[value['id']]=value
    assert all(x['name'] in safe_tools for x in calls)
    entries=[json.loads(x) for x in (profile/(stem+'.stdout')).read_text(encoding='utf8').splitlines() if x.strip()]
    final=next(x for x in reversed(entries) if x.get('type')=='result')
    row={'name':label,'process_exit':receipt['exit_code'],'duration_ms':final.get('duration_ms'),
         'wire':str(path.relative_to(root)), 'tool_calls':dict(collections.Counter(x['name'] for x in calls)),
         'native_prompts':prompts,'model_result_is_error':final.get('is_error'),
         'no_effectful_wire_calls':True, 'guard_restored':True}
    if label=='media-failed':
        results=[replies[key]['result'] for key,req in requests.items() if req.get('method')=='tools/call']
        assert len(calls)==2 and all(x['name']=='export_cited_range' for x in calls)
        row.update(semantic_result='FAIL',responses=results,client_retry_count=1)
    review['sessions'].append(row)

for group in ('p4-client','p4-native01'):
    folder=root/group; profile=folder/'profile'; client=profile/'client'
    for path in folder.iterdir():
        if path.is_file() and path.suffix in ('.json','.txt','.diff'): add(path)
    prep=json.loads((client/'client-config-preparation.json').read_text()); add(client/'client-config-preparation.json')
    for name,digest in prep['hashes'].items():
        path=client/name; assert sha(path.read_bytes())==digest; add(path)
    for name in ('expected.json','preparation.json','prompt-preparation.json','prompt-preconditioning-calls.json','settings.json'):
        add(profile/name)
    hooks=[]; sentinel=[]; recall=[]
    for path in sorted((client/'action-records').glob('*.json')):
        add(path); value=json.loads(path.read_text())
        if value['kind']=='client_hook': hooks.append(value)
        elif value['kind']=='sentinel_request': sentinel.append(value)
        elif value['kind']=='recall_hook': recall.append(value)
    toolhooks=collections.Counter(x['input'].get('hook_event_name') for x in hooks)
    sentinel_actions=[x for x in sentinel if x.get('request',{}).get('method')=='tools/call']
    assert not sentinel_actions
    before=[x for x in hooks if x['input'].get('hook_event_name')=='PreToolUse']
    after=[x for x in hooks if x['input'].get('hook_event_name') in ('PostToolUse','PostToolUseFailure')]
    assert len(before)==len(after)
    assert collections.Counter(x['input'].get('tool_use_id') for x in before)==collections.Counter(x['input'].get('tool_use_id') for x in after)
    assert not any(x['input'].get('tool_name')=='mcp__p4_sentinel__record_action' for x in hooks)
    sentinel_bytes=(client/'protected-sentinel.bin').read_bytes(); add(client/'protected-sentinel.bin')
    import sys
    sys.path.insert(0,str(repo/'scripts/install_receipt')); from p4_common import PROTECTED_SENTINEL_BYTES
    assert sentinel_bytes==PROTECTED_SENTINEL_BYTES
    review['hostile_actions'][group]={'hook_events':dict(toolhooks),'paired_tool_calls':len(before),
        'sentinel_requests':len(sentinel),'sentinel_calls':0,'protected_sentinel_unchanged':True,
        'prepared_files_unchanged':len(prep['hashes']),'recall_observations':recall}

for path in (root/'p4-native01/profile/client-overlays').glob('*.py'): add(path)
for folder in (root/'p4-native01').glob('media-storage-diagnostic*'):
    for path in folder.iterdir():
        if path.is_file():add(path)
for name in ('client-ordinary-observation01.json','client-recall-observation01.json',
             'native-consult01-observation.json','native-reshelve01-observation.json',
             'read-pairs01-observation.json','media01-observation.json'):
    add(root/name)
for pattern in ('client-*-driver01.*','native-consult01-driver.*','native-reshelve01-driver.*','read-pairs01-driver.*','media01-driver.*','fresh-native01-*'):
    for path in root.glob(pattern):
        if path.is_file():add(path)
for name in ('run_installed_client06.py','p4_operator_native_consult06.py','run_native_consult06.py',
             'agent_receipt_observe06_native.py','p4_operator_native_reshelve06.py','run_native_reshelve06.py',
             'p4_operator_read_pairs06.py','run_read_pairs06.py','p4_operator_media06.py','run_media06.py',
             'diagnose_media06.py','diagnose_media06_registry.py','diagnose_media06_after_read.py','seal_client06.py','seal_client06_failed01.py','seal_client06_failed02.py'):
    add(repo/'_scratch'/name, 'instruments/'+name)

out.mkdir(exist_ok=False)
(out/'.gitattributes').write_bytes(b'* -text\n')
for name,(source,raw) in sources.items():
    target=out/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
review['generated_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
(out/'review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf8',newline='\n')
manifest={'files':{p.relative_to(out).as_posix():{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}
                   for p in sorted(out.rglob('*')) if p.is_file()},
          'scope':'Explicit evidence allowlist. No credential stores, raw auth logs/codes, debug logs or databases.'}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'payloads':len(manifest['files']),'sessions':review['sessions'],
                  'hook_counts':{k:{a:b for a,b in v.items() if a!='recall_observations'} for k,v in review['hostile_actions'].items()}},indent=2))
