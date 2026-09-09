"""Independent G2 exchange observation. See the committed supplement brief."""
import argparse, base64, hashlib, importlib.util, json, os, pathlib, site, sqlite3, subprocess, sys, time
from datetime import datetime, timezone

p=argparse.ArgumentParser()
p.add_argument('--worker',type=pathlib.Path,required=True)
p.add_argument('--out',type=pathlib.Path,required=True)
a=p.parse_args(); worker=a.worker.resolve(strict=True); out=a.out.resolve()
assert not os.environ.get('ANTHROPIC_API_KEY')
assert out.is_relative_to(pathlib.Path(__file__).resolve().parent) and not out.exists()
out.mkdir(); profile=out/'profile'; profile.mkdir()
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR','UOINK_OUTPUT_ROOT','UOINK_DATA_ROOT'):
    os.environ[key]=str(profile)
os.environ['UOINK_INDEX_PATH']=str(profile/'unused.db')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.path.insert(0,str(worker))
spec=importlib.util.spec_from_file_location('g2_measure',worker/'scripts/measure_phase5_az5g2.py')
g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
events=[]; label='setup'; replies=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def record(kind,**kw):
    e={'kind':kind,'case':label,'utc':datetime.now(timezone.utc).isoformat(),'perf_ns':time.perf_counter_ns(),
       'monotonic':time.monotonic(),'active':g.library_resources.process_guard()._active,**kw}
    events.append(e)
    with (out/'events.jsonl').open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(e,ensure_ascii=True)+'\n')
def raw_fields(text):
    b=text.encode('utf-8'); obj=json.loads(text)
    return {'bytes':len(b),'sha256':sha(b),'base64':base64.b64encode(b).decode(),
            'id':obj.get('id'),'method':obj.get('method')}
class Input(g._Stdin):
    async def __anext__(self):
        text=await super().__anext__(); record('input_delivery',**raw_fields(text)); return text
class Output:
    def __init__(self,stream,frames):self.stream=stream;self.frames=frames;self.last_id=None
    async def write(self,text):
        self.frames.append(text); self.last_id=json.loads(text).get('id')
        record('output_write',**raw_fields(text))
        # Bounded in-memory sink has capacity eight and at most two responses.
        # No scheduling yield allows the driver to cancel before observing flush.
        self.stream.send_nowait(text)
    async def flush(self):record('output_flush',id=self.last_id)
g._Stdin=Input;g._Stdout=Output
original_dump=g.mcp_types.JSONRPCMessage.model_dump_json
def observed_dump(message,*args,**kwargs):
    rid=getattr(message.root,'id',None); record('serialization_start',id=rid)
    text=original_dump(message,*args,**kwargs)
    record('serialization_end',**raw_fields(text)); return text
g.mcp_types.JSONRPCMessage.model_dump_json=observed_dump
original_reader=g.library_analysis.get_library_activity
def observed_reader(args,**kwargs):
    record('reader_start'); packet=original_reader(args,**kwargs)
    record('reader_end',ok=packet.get('ok'),error=packet.get('error')); return packet
g.library_analysis.get_library_activity=observed_reader
dbs={}; identities={}; result={'scope':'integrator supplement; actual shipped writer with in-memory I/O; no real client',
    'worker_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=worker,text=True).strip(),
    'worker_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=worker,text=True).strip(),
    'g2_harness_sha256':sha((worker/'scripts/measure_phase5_az5g2.py').read_bytes()),'runs':[], 'replay_diagnostics':[]}
names={'548':'db_548.db','10k':'db_10k.db','dense':'db_3mem.db','multi':'db_multi.db','100k':'db_100k.db','70mib':'db_refusal.db'}
try:
    for key,name in names.items():
        path=worker/'_scratch/az5g2/measure/fixture-dbs'/name
        assert not pathlib.Path(str(path)+'-wal').exists() or pathlib.Path(str(path)+'-wal').stat().st_size==0
        identities[key]={'path':str(path),'sha256_before':sha(path.read_bytes())}
        c=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True); c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON'); dbs[key]=c; identities[key]['dimensions']=g.query_dims(c)
    for key,args in [('548',g.PRIMARY_ARGS),('10k',g.PRIMARY_ARGS),('dense',g.PRIMARY_ARGS),('multi',g.REPLAY_ARGS),('100k',g.PRIMARY_ARGS),('70mib',g.PRIMARY_ARGS),('548',g.REPLAY_ARGS),('548',g.PRIMARY_ARGS)]:
        ordinal=len(result['runs']); label=f'{ordinal:02d}-{key}'
        kw={'shift_after_admit':2.1} if ordinal==7 else {}
        rec=g.run_shipped_stdio(dbs[key],args,label=label,**kw)
        rec.pop('frame_text',None); rec['db_key']=key; rec['arguments']=args
        subset=[e for e in events if e['case']==label]
        inbound=next(e for e in subset if e['kind']=='input_delivery' and e['id']==2)
        flushes=[e for e in subset if e['kind']=='output_flush' and e['id']==2]
        rec['call_input_to_flush_ms']=(flushes[-1]['perf_ns']-inbound['perf_ns'])/1e6 if flushes else None
        rec['final_flush_observed']=bool(flushes)
        rec['active_after_exchange']=g.library_resources.process_guard()._active
        result['runs'].append(rec)
        assert rec['error'] is None and flushes and rec['active_after_exchange']==0,rec
    # Profiling is separate from the untraced transport timings.
    g.library_analysis.get_library_activity=original_reader
    old_deadline=g.library_analysis.SERVICE_DEADLINE_SEC
    try:
        g.library_analysis.SERVICE_DEADLINE_SEC=30.0
        for key in ('548','10k'):
            label='profile-'+key; rec=g.replay_probe(dbs[key])
            rec.update(db_key=key,profiling=True,diagnostic_deadline_sec=30.0)
            result['replay_diagnostics'].append(rec)
    finally:g.library_analysis.SERVICE_DEADLINE_SEC=old_deadline
finally:
    g.mcp_types.JSONRPCMessage.model_dump_json=original_dump
    g.library_analysis.get_library_activity=original_reader
    for key,c in dbs.items():
        c.close(); identities[key]['sha256_after']=sha(pathlib.Path(identities[key]['path']).read_bytes())
        assert identities[key]['sha256_after']==identities[key]['sha256_before']
    result['databases']=identities
    (out/'observations.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
for rec in result['runs']:print(rec['label'],rec['activity_completed_frame_bytes'],rec['isError'],round(rec['call_input_to_flush_ms'],3))
print('replay diagnostics',result['replay_diagnostics'])
