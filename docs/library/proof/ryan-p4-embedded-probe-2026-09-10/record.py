import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=r.parent/'Yoink-library-p4-probe-repair'
o=r/'docs/library/proof/ryan-p4-embedded-probe-2026-09-10';o.mkdir(exist_ok=False)
for name,src in [('repair.patch',r/'_scratch/p4-embedded-probe-repair.patch'),
                 ('record.py',Path(__file__))]:shutil.copyfile(src,o/name)
for name,src in [('worker',w/'_scratch/p4-probe-worker-01'),('checkout',r/'_scratch/p4-probe-checkout-01')]:
 (o/name).mkdir()
 for f in ('results.json','tests.log','tests.xml'):shutil.copyfile(src/f,o/name/f)
files={q.relative_to(o).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(o.rglob('*')) if q.is_file()}
(o/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
p=r/'docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md';s=p.read_text(encoding='utf8')
s=s.replace('## State at handoff (updated 2026-09-09; corrected tree `80a4fa8`, replacement installer source `86bfede`)','## State at handoff (updated 2026-09-10; package source `6b5aed8`, final receipt-tree refresh next)')
s=s.replace('Rebuilt-package installed C22 delegated to Astra; exact account/mode must be recorded','Package-05 actual installed C22: 11 passed / zero failed / three original manual placeholders; browser supplement review pending; same account recorded')
s=s.replace('Rebuilt-package installed/client/everyday receipts pending; installation delegated to Astra','Actual prepare exposed embedded probe import defect; bounded repair has 63 passes in each root. Fresh installed/client/everyday receipts next')
s=s.replace('Actual isolated Setup/reinstall, installed C22/P4 and browser/client evidence. Nineteen Python advisory entries remain separately; no model/speaker runs','Actual isolated Setup and same-version reinstall both exit zero; 32,054 installed hashes match. Receipt-source repair requires new complete tree. P4/client and final evidence remain; nineteen advisory entries retained')
old='5. Main release approval remains Ryan\'s. Suggestions/apply false, X 403, no new\n   fetch/speaker runs and deferred Part B remain unchanged.'
new='''5. Package-05 Setup/reinstall and installed C22 now have actual observations.
   Complete the fresh tree and fresh P4 directory under
   P4-EMBEDDED-PROBE-REPAIR-BRIEF-2026-09-09.md and the 2026-09-10 verdict.
   Preserve the initial Desktop observer refusal, decoder instrument failures
   and P4 prepare failure. Original raw manual placeholders remain unchanged.
   Review the actual browser supplement, then seal installed evidence and finish
   notes/runbook/new ZIP. Real-client sign-in remains user-controlled.
6. Main release approval remains Ryan's. Suggestions/apply false, X 403, no new
   fetch/speaker runs and deferred Part B remain unchanged.'''
assert old in s;s=s.replace(old,new,1)
s+='''
### 2026-09-10 - Actual installation and embedded receipt bootstrap

Agent Install 05 is outside the checkout on this same non-elevated account.
Actual Setup and same-version reinstall exit zero. All 32,054 installed file
hashes match; ordinary registry/autorun and inspected shortcut effects remain
unchanged. OneDrive Desktop contents were deliberately not traversed: reviewed
observer metadata plus actual empty Tasks settings and Inno logs establish the
selected no-desktop-task boundary. This is not throwaway-account isolation.

Installed C22 records 11 passes / zero failures / three original unexecuted
manual placeholders. Browser screenshots and before/after state were collected
separately, with owned helper cleanup affirmed. Installed image/Fernet and WAV
decoder checks pass under explicitly temporary no-site instrumentation; ._pth
is restored byte-for-byte. Earlier instrument failures remain preserved.

The first installed P4 prepare fails before fixtures because embedded Python
omits the script directory. Its original guard and path restoration succeed.
The bounded receipt bootstrap repair passes 63 checks in both worktree and
checkout, with four new regressions and no existing test changed. Its raw diff
was applied three-way. See ASTRA-P4-EMBEDDED-PROBE-VERDICT-2026-09-10.md.
Now observe the fresh complete tree and retry installed P4 in a new directory.
No packaged source changed and no installer rebuild is owed for this repair.
'''
p.write_text(s,encoding='utf8',newline='\n')
print(json.dumps({'proof_payloads':len(files),'handoff_updated':True}))
