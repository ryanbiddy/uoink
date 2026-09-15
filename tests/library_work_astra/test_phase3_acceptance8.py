"""AS-8 audits of the superseding S20 scenario 03 and S21 at7 package.

Read retained evidence only within this checkout. Historical receipt paths are
identifiers, never paths to open. The dashboard checks use AS-7's Node VM runner;
no helper, browser, acquisition, client or model is started. AS-7 stays unchanged.
"""

from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3

import pytest

from test_phase3_acceptance7 import run_dashboard
from test_phase3_support import ROOT


S20 = ROOT / 'docs/library/proof/s20-2026-09-08'
S21 = ROOT / 'docs/library/proof/s21-2026-09-08'
RECEIPT = S21 / 'receipt-at7-candidate-1d9e438.json'
RECORD = S21 / 'run-record-at7-candidate-1d9e438.json'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained(folder, relative):
    path = (folder / relative.replace('\\', '/')).resolve()
    assert path.is_relative_to(folder.resolve()), relative
    return path


@pytest.mark.parametrize('folder', [S20, S21], ids=['s20', 's21'])
def test_as8_supplied_manifest_matches_bytes(folder):
    problems = []
    for line in (folder / 'SHA256SUMS').read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        path = retained(folder, relative.strip())
        if not path.is_file():
            problems.append((relative, 'missing'))
        elif digest(path) != expected:
            problems.append((relative, 'hash mismatch'))
    assert not problems, problems


def test_as8_c20_refresh_error_frozen_pair_matches_observed_screenshot():
    # Manually inspected AS-8 image: 1/10 today, 2 captures, 3/25 enrolled,
    # observed 3, http_500 / HTTP 500, 1 consecutive failure. Pin that image.
    assert digest(S20 / '03-refresh-error.jpg') == (
        '93c5f286db8f469ace426d99cc8df325e8bd258bcd0c77ab2c599d86da8709e6')
    before = read_json(S20 / '03-refresh-error.state.json')
    after = read_json(S20 / '03-refresh-error.state.after-screenshot.json')
    assert before.pop('observed_at_ms') < after.pop('observed_at_ms')
    assert before == after, 'Capture/detection state changed across the screenshot'
    source, = before['sources']
    sid = source['source_id']
    assert source['canonical_url'] == 'http://127.0.0.1:57992/feed.xml'
    status = before['source_status'][sid]
    public = status['source']
    cursor, = before['detection_cursors']
    assert cursor['source_id'] == sid == public['source_id']
    assert public['consent_state'] == source['consent_state'] == 'on'
    assert public['revision'] == source['revision'] == 1
    assert public['consent_epoch'] == source['consent_epoch'] == 1
    consent, = before['consent_receipts']
    assert before['receipts'] == 1 and consent['source_id'] == sid
    assert consent['new_state'] == 'on' and consent['after_revision'] == 1
    det = public['detection']
    assert det['error'] == {'code': 'http_500', 'message': 'HTTP 500'}
    assert cursor['last_error_code'] == det['error']['code']
    assert cursor['last_error_message'] == det['error']['message']
    assert det['consecutive_failures'] == cursor['error_count'] == 1
    assert det['last_poll_success_ms'] == cursor['last_poll_success_ms']
    assert det['last_poll_attempt_ms'] == cursor['last_poll_attempt_ms']
    assert det['last_poll_success_ms'] < det['last_poll_attempt_ms']
    assert det['observed_count'] == cursor['observed_count'] == 3
    allowance = public['allowance']
    day = datetime.fromtimestamp(before['clock_ms'] / 1000, timezone.utc).date().isoformat()
    assert day == allowance['utc_day'] == '2026-09-09'
    assert status['as_of_ms'] == before['clock_ms']
    starts = before['starts']
    assert len(starts) == 2 and all(s['source_id'] == sid for s in starts)
    assert all(s['state'] == 'succeeded' and s['started_at_ms'] is not None for s in starts)
    assert Counter(s['utc_day'] for s in starts) == {'2026-09-08': 1, '2026-09-09': 1}
    assert sum(s['utc_day'] == day for s in starts) == allowance['charged'] == 1
    assert (allowance['cap'], allowance['remaining'], allowance['reserved']) == (10, 9, 0)
    assert public['enrollment']['enrolled'] == source['back_catalog_enrolled'] == 3
    assert public['enrollment']['cap'] == 25
    items = before['items']
    assert len(items) == 3 and all(i['source_id'] == sid for i in items)
    assert Counter(i['state'] for i in items) == {'committed': 2, 'eligible': 1}
    assert public['item_counts']['committed'] == 2
    assert {i['item_id'] for i in status['items']} == {i['item_id'] for i in items}
    assert status['next_item_cursor'] is None
    for start in starts:
        item = next(i for i in items if i['item_id'] == start['item_id'])
        assert item['state'] == 'committed' and item['video_id'] == start['video_id']


