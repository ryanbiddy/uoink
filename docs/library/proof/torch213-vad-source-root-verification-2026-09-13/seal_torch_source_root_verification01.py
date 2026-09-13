"""Seal documentary root copy verification; does not rerun a verifier."""
import hashlib
import json
from pathlib import Path

root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
dest = root / 'docs/library/proof/torch213-vad-source-root-verification-2026-09-13'
assert not dest.exists()
dest.mkdir()
sources = [root / '_scratch' / name for name in (
    'verify_copy_torch_source_proof01.py', 'verify_copy_torch_source_proof02.py',
    'TORCH-ROOT-COPY-REPAIR01.md', 'seal_torch_source_root_verification01.py')]
sources.append(root / 'docs/library/ASTRA-TORCH213-VAD-SOURCE-VERDICT-2026-09-13.md')
for source in sources:
    raw = source.read_bytes()
    with (dest / source.name).open('xb') as stream:
        stream.write(raw)
    assert (dest / source.name).read_bytes() == raw == source.read_bytes()
(dest / '.gitattributes').write_bytes(b'* -text\n')
results = {
    'scope': 'Transcribed actual root tool results; raw tool records remain in the task history',
    'source_proof_sha256': '290a815003a3593d0685e5570c61feccf6884edada9dae80f5cc0887665b3a74',
    'attempt01': {'chunk_id': '02a385', 'wall_time_seconds': 0.2182696, 'actual_outer_exit': 1,
                  'failure': 'AssertionError at line 93: expected 48 timestamp receipt JSON files but selected all 51 JSON files',
                  'destination_created': False},
    'attempt02': {'chunk_id': 'e79585', 'wall_time_seconds': 0.6773129, 'actual_outer_exit': 0,
                  'payloads': 199, 'original_copies_verified': 197, 'ordered_passing_cases_each_run': 40,
                  'http_body_pairs_verified': 23, 'utc_strings_verified': 119, 'copied_files': 200},
    'no_tests_or_network_rerun': True}
(dest / 'ACTUAL-TOOL-RESULTS.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
rows = []
for file in sorted(dest.iterdir()):
    raw = file.read_bytes()
    rows.append({'path': file.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
manifest = (json.dumps({'scope': 'Root documentary verification and preserved reporting repair', 'files': rows}, indent=2) + '\n').encode()
(dest / 'SHA256.json').write_bytes(manifest)
assert {f.name for f in dest.iterdir()} == {r['path'] for r in rows} | {'SHA256.json'}
print(json.dumps({'payloads': len(rows), 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
