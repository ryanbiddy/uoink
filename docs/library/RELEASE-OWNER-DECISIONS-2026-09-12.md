# Living Library release owner decisions

Ryan decided items 1-5 on 2026-09-15 at 09:30 PDT, relayed by Fable. These
decisions supersede the earlier pending choices and runtime work queues.
Codex applies items 1-5 in this worktree; Fable owns publication (item 6).

## Decisions for 3.8.0

1. **AT6:** Disclose the missing child-exit status as an unrecoverable historical
   receipt gap. It is not a release blocker. Mark
   `test_as7_c21_at6_receipt_records_process_exit_status` in
   `tests/library_work_astra/test_phase3_acceptance7.py` as `xfail(strict=True)`
   with that reason. Keep its assertion and the original evidence; a new run
   cannot reconstruct the historical exit status.
2. **Controller10:** Approve exactly the two expected-exception changes in
   `proof/controller-custody10-failed-2026-09-14/author/test_controller_resume_publication.py`:
   at line 128, use `SessionClosed if fault == "wrong_permit" else REFUSALS`;
   at line 300, use `self.fail_start(f, SessionClosed if fault == "active" else REFUSALS)`.
   Nothing else in that file changes. Run this file once, then freeze the
   controller track. The original result `6ba3f1` remains 8 passed, 2 failed,
   0 skipped, with 102/104 passing subtests; the correction does not rewrite it.
3. **Signing:** No certificate for 3.8.0. `SigningCertificateThumbprint=none`.
   Skip signing and retain the repaired signing path. Signing is a 3.9 item.
4. **Claude Desktop:** Ryan will create a local standard Windows account and
   sign in himself. If that setup and Desktop verification are not complete by
   packaging, ship 3.8.0 with "tested with Claude Code" and Desktop listed as
   unverified. Codex must not launch Desktop. The failed profile override
   remains unusable; the earlier incident's effects remain unknown.
5. **Model stack and runtime archive:** No migration for 3.8.0. Ship Torch 2.8.0 /
   WhisperX 3.8.6. [Security notes](../security.md) disclose default VAD loading
   through PyAnnote's checkpoint loader with `weights_only=False`, the same
   path as 3.7.0, with local-only model files as the mitigation. Migration is
   planned for 3.9. All synthetic runtime-owner, journal, controller and
   state-machine work is archived in place and frozen. See the
   [archive index](ARCHIVED-RUNTIME-TRACK-2026-09-15.md). No further D3/D4 work.

## Publication ownership and claims

Ryan assigned item 6 to Fable on `release/3.8.0`: remove the `docs/library`
proof bulk from the public tree, squash the product diff onto main, build
Package 09 and tag `v3.8.0`. Codex leaves an uncommitted diff for Fable to
integrate into `cc/living-library-candidate` and stops after items 1-5.
Speaker attribution and autonomous filing claims are withheld. Desktop claims
are withheld unless item 4 passes. Phase 2 stays suggestions-only with
`apply=false` and the 0.90 autonomous threshold; Phase 5 Part B is deferred.
The X blocked-link condition remains.

## Retained historical limits

D1 static inspection was approved and recorded at `4b38948`; D2 local conversion
was approved at `017b559` and recorded at `d13534f`. Their recorded scopes and
results remain historical. Neither authorizes more model access, loading,
fetching, redistribution or runtime work under this release decision.
The retained dependency findings are not a clean security clearance.

The latest recorded production repair is `71d3e70`, following `e8d058f`.
Complete tree `56d9d4c` predates both: 2,796 passed, 1 failed, 3 skipped,
plus 13 subtests. Package 08 represents `b8e44fb`; those results do not
establish Package 09 or current-source installation verification.

The live index and port 5179 remain prohibited. No API key, Desktop launch,
Control Room run, model execution or additional review cycle is part of this
handoff. Focused test outcomes and changed files are recorded in
[Ryan decisions result](RYAN-DECISIONS-2026-09-15-RESULT.md).
