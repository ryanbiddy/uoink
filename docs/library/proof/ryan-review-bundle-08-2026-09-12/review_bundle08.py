"""Check delivered ZIP paths, extracted payloads and portable entry points."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import zipfile

r = Path(__file__).resolve().parents[1]
folder = r / 'build/Uoink-Living-Library-3-8-0-Review-Kit-08-2026-09-12'
receipt = json.loads(folder.with_suffix('.receipt.json').read_text(encoding='utf8'))
manifest = json.loads((folder / 'BUNDLE-SHA256.json').read_text(encoding='utf8'))
files = manifest['files']
assert len(files) == receipt['payload_files'] and len(files) > 1715
for name, row in files.items():
    path = (folder / name).resolve()
    assert path.is_relative_to(folder)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert path.stat().st_size == row['bytes'] and digest == row['sha256'], name
with zipfile.ZipFile(folder.with_suffix('.zip')) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names)) == len({name.casefold() for name in names})
    assert all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name for name in names)
    nested_archives = [name for name in names if Path(name).suffix.lower() in ('.zip', '.7z', '.tar', '.gz')]
    assert not nested_archives, nested_archives
    assert not any(Path(name).suffix.lower() in ('.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm') or Path(name).name.lower() in ('token.txt', '.credentials.json') for name in names)
portable = (folder / 'run_installed_decoders.py').read_text(encoding='utf8')
assert 'r=Path(__file__).resolve().parent\n' in portable and "str(r/script)" in portable
assert "str(r/'_scratch'/script)" not in portable and 'candidate-package-08-2026-09-12' in portable
for name in ('package_decoder_probe.py', 'installed_codec_probe.py', 'agent_install_observer.ps1', 'run_bound_c22.py'):
    assert (folder / name).is_file()
state = json.loads((folder / 'release-state.json').read_text(encoding='utf8'))
assert state['release_ready'] is False and state['installed'] is True
report = {'source': receipt['bundle_source'], 'payload_files': len(files),
          'all_extracted_hashes_match': True, 'unique_safe_casefolded_zip_paths': True,
          'nested_archives': [], 'database_or_auth_files': [],
          'portable_entrypoint_paths_checked': True, 'portable_execution_claimed': False,
          'release_ready': False, 'zip_sha256': receipt['sha256'], 'zip_bytes': receipt['bytes']}
out = r / '_scratch/review-bundle08-inspection.json'
with out.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
