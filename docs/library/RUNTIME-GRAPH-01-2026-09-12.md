# Captured runtime dependency graph, reviewed 2026-09-12

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
