# C22 scenario and operator-path repair — 2026-09-09

The second kit, 6accc421, remains rejected. Its worker reports 26 passes and
two failed original checks; the source-runtime receipt itself has two failed
capture scenarios and several unexecuted boundaries. Preserve them all.
Use `docs/library/proof/ryan-c22-review-02-2026-09-09/original.patch` as input.
Read AS-7's C22 list completely and write
`RYAN-C22-SCENARIO-TRUTH-WORKER-2026-09-09.md` early. Own only non-p4 files in
scripts/install_receipt, new regressions and your report. Freeze both original
kit test files unchanged. Do not alter production code or old acceptance fixtures.

These are concrete instrument defects, not permission to weaken product policy:

1. The launcher hashes the ordinary live index before/after startup. Remove
   every live-index open/hash. Store the forbidden path as a string and prove
   guard activity with a disposable canary only. Also honor the integrator's
   IG_FORBIDDEN_LIVE in every child even if LOCALAPPDATA changes. Install and
   restore the bundled guard only while all owned children have stopped;
   refuse conflicting/changing guard bytes. A repeated relaunch must not put
   raw bytes into JSON or erase the original restore state. Validate the port
   before even probing. Preserve all inherited API-key and network prohibitions.
2. Registered loopback RSS is correctly refused by source_subscriptions.
   Do not repair that product policy. Use a new explicitly synthetic hostname
   such as c22-fixture.invalid, with acquisition wrappers returning fixture
   bytes or routing only that exact hostname/path to the declared loopback
   fixture. Never resolve/fetch that hostname externally and never change
   source URL validation. Keep original server.main, scheduler, consent,
   deduplication, charging, persistence and publication routes intact.
   Wait for actual standing capture before the later manual action. Do not
   count a manual publication as the standing result. Give the three capture
   cases separate data/identities or compare exact scoped before/after deltas;
   the current shared profile and first arbitrary episode cannot prove ordering.
3. Read the actual migration schema. source_capture_starts has no origin,
   authority or kind field; its rows with started_at_ms are standing charges.
   Require exact capture_key, video/episode identity, consent receipt, charge
   and publication deltas for each ordering. Record the protected Phase 2
   baseline before running any scenario, then compare after all work. Current
   _protected takes adjacent snapshots after everything and passes even if
   earlier work mutated protected state. phase2_compare currently allows any
   mutation to a table merely because that table is named in allowed_deltas.
   Match exact new fixture handoff rows and unchanged prior rows instead.
4. child_instrument directly calls record_child_launch_intent/start in a
   separate process using the invoking interpreter. That is not actual helper
   child lifetime or recovery. Drive real original helper capture/subprocess
   paths with the declared acquisition/launch/registration failure hooks.
   Retain actual child creation identity, helper incarnation, claims, locks,
   charges, publication and settlement before/after whole-helper termination
   and relaunch. A boolean surviving_unregistered or any nonempty record is
   insufficient. Validate exact live identity; unknown stays unknown. Complete
   cleanup with owned handles and record surviving children until they exit.
   Child helper provenance must use the bundled interpreter when installed.
5. Complete the operator sequence. plan-install currently demands an already
   installed app, then creates a receipt root that later run refuses to reuse.
   Supply a prepare-before-install / continue-existing-receipt flow with strict
   source/package/profile bindings and no overwrite of completed scenarios.
   Do not rewrite an installed marker to switch profiles on every launch.
   Use separate isolated app/profile installations, or a documented supported
   binding route that preserves installer ownership. Require the new isolated
   Inno switches /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS; reject positive
   overrides. Require real module import paths, exact candidate file hashes,
   bundled interpreter version/dependencies, and checkout/user-site absence
   before installed credit. A printed cwd/server.py path or presence of a
   python.exe is not provenance. Use the final source manifest supplied by
   Astra; no invented seal. Source-runtime mode remains explicitly synthetic.

Use the current corrected startup anchor source from the checkout as the
disposable provisioner's input when needed; do not suppress reconciliation.
The final isolation code is being repaired separately. During worker checks,
the archived Python isolation module may be provisioned in scratch only for
valid runtime flags. No rejected --isolated-stop or Inno execution.

Add new meaningful tests: strict charge/schema oracles, protected old-row
mutation, no live-path opens, actual original-helper capture orderings and
child recovery, guard cleanup, and the prepared receipt continuation. An
instrument test must assert the scenario's measured success, not accept any
fail/unexecuted result as a passing test. Keep operator-only browser/Inno
boundaries unexecuted. Existing two conflicting kit assertions stay unchanged
and visibly failed; do not fabricate obsolete Inno args or synthetic browser
credit to satisfy them. Astra will record their contract conflict separately.

Run the two original files plus new tests under the sealed integrator guard
with direct C:\Python314\python.exe, fresh short scratch labels, disposable
LOCALAPPDATA/APPDATA/USERPROFILE before startup, and IG_FORBIDDEN_LIVE retained.
No raw unsandboxed kit execution. Record exact outputs/commands/counts and
repair reasons before reruns. No Setup/uninstall, 5179 contact/bind/probe,
live index open/hash, paid API, API keys, external fetch, model/client runs,
subagents, existing-test edits, commit, push or merge. Subscription Grok only.

Deliver an executable complete sequence and truthful receipts, not a promise
that Astra will write the missing scenarios later. If actual product behavior
still fails with a valid instrument, retain the evidence and name the precise
product defect; do not weaken any oracle to complete this run.
