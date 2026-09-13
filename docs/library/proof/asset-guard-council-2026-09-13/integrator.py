"""Integrate the completed source-only council report and exact review evidence."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
worker = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\131e52c7-b6e\gemini')
report = 'docs/library/COUNCIL-ASSET-GUARD-REVIEW-2026-09-13.md'
def git(where, *args):
    return subprocess.check_output(['git', *args], cwd=where)
assert git(worker, 'rev-parse', 'HEAD').decode().strip() == '56d9d4cf11f20ff4448b21db172dbf217d02c6d6'
assert git(worker, 'status', '--porcelain').decode().splitlines() == ['?? ' + report]
blob = git(worker, 'rev-parse', 'HEAD:whisper_runner.py').decode().strip()
assert blob == 'e86cfa906664799c5fb934869828c02e5d238f26'
assert git(root, 'rev-parse', 'HEAD:whisper_runner.py').decode().strip() == blob
source = (worker / 'whisper_runner.py').read_bytes()
assert hashlib.sha256(source).hexdigest() == '6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f'
dispatch = root / '_scratch/asset-guard-council01-dispatch'
assert json.loads((dispatch / 'exit.json').read_bytes())['exit'] == 0
independent = root / '_scratch/astra-companion-b2-01'
b2 = json.loads((independent / 'runs/b2-candidate01/result.json').read_bytes())
assert (b2['passed'], b2['failed'], b2['errors'], b2['skipped'], b2['exit']) == (10, 0, 0, 0, 0)
assert b2['source_sha256'] == 'bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d'
launch_receipt = json.loads((independent / 'launch-b2-candidate01/result.json').read_bytes())
assert launch_receipt['exit'] == 0 and launch_receipt['inputs_unchanged'] is True
out = root / 'docs/library/proof/asset-guard-council-2026-09-13'
out.mkdir(exist_ok=False)
def put(name, raw):
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
put('.gitattributes', b'* -text\n')
put('worker-report-original.md', (worker / report).read_bytes())
put('whisper_runner.worker.py', source)
put('whisper_runner.git.py', git(worker, 'show', 'HEAD:whisper_runner.py'))
put('review-brief.md', (root / '_scratch/COUNCIL-ASSET-GUARD-REVIEW-BRIEF-2026-09-13.md').read_bytes())
put('integrator.py', Path(__file__).read_bytes())
for path in dispatch.iterdir():
    if path.is_file():
        put('dispatch/' + path.name, path.read_bytes())
for name in ['probe_asset_council_windows_case01.py', 'asset-council-windows-case01/result.json', 'asset-council-windows-case01/CaseProbe.txt']:
    put('case-probe/' + name, (root / '_scratch' / name).read_bytes())
for name in ['ROOT-REVIEW.json', 'launch-b2-candidate01/result.json', 'runs/b2-candidate01/result.json']:
    put('independent-b2/' + name, (independent / name).read_bytes())
git(worker, 'add', '-N', '--', report)
put('worker.patch', git(worker, 'diff', '--binary', 'HEAD', '--', report))
applied = subprocess.run(['git', 'apply', '--3way', str(out / 'worker.patch')], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
put('apply.log', applied.stdout)
assert applied.returncode == 0
assert git(worker, 'hash-object', '--path=' + report, report) == git(root, 'hash-object', '--path=' + report, report)
verdict = '''# Astra disposition of the cache and tokenizer council review

Gemini's source review supports the bounded cache repair in `b96dbd0`. It does
not approve Uoink for release. The raw report is preserved unchanged alongside
its brief, dispatch, reviewed source and integration patch.

The empty-buffer finding is valid. B1 treated `b''` as absent and could select
an ambient tokenizer file, raise the wrong missing-file error, or reach the
explicit nonlocal fallback after allocation. B2 changes the condition to
`tokenizer_bytes is not None`. The four added cases cross local-only true/false
with ambient file present/absent. B1 passed six cases and failed four; B2 passed
all ten in the author run and in Astra's exact-input independent run, with zero
errors or skips and actual process exit 0. Original six assertions are unchanged.
These checks execute only the selected constructor prefix with inert seams.
B2 remains an unapplied derivative, SHA-256
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.

The Windows casing finding has a false premise. Windows Path equality ignores
drive and component case. Astra's native Windows standard-library probe found
different absolute/resolved string spellings but equal Path objects. This
probe did not test 8.3 aliases or production downloads. Canonical-path checks
intentionally reject redirected aliases. Resolving first and then checking
`is_symlink()` would discard the original alias evidence, so that proposed
change is rejected.

The tokenizer deletion race is an existing open limit while B remains unapplied.
The report's broad no-network statement applies only to the cache helpers: it
does not establish offline enforcement across the dependency stack or default
VAD path. Local-only constructor handling, artifact trust and model loading
still require their own qualification. The raw report's broader wording is
not adopted as a release claim.

No tests were required or run by this source-only council brief. The production
repair had already passed 144 cases plus 13 subtests in worker and checkout.
The later complete tree at `56d9d4c` recorded 2,796 passed, one historical AT6
receipt failure and three skipped cases, plus 13 passing subtests. This
document integration changes no production source or acceptance tests, so it
does not trigger a repeat of that tree. Website and marketing remain paused.
'''
verdict_path = root / 'docs/library/ASTRA-ASSET-COUNCIL-VERDICT-2026-09-13.md'
assert not verdict_path.exists()
verdict_path.write_text(verdict, encoding='utf8', newline='\n')
put('astra-verdict.md', verdict.encode())
put('receipt.json', (json.dumps({'run_id': '131e52c7-b6e7-4b69-bc74-1283f77391fa',
    'engine': 'gemini-3.8-flash-high@high via Antigravity', 'source_git_blob': blob,
    'transport_exit': 0, 'apply_exit': applied.returncode, 'worker_test_runs': 0,
    'source_changes': False, 'release_ready': False,
    'case_probe_outer_exit_observed_in_root_tool': 0,
    'independent_B2': {'passed': 10, 'failed': 0, 'errors': 0, 'skipped': 0, 'exit': 0}}, indent=2) + '\n').encode())
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in out.rglob('*') if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'files': files}, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'payloads': len(files), 'apply_exit': applied.returncode, 'manifest_sha256': hashlib.sha256((out / 'SHA256.json').read_bytes()).hexdigest()}))
