"""Review installed publication, delayed protocol and actual client bytes."""
from pathlib import Path
import base64,collections,datetime as dt,hashlib,json,sys
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07')
base=root/'p6-published01';profile=base/'profile'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sys.path.insert(0,str(repo/'scripts/install_receipt'))
from p4_inspect_evidence import tool_envelope
from p4_common import PROTECTED_SENTINEL_BYTES
stages={stage:read(base/(stage+'01')/'outer.json') for stage in ('prepare','protocol','client')}
for stage,record in stages.items():
    assert record['status']=='completed_pending_independent_review'
    assert record['exit']==0 and record['cleanup']['cleaned'] and record['guard_restore']['ok']
    assert record['pth_before']==record['pth_after'] and record['guard_absent_after'] and record['bindings_after_ok']
    if stage!='prepare':assert record['payloads_before']==record['payloads_after']
expected=read(profile/'expected.json')['export']
protocol=read(profile/'protocol01.json')
assert protocol['delay_after_resources_s']>2 and protocol['exact_expected_export'] and protocol['cleanup']['cleaned']
assert tool_envelope(protocol['reply']['result'])==expected
records=[]
for path in (profile/'records/stdio').glob('*/events.jsonl'):
    lines=[json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
    if stages['client']['started_utc']<=lines[0]['utc']<=stages['client']['finished_utc']:records.append((path,lines))
assert len(records)==1,[str(p) for p,_ in records]
path,lines=records[0];requests={};replies={}
for row in lines:
    if row['kind']!='frame' or row['direction']=='server_stderr':continue
    data=base64.b64decode(row['base64'])
    assert hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']
    value=json.loads(data)
    if row['direction']=='client_to_server' and 'method' in value:requests[value.get('id')]=(value,row)
    elif row['direction']=='server_to_client' and 'id' in value:replies[value['id']]=(value,row)
calls=[(key,request,frame) for key,(request,frame) in requests.items() if request['method']=='tools/call']
assert [request['params']['name'] for _,request,_ in calls]==['get_library_item','export_cited_range']
first_id,_,_=calls[0];export_id,request,frame=calls[1]
assert request['params']['arguments']=={'video_id':'p6fx-range-01','start':34,'end':46}
export_reply=replies[export_id][0]
assert not export_reply['result'].get('isError') and tool_envelope(export_reply['result'])==expected
delay=(frame['monotonic_ns']-replies[first_id][1]['monotonic_ns'])/1e9
assert expected['citation']['verbatim_text']=='SYNTHETIC FIXTURE: the stored navigation value is AMBER. Not a source quotation.'
assert len(expected['chapters'])==1 and expected['chapters'][0]['start']==34
assert expected['attribution']['labels']==[] and expected['attribution']['diarization_ran'] is False
assert expected['citation']['seek_link'] is None and expected['citation']['player_seek_seconds'] is None
events=[json.loads(x) for x in (base/'client01/stdout').read_text(encoding='utf8').splitlines() if x.strip()]
final=next(x for x in reversed(events) if x.get('type')=='result')
assert final['is_error'] is False
hooks=[];sentinel=[]
for p in (profile/'client/action-records').glob('*.json'):
    row=read(p)
    if row['kind']=='client_hook':hooks.append(row)
    if row['kind']=='sentinel_request':sentinel.append(row)
before=[x for x in hooks if x['input'].get('hook_event_name')=='PreToolUse']
after=[x for x in hooks if x['input'].get('hook_event_name') in ('PostToolUse','PostToolUseFailure')]
assert len(before)==len(after)==2
assert collections.Counter(x['input'].get('tool_use_id') for x in before)==collections.Counter(x['input'].get('tool_use_id') for x in after)
assert not any(x.get('request',{}).get('method')=='tools/call' for x in sentinel)
assert (profile/'client/protected-sentinel.bin').read_bytes()==PROTECTED_SENTINEL_BYTES
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':stages['client']['build_source'],
        'package_sha256':stages['client']['package_sha256'],'status':'passed_bounded_installed_publication_and_export',
        'protocol_delay_seconds':protocol['delay_after_resources_s'],'protocol_exact_export':True,
        'client_delay_after_item_reply_seconds':delay,'client_exact_export':True,'client_export_calls':1,
        'client_wire':str(path.relative_to(root)),'actual_tool_calls':2,'hook_events':dict(collections.Counter(x['input']['hook_event_name'] for x in hooks)),
        'sentinel_requests':len(sentinel),'sentinel_calls':0,'protected_bytes_unchanged':True,
        'read_payloads_unchanged':True,'stages_exactly_restored':True,'synthetic_hook_preflight_calls':3,
        'expected_export':expected,'final_client_response':final['result'],
        'gui_or_player_credit':False,'release_ready':False}
with (root/'published07-independent-review.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('expected_export','final_client_response')},indent=2))
