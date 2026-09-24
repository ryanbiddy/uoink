from test_projection import *
import pytest,json,os,subprocess,sys,time,shutil,hashlib
from library_work import LibraryError,canonical,RequestContext,_SCHEMAS
import index as index_module

def wait_for(path,child):
    deadline=time.monotonic()+10
    while not path.exists():
        assert child.poll() is None,child.communicate()
        assert time.monotonic()<deadline
        time.sleep(.01)

@pytest.mark.parametrize('boundary',['before_file_publication','after_publication_before_db_commit','after_db_commit_before_response'])
def test_external_process_kill(boundary):
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='external-kill'))
    (root/'request.json').write_text(canonical(args))
    idx.close()
    child=subprocess.Popen([sys.executable,'tests/library_work_astra/kill_child.py',str(root),boundary],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        wait_for(root/'barrier',child)
        child.kill()
        child.communicate(timeout=10)
    finally:
        if child.poll() is None:
            child.kill();child.wait()
    idx=Index.open(root/'fixture.db')
    svc=LibraryWorkService(idx,root/'library',clock=lambda:1000)
    assert svc.startup_status['ok'],svc.startup_status
    assert idx._conn.execute('SELECT projection_revision FROM library_meta').fetchone()[0]==(0 if boundary=='before_file_publication' else 1)
    receipt=svc.pin_shelf(ctx,args)
    assert receipt['ok'] and receipt['after_revision']==1,receipt
    assert svc.pin_shelf(ctx,args)==receipt
    assert len(list((root/'library'/'journal').glob('*.jsonl')))==1
    idx.close()

def test_two_process_claim():
    root,idx,svc,ctx,clock=fixture()
    idx.close()
    children=[subprocess.Popen([sys.executable,'tests/library_work_astra/claim_child.py',str(root),str(n)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for n in range(2)]
    try:
        for n,c in enumerate(children): wait_for(root/('ready'+str(n)),c)
        (root/'go').write_text('go')
        results=[]
        for c in children:
            out,err=c.communicate(timeout=15)
            assert c.returncode==0,(out,err)
            results.append(json.loads(out))
        assert all(r['ok'] for r in results),results
        assert sum(len(r['work']) for r in results)==1,results
    finally:
        for c in children:
            if c.poll() is None:c.kill();c.wait()

def test_complete_db_loss():
    root,idx,svc,ctx,clock=fixture()
    old=idx.get_yoink('fixture')
    pin=svc.pin_shelf(ctx,intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='db-loss')))
    assert pin['ok'],pin
    idx.close()
    db=(root/'fixture.db').resolve()
    assert db.is_relative_to(Path('tests/library_work_astra/_work').resolve()) and db.name=='fixture.db'
    db.unlink()
    for suffix in ('-wal','-shm'):
        sibling=db.with_name(db.name+suffix)
        assert sibling.is_relative_to(Path('tests/library_work_astra/_work').resolve())
        sibling.unlink(missing_ok=True)
    idx=Index.open(db)
    svc=LibraryWorkService(idx,root/'library',clock=lambda:1000)
    assert svc.startup_status['orphaned_count']==1
    idx.upsert_yoink(old)
    status=idx.rebuild_library_state()
    assert status['ok'] and status['orphaned_count']==0,status
    assert idx._conn.execute('SELECT shelf_id,locked FROM item_shelves').fetchone()[:]==('s1',1)
    assert idx._conn.execute('SELECT exclusive_move FROM library_item_policy').fetchone()[0]==1
    assert idx._conn.execute('SELECT projection_revision FROM library_meta').fetchone()[0]==1
    idx.close()

def test_migration_26_rollback(tmp_path,monkeypatch):
    old=tmp_path/'migrations26';old.mkdir()
    actual=index_module._MIGRATIONS_DIR
    for p in actual.glob('*.sql'):
        if int(p.name.split('_',1)[0])<=26:shutil.copy2(p,old/p.name)
    monkeypatch.setattr(index_module,'_MIGRATIONS_DIR',old)
    db=tmp_path/'populated26.db'
    with Index.open(db) as idx:
        idx.upsert_yoink(dict(video_id='fixture',slug='fixture',title='Before',topic='Keep',yoinked_at='2026-09-04',corpus_path='',sidecar_path=''))
        assert idx.schema_version()==26
    text=(actual/'0027_library_substrate.sql').read_text()
    (old/'0027_library_substrate.sql').write_text(text+'\nTHIS IS NOT SQL;\n')
    import sqlite3
    with pytest.raises(sqlite3.Error):Index.open(db)
    c=sqlite3.connect(db)
    assert c.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]==26
    assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='shelves'").fetchone()[0]==0
    assert c.execute('SELECT title FROM yoinks').fetchone()[0]=='Before'
    c.close()
    (old/'0027_library_substrate.sql').write_text(text)
    with Index.open(db) as idx:
        assert idx.schema_version()==27  # this fixture copies only migrations <= 26 plus 0027
        assert idx._conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert idx._conn.execute('SELECT COUNT(*) FROM library_work').fetchone()[0]==0
        assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0

def test_pending_blocks_until_replay():
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='db-fault'))
    original=svc._project_record
    svc._project_record=lambda *_: (_ for _ in ()).throw(OSError('injected'))
    result=svc.pin_shelf(ctx,args)
    assert result['error']['code']=='recovery_pending',result
    assert idx._conn.execute('SELECT projection_revision,recovery_state FROM library_meta').fetchone()[:]==(0,'pending')
    assert svc.claim_work(ctx,dict(action='claim',run_id='r1',client_id='client'))['error']['code']=='recovery_pending'
    svc._project_record=original
    assert svc.recover_operations(ctx,{})['ok']
    assert svc.pin_shelf(ctx,args)['after_revision']==1
    idx.close()

def test_intent_expiry_session_and_undo_undo():
    root,idx,svc,ctx,clock=fixture()
    op=dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='intent')
    a=intent(svc,ctx,'pin',op)
    foreign=RequestContext(authenticated=True,client_id='client',session_id='foreign')
    assert svc.pin_shelf(foreign,a)['error']['code']=='invalid_user_intent'
    clock[0]+=300000
    assert svc.pin_shelf(ctx,a)['error']['code']=='invalid_user_intent'
    a=intent(svc,ctx,'pin',op)
    pin=svc.pin_shelf(ctx,a)
    undo=intent(svc,ctx,'undo',dict(apply_id=pin['apply_id'],expected_projection_revision=1,operation_key='undo'))
    u=svc.undo_apply(ctx,undo)
    assert u['ok'],u
    redo=intent(svc,ctx,'undo',dict(apply_id=u['apply_id'],expected_projection_revision=2,operation_key='redo'))
    r=svc.undo_apply(ctx,redo)
    assert r['ok'],r
    assert idx._conn.execute('SELECT shelf_id,locked FROM item_shelves').fetchone()[:]==('s1',1)
    assert idx._conn.execute('SELECT exclusive_move FROM library_item_policy').fetchone()[0]==1
    idx.close()

def test_frozen_schemas():
    document=json.loads(Path('docs/library/phase2-contract/tool-schemas.json').read_text())
    assert _SCHEMAS=={t['name']:t['inputSchema'] for t in document['tools']}
