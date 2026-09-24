"""AS-9 confirmation of the original at7 artifact missing at AS-8.

Read retained bytes only in this checkout; historical receipt paths are identifiers.
No helper, browser, model, network or live index is used.
"""

import hashlib
import json

from test_phase3_support import ROOT


def test_as9_c21_ninth_artifact_is_the_receipt_hashed_server_log():
    folder = ROOT / 'docs/library/proof/s21-2026-09-08'
    receipt = json.loads((folder / 'receipt-at7-candidate-1d9e438.json').read_text(
        encoding='utf-8-sig'))
    record = json.loads((folder / 'run-record-at7-candidate-1d9e438.json').read_text(
        encoding='utf-8-sig'))
    archive = 'artifacts-at7-candidate-1d9e438'
    assert record['artifact_archive'] == archive
    assert len(receipt['artifact_hashes']) == len(record['artifact_manifest']) == 9

    relative = archive + '/helper/server.log'
    raw = (folder / relative).read_bytes()
    # Pin the original AS8-EV-01 requirement as well as comparing all records.
    expected = '75c70e5a1c8bf3ec396e233098f3180ec0af8879b71f547263dd0a596c963bdd'
    entry = record['artifact_manifest']['helper/server.log']
    assert len(raw) == entry['bytes'] == 5331
    assert hashlib.sha256(raw).hexdigest() == expected
    assert receipt['artifact_hashes'][r'helper\server.log'] == expected == entry['sha256']
    assert entry['matches_receipt'] is True

    manifest_entries = [line.split(maxsplit=1) for line in
                        (folder / 'SHA256SUMS').read_text().splitlines() if line.strip()]
    log_hashes = [digest for digest, name in manifest_entries
                  if name.replace('\\', '/') == relative]
    assert log_hashes == [expected], 'The sealed manifest must include the log exactly once'
