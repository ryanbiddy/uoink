"""Separate installed publication fixture and original-stdio observation; no model."""
from pathlib import Path
import argparse,datetime as dt,hashlib,json,os,shutil,subprocess,sys,time,uuid
p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','protocol'));a=p.parse_args()
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07')
profile=root/'p6-published01/profile';app=root/'app'
seal=repo/'docs/library/proof/candidate-package-07-2026-09-12'
sys.path.insert(0,str(repo/'scripts/install_receipt'))
import p4_common as common
binding=common.validate_isolation(isolated_profile=profile,isolated_port=18383,receipt_root=profile.parent,
    installed_app=app,installed_interpreter=app/'python/python.exe',package_manifest=seal/'package-manifest.json',
    forbid_checkout=repo,runtime_mode='installed',package_path=repo/'build/Uoink-Setup-3.8.0.exe',source_bindings_path=seal/'source-bindings.json')
sys.path.insert(0,str(app))
import uoink_install_isolation as isolation
isolation.apply_from_process()
import index,library_media as media,library_resources as resources,server
assert Path(server.INDEX_PATH).resolve()==profile/'index.db'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2,default=str)+'\n')
vid='p6fx-range-01'
cue_text='SYNTHETIC FIXTURE: the stored navigation value is AMBER. Not a source quotation.'
chapter_title='SYNTHETIC FIXTURE CHAPTER: Why computer use (not a source quotation)'
from p4_prepare_fixture import TIMED_URL
url=TIMED_URL
if a.stage=='prepare':
    assert not (profile/'index.db').exists() and not (profile/'expected.json').exists()
    save(profile/'settings.json',{'librarian_apply_enabled':False,'library_mirror_enabled':False,'synthetic_fixture':True})
    folder=profile/'items'/vid;folder.mkdir(parents=True,exist_ok=False)
    corpus=folder/'corpus.md';sidepath=folder/'corpus.json'
    corpus.write_text('# SYNTHETIC FIXTURE\n\n'+cue_text+'\n',encoding='utf8')
    side={'video_id':vid,'title':'SYNTHETIC FIXTURE published media item','channel':'Synthetic fixture',
          'topic':'fixture','url':url,'source_type':'video','duration_seconds':120,
          'yoinked_at':'2026-09-12T00:00:00Z','synthetic_fixture':True,'transcript_source':'supplied_metadata',
          'transcript':[{'start':34.0,'end':46.0,'text':cue_text,'source_url':url,'source_deep_link':url+'#t=34'}],
          'source_chapters':[{'start_time':34.0,'end_time':90.0,'title':chapter_title}]}
    save(sidepath,side)
    save(profile/'input.json',{'sidecar':side,'corpus_sha256':sha(corpus),'sidecar_sha256':sha(sidepath),
         'scope':'Generated data only; no source fetch or transcript inference'})
    idx=index.Index.open(profile/'index.db')
    try:
        item={'video_id':vid,'slug':vid,'title':side['title'],'channel':side['channel'],'topic':'fixture',
              'platform':'youtube','source_type':'video','yoinked_at':side['yoinked_at'],
              'corpus_path':str(corpus),'sidecar_path':str(sidepath),
              'metadata_json':json.dumps({'url':url,'duration_seconds':120,'source_type':'video'})}
        idx.upsert_yoink(item,content=corpus.read_text(encoding='utf8'))
        published=server._publish_capture_media(idx,folder,side,corpus,sidepath)
        assert published is True
        exported=media.export_cited_range(idx._conn,{'video_id':vid,'start':34,'end':46})
        assert exported.get('ok') is True,exported
        assert exported['citation']['verbatim_text']==cue_text
        assert len(exported['chapters'])==1 and exported['chapters'][0]['title']==chapter_title
        assert not exported['attribution']['labels'] and not exported['attribution']['diarization_ran']
        assert all(u['speaker'] is None and u['speaker_provenance'] is None for u in exported['units'])
        assert exported['citation']['seek_link'] is None and exported['citation']['player_seek_seconds'] is None
        save(profile/'expected.json',{'video_id':vid,'request':{'video_id':vid,'start':34,'end':46},
             'export':exported,'producer':'server._publish_capture_media -> Index.publish_media_snapshot',
             'source_sha256':sha(app/'library_resources.py'),'synthetic':True,'published_sidecar_sha256':sha(sidepath)})
    finally:idx.close()

    env=common.isolation_env(binding)
    kit=profile/'kit';kit.mkdir(exist_ok=True)
    for name in ('p4_stdio_tap.py','p4_common.py','p4_session.py'):
        shutil.copyfile(repo/'scripts/install_receipt'/name,kit/name)
    client=profile/'client';client.mkdir(exist_ok=True)
    observer=client/'observe_media_actions.py'
    old=(repo/'scripts/install_receipt/p4_observe_actions.py').read_text(encoding='utf8')
    anchor='    "mcp__uoink__read_library_resource",'
    assert old.count(anchor)==1
    observer.write_text(old.replace(anchor,anchor+'\n    "mcp__uoink__export_cited_range",'),encoding='utf8')
    selected={k:v for k,v in env.items() if k.startswith(('P4_','UOINK_')) or k in common.ENV_ROOT_KEYS or k in
              ('PYTHONDONTWRITEBYTECODE','PYTHONUTF8','PYTHONPATH','PYTHONNOUSERSITE','PYTHONSAFEPATH','IG_FORBIDDEN_LIVE')}
    original={'mcpServers':{'uoink':{'type':'stdio','command':binding['installed_interpreter'],
      'args':['-P','-B','-s',str(kit/'p4_stdio_tap.py'),'--isolated-profile',str(profile),'--isolated-port','18383',
        '--fixture-root',str(profile),'--record-dir',str(profile/'records/stdio'),'--cwd',str(app),
        '--route-label','original-installed','--',*common.installed_stdio_command(binding)],'env':selected}}}
    from p4_prepare_client import build,validate_original_config,BUILTINS
    config,settings,unused,allowed,denied=build(profile,original,list(common.EXPECTED_STDIO_TOOLS),
        app/'python/python.exe',observer,profile,18383)
    auth=str(Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\profile\client\claude-config'))
    settings['env']['CLAUDE_CONFIG_DIR']=auth
    for entry in config['mcpServers'].values():entry['env']['CLAUDE_CONFIG_DIR']=auth
    name='mcp__uoink__export_cited_range';assert name not in allowed and denied.count(name)==1
    allowed.append(name);denied.remove(name)
    settings['permissions']['allow']=allowed;settings['permissions']['deny']=denied
    validate_original_config(config,binding)
    save(client/'mcp-client.json',config);save(client/'settings.json',settings)
    session=str(uuid.uuid4())
    launch={'args':['--restricted','--strict-mcp-config','--no-chrome','--permission-mode','dontAsk',
        '--tools',','.join(BUILTINS),'--allowedTools',','.join(allowed),'--disallowedTools',','.join(denied),
        '--mcp-config',str(client/'mcp-client.json'),'--settings',str(client/'settings.json'),
        '--session-id',session,'--debug-file',str(client/'claude-debug-published01.log')],
        'environment':{**selected,**settings['env']},'session_id':session,'credentials_copied':False}
    save(client/'launch.json',launch)
    (client/'protected-sentinel.bin').write_bytes(common.PROTECTED_SENTINEL_BYTES)
    save(client/'configuration-manifest.json',{'hashes':{name:sha(client/name) for name in
        ('mcp-client.json','settings.json','launch.json','observe_media_actions.py')},
        'apply_enabled':False,'scope':'New dedicated publication scenario; original P4 fixtures unchanged'})
    probe=profile/'permission-probe';(probe/'client').mkdir(parents=True,exist_ok=False)
    probe_env=dict(env,P4_FIXTURE_ROOT=str(probe))
    checks=[]
    for tool,want in [('mcp__uoink__export_cited_range','allow'),('mcp__uoink__uoink_video','deny'),('Bash','deny')]:
        command=[str(app/'python/python.exe'),'-P','-B','-s',str(observer),'hook',
                 '--fixture-root',str(probe),'--isolated-profile',str(profile),'--isolated-port','18383']
        payload={'hook_event_name':'PreToolUse','tool_name':tool,'tool_input':{},'tool_use_id':'synthetic-policy-probe-'+tool}
        response=subprocess.run(command,input=json.dumps(payload),text=True,capture_output=True,env=probe_env,cwd=profile,timeout=10)
        row={'tool':tool,'expected':want,'exit':response.returncode,'stdout':response.stdout,'stderr':response.stderr}
        checks.append(row)
        save(probe/(tool+'.json'),row)
        assert response.returncode==0 and json.loads(response.stdout)['hookSpecificOutput']['permissionDecision']==want,row
    save(probe/'result.json',{'synthetic_hook_probes_only':True,'actual_client_tool_calls':0,'checks':checks})
    print('Published synthetic chapter through the installed producer and froze a separate client configuration.')
else:
    expected=json.loads((profile/'expected.json').read_text(encoding='utf8'))
    from p4_stdio_check import launch as start,_close_session
    env=common.isolation_env(binding)
    result={'scope':'Original installed protocol observer; not an actual model client','request':expected['request']}
    session,command=start(binding,profile,env,'original-installed',common.installed_stdio_command(binding),'published-protocol01')
    result['command']=command
    try:
        reply,elapsed,raw,error=session.rpc(1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},
            'clientInfo':{'name':'Astra installed chapter observer','version':'1'}})
        assert not error and reply.get('result'),(reply,error)
        session.notify('notifications/initialized')
        reply,elapsed,raw,error=session.rpc(2,'resources/list',{})
        assert not error and 'result' in reply,(reply,error)
        first=time.monotonic();time.sleep(2.1)
        result['delay_after_resources_s']=time.monotonic()-first
        reply,elapsed,raw,error=session.rpc(3,'tools/call',{'name':'export_cited_range','arguments':expected['request']})
        result.update(reply=reply,elapsed_ms=elapsed,transport_error=error)
        assert not error and not reply['result'].get('isError'),reply
        rendered=next(x['text'] for x in reply['result']['content'] if x['type']=='text')
        assert rendered==resources.render_tool_text(expected['export']),rendered
        result['exact_expected_export']=True
    finally:
        result['cleanup']=_close_session(session)
        save(profile/'protocol01.json',result)
    assert result['cleanup']['cleaned']
    print(json.dumps({'exact_expected_export':result['exact_expected_export'],
                      'delay_after_resources_s':result['delay_after_resources_s'],'cleanup':result['cleanup']},indent=2))
