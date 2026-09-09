"""Actual isolated Mirror disconnection/edit/deletion accounting, no client effects."""
import datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
root=Path(__file__).resolve().parent
env=json.loads((root/'mcp.json').read_text(encoding='utf-8'))['mcpServers']['uoink']['env']
os.environ.pop('ANTHROPIC_API_KEY',None);os.environ.update(env);sys.path[:0]=env['PYTHONPATH'].split(os.pathsep)
g=root/'guard/sitecustomize.py';exec(compile(g.read_text(),str(g),'exec'),{})
import index, library_work, library_resources, library_briefs, library_mirror, server
folder=root/'m';folder.mkdir(exist_ok=False)
data=folder/'d';data.mkdir();vault=folder/'v';vault.mkdir();offline=folder/'v-offline'
corpus=folder/'c';corpus.mkdir();events=[]
def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():
 return {str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size,
              'text':p.read_text(encoding='utf-8',errors='replace') if p.suffix in ('.md','.json') else None}
         for top in (vault,offline,data) if top.exists() for p in sorted(top.rglob('*')) if p.is_file()}
def record(name,result=None):
 event={'name':name,'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'result':result,
        'status':mirror.status(),'files':snapshot()};events.append(event);save(folder/'events.json',events)
 print(json.dumps({'name':name,'result':result,'status':event['status']}),flush=True)
def rename_verified(source,target):
 assert source.resolve(strict=True).is_relative_to(folder.resolve())
 assert target.resolve().is_relative_to(folder.resolve()) and not target.exists()
 for p in [source,*source.rglob('*')]:
  assert not p.is_symlink() and not (getattr(p.lstat(),'st_file_attributes',0)&0x400)
 source.rename(target)
idx=index.Index.open(folder/'index.db')
def seed(vid):
 p=corpus/(vid+'.md');p.write_text('# '+vid+'\n\nSynthetic mirror evidence for '+vid+'.\n',encoding='utf-8')
 idx.upsert_yoink({'video_id':vid,'slug':vid,'title':vid,'channel':'Fixture','yoinked_at':'2026-09-09T00:00:00Z',
   'corpus_path':str(p),'sidecar_path':str(corpus/(vid+'.json')),'metadata_json':'{}','platform':'note','source_type':'note'},content=p.read_text())
def itemfile(vid):return vault/library_mirror.MIRROR_ROOT/library_mirror.item_relpath(vid)
try:
 for vid in ('owned-purge','edited-keep'):seed(vid)
 service=library_work.LibraryWorkService(idx,folder/'store',librarian_apply_enabled=False)
 reader=library_resources.LibraryReader(idx,data_root=data)
 briefs=library_briefs.BriefStore(idx,service,data_root=data)
 marker='aw02-disposable-volume'
 (vault/'.uoink-volume-marker').write_text(marker,encoding='utf-8')
 (vault/library_mirror.MIRROR_ROOT).mkdir()
 (vault/library_mirror.MIRROR_ROOT/'.uoink-volume-marker').write_text(marker,encoding='utf-8')
 (vault/'TASTE.md').write_text('Unowned taste fixture.\n',encoding='utf-8')
 (vault/'USER.md').write_text('Unowned user fixture.\n',encoding='utf-8')
 unowned={name:sha(vault/name) for name in ('TASTE.md','USER.md')}
 consent=library_mirror.MirrorConsent(str(vault),library_mirror.SCOPE_ALL,(),int(time.time()*1000),marker)
 mirror=library_mirror.Mirror(idx,reader,briefs,data_root=data,consent=consent,enabled=True)
 for vid in ('owned-purge','edited-keep'):mirror.on_committed_event('capture',video_id=vid)
 initial=mirror.resync();record('initial_sync',initial)
 assert initial.get('ok') and all(itemfile(v).is_file() for v in ('owned-purge','edited-keep'))
 rename_verified(vault,offline)
 with idx.write_transaction():idx._conn.execute("UPDATE yoinks SET deleted_at='2026-09-09T00:01:00Z' WHERE video_id='owned-purge'")
 mirror.on_committed_event('hard_purge',video_id='owned-purge')
 seed('new-after-disconnect');mirror.on_committed_event('capture',video_id='new-after-disconnect')
 disconnected=mirror.resync();record('disconnected_with_delete_and_write_queued',disconnected)
 assert disconnected.get('ok') is False and not vault.exists()
 assert mirror.status()['deletion_pending']>=1
 rename_verified(offline,vault)
 reconnected=mirror.resync();record('reconnected_deletions_drained',reconnected)
 assert reconnected.get('ok') and not itemfile('owned-purge').exists() and itemfile('new-after-disconnect').is_file()
 userbytes=b'# Personal fixture note\nMust remain exactly as edited.\n'
 itemfile('edited-keep').write_bytes(userbytes)
 mirror.on_committed_event('capture',video_id='edited-keep')
 edit=mirror.resync();record('user_edit_conflict',edit)
 assert itemfile('edited-keep').read_bytes()==userbytes
 with idx.write_transaction():idx._conn.execute("UPDATE yoinks SET deleted_at='2026-09-09T00:02:00Z' WHERE video_id='edited-keep'")
 purge=mirror.purge('edited-keep');record('purge_preserves_user_edit',purge)
 assert itemfile('edited-keep').read_bytes()==userbytes
 assert 'purge_blocked_user_edit' in json.dumps(purge) and mirror.status()['exports_paused']
 assert unowned=={n:sha(vault/n) for n in unowned}
 temps=[str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and ('tmp' in p.name.lower() or p.suffix=='.temp')]
 assert not temps,temps
 final={'scope':'Real production Mirror on synthetic isolated files; no client or live vault',
  'observations_completed':True,'user_edit_preserved':True,'owned_delete_removed':not itemfile('owned-purge').exists(),
  'new_item_written_after_reconnect':itemfile('new-after-disconnect').exists(),'unowned_files_unchanged':True,
  'temporary_files':temps,'final_status':mirror.status(),'pending_user_edit_conflict_is_expected':True,
  'mirror_session_retained':mirror._vault_io is not None,'apply_enabled':service.librarian_apply_enabled}
 save(folder/'summary.json',final);print(json.dumps(final),flush=True)
finally:
 if offline.exists() and not vault.exists():rename_verified(offline,vault)
 idx.close();save(folder/'events.json',events)
