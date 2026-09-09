"""Preserve the local candidate build and synthetic runtime receipts, without fixture data."""
import datetime as dt
import hashlib
import json
import shutil
import stat
import subprocess
import re
import fnmatch
from pathlib import Path

repo = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
candidate = 'e47e4f2e8e1b6a83ecb1171436092b9077186430'
build = repo / '_scratch/candidate-build-20260909-002419'
probe = repo / '_scratch/packaged-runtime-02'
failed_probe = repo / '_scratch/packaged-runtime-01'
stage = repo / 'installer/staging'
archive = repo / 'docs/library/proof/candidate-package-01-2026-09-09'

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

receipt = read(build / 'receipt.json')
assert receipt['status'] == 'built; not installed', receipt
assert receipt['candidate'] == candidate
artifact = Path(receipt['artifact']['path'])
assert artifact.stat().st_size == receipt['artifact']['bytes']
assert sha(artifact) == receipt['artifact']['sha256']
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == candidate
outcome = read(probe / 'outcome.json')
launch = read(probe / 'launch.json')
assert launch['candidate'] == candidate
assert launch['interpreter_sha256'] == sha(stage / 'python/python.exe')
assert launch['entry_sha256'] == sha(stage / 'uoink_mcp.py')
assert launch['seed_sha256'] == sha(probe / 'seed.py')
assert launch['launcher_sha256'] == sha(probe / 'launch.py')

tracked = {}
tree = subprocess.check_output(['git', 'ls-tree', '-r', '-z', candidate], cwd=repo)
for entry in tree.split(b'\0'):
    if not entry:
        continue
    metadata, name = entry.split(b'\t', 1)
    mode, kind, blob = metadata.decode().split()
    if kind == 'blob':
        tracked[name.decode('utf-8')] = blob

inventory = []
bindings = []
unmapped = []
expected_mtime = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', candidate], cwd=repo, text=True))
inno_text = (repo / 'installer/uoink.iss').read_text(encoding='utf-8')
inno_sources = [item.replace('\\', '/') for item in re.findall(r'^Source: "staging\\([^"]+)"', inno_text, re.M)]
for excluded in ('server.log', 'token.txt'):
    assert not any(fnmatch.fnmatchcase(excluded, pattern) for pattern in inno_sources)
for path in sorted(stage.rglob('*')):
    attributes = path.lstat().st_file_attributes
    assert not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, path
    if not path.is_file():
        continue
    relative = path.relative_to(stage).as_posix()
    if relative in ('server.log', 'token.txt'):
        continue
    assert abs(path.stat().st_mtime - expected_mtime) < .01, ('input timestamp changed', relative)
    digest = sha(path)
    inventory.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': digest})
    source = relative
    if relative in ('verify_install.ps1', 'upgrade_prep.ps1'):
        source = 'installer/' + relative
    elif relative in ('stop-server.bat', 'stop-server.ps1'):
        source = 'installer/templates/' + relative
    if source in tracked:
        source_hash = sha(repo / source)
        assert source_hash == digest, (relative, source)
        bindings.append({'staged_path': relative, 'source_path': source, 'source_git_blob': tracked[source], 'checkout_and_staged_sha256': digest})
    elif not relative.startswith(('python/', 'bin/', 'installer-assets/')) and relative not in ('VERSION', 'uoink.ico'):
        unmapped.append(relative)

for required in ('index.py', 'uoink_mcp.py', 'uoink_mcp_tools.py', 'library_cards.py', 'library_work.py', 'source_subscriptions.py', 'library_analysis.py', 'library_resources.py', 'library_prompts.py', 'library_briefs.py', 'library_mirror.py', 'library_mirror_vault_io.py', 'library_media.py', 'library_faithfulness.py', 'scripts/recall_hook.py'):
    assert any(item['staged_path'] == required for item in bindings), required
assert not unmapped, unmapped
assert not any(item['path'].endswith(('.pyc', '.db', '.db-wal', '.db-shm', '.sqlite', '.sqlite3')) or Path(item['path']).name in ('token.txt', '.credentials.json') for item in inventory)

archive.mkdir(exist_ok=False)
copies = {
    'build/receipt.json': build / 'receipt.json',
    'build/build.log': build / 'build.log',
    'build/build_library_candidate.ps1': repo / '_scratch/build_library_candidate.ps1',
    'runtime/packaged_runtime_probe_02.py': repo / '_scratch/packaged_runtime_probe_02.py',
    'failed-runtime-01/packaged_runtime_probe.py': repo / '_scratch/packaged_runtime_probe.py',
    'runtime/staged-side-effects.json': repo / '_scratch/packaged-runtime-side-effects.json',
}
for name in ('launch.json', 'outcome.json', 'exchanges.json', 'frames.json', 'seed.py', 'launch.py', 'seed-stdout.txt', 'seed-stderr.txt', 'stderr.log'):
    copies['runtime/' + name] = probe / name
    copies['failed-runtime-01/' + name] = failed_probe / name
for name, source in copies.items():
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(source) == sha(target)

save(archive / 'staged-inventory.json', {'build_source': candidate, 'files': inventory})
save(archive / 'source-bindings.json', {'build_source': candidate, 'note': 'Checkout bytes equal staged bytes; Git blob identifiers retain Git newline normalization independently.', 'files': bindings})
summary = {
    'build_source': candidate,
    'artifact': receipt['artifact'],
    'build_elapsed_s': receipt['elapsed_s'],
    'staged_files': len(inventory),
    'staged_bytes': sum(item['bytes'] for item in inventory),
    'source_bindings': len(bindings),
    'unmapped_source_files': unmapped,
    'inventory_scope': 'Post-observation staged compiler inputs, normalized timestamp verified. server.log and token.txt are excluded only after checking the explicit Inno source patterns; side effects and token cleanup recorded separately. This is not an extraction of installer bytes.',
    'inno_definition_sha256': sha(repo / 'installer/uoink.iss'),
    'dependency_lock': '142 packages verified by build log',
    'runtime': outcome,
    'failed_runtime_observation_01': read(failed_probe / 'outcome.json'),
    'runtime_repair_brief': 'CANDIDATE-PACKAGED-RUNTIME-REPAIR-BRIEF-2026-09-09.md',
    'scope': 'Local Inno compilation and original staged embedded runtime with a synthetic stdio caller; no installation, resident helper, model inference or release publish.',
    'candidate_full_tree': {'passed': 2102, 'failed': 92, 'skipped': 3, 'xfail': 1, 'only_exclusion': 'tests/library_work_astra/test_phase3_s21.py'},
    'generated_notice_change': 'Source-bound generation date only: 2026-07-25 to 2026-09-09; dependency table unchanged.',
    'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
}
save(archive / 'summary.json', summary)
shutil.copyfile(Path(__file__), archive / 'seal_candidate_package.py')
seal = [{'path': path.relative_to(archive).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in sorted(archive.rglob('*')) if path.is_file()]
save(archive / 'SHA256.json', {'files': seal})
print(json.dumps({'archive': str(archive), 'sealed_files': len(seal), **summary}))
