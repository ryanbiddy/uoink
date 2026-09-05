from test_projection import *
import copy
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import pytest
from library_work import validate_arguments, decode_json, LibraryError, canonical

@pytest.mark.parametrize('bad',[None,[],True,{'limit':True},{'limit':float('nan')},{'limit':10**1000},{'run_id':[]},{'extra':1}])
def test_strict_inputs(bad):
    root,idx,svc,ctx,clock=fixture()
    assert svc.list_work(ctx,bad)['ok'] is False
    idx.close()

@pytest.mark.parametrize('raw',['{"limit":1,"limit":2}', '{"limit":NaN}', '{"limit":Infinity}'])
def test_decode(raw):
    with pytest.raises(LibraryError): decode_json(raw)

def test_expiry_ceiling_renew_release():
    root,idx,svc,ctx,clock=fixture()
    w=claim(svc,ctx)
    clock[0]=w['lease_expires_ms']-1
    renew=svc.renew_attempt(ctx,dict(action='renew',work_id=w['work_id'],client_id='client',attempt_token=w['attempt_token'],lease_seconds=900))
    assert renew['ok'],renew
    assert renew['lease_expires_ms']<=3601000
    clock[0]=renew['lease_expires_ms']
    assert svc.submit_result(ctx,submission(w))['error']['code']=='stale_attempt'
    w2=claim(svc,ctx)
    assert w2['attempt_number']==2 and w2['attempt_token']!=w['attempt_token']
    rejected=svc.submit_result(ctx,dict(submission(w2,'reject'),result={'outcome':'assigned','memberships':[]}))
    assert rejected['outcome']=='rejected' and rejected['retryable']
    w3=claim(svc,ctx)
    release=svc.release_attempt(ctx,dict(action='release',work_id=w3['work_id'],client_id='client',attempt_token=w3['attempt_token'],reason='stopped'))
    assert release['state']=='blocked' and release['remaining_attempts']==0
    assert svc.claim_work(ctx,dict(action='claim',run_id='r1',client_id='client'))['work']==[]
    assert svc.refresh_run_item(ctx,dict(run_id='r1',video_id='fixture',reason='refresh'))['error']['code']=='attempts_exhausted'
    assert svc.submit_result(ctx,dict(submission(w2,'reject'),result={'outcome':'assigned','memberships':[]}))==rejected
    idx.close()

@pytest.mark.parametrize('mutation',['wrong_id','foreign_shelf','duplicate_shelf','quote','low_confidence','extra','malformed','usage'])
def test_validation(mutation):
    root,idx,svc,ctx,clock=fixture()
    a=submission(claim(svc,ctx))
    m=a['result']['memberships'][0]
    if mutation=='wrong_id': a['video_id']='wrong'
    elif mutation=='foreign_shelf': m['shelf_id']='foreign'
    elif mutation=='duplicate_shelf': a['result']['memberships'].append(copy.deepcopy(m))
    elif mutation=='quote': m['evidence']['quote']='Original source evidence. Joined different clip.'
    elif mutation=='low_confidence': m['confidence']=.59999
    elif mutation=='extra': m['override']=True
    elif mutation=='malformed': a['result']=[]
    elif mutation=='usage': a['usage']={'status':'reported','model':'fixture','input_tokens':True,'output_tokens':0,'wall_time_ms':0}
    r=svc.submit_result(ctx,a)
    assert r['ok'] and r['outcome']=='rejected',r
    assert svc.submit_result(ctx,a)==r
    assert svc.submit_result(ctx,dict(a,submission_key='other'))['error']['code']=='idempotency_conflict'
    assert svc.submit_result(ctx,dict(a,video_id='changed'))['error']['code']=='idempotency_conflict'
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0
    assert idx._conn.execute('SELECT COUNT(*) FROM library_proposals').fetchone()[0]==0
    idx.close()

def test_concurrent_claim():
    root,idx,svc,ctx,clock=fixture()
    second=Index.open(root/'fixture.db')
    other=LibraryWorkService(second,root/'library',clock=lambda:clock[0])
    barrier=threading.Barrier(2)
    def run(s):
        barrier.wait()
        return s.claim_work(ctx,dict(action='claim',run_id='r1',client_id='client'))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results=list(pool.map(run,[svc,other]))
    assert all(r['ok'] for r in results),results
    assert sum(len(r['work']) for r in results)==1
    assert idx._conn.execute("SELECT COUNT(*) FROM library_attempts WHERE state='current'").fetchone()[0]==1
    second.close();idx.close()

