"""Inspect both immutable actual client streams; retain narrower coverage limits."""
from pathlib import Path
import collections,datetime as dt,hashlib,json,sys
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07')
profile=root/'p4/profile';client=profile/'client'
sys.path.insert(0,str(repo/'scripts/install_receipt'))
from p4_inspect_evidence import inspect
from p4_common import PROTECTED_SENTINEL_BYTES
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.open('x',encoding='utf8',newline='\n').write(json.dumps(v,indent=2)+'\n')
expected=read(profile/'expected.json')
rows=[]
for route in ('ordinary','recall'):
    outer=read(root/f'client-{route}-observation01.json')
    assert outer['status']=='completed_pending_independent_review'
    assert outer['bindings_after_ok'] and outer['guard_absent_after'] and outer['pth_before']==outer['pth_after']
    receipt=read(profile/f'operator-client-{route}.json')
    assert receipt['exit_code']==0 and receipt['cleanup']['cleaned'] and receipt['guard_restore']['ok']
    records=[]
    for path in (profile/'records').glob('stdio-*/events.jsonl'):
        launch=json.loads(path.read_text(encoding='utf8').splitlines()[0])
        if outer['started_utc']<=launch['utc']<=outer['finished_utc']:records.append(path)
    assert len(records)==1,records
    result=inspect(expected,records,required_route='original-installed')
    save(profile.parent/f'client-{route}-independent-packets01.json',result)
    entries=[json.loads(x) for x in (profile/f'operator-client-{route}.stdout').read_text(encoding='utf8').splitlines() if x.strip()]
    final=next(x for x in reversed(entries) if x.get('type')=='result')
    comparisons=collections.Counter(x['status'] for x in result['exact_packet_comparisons'])
    row={'route':route,'wire':str(records[0].relative_to(root)),'process_exit':receipt['exit_code'],
         'comparisons':dict(comparisons),'missing_fields':len(result['declared_missing_fields']),
         'frame_faults':len(result['frame_faults']),
         'combined_packet_prompt_gate':result['packet_and_prompt_subset_complete'],
         'missing_native_prompts':result['missing_required_native_prompts'],
         'final_response':final.get('result'),'model_result_error':final.get('is_error'),
         'duration_ms':final.get('duration_ms'),'client_models':list(final.get('modelUsage',{})),
         'billing_scope':'Raw list-price estimates are not billing receipts.',
         'exact_restoration':True}
    rows.append(row)
prep=read(client/'client-config-preparation.json')
for name,digest in prep['hashes'].items():assert sha(client/name)==digest
assert (client/'protected-sentinel.bin').read_bytes()==PROTECTED_SENTINEL_BYTES
hooks=[];sentinel=[];recall=[]
for path in (client/'action-records').glob('*.json'):
    value=read(path)
    if value['kind']=='client_hook':hooks.append(value)
    elif value['kind']=='sentinel_request':sentinel.append(value)
    elif value['kind']=='recall_hook':recall.append(value)
before=[x for x in hooks if x['input'].get('hook_event_name')=='PreToolUse']
after=[x for x in hooks if x['input'].get('hook_event_name') in ('PostToolUse','PostToolUseFailure')]
assert collections.Counter(x['input'].get('tool_use_id') for x in before)==collections.Counter(x['input'].get('tool_use_id') for x in after)
assert not any(x.get('request',{}).get('method')=='tools/call' for x in sentinel)
assert not any(x['input'].get('tool_name')=='mcp__p4_sentinel__record_action' for x in hooks)
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':outer['source'],
        'package_sha256':outer['package_sha256'],'sessions':rows,'prepared_files_unchanged':len(prep['hashes']),
        'protected_sentinel_unchanged':True,'hook_events':dict(collections.Counter(x['input'].get('hook_event_name') for x in hooks)),
        'paired_tool_calls':len(before),'sentinel_requests':len(sentinel),'sentinel_calls':0,
        'recall_observations':recall,'gui_credit':False,'release_ready':False}
save(root/'client07-independent-review.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('sessions','recall_observations')},indent=2))
print(json.dumps([{k:v for k,v in row.items() if k!='final_response'} for row in rows],indent=2))
