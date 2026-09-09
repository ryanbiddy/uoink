# AV-5m4b5: retain exclusion through uncertain worker lifetime

Engine: Grok. Read `PHASE4-AW9-2026-09-08.md` and
`PHASE4-AV5M4B4-BRIEF-2026-09-08.md` completely. Start from the current
checkout and three-way apply
`patches/av5m4b4-grok-rejected-2026-09-08.patch`. Retain all A3 identity,
F/H2 transport and BC-3f media changes. Write
`docs/library/PHASE4-AV5M4B5-GROK-2026-09-08.md` early; a run without the
report and decisive evidence is incomplete. Record any overlap resolution.

## Three required repairs

1. Treat unknown physical liveness as unresolved ownership, distinct from
   cancelled admission and proven death. Audit kill, stop, shutdown, start,
   forgetting, lease cleanup and exclusion release. Do not turn an unknown
   writer into dead merely because its launcher exited. Preserve identity
   evidence across PID reuse; do not terminate a process from a recycled PID
   or executable name alone.
2. Retain actual cross-process exclusion independently of the request thread.
   Keeping a Windows mutex handle does not keep its ownership after the
   acquiring thread exits. Establish a lifetime owner before any writer can
   start, with bounded acquisition/refusal. A dedicated owner thread or
   process must acquire and release the mutex itself and remain responsible
   until all mutators are proven dead. An abandoned mutex is not evidence
   that an old writer is dead. Cover caller return and exit before a lease
   exists and after it exists. Audit process exit and shutdown too. Preserve
   exclusion across different TEMP/profile roots and supported destination
   aliases; do not reintroduce parent filesystem resolution that can hang.
3. Retain a failed-start session before starting the process. If job
   assignment or readiness fails and termination is unconfirmed, keep its
   process ownership and destination exclusion after the exception and
   caller-thread exit. Cover helper-created sessions as well as Mirror's
   regular path. Cleanup may release only after proven physical death.

Keep B4's final local intent/binding/ledger replace and unlink inside the
original isolated operation. No parent fallback or adoption of a later
session. Preserve A3's creating file/volume/hash authority, Windows bound
rename/delete and unsupported POSIX refusal. Keep B3's supported Index
write-transaction marker; no native SQLite pointer guesses or caller rollback.
If a new runtime module is needed, stage it in the installer and verify that
path. Existing acceptance tests and helpers are frozen. B/B2/B3/B4 tests in
the rejected patch are unintegrated; repair only demonstrated setup defects,
preserve behavioral assertions and remove vacuous evidence claims.

## Verification

Run one combined union from final source bytes with these explicit selectors:

```
tests/library_work_astra/test_phase4_aw_acceptance.py
tests/library_work_astra/test_phase4_aw2_acceptance.py
tests/library_work_astra/test_phase4_aw3_acceptance.py
tests/library_work_astra/test_phase4_aw4_acceptance.py
tests/library_work_astra/test_phase4_aw5_acceptance.py
tests/library_work_astra/test_phase4_aw6_acceptance.py
tests/library_work_astra/test_phase4_aw7_acceptance.py
tests/library_work_astra/test_phase4_aw9_acceptance.py
tests/library_work_astra/test_phase4_aw9_startup_acceptance.py
tests/test_phase4_av5m3_isolation.py
tests/test_phase4_av5m4a2_binding.py
tests/test_phase4_av5m4a3_identity.py
tests/test_phase4_av5m4b_lifetime.py
tests/test_phase4_av5m4b2_lifetime.py
tests/test_phase4_av5m4b3_lifetime.py
tests/test_phase4_av5m4b4_lifetime.py
tests/test_library_resources.py
tests/test_library_prompts.py
tests/test_library_briefs.py
tests/test_library_mirror.py
tests/test_library_mirror_wiring.py
tests/test_phase4_stdio.py
tests/test_c01_mcp_stdio.py
```

Include new B5 tests in that union. B4's independent result was **255 passed,
nine failed**, 134.12 seconds; its three AW-9 failures are additional. Retain
all prior failed outputs. The nine frozen setup cases remain failed for Ryan;
the three AW-9 cases and all other implementation defects remain your work.
Prove actual writer stall and physical death under the Windows virtual
environment's launcher/child topology, not just direct Python. Add real
competitor-process observations before and after lease creation, and verify
that eventual proven death permits later ownership without a leaked gate.
Separate startup, operation, termination and caller-return timing.

Use a task-specific selector variable, never PowerShell's automatic `$args`.
Use short disposable roots, no bytecode and resolved installed dependencies
including pywin32. No live index, port 5179, model, API key, paid API, commits,
pushes, subagents, test-wrapper inspection, async Python exceptions, destination
rollback or broad process stops. Apply stays false. Astra verifies both roots
before integration, then finishes AW-4 and the real-client receipt.
