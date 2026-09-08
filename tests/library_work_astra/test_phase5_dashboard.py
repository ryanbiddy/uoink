"""Execute the shipped activity JavaScript with a disposable DOM/transport double.

No browser, HTTP listener, model, helper or live index is used.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BOOT = r"""
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const first = html.indexOf('    const libraryActivityState =');
const last = html.indexOf('    async function loadStandingSubscriptions()', first);
if (first < 0 || last < first) throw Error('Activity script not found');
const nodes = new Map();
const document = {
  hidden: false,
  activeElement: null,
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, {
      id, textContent: '', innerHTML: '', disabled: false, style: {}, dataset: {},
      classList: {add() {}, remove() {}, contains() {return false;}},
      addEventListener() {},
      focus() {document.activeElement = this;},
      querySelector() {return null;}, querySelectorAll() {return [];}
    });
    return nodes.get(id);
  },
  querySelectorAll() {return [];}, addEventListener() {}
};
const calls = [];
let replies = [];
class FixedDate extends Date {
  constructor(...args) {super(...(args.length ? args : ['2026-09-08T12:00:00.123Z']));}
  static now() {return Date.parse('2026-09-08T12:00:00.123Z');}
}
const context = vm.createContext({
  document, URL, Date:FixedDate,
  window: {addEventListener() {}},
  setInterval() {return 1;}, clearInterval() {},
  callRegistryTool: async (name, args) => {calls.push({name, args}); return replies.shift();}
});
vm.runInContext(html.slice(first, last), context);
const run = code => vm.runInContext(code, context);
const packet = {
  ok: true, report_revision: 'a'.repeat(64), as_of: '2026-09-08T12:00:00.000Z',
  date_basis: 'capture_time',
  interval: {start:'2026-09-05T00:00:00.000Z', end:'2026-09-06T00:00:00.000Z'},
  items: {total:{value:1}, coverage_ref:'cov_capture'},
  coverage: {cov_capture:{coverage_status:'retained_records'}},
  shelf_activity: {}, sources: {}, events: {}, warnings: []
};
context.fixturePacket = packet;
run('libraryActivityState.packet = fixturePacket;');
"""


def execute(body):
    script = BOOT + "\n(async () => {\n" + body + "\n})().catch(e => {console.error(e); process.exitCode=1;});"
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("days", [1, 7, 30])
def test_phase5_dashboard_preset_produces_valid_utc_bounds(days):
    value = execute(f"console.log(JSON.stringify(run('getRollingUtcInterval({days})')));")
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", v) for v in value.values()), value


def test_phase5_dashboard_stale_evidence_requests_new_summary_and_disables_old_pages():
    value = execute("""
      replies = [{ok:false,error:{code:'stale_report',message:'changed'}}, packet];
      await run("fetchActivityEvidence('items.total', 20)");
      console.log(JSON.stringify({calls, disabled:document.getElementById('evidenceNextPageBtn').disabled}));
    """)
    assert len(value["calls"]) == 2, value
    assert "detail" not in value["calls"][1]["args"]
    assert value["disabled"] is True


def test_phase5_dashboard_failed_refresh_disables_old_evidence():
    value = execute("""
      replies = [{ok:false,error:{code:'storage_unavailable',message:'offline'}}];
      await run('loadLibraryActivity(true)');
      await run("fetchActivityEvidence('items.total', 20)");
      console.log(JSON.stringify({calls, stale:run('libraryActivityState.stale')}));
    """)
    assert value["stale"] is True, value
    assert len(value["calls"]) == 1


def test_phase5_dashboard_unknown_historical_total_is_not_rendered_zero():
    value = execute("""
      packet.items.total = {value:null, recorded_count:0};
      packet.coverage.cov_capture.coverage_status = 'no_history';
      run('renderLibraryActivityUI()');
      console.log(JSON.stringify({total:document.getElementById('activityTotalItems').textContent}));
    """)
    assert value["total"] == "Unavailable"


def test_phase5_dashboard_escapes_evidence_error_text():
    value = execute("""
      replies = [{ok:false,error:{code:'invalid_source_data',message:'<img src=x onerror=alert(1)>'}}];
      await run("fetchActivityEvidence('items.total')");
      console.log(JSON.stringify({html:document.getElementById('evidenceRowsContainer').innerHTML}));
    """)
    assert "<img" not in value["html"]
    assert "&lt;img" in value["html"]


def test_phase5_dashboard_opening_evidence_moves_keyboard_focus():
    value = execute("""
      replies = [{ok:true,rows:[],total_rows:0,report_revision:packet.report_revision}];
      await run("fetchActivityEvidence('items.total')");
      console.log(JSON.stringify({focus:document.activeElement?.id || null}));
    """)
    assert value["focus"] is not None
