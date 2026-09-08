"""AS-7: supplied-evidence audits and C21 classification-surface reproductions.

Evidence failures describe the retained package, not a failed capture. Never follow
receipt paths into another checkout. UI cases run only extracted dashboard functions
in a Node VM with injected API replies; they start no helper, browser or model.
The service pagination control uses the existing isolated Phase 3 fixture.
C22 requires Ryan's actual installed-build observations; no fixture substitutes for it.
"""

import ast
import hashlib
import json
import re
import shutil
import subprocess

import pytest

from test_phase3_publication import configure
from test_phase3_support import (
    MINUTE, ROOT, item_rows, migration_dir, observation, ok, phase3_isolation,
    phase3_module, rig, snapshot,
)

S20 = ROOT / 'docs/library/proof/s20-2026-09-08'
S21 = ROOT / 'docs/library/proof/s21-2026-09-08'
AT6 = S21 / 'receipt-at6-candidate-1830b7a.json'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def retained_files():
    return [p for p in S21.rglob('*') if p.is_file()]


@pytest.mark.parametrize('folder', [S20, S21], ids=['s20', 's21'])
def test_as7_supplied_manifest_matches_bytes(folder):
    for line in (folder / 'SHA256SUMS').read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        path = (folder / relative.strip()).resolve()
        assert path.is_relative_to(folder.resolve())
        assert digest_bytes(path.read_bytes()) == expected, relative


def test_as7_c20_refresh_error_dump_matches_observed_screenshot():
    """03's JPG shows 2/10 starts, http_500, and 1 consecutive failure.

    These are manually transcribed observations of the supplied image, not OCR
    or invented service output. Compare its named state partner without mutation.
    """
    text = (S20 / '03-refresh-error.state.txt').read_text(encoding='utf-8-sig')
    starts = ast.literal_eval(re.search(r"starts (\[.*\])", text)[1])
    observed = {
        'charged': len(starts),
        'error': re.search(r'detection error (\S+)', text)[1],
        'failures': re.search(r'failures (\S+)', text)[1],
    }
    expected = {'charged': 2, 'error': 'http_500', 'failures': '1'}
    assert observed == expected, {'dump': observed, 'screenshot': expected}


def test_as7_c21_executed_launcher_bytes_are_retained():
    receipt = read_json(AT6)
    expected = receipt['input_hashes'][r'tests\library_work_astra\test_phase3_s21.py']
    paths = [ROOT / 'tests/library_work_astra/test_phase3_s21.py', *retained_files()]
    hashes = {digest_bytes(p.read_bytes()) for p in paths}
    hashes.update(digest_bytes(p.read_bytes().replace(b'\r\n', b'\n')) for p in paths)
    assert expected in hashes, f'No retained bytes match executed launcher SHA256 {expected}'


def test_as7_c21_at6_receipt_records_process_exit_status():
    receipt = read_json(AT6)
    exits = {key: receipt[key] for key in ('exit_code', 'returncode', 'process_exit_code')
             if key in receipt}
    assert exits and all(type(value) is int and value == 0 for value in exits.values()), (
        'Retained AT6 receipt has no explicit successful process exit status', exits)


def test_as7_c21_all_at6_artifact_bytes_are_archived():
    receipt = read_json(AT6)
    hashes = {digest_bytes(p.read_bytes()) for p in retained_files()}
    missing = [name for name, expected in receipt['artifact_hashes'].items()
               if expected not in hashes]
    assert missing == [], {'missing_artifacts': missing}


@pytest.mark.parametrize('feed_port', [64703, 49557], ids=['at6-browser', 'c21-pill-browser'])
def test_as7_c21_browser_run_has_retained_receipt_and_database(feed_port):
    """Ports are visible in the retained AT6 and new C21 Sources screenshots."""
    receipts = [read_json(p) for p in S21.glob('*.json')]
    matching = [r for r in receipts if r.get('feed_url') == f'http://127.0.0.1:{feed_port}/feed.xml']
    assert matching, {'missing_browser_run_feed_port': feed_port,
                      'retained_feed_urls': [r.get('feed_url') for r in receipts]}
    db_hashes = {digest_bytes(p.read_bytes()) for p in S21.glob('*.db')}
    assert any(r.get('evidence_sha256') in db_hashes for r in matching)


