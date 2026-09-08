"""Fable-only wrapper around Astra's S21 launcher (AS-7 C21 evidence requirements).

Runs ``tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds N`` as a
child process and retains, next to the launcher's own receipt: the executed launcher bytes
(copied verbatim) and their raw/LF hashes, the exact command, the process exit status,
start/finish timestamps, stdout/stderr, and every artifact the receipt hashes (copied into
an archive directory with a manifest). Nothing here touches the launcher's behaviour.

    python -B tests/library_work_astra/s21_run_record.py --hold-seconds 540 --out <dir> --label at7
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / 'tests' / 'library_work_astra' / 'test_phase3_s21.py'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold-seconds', type=int, default=540)
    parser.add_argument('--out', required=True, help='archive directory (created)')
    parser.add_argument('--label', required=True, help='run label, e.g. at7')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    candidate = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    launcher_bytes = LAUNCHER.read_bytes()
    executed_copy = out / f'executed-launcher-{args.label}-{candidate[:7]}.py'
    executed_copy.write_bytes(launcher_bytes)
    command = [sys.executable, '-B', 'tests/library_work_astra/test_phase3_s21.py', '--execute-s21',
               '--hold-seconds', str(args.hold_seconds)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT), S21_CANDIDATE_SHA=candidate)
    env.pop('ANTHROPIC_API_KEY', None)
    stdout_path, stderr_path = out / f'stdout-{args.label}.log', out / f'stderr-{args.label}.log'
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    with stdout_path.open('wb') as so, stderr_path.open('wb') as se:
        proc = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=so, stderr=se)
        (out / 'RUNNING.json').write_text(json.dumps({'pid': proc.pid, 'started_utc': started}), encoding='utf-8')
        code = proc.wait()
    finished = datetime.now(timezone.utc).isoformat()
    (out / 'RUNNING.json').unlink(missing_ok=True)

    text = stdout_path.read_text(encoding='utf-8', errors='replace')
    receipt_line = next((ln for ln in text.splitlines() if ln.startswith('S21 receipt: ')), None)
    record = {
        'schema': 'fable-s21-run-record-v1', 'label': args.label, 'candidate_sha': candidate,
        'command': command, 'cwd': str(ROOT), 'python': sys.version,
        'exit_code': code, 'started_utc': started, 'finished_utc': finished,
        'wall_seconds': round(time.time() - t0, 3),
        'executed_launcher': {'path': 'tests/library_work_astra/test_phase3_s21.py',
                              'retained_copy': executed_copy.name,
                              'sha256_raw': sha(launcher_bytes),
                              'sha256_lf': sha(launcher_bytes.replace(b'\r\n', b'\n'))},
        'stdout': stdout_path.name, 'stderr': stderr_path.name,
        'env': {'PYTHONPATH': str(ROOT), 'S21_CANDIDATE_SHA': candidate, 'ANTHROPIC_API_KEY': 'unset',
                'PHASE3_REQUIRE_IMPLEMENTATION': env.get('PHASE3_REQUIRE_IMPLEMENTATION')},
    }
    if receipt_line:
        receipt_path = Path(receipt_line[len('S21 receipt: '):].strip())
        root = receipt_path.parent
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt_copy = out / f'receipt-{args.label}-candidate-{candidate[:7]}.json'
        shutil.copy2(receipt_path, receipt_copy)
        archive = out / f'artifacts-{args.label}-candidate-{candidate[:7]}'
        manifest = {}
        for rel, expected in receipt.get('artifact_hashes', {}).items():
            src = root / rel
            dest = archive / Path(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = src.read_bytes()
            dest.write_bytes(data)
            manifest[rel.replace('\\', '/')] = {'sha256': sha(data), 'matches_receipt': sha(data) == expected, 'bytes': len(data)}
        evidence = root / 'evidence.db'
        if evidence.is_file():
            ev_copy = out / f'evidence-{args.label}-candidate-{candidate[:7]}.db'
            shutil.copy2(evidence, ev_copy)
            record['evidence_db'] = {'retained_copy': ev_copy.name, 'sha256': sha(ev_copy.read_bytes()),
                                     'matches_receipt': sha(ev_copy.read_bytes()) == receipt.get('evidence_sha256')}
        record.update(receipt='%s' % receipt_copy.name, data_root=str(root), artifact_archive=archive.name,
                      artifact_manifest=manifest,
                      all_artifacts_match=all(v['matches_receipt'] for v in manifest.values()),
                      result=receipt.get('result'), feed_url=receipt.get('feed_url'), helper_url=receipt.get('helper_url'),
                      launcher_hash_in_receipt=receipt.get('input_hashes', {}).get(r'tests\library_work_astra\test_phase3_s21.py'))
        record['launcher_hash_matches_executed_bytes'] = record['launcher_hash_in_receipt'] in (
            record['executed_launcher']['sha256_raw'], record['executed_launcher']['sha256_lf'])
    (out / f'run-record-{args.label}-candidate-{candidate[:7]}.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('exit_code', 'result', 'all_artifacts_match', 'launcher_hash_matches_executed_bytes') if k in record}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
