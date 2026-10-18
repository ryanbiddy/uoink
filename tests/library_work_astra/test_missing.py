from test_durable import *

def test_missing_entire_journal_after_db_loss():
    root,idx,svc,ctx,clock=fixture()
    args=intent(svc,ctx,'pin',dict(video_id='fixture',shelf_id='s1',action='pin',expected_projection_revision=0,operation_key='missing'))
    assert svc.pin_shelf(ctx,args)['ok']
    idx.close()
    # Rename inside the fixture, preserving evidence while simulating missing records.
    journal=root/'library'/'journal'
    assert journal.resolve().is_relative_to(Path('tests/library_work_astra/_work').resolve())
    journal.rename(root/'library'/'journal-hidden')
    fresh=Index.open(root/'empty.db')
    result=fresh.library_service().startup_status
    assert not result['ok'] and result['error']['code']=='recovery_conflict',result
    fresh.close()
