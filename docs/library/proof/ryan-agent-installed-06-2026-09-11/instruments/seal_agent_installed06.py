"""Seal actual isolated installation observations; exclude databases and secrets."""
import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--summary', required=True, type=Path)
a = p.parse_args()
r = Path(__file__).resolve().parents[1]
root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06')
prior = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 05\uninstall-before-package06-2026-09-11')
out = r / 'docs/library/proof/ryan-agent-installed-06-2026-09-11'
summary = json.loads(a.summary.read_text(encoding='utf8'))
package = json.loads((r / 'docs/library/proof/candidate-package-06-2026-09-11/package-manifest.json').read_text())
assert summary['setup_observed'] and summary['package_sha256'] == package['package_sha256']
for stage in ('install', 'same-version-reinstall'):
    row = json.loads((root / (stage + '.json')).read_text())
    assert row['exit'] == 0 and row['package_sha256'] == package['package_sha256']
    assert (root / (stage + '.shortcuts.json')).is_file()
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_text('* -text\n', encoding='utf8', newline='\n')

def copy(source, relative):
    assert source.is_relative_to(root) or source.is_relative_to(prior) or source.is_relative_to(r / '_scratch')
    assert not source.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

for source in root.iterdir():
    if source.is_file() and source.suffix in ('.json', '.stdout', '.stderr', '.log', '.inf'):
        copy(source, Path('observation') / source.name)
copy(root / 'app/isolated-install.json', Path('observation/installed-marker.json'))
for stage in ('install', 'same-version-reinstall'):
    copy(root / (stage + '-temp') / 'uoink-install-verify.log', Path('observation') / (stage + '-files-only.log'))
for source in prior.iterdir():
    if source.is_file() and source.suffix in ('.json', '.log'):
        copy(source, Path('prior-isolated-uninstall') / source.name)
c22 = root / 'c22'
for source in c22.iterdir():
    if source.is_file() and (source.suffix == '.json' or source.name == 'journal.jsonl'):
        copy(source, Path('c22') / source.name)
for folder in ('commands', 'evidence', 'artifacts'):
    for source in (c22 / folder).rglob('*'):
        if source.is_file() and source.suffix in ('.json', '.jsonl', '.log', '.png', '.jpg', '.txt'):
            copy(source, Path('c22') / source.relative_to(c22))
for source in (c22 / 'profiles').glob('*/c22-guard-events.jsonl'):
    copy(source, Path('c22') / source.relative_to(c22))
p4 = root / 'p4/profile'
fresh_client = root / 'p4-client/profile'
for folder, label in ((p4, 'p4'), (fresh_client, 'fresh-client')):
    for base, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name not in ('claude-config', 'tmp', '__pycache__')]
        for name in files:
            source = Path(base) / name
            if name in ('token.txt', '.credentials.json') or source.suffix.lower() in ('.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm'):
                continue
            if source.suffix in ('.json', '.jsonl', '.stdout', '.stderr', '.png', '.jpg'):
                copy(source, Path(label) / source.relative_to(folder))
for folder, label in (('decoder-probe-02', 'decoder-probe'), ('codec-probe-02', 'codec-probe')):
    for source in (root / folder).iterdir():
        if source.is_file() and source.suffix in ('.json', '.png', '.jpg', '.webp'):
            copy(source, Path(label) / source.name)
for name in ('agent_receipt_observe06.py', 'check_installed_package_inputs.py',
             'package_decoder_probe.py', 'installed_codec_probe.py', 'review_package06_pins.py',
             'inventory_installed_extras06.py', 'seal_agent_installed06.py',
             'agent_install_observer05.ps1', 'uninstall_retained_package05.ps1',
             'run_installed_decoders06.py', 'run_installed_decoders06_portable.py',
             'decoder06-portable-review.json', 'review_installed06.py', 'complete_browser06.py',
             'agent_receipt_observe06_client.py', 'agent_receipt_observe06_client_unexecuted_draft.py',
             'client06-observer.patch', 'client06-observer-review.json',
             'client06-observer-final.patch', 'client06-observer-final-review.json'):
    copy(r / '_scratch' / name, Path('instruments') / name)
copy(r / '_scratch/package06-preinstall-review-01/result.json', Path('preinstall-pins/result.json'))
copy(a.summary, Path('summary.json'))
tokens = []
for source in [*(c22 / 'profiles').glob('*/token.txt'), p4 / 'token.txt', fresh_client / 'token.txt']:
    if source.is_file():
        value = source.read_text(encoding='utf8').strip()
        if len(value) >= 16:
            tokens.append(value.encode())
for source in out.rglob('*'):
    if source.is_file() and source.suffix not in ('.png', '.jpg', '.webp'):
        data = source.read_bytes()
        assert all(token not in data for token in tokens), 'Disposable token in export: ' + str(source.relative_to(out))
files = {source.relative_to(out).as_posix(): {'bytes': source.stat().st_size,
         'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
         for source in sorted(out.rglob('*')) if source.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'algorithm': 'sha256',
    'scope': 'Actual same-account isolated Setup/reinstall. Raw statuses retained; independent summary separate. No databases, token files or client credential store exported.',
    'files': files}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'payloads': len(files), 'setup_exits': summary['setup_exits'],
                  'c22': summary['c22_raw_counts'], 'p4': summary['p4_raw_counts'],
                  'browser': summary['browser']['status'], 'release_ready': summary['release_ready']}, indent=2))
