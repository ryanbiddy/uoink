# Native note display: integrator review and repair

Control Room run d8840cdd-c3ae-4816-aa90-af5d577e544c proposed a focused
dashboard repair. Astra independently reproduced its 54 passing tests under
astra-native12-worker01. That result does not close the review findings below.

The worker made `synthetic_fixture` sufficient for healthy note content, and
accepted any truthy `note` value, including the boolean marker used in metadata.
Neither proves that text exists. Its new enrichment test expressly expects the
fixture flag to pass. Reject that new test module from the active tree and retain
its exact bytes with the raw worker patch. Existing repository tests are unchanged.
New integrator regressions exercise real note persistence, actual rendering and
negative states without depending on that fixture flag. The worker's original
54-pass observation remains separate from these new checks.

The worker also reports both Saved details and Local facts as ready for every
note before the markdown request finishes or after it fails. Replace this with
the actual markdown state: checking, ready, empty or unavailable, with a specific
load error retained when available. A note does not need a media JSON fetch, but
skipping that fetch must not manufacture readiness. Use the existing text endpoint
and retain the image-only `/file` endpoint and its path restrictions.

Repair scope: require nonblank string content for a note health snapshot; ignore
synthetic and boolean markers; keep inapplicable media assets skipped; share the
snapshot calculation within notes.py to avoid duplicate persistence logic. Make
note readiness follow the actual text load. Keep source labels and the worker's
omission of video-only controls. Do not make sparse historical fixtures healthy
without evidence or change the original fixture generator. No new file reads,
fetches, dependencies, models or sidecar-serving endpoint are needed.

Before repair, run the new regressions against both original checkout source and
the original worker patch, preserving failures. Then repair in the worker tree,
run the five existing suites from the original brief plus the new regressions,
export the accepted binary diff, apply it with `git apply --3way`, and repeat the
same suites in the checkout. Preserve the original worker report and every failed
attempt. Source changes require a new complete tree and package-08 qualification.

This review accepts no security clearance. The dependency advisories, historical
AT6 exit-record gap and incomplete Claude Desktop GUI observation remain open.

## Observed results and verdict

The 16 new regressions produced 6 passes / 10 failures against original source
(astra-note12-negative01) and 7 passes / 9 failures against the original worker
patch (astra-note12-negative02). The corrected patch passed all 60 selected cases
in the worker tree (astra-note12-repair-worker02, 5.22 s) and in the checkout
(astra-note12-repair-checkout01, 4.87 s). No existing tests changed. The worker's
ten-test proposal is retained as rejected evidence, not counted in the new tree.

One attempted verifier launch failed before pytest because the outer command
omitted IG_FORBIDDEN_LIVE, which an inherited audit hook requires. Its exit 1 and
diagnosis are retained. Restoring the literal guard variable was the only change
before the worker02 invocation. There was no test execution in worker01.

Three-way application succeeded. The transport script's subsequent exact
worktree-byte assertion failed because Git checked the new Python file out with
CRLF. The index blob matches the original LF source; normalized worktree bytes
match too. This is a transport check limitation, not a failed application or a
reason to rerun passing product checks. Both original and accepted patches and
the byte comparison are retained in proof/native-note12-astra-review-2026-09-12.

Verdict: accept the bounded product repair, subject to the complete tree and new
installed native observation. Package-07's screenshots still show the old defects.
