"""Retain source/log evidence without ordinary profile inspection or raw log export."""
import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch';out=s/'native-client-incident12-review';out.mkdir(exist_ok=False)
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\46e8e6dc-ea4\gemini')
expected={
 '_scratch/desktop-startup12-static/.vite/build/index.pre.js':(896736,'389412c74487cfded562bd8808f2b245721c397147ff0c1e1d9dfc7c1a42d821'),
 '_scratch/native_gui07_driver.py':(5839,'b28770d766392f49ceb09fa22b37681a0a1d3daf2776e4ee23455bb43e0dc411'),
 'scripts/install_receipt/p4_common.py':(55973,'6e44bcfb5edee0d282de70d3f9100f0de77b234d67fd302b8dec2761dbebf238'),
 'scripts/install_receipt/p4_session.py':(32779,'8f4b63aac375922c2cd642c816b7ec5253842ac92fc8a8c2df0af604f99d17a8')}
bindings=[]
for name,(size,digest) in expected.items():
    data=(r/name).read_bytes();assert len(data)==size and hashlib.sha256(data).hexdigest()==digest
    bindings.append({'path':name,'bytes':size,'sha256':digest})
source=(r/next(iter(expected))).read_text(encoding='utf8')
deletion='E.app.isPackaged&&!QJ&&(delete process.env.CLAUDE_USER_DATA_DIR'
setter='if(process.env.CLAUDE_USER_DATA_DIR){let e=process.env.CLAUDE_USER_DATA_DIR;E.app.setPath("userData",e)'
assert source.index(deletion)<source.index(setter)
snippet={'source_sha256':bindings[0]['sha256'],'deletion_offset':source.index(deletion),'deletion':source[source.index(deletion):source.index(deletion)+175],'later_setter_offset':source.index(setter),'later_setter':source[source.index(setter):source.index(setter)+160]}
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07\native-gui01')
logs=root/'environment/LOCALAPPDATA/Claude/logs';events=[]
for filename in ('mcp-server-uoink.log','mcp-server-filesystem.log'):
    raw=(logs/filename).read_bytes()
    selected=[line for line in raw.decode('utf8').splitlines() if any(needle in line for needle in ('Initializing server...','Server started and connected successfully','Processing request of type ListToolsRequest','Using MCP server command: C:\\Users\\hello\\AppData\\Local\\Uoink\\python\\python.exe'))]
    events.append({'private_source':str(logs/filename),'sha256':hashlib.sha256(raw).hexdigest(),'selected_events':selected,'raw_log_exported':False})
assert any('Using MCP server command:' in line for line in events[0]['selected_events'])
assert any('ListToolsRequest' in line for line in events[0]['selected_events'])
result=json.loads((root/'desktop/result.json').read_text(encoding='utf8'))
assert all(x['cleaned'] and x['job_empty_affirmed'] for x in result['cleanup'])
assert result['guard_restore']['ok'] and result['window_exit_before_cleanup']==0
record={'source_bindings':bindings,'startup_evidence':snippet,'selected_log_events':events,'cleanup':result['cleanup'],'cleanup_finished_utc_record':result['utc_end'],'guard_restore':result['guard_restore'],'conclusion':'Intended Desktop configuration isolation failed. Earlier ordinary connector effects unknown. No live-index/port/auth-store inspection performed.','executed_model_code':False}
(out/'independent-review.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
name='docs/library/NATIVE-CLIENT-ISOLATION-WORKER-2026-09-12.md'
subprocess.run(['git','add','-N','--',name],cwd=w,check=True)
assert subprocess.check_output(['git','diff','--name-only'],cwd=w,text=True).strip()==name
(out/'worker-original.patch').write_bytes(subprocess.check_output(['git','diff','--binary','--',name],cwd=w))
(out/'worker-original-report.txt').write_bytes((w/name).read_bytes())
print(json.dumps({'source_hashes_verified':len(bindings),'ordinary_connector_launch_confirmed':True,'owned_job_cleanup_confirmed':True,'live_index_or_port_effects':'unknown','no_new_launch':True}))
