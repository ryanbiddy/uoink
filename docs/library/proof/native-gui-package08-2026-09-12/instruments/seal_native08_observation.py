"""Review and seal actual native-window observations; retain the failed seed attempt."""
from pathlib import Path
import datetime as dt, hashlib, json, re, stat
r=Path(__file__).resolve().parents[1];s=r/'_scratch';d=r/'docs/library'
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08')
run=root/'native-gui02/dashboard';out=d/'proof/native-gui-package08-2026-09-12'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda b:hashlib.sha256(b).hexdigest()
actual=read(run/'observation-complete.json');result=read(run/'result.json')
failed=read(root/'native-gui01/dashboard/result.json')
package=read(d/'proof/candidate-package-08-2026-09-12/package-manifest.json')
assert actual['package_sha256']==package['package_sha256']
assert actual['actual_gui_observation'] and len(actual['passed_observations'])==11
assert result['status']=='completed_pending_review' and result['operator_completion_present'] and not result['deadline_reached']
assert result['guard_restore']['ok'] and all(x['cleaned'] and x['job_empty_affirmed'] and not x['identity_uncertain'] for x in result['cleanup'])
assert result['window_exit_before_cleanup'] is None
assert failed['status']=='failed' and 'fixture preparation failed' in failed['error'].lower()
assert failed['guard_restore']['ok'] and all(x['cleaned'] for x in failed['cleanup'])
records=sorted(run.glob('[0-9][0-9]-*.json'));assert len(records)==11
images=[]
for p in records:
    row=read(p);assert row['window']['id']==397512 and 'Agent Install 08' in row['window']['app']
    for x in row['screenshots']:
        q=run/x['file'];b=q.read_bytes()
        assert q.suffix=='.jpg' and b.startswith(b'\xff\xd8\xff') and sha(b)==x['sha256'] and len(b)==x['bytes']
        images.append({'file':q.name,'sha256':sha(b),'bytes':len(b),'mimeType':'image/jpeg'})
assert len(images)==11
note=read(run/'09-note-detail.json')['accessibility']['document_text']
assert 'Saved note source.' in note and 'Verification word: AMBER.' in note and 'Note file\nready' in note
assert all(x not in note for x in ('Screenshots','Comments file','Duration','Speaker 1','checking'))
video=read(run/'03-video-transcript.json')['accessibility']['document_text']
assert '0:34' in video and 'time not stored' in video and 'Speaker 1' not in video
activity=read(run/'11-activity.json')['accessibility']['document_text']
assert '0 running' in activity and '0 queued' in activity and 'SYNTHETIC native note 08' in activity
legacy=[]
for p in sorted((d/'proof/native-gui-package07-2026-09-12/dashboard').glob('*.png')):
    b=p.read_bytes();legacy.append({'file':p.name,'actual_format':'JPEG' if b.startswith(b'\xff\xd8\xff') else 'PNG' if b.startswith(b'\x89PNG\r\n\x1a\n') else 'unknown','sha256':sha(b)})
assert len(legacy)==10 and all(x['actual_format']!='unknown' for x in legacy)
summary={**actual,'utc_review':dt.datetime.now(dt.timezone.utc).isoformat(),'build_source':package['build_source'],
    'status':'passed_enumerated_native_uoink_flows','owned_cleanup_affirmed':True,'guard_restored':True,
    'utc_start':result['utc_start'],'utc_end':result['utc_end'],'images':images,
    'owned_exit_codes':{x['label']:x['exit_code'] for x in result['cleanup']},
    'natural_close_observed':False,'failed_attempt':'native-gui01 seed import failed before fixture write; no GUI credit; original retained',
    'legacy_image_format_check':legacy,'release_ready':False}
with (s/'native08-observed-summary.json').open('x',encoding='utf8') as f:json.dump(summary,f,indent=2);f.write('\n')
sources={}
def add(p,name):
    assert p.is_relative_to(root) or p.is_relative_to(s)
    assert not p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    assert not any(x in str(p).lower() for x in ('claude-config','credentials','token.txt','.db'))
    b=p.read_bytes()
    if p.suffix not in ('.jpg','.png'):
        assert not re.search(rb'sk-ant-[A-Za-z0-9_-]{20,}',b)
        assert not re.search(rb'"(?:access_token|refresh_token)"\s*:\s*"[^"\r\n]{12,}"',b)
    assert name not in sources;sources[name]=b
for attempt in ('native-gui01','native-gui02'):
    a=root/attempt
    for p in a.iterdir():
        if p.is_file() and p.suffix in ('.json','.cs','.stdout','.stderr'):add(p,attempt+'/'+p.name)
    for p in (a/'dashboard').iterdir():
        if p.is_file() and p.suffix in ('.json','.jpg','.stdout','.stderr'):add(p,attempt+'/dashboard/'+p.name)
    add(a/'p4/profile/operator-prepare.json',attempt+'/operator-prepare.json')
for name in ('prepare_native_gui08.py','native_media08_seed.py','native_gui08_driver.py','build_native_gui08_launchers.py',
             'prepare_native_gui08_02.py','native_media08_seed02.py','native_gui08_driver02.py','build_native_gui08_launchers02.py',
             'repair_native08_seed.py','NATIVE08-SEED-REPAIR-BRIEF.md','native08-seed-preexecution-review.json',
             'native08-screenshot-archiver01.js','native08-screenshot-archiver02.js','native08-screenshot-format-repair.json',
             'seal_native08_observation.py'):
    add(s/name,'instruments/'+name)
    if (s/(name+'.diff')).is_file():add(s/(name+'.diff'),'instruments/'+name+'.diff')
for p in (root/'native-gui02/p4/profile/output').rglob('*'):
    if p.is_file() and p.suffix in ('.md','.json'):
        if 'synthetic-native-media-08' in str(p) or 'synthetic-native-note-08' in str(p):
            add(p,'synthetic-saved-files/'+p.relative_to(root/'native-gui02/p4/profile/output').as_posix())
add(s/'native08-observed-summary.json','summary.json')
out.mkdir(exist_ok=False);sources['.gitattributes']=b'* -text\n'
for name,b in sources.items():
    q=out/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
files={name:{'bytes':len(b),'sha256':sha(b)} for name,b in sorted(sources.items())}
(out/'SHA256.json').write_text(json.dumps({'scope':'Actual Uoink native window only; synthetic profile; failed attempt retained; no Desktop acceptance or natural shutdown credit. Original JPEG bytes unchanged.','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'original_images':len(images),'native_flows':len(actual['passed_observations']),'cleanup':True,'legacy_formats':sorted(set(x['actual_format'] for x in legacy))}))
