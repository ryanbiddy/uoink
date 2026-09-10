import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1];d=r/'docs/library';out=d/'proof/ryan-review-bundle-05-2026-09-10';out.mkdir(exist_ok=False)
receipt=r/'build/Uoink-Living-Library-3-8-0-Review-Kit-05-2026-09-10.receipt.json'
value=json.loads(receipt.read_text(encoding='utf8'))
for src,name in [(receipt,'bundle-receipt.json'),(r/'_scratch/reviewkit05-extraction-verification.json','extraction-verification.json'),(r/'_scratch/committed-candidate05-proof-verification.json','committed-proof-verification.json'),(r/'_scratch/runbook05-syntax.json','runbook-syntax.json'),(r/'_scratch/build_release_bundle05.py','build_review_kit.py'),(r/'_scratch/extract_verify_reviewkit05.py','extract_verify_reviewkit.py'),(Path(__file__),'record_delivery.py')]:shutil.copyfile(src,out/name)
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
hand=d/'ORCHESTRATION-HANDOFF-2026-09-08.md';h=hand.read_text(encoding='utf8');lines=h.splitlines()
for i,line in enumerate(lines):
 if line.startswith('| Integration |'):
  lines[i]=line.replace('All 2,493 cases','All 2,497 cases').replace('`9a62e84` tree: 2,489','`393010f` tree: 2,493')
h='\n'.join(lines)+'\n'
h+='''
### 2026-09-10 - Review kit delivered; release still held

Review source 7a7b9aa binds complete validation 393010f and installer source
6b5aed8. The new local kit contains 1,485 payloads; every ZIP member and extracted
file hash matches, with no unsafe path or case-insensitive collision. All 333
public proof payloads match their hashes in committed Git objects. Nine runbook
PowerShell blocks parse without error; this is syntax verification only.

Local artifact: build/Uoink-Living-Library-3-8-0-Review-Kit-05-2026-09-10.zip,
415,554,388 bytes, SHA256
b6b49a87622af82421c99f09307c6dcb707c005c2b1058a668d0a47672c9ac3b.
Its release_ready=false is deliberate. It preserves package-05 while the bounded
browser repair and fresh client/visual observations remain. The broader inventory
and product-suite critique are excluded from this public-source kit and stay in
the local report directory. Earlier packages and ZIPs remain unchanged.

Proof: proof/ryan-review-bundle-05-2026-09-10/SHA256.json. The next source work is
Queue 6, then a new complete tree and package only after that packaged UI repair.
Back up this documentary commit only through origin/cc/living-library; no main
merge or candidate-branch push. Keep the final transport receipt outside Git to
avoid a self-referential commit/hash loop.
'''
hand.write_text(h,encoding='utf8',newline='\n')
notes=d/'RELEASE-NOTES-LIVING-LIBRARY.md';n=notes.read_text(encoding='utf8')
n+='''
## Current review kit

The local review kit is
`build/Uoink-Living-Library-3-8-0-Review-Kit-05-2026-09-10.zip`:
415,554,388 bytes, SHA-256
`b6b49a87622af82421c99f09307c6dcb707c005c2b1058a668d0a47672c9ac3b`.
It binds review source `7a7b9aa`, validation `393010f` and installer `6b5aed8`.
All 1,485 ZIP and extracted payload hashes match. It contains the matching
installer, receipt tools and notes, with release_ready=false. Preserve it as
review evidence; the browser repair will require a later package. See the
[delivery seal](proof/ryan-review-bundle-05-2026-09-10/SHA256.json).
'''
notes.write_text(n,encoding='utf8',newline='\n')
print(json.dumps({'proof_payloads':len(files),'zip_sha256':value['sha256']}))
