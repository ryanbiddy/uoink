"""BA-3 dashboard continuations and overlapping-request regressions.

Executes shipped JavaScript through the existing isolated Node/DOM test adapter.
"""
from test_phase5_dashboard2 import execute


def test_phase5_ba3_evidence_uses_returned_continuation():
    result = execute("""
      run('wireLibraryActivityEvents();');
      replies = [{ok:true, rows:Array.from({length:5},(_,i)=>({row_id:String(i)})), total_rows:30,
        next:{detail:'evidence',metric_id:'items.total',offset:5,limit:20,interval:packet.interval,expected_revision:packet.report_revision}}];
      await run("fetchActivityEvidence('items.total',0)");
      replies = [{ok:true,rows:[],total_rows:30,next:null}];
      document.getElementById('evidenceNextPageBtn').listeners.click();
      await Promise.resolve();
      console.log(JSON.stringify({offset:calls[1].args.offset}));
    """)
    assert result["offset"] == 5, result


def test_phase5_ba3_latest_page_of_same_metric_wins():
    result = execute("""
      let first,second;
      replies = [new Promise(r=>first=r),new Promise(r=>second=r)];
      const one=run("fetchActivityEvidence('items.total',0)");
      const two=run("fetchActivityEvidence('items.total',20)");
      second({ok:true,rows:[{row_id:'new_page'}],total_rows:50}); await two;
      first({ok:true,rows:[{row_id:'old_page'}],total_rows:50}); await one;
      console.log(JSON.stringify({row:run('libraryActivityState.evidenceRows[0].row_id'),offset:run('libraryActivityState.evidenceOffset')}));
    """)
    assert result == {"row": "new_page", "offset": 20}, result


def test_phase5_ba3_latest_collection_page_wins():
    result = execute("""
      let first,second;
      replies = [new Promise(r=>first=r),new Promise(r=>second=r)];
      const one=run("fetchActivityCollection('creator_hints',20)");
      const two=run("fetchActivityCollection('creator_hints',40)");
      second({ok:true,rows:[{hint:'new_page',count:{value:1}}],total_rows:60}); await two;
      first({ok:true,rows:[{hint:'old_page',count:{value:1}}],total_rows:60}); await one;
      console.log(JSON.stringify({offset:run('libraryActivityState.collectionOffsets.creator_hints'),html:document.getElementById('activityHintsBody').innerHTML}));
    """)
    assert result["offset"] == 40 and "new_page" in result["html"], result


def test_phase5_ba3_obsolete_metric_response_does_not_disable_current_pager():
    result = execute("""
      let old;
      replies = [new Promise(r=>old=r),{ok:true,rows:[{row_id:'new'}],total_rows:50}];
      const pending=run("fetchActivityEvidence('items.total',0)");
      await run("fetchActivityEvidence('shelf_activity.current_memberships',0)");
      const before=document.getElementById('evidenceNextPageBtn').disabled;
      old({ok:true,rows:[],total_rows:0}); await pending;
      console.log(JSON.stringify({before,after:document.getElementById('evidenceNextPageBtn').disabled}));
    """)
    assert result == {"before": False, "after": False}, result


def test_phase5_ba3_obsolete_failure_does_not_replace_current_evidence():
    result = execute("""
      let rejectOld;
      replies = [new Promise((r,j)=>rejectOld=j),{ok:true,rows:[{row_id:'new',source_key:'CURRENT'}],total_rows:1}];
      const pending=run("fetchActivityEvidence('items.total',0)");
      await run("fetchActivityEvidence('shelf_activity.current_memberships',0)");
      rejectOld(Error('obsolete request failure')); await pending;
      console.log(JSON.stringify({html:document.getElementById('evidenceRowsContainer').innerHTML}));
    """)
    assert "CURRENT" in result["html"] and "obsolete request failure" not in result["html"], result


def test_phase5_ba3_displayed_exclusions_have_evidence_links():
    result = execute("""
      packet.items.capture_time_unavailable={value:2,metric_id:'items.capture_time_unavailable'};
      packet.items.deleted_items_excluded={value:3,metric_id:'items.deleted_items_excluded'};
      run('renderLibraryActivityUI()');
      console.log(JSON.stringify({html:document.getElementById('activityExclusions').innerHTML,text:document.getElementById('activityExclusions').textContent}));
    """)
    for metric_id in ("items.capture_time_unavailable", "items.deleted_items_excluded"):
        assert f'data-metric-id="{metric_id}"' in result["html"], result


def test_phase5_ba3_publication_view_displays_publication_exclusions():
    result = execute("""
      packet.date_basis='publication_time';
      packet.items.capture_time_unavailable={value:0,metric_id:'capture_unavailable'};
      packet.items.publication_time_unavailable={value:7,metric_id:'publication_unavailable'};
      packet.items.deleted_items_excluded={value:0,metric_id:'deleted_excluded'};
      run('libraryActivityState.date_basis="publication_time"; renderLibraryActivityUI()');
      console.log(JSON.stringify({html:document.getElementById('activityExclusions').innerHTML,text:document.getElementById('activityExclusions').textContent}));
    """)
    assert "7" in result["html"] + result["text"], result
