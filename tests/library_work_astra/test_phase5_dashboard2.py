"""BA-2 executable dashboard races, pagination and keyboard checks.

Runs shipped JS in Node with an isolated DOM/transport double; no browser or port.
"""
import json
import subprocess

import pytest

from test_phase5_dashboard import BOOT, ROOT


BOOT2 = BOOT.replace(
    "const nodes = new Map();", "const nodes = new Map(); const windowListeners = {}; const documentListeners = {}; const timers = [];"
).replace(
    "addEventListener() {},\n      focus()", "listeners: {}, addEventListener(kind, fn) {this.listeners[kind] = fn;},\n      focus()"
).replace(
    "querySelectorAll() {return [];}, addEventListener() {}", "querySelectorAll() {return [];}, addEventListener(kind, fn) {documentListeners[kind] = fn;}"
).replace(
    "window: {addEventListener() {}}", "window: {addEventListener(kind, fn) {windowListeners[kind] = fn;}}"
).replace(
    "setInterval() {return 1;}, clearInterval() {}", "setInterval(fn, ms) {timers.push({fn, ms, cleared:false}); return timers.length;}, clearInterval(id) {timers[id-1].cleared = true;}"
)


def execute(body):
    script = BOOT2 + "\n(async () => {\n" + body + "\n})().catch(e => {console.error(e); process.exitCode=1;});"
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_phase5_ba2_dashboard_refresh_disables_evidence_while_loading():
    result = execute("""
      let finish;
      replies = [new Promise(resolve => finish = resolve)];
      const pending = run('loadLibraryActivity(true)');
      const callable = run('activityEvidenceCallable()');
      finish(packet); await pending;
      console.log(JSON.stringify({callable}));
    """)
    assert result["callable"] is False, result


def test_phase5_ba2_dashboard_discards_evidence_arriving_after_invalidation():
    result = execute("""
      let finish;
      replies = [new Promise(resolve => finish = resolve)];
      const pending = run("fetchActivityEvidence('items.total', 0)");
      run('libraryActivityState.stale=true; invalidateActivityEvidence();');
      finish({ok:true,rows:[{row_id:'old'}],total_rows:21,report_revision:packet.report_revision});
      await pending;
      console.log(JSON.stringify({rows:run('libraryActivityState.evidenceRows'),next:document.getElementById('evidenceNextPageBtn').disabled}));
    """)
    assert result == {"rows": [], "next": True}, result


def test_phase5_ba2_dashboard_latest_refresh_wins():
    result = execute("""
      let first, second;
      replies = [new Promise(resolve => first=resolve),new Promise(resolve => second=resolve)];
      const one = run('loadLibraryActivity(true)');
      const two = run('loadLibraryActivity(true)');
      const fresh = {...packet,report_revision:'b'.repeat(64)};
      second(fresh); await two; first(packet); await one;
      console.log(JSON.stringify({revision:run('libraryActivityState.packet.report_revision')}));
    """)
    assert result["revision"] == "b" * 64, result


def test_phase5_ba2_dashboard_collection_uses_returned_continuation():
    result = execute("""
      packet.items.by_creator_hint = Array.from({length:5},()=>({hint:'x',count:{value:1}}));
      packet.pagination = {creator_hints:{total_rows:25,returned_rows:5,omitted_rows:20,next:{detail:'creator_hints',offset:5,limit:20,interval:packet.interval,expected_revision:packet.report_revision}}};
      run('renderLibraryActivityUI(); wireActivityCollectionPager("creator_hints", "activityHints");');
      replies = [{ok:true,rows:[],total_rows:25}];
      document.getElementById('activityHintsNextBtn').listeners.click();
      await Promise.resolve();
      console.log(JSON.stringify({calls}));
    """)
    assert result["calls"][0]["args"]["offset"] == 5, result


@pytest.mark.parametrize("kind", ["daily_share", "shelf_start", "shelf_end", "shelf_churn"])
def test_phase5_ba2_dashboard_all_displayed_metrics_have_evidence_links(kind):
    result = execute("""
      context.rows = [{bucket_start:'2026-09-05',count:{value:1,metric_id:'daily_count'},share:{percent:100,metric_id:'daily_share'}}];
      run('renderActivityDaily(rows)');
      context.rows = [{shelf_id:'alpha',current_size:{value:1,metric_id:'current'},start_size:{value:1,metric_id:'shelf_start'},end_size:{value:1,metric_id:'shelf_end'},churn:{percent:0,metric_id:'shelf_churn'}}];
      run('renderActivityShelves(rows)');
      console.log(JSON.stringify({html:document.getElementById('activityDailyBody').innerHTML+document.getElementById('activityShelvesBody').innerHTML}));
    """)
    assert f'data-metric-id="{kind}"' in result["html"]


def test_phase5_ba2_dashboard_modal_trap_includes_item_buttons():
    result = execute("""
      document.getElementById('activityEvidenceModal').classList.contains = () => false;
      const viewItem = document.getElementById('dynamicViewItem');
      document.getElementById('evidencePrevPageBtn').disabled = true;
      document.getElementById('evidenceNextPageBtn').disabled = true;
      document.getElementById('evidenceRowsContainer').querySelectorAll = () => [viewItem];
      document.getElementById('activityEvidenceModal').querySelectorAll = () => [document.getElementById('closeEvidenceBtn'),document.getElementById('evidenceRowsContainer'),viewItem];
      viewItem.focus(); let prevented = false;
      context.event = {key:'Tab',shiftKey:false,preventDefault(){prevented=true;}};
      run('trapActivityEvidenceKeys(event)');
      console.log(JSON.stringify({prevented,focus:document.activeElement.id}));
    """)
    assert result == {"prevented": True, "focus": "closeEvidenceBtn"}, result


def test_phase5_ba2_dashboard_focus_and_visible_timer_refresh_without_hidden_reads():
    result = execute("""
      document.getElementById('tab-library').classList.contains = key => key==='active';
      run('wireLibraryActivityEvents(); startLibraryActivityTimer();');
      replies=[packet,packet]; windowListeners.focus(); await Promise.resolve();
      timers[0].fn(); await Promise.resolve();
      const visibleCalls = calls.length;
      document.hidden=true; documentListeners.visibilitychange();
      windowListeners.focus(); timers[0].fn(); await Promise.resolve();
      console.log(JSON.stringify({ms:timers[0].ms,cleared:timers[0].cleared,visibleCalls,allCalls:calls.length}));
    """)
    assert result == {"ms": 60000, "cleared": True, "visibleCalls": 2, "allCalls": 2}, result
