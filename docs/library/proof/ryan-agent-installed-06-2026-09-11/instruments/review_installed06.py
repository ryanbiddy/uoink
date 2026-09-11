"""Independently review retained package-06 receipts without opening databases."""
import datetime as dt
import hashlib
import json
from pathlib import Path

r = Path(__file__).resolve().parents[1]
root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06')
read = lambda name: json.loads((root / name).read_text(encoding='utf8'))
package = json.loads((r / 'docs/library/proof/candidate-package-06-2026-09-11/package-manifest.json').read_text(encoding='utf8'))
for stage in ('install', 'same-version-reinstall'):
    row = read(stage + '.json')
    assert row['exit'] == 0 and row['package_sha256'] == package['package_sha256']
    assert len(read(stage + '.shortcuts.json')) == 4
comparison = read('installed-file-comparison.json')
assert comparison['compared'] == comparison['expected_installed'] == 32497 and not comparison['failures']
extras = read('installed-generated-files.json')
assert not extras['missing_expected'] and not extras['unrecognized_extra_files'] and len(extras['extra_files']) == 3
c22 = read('c22-observation.json')
assert c22['verdict']['counts'] == {'pass': 11, 'fail': 0, 'unexecuted': 3, 'executed': 11}
assert c22['source_bindings_after'] and c22['guard_absent_after'] and c22['pth_before'] == c22['pth_after']
assert not c22['unexpected_runtime_errors'] and all(row['observed'] == 'dead' for row in c22['owned_command_liveness'])
browser = read('c22/evidence/browser-held-observation.json')
first = browser['before_observation']
changes = {name: [key for key, value in first.items() if value != browser[name].get(key)]
           for name in ('after_observation', 'after_stop')}
assert all(set(value) == {'label', 'utc'} for value in changes.values())
stop = browser['stop']
assert stop['exit'] == 0 and stop['stopped'] and stop['port_freed'] and stop['pth_preserved']['matches_original']
ledger = first['ledger_summary']
assert ledger['standing_charge_count'] == 1 and ledger['publication_count'] == 0
assert len(ledger['starts']) == 1 and ledger['starts'][0]['state'] == 'failed'
assert ledger['starts'][0]['release_or_failure_code'] == 'worker_lost'
source = ledger['subscriptions'][0]
assert source['consent_state'] == 'on' and source['revision'] == 1 and source['back_catalog_enrolled'] == 1
assert ledger['items'][0]['state'] == 'eligible' and ledger['items'][0]['actual_starts'] == 1
assert ledger['items'][0]['blocked_reason'] == 'worker_lost'
visual = read('c22/artifacts/browser-observation-complete.json')
assert len(visual['images']) == 6 and not visual['browser_page_errors']
for row in visual['images']:
    path = root / 'c22/artifacts' / row['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
    stamp = dt.datetime.fromisoformat(row['captured_file_mtime_utc'])
    assert dt.datetime.fromisoformat(browser['utc_start']) <= stamp <= dt.datetime.fromisoformat(browser['utc_end'])
p4 = read('p4/profile/collection.json')
assert p4['counts'] == {'passed': 15, 'failed': 0, 'blocked': 1, 'unobserved': 7, 'pending_review': 0}
assert not p4['product_findings'] and not p4['isolation']['instrument_only']
stdio = read('p4/profile/stdio-check-original-installed.json')
assert stdio['installed_credit'] and not stdio['fake_child_used'] and not stdio['product_findings']
assert stdio['inspection']['packet_and_prompt_subset_complete'] and stdio['reconnect']['distinct']
assert stdio['unavailable_storage']['expected_refusal'] and not stdio['unavailable_storage']['replacement_index_created']
assert stdio['guard_restore']['children_confirmed_gone']
for stage in ('prepare', 'check', 'prepare-client', 'collect'):
    row = read('p4/profile/operator-' + stage + '.json')
    assert row['exit_code'] == 0 and row['cleanup']['cleaned']
for stage in ('p4-prepare', 'p4-check', 'p4-prepare-client'):
    row = read('fresh-client-' + stage + '-observation.json')
    assert row['status'] == 'completed_pending_independent_review' and row['source_bindings_after']
    assert row['guard_absent_after'] and row['pth_before'] == row['pth_after']
assert not (root / 'p4-client/profile/collection.json').exists()
decoder = read('decoder-commands-02.json')
assert decoder['status'] == 'passed' and decoder['startup_restored']
summary = {
    'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'package_sha256': package['package_sha256'],
    'build_source': package['build_source'], 'setup_observed': True, 'same_version_reinstall_observed': True,
    'setup_exits': [0, 0], 'throwaway_account': False, 'ordinary_installation_replaced': False,
    'account_scope': 'Same non-elevated account; separate app, data, credential namespace, uninstall entry and Start Menu group. Not OS-wide containment.',
    'installed_files_compared': 32497, 'installed_files_failed': 0, 'recognized_generated_files': 3,
    'c22_raw_counts': c22['verdict']['counts'], 'unexpected_runtime_errors': [], 'all_owned_children_dead': True,
    'browser': {'status': 'passed_independent_visual_review', 'images': 6,
                'raw_status': browser['status'], 'state_changes': changes,
                'visible': visual['reviewed_visible_fields'], 'page_errors': [],
                'scope': 'Astra inspected actual source/recovery and Activity images. Consent rev 1, 1/25 enrollment, 1/10 charged start, worker_lost failure and eligible attempt 1/3 match persisted state. Current UTC is paired in records; Library image also displays its actual UTC snapshot time.',
                'cleanup': 'Owned helper exit zero, port freed, exact guard and interpreter restoration.'},
    'p4_raw_counts': p4['counts'], 'p4_route_installed_credit': stdio['installed_credit'],
    'p4_collection_installed_credit': p4['isolation']['installed_credit'], 'p4_product_findings': [],
    'p4_unobserved': [row['name'] for row in p4['checkpoints'] if row['status'] == 'unobserved'],
    'p4_notes': 'Actual installed stdio route verified. Overall client gate remains incomplete. Terminated transport/wrapper exit one is retained; no graceful-exit claim. X row records only the prior blocked-link disposition, without a new fetch.',
    'fresh_client_fixture': {'path': str(root / 'p4-client/profile'), 'prepared_and_checked': True,
                            'collected': False, 'authentication': 'Pending user confirmation; no credentials inspected or copied by Astra.',
                            'model_invoked_by_astra': False},
    'decoders': 'Installed synthetic image/encryption and product-loader WAV checks pass with temporary no-site instrumentation and byte-exact restoration. No model/checkpoint inference.',
    'failed_history': ['All earlier package-05 failed/partial attempts retained separately.',
                       'Browser CLI ref/scroll limitations and rejected combined shell save are recorded in original observation; no product scenario rerun.'],
    'release_ready': False, 'main_merged': False, 'published': False,
    'open': ['Fresh subscription sign-in/extra-usage confirmation and real-client/visual flows',
             'Historical AT6 exit disposition', 'Retained dependency findings and unsigned package',
             'Ryan main/public release decision']}
out = r / '_scratch/installed06-reviewed-summary.json'
with out.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(json.dumps(summary, indent=2) + '\n')
print(json.dumps({key: summary[key] for key in ('setup_exits', 'installed_files_compared', 'c22_raw_counts', 'p4_raw_counts', 'release_ready')}, indent=2))
