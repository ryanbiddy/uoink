"""New synthetic operator item, in a fresh native profile, using installed code."""
import datetime as dt,hashlib,json,os,sys
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\native-gui01')
profile=root/'p4/profile';app=root.parent/'app'
assert Path(sys.executable).resolve()==(app/'python/python.exe').resolve()
assert Path(os.environ['UOINK_INDEX_PATH']).absolute()==profile/'index.db'
assert Path(os.environ['UOINK_OUTPUT_DIR']).absolute()==profile/'output'
assert os.environ['IG_FORBIDDEN_LIVE']==r'C:\Users\hello\AppData\Local\Uoink\index.db'
assert (app/'python/Lib/site-packages/sitecustomize.py').is_file()
import index as index_mod
assert Path(index_mod.__file__).resolve()==(app/'index.py').resolve()
settings=json.loads((profile/'settings.json').read_text(encoding='utf8'))
assert settings.get('librarian_apply_enabled',False) is False
folder=profile/'output/videos/synthetic-native-media-08';folder.mkdir(parents=True,exist_ok=False)
cue='SYNTHETIC stored cue at thirty-four seconds. Verification word: AMBER.'
unknown='SYNTHETIC line with no recorded timestamp.'
corpus=folder/'synthetic-native-media-08.md'
corpus.write_text('# SYNTHETIC native saved video 08\n\n'+cue+'\n\n'+unknown+'\n',encoding='utf8')
sidecar=folder/'synthetic-native-media-08.json'
data={'video_id':'synthetic-native-media-08','title':'SYNTHETIC native saved video 08','source_type':'video','platform':'youtube','channel':'SYNTHETIC operator fixture','duration_seconds':90,'screenshots':[],'transcript':[{'start_seconds':34,'end_seconds':46,'text':cue},{'text':unknown}]}
sidecar.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8')
idx=index_mod.Index.open(profile/'index.db')
try:
    assert idx.get_yoink(data['video_id']) is None
    idx.upsert_yoink({**{k:data[k] for k in ('video_id','title','source_type','platform','channel')},'slug':data['video_id'],'yoinked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'corpus_path':str(corpus),'sidecar_path':str(sidecar),'topic':'Synthetic operator verification','metadata_json':json.dumps({'synthetic_operator_fixture':True})},content=cue+' '+unknown)
    row=idx.get_yoink(data['video_id']);assert row['sidecar_path']==str(sidecar)
finally:idx.close()
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'synthetic_operator_fixture':True,'video_id':data['video_id'],'cue':cue,'untimed_line':unknown,'stored_time':[34,46],'duration_seconds':90,'model_or_fetch_performed':False,'original_acceptance_fixture_modified':False,'installed_index_module':str(index_mod.__file__),'files':{p.relative_to(profile).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (corpus,sidecar)}}
with (root/'media-seed.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
