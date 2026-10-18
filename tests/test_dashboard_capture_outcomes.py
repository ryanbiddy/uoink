"""Exercise ledger outcomes and the actual dashboard renderer without a helper."""
import json
from pathlib import Path
import subprocess

import pytest

from tests.source_subscriptions_fixtures import (
    FakeAdapter, make_service, open_index, register, snapshot, status, turn_on,
)

ROOT = Path(__file__).resolve().parents[1]


def render(source):
    # Execute the product's functions, rather than reimplementing escaping in Python.
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const escapeStart = page.indexOf('    function htmlEscape(');
const escapeEnd = page.indexOf('\n    }', escapeStart) + 6;
const start = page.indexOf('    function renderStandingSubscriptions()');
const end = page.indexOf('    const CLASSIFICATION_LABELS', start);
if ([escapeStart, escapeEnd, start, end].some(n => n < 0)) throw Error('Missing product renderer');
const list = {innerHTML: '', querySelectorAll: () => []};
const context = {state: {standingSources: [input]},
  els: {standingSubscriptionList: list, standingSummaryBar: {} }};
vm.createContext(context);
vm.runInContext(page.slice(escapeStart, escapeEnd) + '\n' + page.slice(start, end)
  + '\nrenderStandingSubscriptions();', context);
process.stdout.write(list.innerHTML);
'''
    result = subprocess.run(['node', '-e', script], input=json.dumps(source),
                            cwd=ROOT, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture
def source_env(tmp_path):
    idx = open_index(tmp_path)
    service = make_service(idx, adapter=FakeAdapter([snapshot(['one'])]))
    sid = register(service)['source_id']
    turn_on(service, sid)
    service.detection_pass()
    yield service, sid
    idx.close()


def test_uncertain_ledger_is_visibly_uncertain(source_env):
    service, sid = source_env
    claim = service.claim_start(sid)
    service.mark_started(claim['start_id'], claim['owner_token'])
    service.mark_uncertain(claim['start_id'], claim['owner_token'])
    source = status(service, sid)['source']
    assert source['capture_outcome'] == 'uncertain'
    assert source['current_item']['start_state'] == 'uncertain'
    assert 'Capture: uncertain<' in render(source)


def test_unstarted_block_is_not_a_failed_capture(source_env):
    service, sid = source_env
    with service.store.write() as conn:
        conn.execute("UPDATE source_items SET blocked_reason='capture_in_progress_elsewhere' WHERE source_id=?", (sid,))
    source = status(service, sid)['source']
    assert source['capture_outcome'] == 'blocked'
    assert source['current_item']['actual_starts'] == 0
    markup = render(source)
    assert 'Capture: waiting<' in markup
    assert 'attempt 0/3' in markup
    assert 'settled failed' not in markup


@pytest.mark.parametrize(('outcome', 'label'), [
    ('idle', 'idle'), ('released', 'reservation released'),
    ('succeeded', 'completed'), ('archived', 'archived'),
    ('uncertain', 'uncertain'), ('blocked', 'waiting'),
    ('settled_failed', 'settled failed'), ('in_flight', 'in-flight'),
])
def test_renderer_uses_latest_outcome_not_historical_count(outcome, label):
    source = {'source_id': 'src_test', 'consent_state': 'on', 'revision': 3,
              'capture_outcome': outcome, 'item_counts': {'committed': 9},
              'allowance': {'remaining': 9}}
    assert f'Capture: {label}<' in render(source)


def test_actual_renderer_escapes_recovery_fields():
    hostile = '\"><img src=x onerror=alert(1)>'
    source = {'source_id': 'src_test', 'consent_state': 'on', 'revision': 4,
              'capture_outcome': 'settled_failed', 'recovery_reason': hostile,
              'display_name': hostile, 'canonical_url': hostile,
              'current_item': {'title': hostile, 'state': hostile,
                               'start_state': hostile, 'actual_starts': 1}}
    markup = render(source)
    assert '<img src=x' not in markup
    assert '&lt;img src=x onerror=alert(1)&gt;' in markup
    assert 'rev 4<' in markup
    assert 'Detection: healthy<' in markup


def test_consent_off_does_not_hide_uncertain_drain():
    source = {'source_id': 'src_test', 'consent_state': 'off', 'revision': 2,
              'capture_outcome': 'draining', 'in_flight': [{'state': 'uncertain'}]}
    assert 'Capture: draining; outcome uncertain<' in render(source)
