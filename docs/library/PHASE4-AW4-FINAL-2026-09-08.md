# AW-4 final implementation review

The observed implementation findings are closed at `6858b81`. The complete
named union produced **286 passed, nine frozen failures** in both roots,
168.87 seconds worker and 168.01 seconds checkout. The four remaining broader
companion files passed **113 tests**, 1.27 seconds, on `fad7e87` with the same
production bytes. These are separate invocations, not one combined measurement.

Phase 4 still needs the actual client receipt. This implementation review does
not replace its five requirements or Ryan's installed Inno and fixture rulings.

## Closed boundaries

| Boundary | Final evidence and behavior |
|---|---|
| Destination consent and binding | AW4-01/02 and A2: missing previous authority requires reconciliation; failed atomic persistence preserves prior durable binding bytes. |
| Owned file mutation | A3/AW-6: creating file/volume identity and hash stay bound through Windows replacement and cleanup. A different file at the allocated path remains intact, even with identical content. |
| Process lifetime | AW-9, B5, B7 and AW-12 retain unknown children and unresolved launch ownership, distinguish launcher/writer identities, preserve the gate after caller-thread exit, and release after proven death. |
| Destination aliases | AW-10/B6 verify that the shared Windows admission gate covers an owned junction before lease creation. Unrelated destinations serialize on `Local\uoink-mirror-writer-admission`. Session/destination/token/operation binding stays separate. |
| Local intent mutation | B4 isolates the final put/unlink. AW-11/B7/AW-12 preserve original operation authority, refuse foreign helpers and recycled integer-ID adoption, and retain ordinary originating-helper behavior. |
| Job cleanup | AW-12 holds the job through launch assignment and gives overlapping cancellation one cleanup owner. Its concurrent termination case observed one job close and retained exclusion until cleanup. |
| SQLite ownership | The supported Index write-transaction marker preserves caller work. An inherited deferred read or other unproven transaction refuses publication without rollback or a fabricated write-lock probe. |
| Staging and shared contracts | The required writer is included in source staging and the full installer path. Broader stdio clip, registry/capture, adapter and live-documentation contracts pass. F/H2 and BC-3f source bindings remain preserved. |

The nine frozen failures retain their original status. They concern old
parent-process interceptors, the contradictory D13 user-edit setup and D15's
interception of a removed direct write. New observations of isolated mutation
do not relabel those assertions as passed. No existing acceptance test or
helper changed. Original rejected patches and measurements remain archived.

## Evidence and limits

`PHASE4-AW12-2026-09-08.md` distinguishes Grok's original B7 output from
Astra's correction. Its original seal covers 21 files and its final seal 38;
all hashes match committed bytes. Worker/checkout mirror raw hashes differ
only in line endings; normalized bytes match exactly. The final proof retains
both forms, the exact applied patch, commands, complete logs and XML.

The broader result is retained under `proof/aw4-final-2026-09-08/`. It ran
`test_stdio_clip_tools.py`, `test_phase0_registry_capture.py`,
`test_library_adapters.py` and `test_docs_live_contracts.py`. It adds to the
immediately preceding full implementation union on identical production code.

This is the Windows release. Unsupported POSIX identity deletion/publication
refuses and retains cleanup. Parent destination probes can outlive their
timeout in a thread; terminating a writer does not terminate that parent
syscall. Startup, publication budget, cancellation return and termination are
separate observations. A two-second publication budget is not a two-second
bound for the entire startup-to-cleanup sequence.

AW-12's integer-ID reuse was simulated at the identity query; its thread,
writer and changed/refused intent bytes were real. Its job-assignment probe
prevented a known stale-handle kernel call. No actual recycled Windows handle
call or post-timeout publication is claimed by that probe.

Proceed with `PHASE4-CLIENT-RERUN-BRIEF-2026-09-08.md` on a clean frozen SHA.
The original real-client receipt at `d4d99bb` remains partial. Keep label apply
disabled, use only the authorized archived copy and held item pairs, and retain
native prompt traffic, full returned content and actual client actions.