def test_as8_c21_executed_launcher_bytes_are_retained():
    receipt, record = read_json(RECEIPT), read_json(RECORD)
    launcher = record['executed_launcher']
    path = retained(S21, launcher['retained_copy'])
    expected = receipt['input_hashes'][r'tests\library_work_astra\test_phase3_s21.py']
    assert digest(path) == launcher['sha256_raw'] == expected
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(raw).hexdigest() == launcher['sha256_lf']
    assert raw == (ROOT / 'tests/library_work_astra/test_phase3_s21.py').read_bytes().replace(b'\r\n', b'\n')


def test_as8_c21_run_record_records_process_exit_status():
    receipt, record = read_json(RECEIPT), read_json(RECORD)
    assert retained(S21, record['receipt']) == RECEIPT.resolve()
    assert type(record['exit_code']) is int and record['exit_code'] == 0
    assert record['command'] == receipt['command']
    assert record['command'][1:] == [
        '-B', 'tests/library_work_astra/test_phase3_s21.py', '--execute-s21', '--hold-seconds', '560']
    assert record['candidate_sha'] == receipt['candidate_sha']
    assert record['python'] == receipt['python']
    assert record['env']['PHASE3_REQUIRE_IMPLEMENTATION'] == '1'
    assert record['env']['ANTHROPIC_API_KEY'] == 'unset'
    assert record['env']['PYTHONPATH'] == record['cwd']
    assert record['data_root'] == receipt['root']
    start, end = (datetime.fromisoformat(record[k]) for k in ('started_utc', 'finished_utc'))
    assert 560 <= record['wall_seconds'] < 600
    assert abs((end - start).total_seconds() - record['wall_seconds']) < 0.1
    archive = retained(S21, record['artifact_archive'])
    stdout = retained(archive / 'logs', record['stdout']).read_text(encoding='utf-8-sig')
    assert stdout.rstrip().endswith('S21 receipt: ' + receipt['root'] + '\\receipt.json')
    assert retained(archive / 'logs', record['stderr']).is_file()


def test_as8_c21_all_at7_artifact_bytes_are_archived():
    receipt, record = read_json(RECEIPT), read_json(RECORD)
    archive = retained(S21, record['artifact_archive'])
    expected = {name.replace('\\', '/'): value for name, value in receipt['artifact_hashes'].items()}
    assert len(expected) == 9  # Seven requested artifacts, publication.json and the DB.
    assert expected.keys() == record['artifact_manifest'].keys()
    problems = []
    for name, wanted in expected.items():
        path = retained(archive, name)
        entry = record['artifact_manifest'][name]
        if not path.is_file():
            problems.append((name, 'missing', wanted))
            continue
        if not (digest(path) == wanted == entry['sha256']
                and path.stat().st_size == entry['bytes'] and entry['matches_receipt'] is True):
            problems.append((name, 'manifest/receipt/bytes mismatch'))
    assert not problems, problems


