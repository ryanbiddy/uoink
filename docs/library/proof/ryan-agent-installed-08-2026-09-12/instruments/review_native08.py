"""Review native prompt exchanges and complete client action accounting."""
from pathlib import Path
import base64,collections,datetime as dt,hashlib,json,sys
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08');profile=root/'p4/profile';client=profile/'client'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(repo/'scripts/install_receipt'))
from p4_common import PROTECTED_SENTINEL_BYTES
rows=[]
for label,name in [('native-reshelve01','reshelve-review'),('native-consult01','consult-library')]:
    outer=read(root/(label+'-observation.json'))
    assert outer['status']=='completed_pending_independent_review' and outer['driver_exit']==0
    assert outer['guard_absent_after'] and outer['bindings_after_ok'] and outer['pth_before']==outer['pth_after']
    receipt=read(profile/('operator-client-ordinary-'+label+'.json'))
    assert receipt['exit_code']==0 and receipt['cleanup']['cleaned'] and receipt['guard_restore']['ok']
    records=[]
    for path in (profile/'records').glob('stdio-*/events.jsonl'):
        values=[json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
        if outer['started_utc']<=values[0]['utc']<=outer['finished_utc']:records.append((path,values))
    assert len(records)==1
    path,values=records[0];requests={};replies={}
    for frame in values:
        if frame['kind']!='frame' or frame['direction']=='server_stderr':continue
        data=base64.b64decode(frame['base64']);assert hashlib.sha256(data).hexdigest()==frame['sha256'] and len(data)==frame['bytes']
        value=json.loads(data)
        if frame['direction']=='client_to_server' and 'method' in value:requests[value.get('id')]=value
        elif frame['direction']=='server_to_client' and 'id' in value:replies[value['id']]=value
    prompts=[(key,request) for key,request in requests.items() if request['method']=='prompts/get']
    assert len(prompts)==1 and prompts[0][1]['params']['name']==name
    reply=replies[prompts[0][0]];assert 'error' not in reply and reply.get('result',{}).get('messages')
    if name=='reshelve-review':
        text='\n'.join(m['content'].get('text','') for m in reply['result']['messages'])
        assert 'resource_not_found' not in text and 'preview_expired' not in text
        assert read(profile/'prompt-preparation.json')['preview']['preview_id'] in text
    assert not any(req['method']=='tools/call' for req in requests.values())
    entries=[json.loads(x) for x in (profile/('operator-client-ordinary-'+label+'.stdout')).read_text(encoding='utf8').splitlines() if x.strip()]
    final=next(x for x in reversed(entries) if x.get('type')=='result');assert final['is_error'] is False
    rows.append({'name':name,'status':'passed_native_prompt_observation','wire':str(path.relative_to(root)),
                 'request':prompts[0][1]['params'],'reply':reply,'tool_calls':0,'final_response':final['result']})
prep=read(client/'client-config-preparation.json')
for name,digest in prep['hashes'].items():assert sha(client/name)==digest
assert (client/'protected-sentinel.bin').read_bytes()==PROTECTED_SENTINEL_BYTES
events=[read(p) for p in (client/'action-records').glob('*.json')]
hooks=[x for x in events if x['kind']=='client_hook'];sentinel=[x for x in events if x['kind']=='sentinel_request']
before=[x for x in hooks if x['input'].get('hook_event_name')=='PreToolUse']
after=[x for x in hooks if x['input'].get('hook_event_name') in ('PostToolUse','PostToolUseFailure')]
assert collections.Counter(x['input'].get('tool_use_id') for x in before)==collections.Counter(x['input'].get('tool_use_id') for x in after)
assert not any(x.get('request',{}).get('method')=='tools/call' for x in sentinel)
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'sessions':rows,'total_p4_tool_calls':len(before),
        'hook_events':dict(collections.Counter(x['input']['hook_event_name'] for x in hooks)),
        'sentinel_requests':len(sentinel),'sentinel_calls':0,'prepared_files_unchanged':len(prep['hashes']),
        'protected_sentinel_unchanged':True,'combined_session_gate':False,'gui_credit':False}
with (root/'native08-independent-review.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='sessions'},indent=2))
print(json.dumps([{'name':row['name'],'status':row['status'],'tool_calls':row['tool_calls']} for row in rows]))