def test_source_change_invalidates():
    root,idx,svc,ctx,clock=accepted()
    a,p=approved(svc,ctx)
    item=idx.get_yoink('fixture');item['title']='Changed'
    idx.upsert_yoink(item)
    assert idx._conn.execute('SELECT disposition FROM library_manifest').fetchone()[0]=='changed'
    assert idx._conn.execute('SELECT COUNT(*) FROM library_proposals').fetchone()[0]==0
    svc.librarian_apply_enabled=True
    assert not svc.apply_preview(ctx,a)['ok']
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0
    idx.close()

def test_rebuild_and_orphan():
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='pin'))
    receipt=svc.pin_shelf(ctx,args)
    assert receipt['ok'],receipt
    old=idx.get_yoink('fixture')
    idx.close()
    # A distinct empty DB simulates total DB loss without deleting any DB.
    fresh=Index.open(root/'rebuilt.db')
    service=LibraryWorkService(fresh,root/'library',clock=lambda:clock[0])
    assert service.startup_status['ok'],service.startup_status
    assert service.startup_status['orphaned_count']==1
    fresh.upsert_yoink(old)
    rebuilt=service.rebuild_library_state(ctx,{})
    assert rebuilt['ok'] and rebuilt['orphaned_count']==0,rebuilt
    assert fresh._conn.execute('SELECT shelf_id,locked,confidence FROM item_shelves').fetchone()[:]==('s1',1,None)
    assert fresh._conn.execute('SELECT exclusive_move FROM library_item_policy').fetchone()[0]==1
    assert service.pin_shelf(ctx,args)==receipt
    fresh.close()

def test_nochange_and_stale_undo():
    root,idx,svc,ctx,clock=accepted()
    svc.librarian_apply_enabled=True
    a,p=approved(svc,ctx)
    receipt=svc.apply_preview(ctx,a)
    b,_=approved(svc,ctx,rev=1,key='apply2')
    second=svc.apply_preview(ctx,b)
    assert second['ok'] and second['no_change'] and second['after_revision']==1,second
    assert idx._conn.execute('SELECT COUNT(*) FROM library_applies').fetchone()[0]==1
    assert idx._conn.execute('SELECT COUNT(*) FROM library_operation_receipts').fetchone()[0]==2
    pin=svc.pin_shelf(ctx,intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s2',action='pin',expected_projection_revision=1,operation_key='pin2')))
    assert pin['ok'],pin
    stale=svc.mint_user_intent(ctx,dict(kind='undo',operation=dict(apply_id=receipt['apply_id'],expected_projection_revision=2,operation_key='undo')))
    assert stale['error']['code']=='revision_conflict',stale
    idx.close()

@pytest.mark.parametrize('boundary',['before_file_publication','after_publication_before_db_commit','after_db_commit_before_response'])
def test_forced_crash(boundary):
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='move',expected_projection_revision=0,operation_key='crash-pin'))
    (root/'request.json').write_text(canonical(args))
    idx.close()
    env=dict(os.environ,PYTHONPATH='.')
    child=subprocess.run([sys.executable,'tests/library_work_astra/crash_child.py',str(root),boundary],env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==73,(child.returncode,child.stdout,child.stderr)
    idx=Index.open(root/'fixture.db')
    service=LibraryWorkService(idx,root/'library',clock=lambda:1000)
    assert service.startup_status['ok'],service.startup_status
    before=idx._conn.execute('SELECT projection_revision FROM library_meta').fetchone()[0]
    assert before==(0 if boundary=='before_file_publication' else 1)
    receipt=service.pin_shelf(ctx,args)
    assert receipt['ok'] and receipt['after_revision']==1,receipt
    assert service.pin_shelf(ctx,args)==receipt
    assert idx._conn.execute('SELECT COUNT(*) FROM library_applies').fetchone()[0]==1
    assert idx._conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    idx.close()

def test_corrupt_record_stops():
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='pin',expected_projection_revision=0,operation_key='corrupt'))
    assert svc.pin_shelf(ctx,args)['ok']
    path=next((root/'library'/'journal').glob('*.jsonl'))
    path.write_bytes(b'{damaged}\n')
    result=svc.recover_operations(ctx,{})
    assert result['error']['code']=='recovery_conflict',result
    assert idx._conn.execute('SELECT recovery_state FROM library_meta').fetchone()[0]=='conflict'
    idx.close()
