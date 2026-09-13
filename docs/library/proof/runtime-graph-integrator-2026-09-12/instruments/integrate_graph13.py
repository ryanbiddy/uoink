import gzip, json, subprocess
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\6c96f0a3-c02\gemini')
report='''# Captured runtime dependency graph, reviewed 2026-09-12

Both evaluated selections fail. These results use saved PyPI JSON and exact
wheel METADATA; they do not establish binary authenticity or runtime behavior.
The previous worker reports are preserved in the review proof. Astra's boundary
verdict governs their broader statements.

| Saved selection | Process exit | Observed result |
|---|---|---|
| 140 pins from 02e06db | 1 | 138 compatible published wheel records, 283 active edges, zero missing targets or constraint conflicts among inspected metadata; two source-only distributions fail the wheel requirement |
| Earlier proposed upgrades | 1 | 275 active edges, five WhisperX conflicts, two missing targets, and three wheel failures |

The current selection's two failures are antlr4-python3-runtime 4.9.3 and
proxy-tools 0.1.0. Their source-built installed packages were checked separately
in package 08. This wheel-only result does not revoke those installed receipts.
It also cannot inspect requirements of the two absent wheels. Extras propagation
includes fsspec[http] and pyjwt[crypto]. The historical input lock is preserved so
future production pin changes do not silently change this observation.

The earlier proposal conflicts with WhisperX 3.8.6 on torch, torchaudio,
torchvision, torchcodec and huggingface-hub. It also omits hf-xet and typer, and
the captured Transformers 5.10.0 wheel is yanked. That proposal is rejected.
Torch 2.10.0 is not a complete repair for the retained advisory ranges. The
captured Torchaudio releases through 2.11.0 constrain the evaluated package
choices; they do not prove that a different source migration cannot work.
WhisperX 3.8.7rc1 metadata retains the Torch-family constraints. Widening them
would still require source review and authorized runtime qualification.

NLTK 3.10.4 is absent from the retained package capture. The separate local
backport was prepared at 4aec8ff; this graph observation neither packages nor
qualifies it. No security advisory is suppressed by these results.

The 306 original capture files remain unchanged. Their original SHA256.json
covers 304 files; fetch_summary.json was written afterward and the manifest does
not hash itself. The new review seal binds all 306 retained files. A local hash
manifest proves retained-byte consistency, not who published those bytes.

Fresh commands, stdout, stderr, JSON and process exits are in
proof/runtime-graph-astra-review-2026-09-12/execution.json. They ran offline with
socket and subprocess audit guards. No package import, build hook, checkpoint,
model or media fetch was used. Production pins and installed files are unchanged.
'''
(worker / 'docs/library/RUNTIME-GRAPH-01-2026-09-12.md').write_text(report,encoding='utf8',newline='\n')
verdict='''# Astra verdict: runtime graph checker boundaries

Accept the repaired offline checker, subject to checkout verification. Do not
accept either evaluated dependency selection as a security-cleared runtime.

Control Room db13e13b and 6c96f0a3 delivered proposals. Run 85ce8600 reported
completed/exit zero but had none of its required files; it remains incomplete.
Astra preserved all earlier source, reports and outcomes, then completed the
bounded repair in the 6c96f0a3 worktree. The repair brief and takeover brief
explain why these fresh observations were needed.

The checker preserves lock extras, rejects duplicate JSON and singleton METADATA
fields, requires usable HTTPS artifact URLs, stops after failed/bypassed integrity
checks, and reads only enumerated PyPI records and exact wheel metadata paths.
Consumed bytes are rehashed and parsed from the same read. Ancestors are checked
for links/reparse points; unsafe Windows roots are rejected before probing them.
Target overrides cannot mix non-Windows markers with fixed Windows wheel tags.
Exhausted extras propagation is an error. These controls do not claim protection
against every concurrent filesystem race or authenticate downloaded binaries.

Eighteen new boundary cases on the preserved worker checker produce 13 failures
and five passes. After repair, all 36 focused cases pass in the worker: 13 original
worker cases, 18 boundary cases and five unchanged installer-lock cases. Earlier
18- and 30-pass observations are retained. Checkout verification follows raw git
diff export and git apply --3way. No previously committed test is edited.

The current captured selection exits 1: 283 active edges, two source-only wheel
failures, no missing targets/conflicts among inspected metadata. The proposal
exits 1: 275 edges, five conflicts, two missing targets and three wheel failures,
including a yanked Transformers wheel. The original reports omitted some of those
limits and overstated impossibility of a future clean graph. The revised report
states only what these captures establish. NLTK preparation is separate.

Source migration, model qualification and original advisory dispositions remain
open. No production pin, installed runtime, source/media fetch, model execution,
live library, port 5179 or paid provider was used for this repair.
'''
(worker / 'docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md').write_text(verdict,encoding='utf8',newline='\n')
for tree in (root,worker):
    path=tree / '.gitattributes'
    raw=path.read_text(encoding='utf8')
    for name in ['runtime-graph-01-2026-09-12','runtime-graph-review-2026-09-12','runtime-graph-astra-review-2026-09-12','runtime-graph-integrator-2026-09-12']:
        rule='docs/library/proof/'+name+'/** -text'
        if rule not in raw: raw+='\n'+rule+'\n'
    path.write_text(raw,encoding='utf8',newline='\n')
paths=['scripts/check_runtime_graph.py','tests/test_runtime_graph.py','tests/test_runtime_graph_boundaries.py',
       'docs/library/RUNTIME-GRAPH-01-2026-09-12.md','docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md',
       'docs/library/proof/runtime-graph-01-2026-09-12','docs/library/proof/runtime-graph-review-2026-09-12',
       'docs/library/proof/runtime-graph-astra-review-2026-09-12']
out=root / '_scratch/graph13-integration01'
out.mkdir(exist_ok=False)
subprocess.run(['git','add','-N','-f','--',*paths],cwd=worker,check=True,capture_output=True)
patch=subprocess.check_output(['git','diff','--binary','--',*paths],cwd=worker)
(out / 'worker.patch').write_bytes(patch)
with (out / 'worker.patch.gz').open('wb') as f: f.write(gzip.compress(patch,mtime=0))
applied=subprocess.run(['git','apply','--3way',str(out / 'worker.patch')],cwd=root,capture_output=True)
(out / 'apply.stdout').write_bytes(applied.stdout)
(out / 'apply.stderr').write_bytes(applied.stderr)
(out / 'result.json').write_text(json.dumps({'worker':str(worker),'scope':paths,'exit':applied.returncode})+'\n',encoding='utf8')
print(json.dumps({'patch_bytes':len(patch),'compressed_bytes':(out/'worker.patch.gz').stat().st_size,'exit':applied.returncode}))
raise SystemExit(applied.returncode)
