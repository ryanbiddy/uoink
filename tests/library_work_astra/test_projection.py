from test_substrate import *

def accepted():
    root,idx,svc,ctx,clock=fixture()
    w=claim(svc,ctx)
    s=svc.submit_result(ctx,submission(w))
    assert s['outcome']=='accepted',s
    return root,idx,svc,ctx,clock

def approved(svc,ctx,rev=0,key='apply1',activate=True):
    p=svc.preview_apply(ctx,dict(run_id='r1',expected_projection_revision=rev,activate_version=activate))
    assert p['ok'],p
    a=dict(preview_id=p['preview_id'],delta_hash=p['delta_hash'],operation_key=key,expected_projection_revision=rev)
    r=svc.approve_preview(ctx,a)
    assert r['ok'],r
    return dict(mode='apply',**a),p

def intent(svc,ctx,kind,op):
    result=svc.mint_user_intent(ctx,dict(kind=kind,operation=op))
    assert result['ok'],result
    return dict(op,user_intent_token=result['user_intent_token'])

def test_stage_b():
    root,idx,svc,ctx,clock=accepted()
    a,p=approved(svc,ctx)
    assert p['initial_filing'] and p['baseline_items']==0
    assert idx._conn.execute('SELECT COUNT(*) FROM item_shelves').fetchone()[0]==0
    assert svc.apply_preview(ctx,a)['error']['code']=='apply_disabled'
    svc.librarian_apply_enabled=True
    r=svc.apply_preview(ctx,a)
    assert r['ok'] and r['after_revision']==1,r
    assert svc.apply_preview(ctx,a)==r
    assert idx._conn.execute('SELECT topic FROM yoinks').fetchone()[0]=='Old'
    op=dict(video_id='fixture',shelf_id='s2',action='move',expected_projection_revision=1,operation_key='move1')
    pin=svc.pin_shelf(ctx,intent(svc,ctx,'pin',op))
    assert pin['ok'] and pin['after_revision']==2,pin
    assert idx._conn.execute('SELECT shelf_id,locked,confidence FROM item_shelves').fetchone()[:]==('s2',1,None)
    assert idx._conn.execute('SELECT exclusive_move FROM library_item_policy').fetchone()[0]==1
    bad=svc.mint_user_intent(ctx,dict(kind='pin',operation=dict(op,shelf_id='s1',action='pin',operation_key='bad',expected_projection_revision=2)))
    assert bad['error']['code']=='exclusive_move_conflict',bad
    u=intent(svc,ctx,'undo',dict(apply_id=pin['apply_id'],expected_projection_revision=2,operation_key='undo1'))
    undone=svc.undo_apply(ctx,u)
    assert undone['ok'] and undone['after_revision']==3,undone
    assert svc.undo_apply(ctx,u)==undone
    assert idx._conn.execute('SELECT shelf_id,locked FROM item_shelves').fetchone()[:]==('s1',0)
    assert idx._conn.execute('SELECT COUNT(*) FROM library_item_policy').fetchone()[0]==0
    recovered=svc.recover_operations(ctx,{})
    assert recovered['ok'] and recovered['replayed']==0,recovered
    export=svc.export_library_state(ctx,{})
    assert export['ok'] and len(export['records'])==3,export
    assert idx._conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert idx._conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    idx.close()

if __name__=='__main__':
    test_stage_b()
    print('Stage B passed: initial filing preview, default-off apply, approved apply/retry, exclusive move, inverse undo/retry, replay, export, FK/integrity.')
