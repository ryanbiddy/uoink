from test_projection import *
import copy,json,pytest
from library_work import RequestContext

def accept_run(svc,ctx,run_id,choices):
    while True:
        claimed=svc.claim_work(ctx,dict(action='claim',run_id=run_id,client_id='client'))
        assert claimed['ok'],claimed
        if not claimed['work']:break
        for w in claimed['work']:
            a=submission(w,run_id+'-'+w['video_id'])
            if w['video_id'] in choices:
                second=copy.deepcopy(a['result']['memberships'][0]);second.update(shelf_id='s2',shelf_path=['Other'])
                a['result']['memberships'].append(second)
            result=svc.submit_result(ctx,a)
            assert result['outcome']=='accepted',result

def test_distinct_item_churn_and_approval():
    root,idx,svc,ctx,clock=fixture()
    ids=['fixture']+[f'item-{n}' for n in range(6)]
    for video_id in ids[1:]:
        item=idx.get_yoink('fixture');item.update(video_id=video_id,slug=video_id)
        idx.upsert_yoink(item)
        with idx.write_transaction() as c:c.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,0,0,10,'Original source evidence.')",(video_id,))
    for run_id in ['base','change']:
        assert svc.prepare_run(ctx,dict(run_id=run_id,version_id='v1',video_ids=ids,prompt_hash='0'*64))['ok']
    accept_run(svc,ctx,'base',set())
    svc.librarian_apply_enabled=True
    p=svc.preview_apply(ctx,dict(run_id='base',expected_projection_revision=0,activate_version=True))
    a=dict(preview_id=p['preview_id'],delta_hash=p['delta_hash'],operation_key='base',expected_projection_revision=0)
    assert svc.approve_preview(ctx,a)['ok']
    assert svc.apply_preview(ctx,dict(mode='apply',**a))['ok']
    accept_run(svc,ctx,'change',{'fixture','item-0'})
    p=svc.preview_apply(ctx,dict(run_id='change',expected_projection_revision=1))
    assert p['changed_items']==2 and p['baseline_items']==7,p
    assert len(p['summary']['changed_item_ids'])==2
    a=dict(preview_id=p['preview_id'],delta_hash=p['delta_hash'],operation_key='change',expected_projection_revision=1)
    assert svc.approve_preview(ctx,a)['error']['code']=='churn_limit'
    assert svc.apply_preview(ctx,dict(mode='apply',**a,max_churn=100))['error']['code']=='validation_error'
    assert svc.approve_preview(ctx,dict(a,approved_churn_percent=29))['ok']
    result=svc.apply_preview(ctx,dict(mode='apply',**a))
    assert result['ok'],result
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==9
    idx.close()

def test_full_card_and_unicode_quote():
    root,idx,svc,ctx,clock=fixture()
    w=claim(svc,ctx)
    a=submission(w)
    full=svc._card(idx._conn,'fixture','full')
    a['result']['memberships'][0]['evidence'].update(basis='fetched_full',card_hash=full['card_hash'],quote='source  \n evidence')
    result=svc.submit_result(ctx,a)
    assert result['outcome']=='accepted',result
    assert result['accepted_memberships'][0]['evidence']['start']==0
    idx.close()

@pytest.mark.parametrize('source_type,accepted',[('page',True),('video',False)])
def test_text_provenance(tmp_path,source_type,accepted):
    root,idx,svc,ctx,clock=fixture()
    corpus=tmp_path/'source.md';corpus.write_text('Original source evidence.')
    item=idx.get_yoink('fixture');item.update(corpus_path=str(corpus),source_type=source_type)
    idx.upsert_yoink(item)
    with idx.write_transaction() as c:c.execute('DELETE FROM clips')
    assert svc.refresh_run_item(ctx,dict(run_id='r1',video_id='fixture',reason='text fixture'))['ok']
    w=claim(svc,ctx);a=submission(w)
    a['result']['memberships'][0]['evidence']['kind']='text_only'
    result=svc.submit_result(ctx,a)
    assert (result['outcome']=='accepted')==accepted,result
    if accepted:assert result['accepted_memberships'][0]['evidence']['start'] is None
    idx.close()

def test_preview_alteration_and_pin_invalidation():
    root,idx,svc,ctx,clock=accepted()
    a,p=approved(svc,ctx)
    svc.librarian_apply_enabled=True
    with idx.write_transaction() as c:c.execute("UPDATE library_previews SET forward_json='{}'")
    assert svc.apply_preview(ctx,a)['error']['code']=='preview_conflict'
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0
    a,p=approved(svc,ctx)
    pin=svc.pin_shelf(ctx,intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='pin',expected_projection_revision=0,operation_key='pin')))
    assert pin['ok']
    assert not svc.apply_preview(ctx,a)['ok']
    assert idx._conn.execute('SELECT COUNT(*) FROM library_proposals').fetchone()[0]==0
    assert idx._conn.execute('SELECT disposition FROM library_manifest').fetchone()[0]=='pinned'
    idx.close()
