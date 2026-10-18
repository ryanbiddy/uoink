2026-09-13. Accept the repaired outer runner's tested exit-recording behavior
and the source-reviewed dormant D1 invocation. Actual checkpoint inspection
remains disabled pending the handoff's separate D1 decision. This review grants
no conversion, native model, installation or release approval.

The repaired wrapper passed the same 12 cases in both author and independent
Astra runs: zero failures, 5.7517623 and 5.657456 seconds respectively. All
qualification/native/outer exits were zero, stderr was empty and 13 inputs in
each run remained unchanged. Four separate controls matched in each run;
they are observations of the original wrapper, not additional repair passes.

On the observed PowerShell 7.6.5, inherited native-error promotion caused the
original wrapper to throw before recording child exits 1, 2 and 3. The repair
disables that promotion and writes an exclusive, flushed numeric receipt before
later formatting or log reads. All four native exits survive the deliberately
failed log postcheck, whose caller exit stays 91. Neither native success nor
an existing output file can erase that later failure. These checks do not
simulate power loss or every filesystem failure.

Wrapper SHA-256:
11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63.
Both runs execute only the inert child 9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f.
The repeated case directories use the expected launch_d1.py filename, but do
not contain or execute the real D1 launcher. The source-review refinement also
moves the qualifier's own process-outcome receipt ahead of stream/log handling.

Astra separately read the complete dormant launcher bf865aff26515aa54e09ae046e53e6c9fb5efb688ccec676b170e8313af851e4
and child 577b1a22ebe5490ba28f5a56a46e5b3d3f5b85e077de3c1cafad6205aeb29a90.
Both owner pins remain None and refuse before artifact operations or helper
execution. A future activated copy must bind the actual decision, all reviewed
sources and the repaired wrapper in a fresh source map; old pins cannot be
reused as approval.

The concrete proposed D1 action is one static inspection of the fixed existing
17,719,103-byte checkpoint, SHA-256
0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea,
at installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin.
The reviewed adapter hashes the bounded snapshot and checks the stored ZIP
inventory, then interprets only two 500-byte buffers and two version bytes.
It never evaluates pickle, converts tensors, loads a model or contacts a network.
The fixed eight-ULP comparison may establish one consistent orientation; it
cannot authenticate the writer or establish every other storage's encoding.

The activated child would have one exact artifact-open allowance and one
exclusive bounded JSON output. The parent allows one child with a 60-second
external timeout; the adapter has a cooperative 30-second budget. Private,
quiescent paths remain required. Reviewed Python guards are not an OS sandbox.
Any actual result must be reviewed before the separately reserved conversion
or runtime decisions. This task did not access the checkpoint.

The combined proof has 102 payloads (980,492 bytes), with all 460 source files
accounted for and 370 exact case files in a deterministic stored ZIP. Manifest
SHA-256 is 6e66e110c39f12789b30414ebca3603bddb1d267ce62c4c34c56274581f0394b.
Astra independently ran its reviewed documentary verifier: tool aedbb3,
exit 0, 0.1981246 seconds. It checked both original seals, the 12 root copy
bindings, the sole launcher-path change, exact ordered case equality and all
native/outer receipts. It executed no archived test or D1 program. See
[the sealed proof](proof/vad-d1-wrapper-2026-09-13/README.md).

The unrelated ASR wrapper check subsequently exposed a null exit capture after
a locally assigned LASTEXITCODE. That failed instrument remains under repair;
the passing D1 evidence cannot qualify its different reset/capture block.
Website and marketing remain paused.
