from pathlib import Path
import tempfile
from index import Index
from library_work import LibraryWorkService, RequestContext

def fixture():
    root = Path(tempfile.mkdtemp(prefix='fixture-', dir='tests/library_work_astra/_work'))
    idx = Index.open(root / 'fixture.db')
    idx.upsert_yoink(dict(video_id='fixture',slug='fixture',title='Fixture',topic='Old',yoinked_at='2026-09-04',corpus_path='',sidecar_path=''))
    with idx.write_transaction() as c:
        c.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES('fixture',0,0,10,'Original source evidence.')")
    clock = [1000]
    svc = LibraryWorkService(idx, root / 'library', clock=lambda: clock[0])
    ctx = RequestContext(authenticated=True, client_id='client', session_id='local', operator=True, local_user_confirmed=True)
    tax = svc.approve_taxonomy(ctx, dict(version_id='v1',nodes=[dict(shelf_id='s1',path=['Testing'],definition='Tests',include=['tests'],exclude=['other']),dict(shelf_id='s2',path=['Other'],definition='Other',include=['other'],exclude=['tests'])]))
    assert tax['ok'], tax
    run = svc.prepare_run(ctx, dict(run_id='r1',version_id='v1',video_ids=['fixture'],prompt_hash='0'*64))
    assert run['ok'], run
    return root, idx, svc, ctx, clock

def claim(svc,ctx):
    result=svc.claim_work(ctx, dict(action='claim',run_id='r1',client_id='client'))
    assert result['ok'] and len(result['work']) == 1,result
    return result['work'][0]

def submission(w, key='submit1'):
    e=w['card']['excerpts'][0]
    a={k:w[k] for k in ['work_id','video_id','attempt_token','source_revision','taxonomy_revision','packet_hash']}
    a.update(client_id='client',submission_key=key,schema_version=1,usage={'status':'unavailable','reason':'fixture'},result={'outcome':'assigned','memberships':[{'shelf_id':'s1','shelf_path':['Testing'],'confidence':.8,'evidence':{'basis':'packet','kind':'timed_clip','excerpt_id':e['excerpt_id'],'card_hash':w['card']['card_hash'],'quote':'source evidence'}}]})
    return a

def test_stage_a():
    root,idx,svc,ctx,clock=fixture()
    w=claim(svc,ctx)
    a=submission(w)
    s=svc.submit_result(ctx,a)
    assert s['ok'] and s['outcome']=='accepted',s
    clock[0]+=900000
    assert svc.submit_result(ctx,a)==s
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0
    assert idx._conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert idx._conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert idx.schema_version()==27
    idx.close()

if __name__=='__main__':
    test_stage_a()
    print('Stage A passed: migration 27, taxonomy, run, claim, evidence, exact receipt retry after expiry, zero assignments, FK and integrity.')

