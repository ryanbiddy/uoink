import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'docs/library/proof/aw-rerun-2026-09-08/observe_client_actions.py'

def run(tmp_path,mode,payload):
    (tmp_path/'client').mkdir(exist_ok=True)
    env=os.environ.copy();env.update(AW_FIXTURE_ROOT=str(tmp_path));env.pop('ANTHROPIC_API_KEY',None)
    r=subprocess.run([sys.executable,'-B',str(SCRIPT),mode,'--fixture-root',str(tmp_path)],input=payload,env=env,text=True,capture_output=True,timeout=8)
    assert r.returncode==0,r.stderr
    events=[json.loads(p.read_text()) for p in (tmp_path/'client/action-records').glob('*.json')]
    return r,events

@pytest.mark.parametrize('name,decision',[('mcp__uoink__get_library_item','allow'),('Bash','deny')])
def test_hook_records_actual_input_and_decision(tmp_path,name,decision):
    payload={'hook_event_name':'PreToolUse','tool_name':name,'tool_input':{'marker':'full request input'},'session_id':'synthetic'}
    r,events=run(tmp_path,'hook',json.dumps(payload))
    assert json.loads(r.stdout)['hookSpecificOutput']['permissionDecision']==decision
    assert events[0]['input']==payload and events[0]['response']==json.loads(r.stdout)

def test_sentinel_refuses_effect_and_keeps_protected_bytes(tmp_path):
    protected=tmp_path/'protected.bin';protected.write_bytes(b'UNTOUCHED SENTINEL')
    before=hashlib.sha256(protected.read_bytes()).hexdigest()
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'record_action','arguments':{'action':'file','marker':str(protected)}}}]
    r,events=run(tmp_path,'sentinel','\n'.join(json.dumps(x) for x in messages)+'\n')
    replies=[json.loads(x) for x in r.stdout.splitlines()]
    assert replies[2]['result']['isError'] is True
    assert len(events)==3 and any(e['request']==messages[2] for e in events)
    assert all(e['effects_executed']==[] for e in events)
    assert hashlib.sha256(protected.read_bytes()).hexdigest()==before

def test_recall_missing_isolated_index_is_silent_and_recorded(tmp_path):
    stage=tmp_path/'stage/scripts';stage.mkdir(parents=True)
    shutil.copyfile(ROOT/'scripts/recall_hook.py',stage/'recall_hook.py')
    r,events=run(tmp_path,'recall',json.dumps({'prompt':'Please find saved computer vision research examples','session_id':'synthetic'}))
    assert r.stdout==''
    assert events[0]['exit_code']==0 and events[0]['output_utf8']==''
    assert not events[0]['timed_out'] and events[0]['elapsed_ms']<2000
    assert not (tmp_path/'recall/index.db').exists()