def test_as8_c21_browser_run_has_retained_receipt_and_database():
    receipt, record = read_json(RECEIPT), read_json(RECORD)
    browser = read_json(S21 / 'browser-observation-at7.json')
    assert browser['label'] == record['label'] == 'at7'
    assert browser['feed_url'] == record['feed_url'] == receipt['feed_url'] == 'http://127.0.0.1:59403/feed.xml'
    assert browser['dashboard_url'] == receipt['helper_url'] + '/dashboard'
    assert record['helper_url'] == receipt['helper_url'] == 'http://127.0.0.1:59404'
    # These are the inspected images, not OCR assertions or a new live browser run.
    images = {
        'dashboard-sources-waiting-for-client-at7.jpg': '41a541159f2943e42f88924b8742ffb85f794c7ad2d82f622b9df5b71922b6d0',
        'dashboard-library-unfiled-at7.jpg': 'c1310f2085f551020ebbb0b146507120ca53be576fb048ab411440df186968e2',
        'dashboard-item-detail-at7.jpg': '1d8265618eeadaa650d7fd7ba4d1e5590dfa7d847795dcaf74d3be3092376ddb',
    }
    assert images.keys() == browser['screenshots'].keys()
    assert all(digest(retained(S21, name)) == expected for name, expected in images.items())
    # The note's approximate 23:37 UTC is wrong. Its precise screenshot epochs
    # convert to 22:17:08.769, 22:17:26.076, 22:17:49.279 UTC, within the hold.
    epochs = re.findall(r'\b\d{13}\b', browser['observed_utc'])
    assert len(epochs) == 3
    start, end = (datetime.fromisoformat(record[k]) for k in ('started_utc', 'finished_utc'))
    assert all(start < datetime.fromtimestamp(int(ms) / 1000, timezone.utc) < end for ms in epochs)
    status = receipt['source_status']
    sid = status['source']['source_id']
    assert sid.startswith(browser['source_id_prefix'])
    assert status['source']['canonical_url'] == receipt['feed_url']
    assert status['source']['allowance']['charged'] == 1
    assert status['source']['item_counts']['committed'] == 1
    item, = status['items']
    assert item['title'] == 'S21 controlled capture'
    assert item['classification']['state'] == 'waiting_for_client'
    assert item['video_id'] == receipt['video_id']
    assert receipt['unfiled'] is True
    assert receipt['fixture_downloads'] == receipt['fixture_transcripts'] == 1
    assert receipt['model_calls'] == 0 and receipt['forbidden_attempts'] == []
    assert receipt['prepare_observations'] == [{'after_commit': True, 'video_id': receipt['video_id']}]
    db = retained(S21, record['evidence_db']['retained_copy'])
    assert digest(db) == record['evidence_db']['sha256'] == receipt['evidence_sha256']
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        for table in ('source_subscriptions', 'source_capture_starts', 'source_items',
                      'source_classification_outbox', 'library_work', 'library_runs',
                      'yoinks', 'podcast_episodes', 'citations', 'clips'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 1, table
        for table in ('library_attempts', 'item_shelves'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
        source = conn.execute('SELECT * FROM source_subscriptions').fetchone()
        assert source['source_id'] == sid and source['canonical_url'] == receipt['feed_url']
        saved = conn.execute('SELECT * FROM source_items').fetchone()
        assert saved['item_id'] == item['item_id'] and saved['state'] == 'committed'
        assert saved['video_id'] == receipt['video_id'] and saved['actual_starts'] == 1
        charged = conn.execute('SELECT * FROM source_capture_starts').fetchone()
        assert charged['start_id'] == item['start_id'] and charged['state'] == 'succeeded'
        assert charged['started_at_ms'] is not None and charged['utc_day'] == item['charged_utc_day']
        work = conn.execute('SELECT * FROM library_work').fetchone()
        assert work['work_id'] == item['classification']['work_id']
        assert work['run_id'] == item['classification']['run_id']
        assert work['state'] == 'ready' and work['attempts'] == 0
        clip = conn.execute('SELECT * FROM clips').fetchone()
        assert (clip['video_id'], clip['start'], clip['end']) == (receipt['video_id'], 12.5, 21.75)


@pytest.mark.parametrize('capture_page', [2, 9], ids=['automatic-page-two', 'load-more-page-nine'])
def test_as8_c21_waiting_capture_is_reached_through_returned_cursor(capture_page):
    result = run_dashboard('const capturePage = ' + str(capture_page) + ';\n' + """
const calls = [];
callRegistryTool = async (name, args) => {
  calls.push({name, args});
  const page = args.item_cursor ? Number(args.item_cursor.split('-')[1]) : 1;
  return {
    source: {item_counts: {committed: 1}},
    items: page === capturePage ? [{entry_id: 'waiting', title: 'Later capture',
      capture_state: 'committed', classification: {state: 'waiting_for_client'}}] :
      Array.from({length: 25}, (_, n) => ({entry_id: `old-${page}-${n}`, capture_state: 'eligible'})),
    next_item_cursor: page < capturePage ? `page-${page + 1}` : null,
  };
};
await toggleCapturedItems('src_fixture');
const initial = renderCapturedItems(state.standingItemsBySource.src_fixture);
const initialCalls = calls.length;
if (capturePage > 8) await loadMoreCapturedItems('src_fixture');
return {initial, initialCalls, calls,
  final: renderCapturedItems(state.standingItemsBySource.src_fixture)};
""")
    assert result['initialCalls'] == min(capture_page, 8)
    if capture_page > 8:
        assert 'Load more items' in result['initial']
        assert 'data-source-id="src_fixture"' in result['initial']
    assert len(result['calls']) == capture_page
    for page, call in enumerate(result['calls'], 1):
        assert call['name'] == 'source_status'
        assert call['args'] == dict(source_id='src_fixture', item_limit=25,
                                   **({'item_cursor': f'page-{page}'} if page > 1 else {}))
    assert 'Waiting for client (unfiled)' in result['final']
    assert 'Load more items' not in result['final']


def test_as8_c21_accepted_classification_is_labelled_staged():
    rendered = run_dashboard('return renderCapturedItems({items: [' + json.dumps({
        'title': 'Accepted fixture', 'capture_state': 'committed',
        'classification': {'state': 'accepted'},
    }) + ']});')
    assert 'Classification accepted (staged)' in rendered
    assert not re.search(r'>\s*Filed\s*</span>', rendered)
