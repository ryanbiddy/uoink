import base64, hashlib, importlib.util, json
from pathlib import Path

P=Path(__file__).resolve().parents[1]/'docs/library/proof/aw-rerun-2026-09-08/inspect_client_evidence.py'
spec=importlib.util.spec_from_file_location('inspect_aw',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def frame(direction, message, tick):
    raw=(json.dumps(message)+'\n').encode()
    return {'kind':'frame','direction':direction,'received_ns':tick,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}

def fixture(tmp_path):
    expected={'a':{'card_uri':'uoink://card/a','card_text':'Full card: first and LAST boundary.', 'excerpt_uri':'uoink://excerpt/a','excerpt_text':'Complete quote at 34 seconds.'}}
    rows=[];i=0
    def exchange(method,params,result):
        nonlocal i
        i+=1
        rows.extend([frame('client_to_server',{'jsonrpc':'2.0','id':i,'method':method,'params':params},i*1000),frame('server_to_client',{'jsonrpc':'2.0','id':i,'result':result},i*1000+500)])
    for kind in ['card','excerpt']:
        uri=expected['a'][kind+'_uri'];text=expected['a'][kind+'_text']
        exchange('resources/read',{'uri':uri},{'contents':[{'uri':uri,'text':text,'mimeType':'text/plain'}]})
        env={'ok':True,'contents':[{'uri':uri,'text':text,'mimeType':'text/plain'}]}
        exchange('tools/call',{'name':'read_library_resource','arguments':{'uri':uri}},{'isError':False,'content':[{'type':'text','text':m.PREFIX+json.dumps(env)+m.SUFFIX}]})
    for name in ['consult-library','reshelve-review']:
        exchange('prompts/get',{'name':name},{'messages':[{'role':'user','content':{'type':'text','text':'Actual prompt content'}}]})
    p=tmp_path/'events.jsonl'
    def save(): p.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    save();return expected,rows,p,save

def test_exact_complete_packets_and_native_prompts(tmp_path):
    e,r,p,save=fixture(tmp_path)
    report=m.inspect(e,[p])
    assert report['packet_and_prompt_subset_complete']
    assert len(report['exact_packet_comparisons'])==4
    assert len(report['native_prompts'])==2
    assert len(report['exchanges'])==6
    assert report['exchanges'][0]['elapsed_ms']==0.0005

def test_same_prefix_different_tail_is_mismatch(tmp_path):
    e,r,p,save=fixture(tmp_path)
    message=json.loads(base64.b64decode(r[1]['base64']))
    message['result']['contents'][0]['text']='Full card: first and CORRUPTED boundary.'
    r[1]=frame('server_to_client',message,1500);save()
    report=m.inspect(e,[p])
    assert not report['packet_and_prompt_subset_complete']
    assert report['exact_packet_comparisons'][0]['status']=='mismatch'

def test_missing_prompts_cannot_be_summary_claim(tmp_path):
    e,r,p,save=fixture(tmp_path);del r[-4:];save()
    report=m.inspect(e,[p])
    assert not report['packet_and_prompt_subset_complete']
    assert len(report['missing_required_native_prompts'])==2

def test_corrupt_frame_hash_cannot_count_as_evidence(tmp_path):
    e,r,p,save=fixture(tmp_path);r[1]['sha256']='0'*64;save()
    report=m.inspect(e,[p])
    assert not report['packet_and_prompt_subset_complete']
    assert len(report['frame_faults'])==1
    assert report['sessions'][0]['unanswered']