def run_dashboard(body):
    """Execute production rendering/loading functions with fixture-only globals."""
    node = shutil.which('node')
    assert node, 'Node is required for the AS-7 dashboard reproductions'
    html = (ROOT / 'assets/dashboard/index.html').read_text(encoding='utf-8')
    escape = html[html.index('    function htmlEscape('):html.index('    const FOCUSABLE_SELECTOR')]
    source = html[html.index('    const CLASSIFICATION_LABELS ='):html.index('    async function startConsentFlow(')]
    program = "const vm = require('node:vm');\n" + 'const code = ' + json.dumps(
        escape + source + '\n(async () => {\n' + body + '\n})()') + ";\n"
    program += """
const context = {
  state: {}, renderStandingSubscriptions: () => {},
  consentErrorMessage: (error) => String(error),
};
Promise.resolve(vm.runInNewContext(code, context, {timeout: 5000}))
  .then(value => process.stdout.write(JSON.stringify(value)))
  .catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""
    result = subprocess.run([node, '-'], input=program, text=True, encoding='utf-8',
                            capture_output=True, cwd=ROOT, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('classification', ['waiting_for_client', 'accepted'])
def test_as7_c21_classification_does_not_claim_unapplied_shelving(classification):
    rendered = run_dashboard('return renderCapturedItems({items: [' + json.dumps({
        'title': 'Captured fixture', 'capture_state': 'committed',
        'classification': {'state': classification},
    }) + ']});')
    if classification == 'waiting_for_client':
        assert 'Waiting for client (unfiled)' in rendered
    else:
        # Contract line 725: accepted describes staging, not applied shelving.
        assert not re.search(r'>\s*Filed\s*</span>', rendered), rendered


def test_as7_c21_waiting_item_after_first_page_is_reachable():
    """A source can have 25 older uncommitted rows and a captured 26th row."""
    observed = run_dashboard("""
const calls = [];
const waiting = {entry_id: 'new-episode', title: 'Newly captured episode',
  capture_state: 'committed', classification: {state: 'waiting_for_client'}};
callRegistryTool = async (name, args) => {
  calls.push({name, args});
  return args.item_cursor ? {items: [waiting], next_item_cursor: null} : {
    items: Array.from({length: 25}, (_, n) => ({entry_id: `old-${n}`,
      capture_state: 'eligible', classification: {state: 'not_captured'}})),
    next_item_cursor: 'fixture-page-two',
  };
};
await toggleCapturedItems('src_fixture');
return {calls, html: renderCapturedItems(state.standingItemsBySource.src_fixture)};
""")
    # Either load further pages or offer a control that can reach them.
    visible = 'Waiting for client (unfiled)' in observed['html']
    pager = bool(re.search(r'<(?:button|a)\b', observed['html']))
    assert visible or pager, observed


def test_as7_c21_service_can_put_only_waiting_capture_on_page_two(rig):
    """Passing service control for the API replies injected into the UI failure."""
    configure(rig)
    sid = rig.register()
    rig.feed.responses[sid] = snapshot([observation(n) for n in range(25)])
    rig.svc.poll_source(sid)  # Metadata discovered while off.
    rig.consent(sid, 'on')
    rig.clock.advance(16 * MINUTE)
    rig.svc.poll_source(sid)  # Initial cohort; do not capture yet.
    rig.clock.advance(16 * MINUTE)
    rig.feed.responses[sid] = snapshot([observation(n) for n in range(26)])
    rig.svc.poll_source(sid)
    newest = next(item for item in item_rows(rig.idx, sid)
                  if item['entry_id'] == observation(25)['entry_id'])
    rig.complete(rig.start(sid, newest))
    rig.svc.dispatch_classification()
    first = ok(rig.svc.source_status(rig.context, {'source_id': sid, 'item_limit': 25}))
    assert first['source']['item_counts']['committed'] == 1
    assert all(i['capture_state'] != 'committed' for i in first['items'])
    second = ok(rig.svc.source_status(rig.context, {
        'source_id': sid, 'item_limit': 25, 'item_cursor': first['next_item_cursor']}))
    assert second['items'][0]['classification']['state'] == 'waiting_for_client'
