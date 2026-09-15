# Phase 3 repair brief, round 2 (run AT-3, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Astra's rerun
([PHASE3-ACCEPTANCE-2-2026-09-08.md](PHASE3-ACCEPTANCE-2-2026-09-08.md)) is NOT ACCEPTED: AS-04
and AS-05 are closed; AS-01, AS-02, AS-03 and AS-06 remain open, each with an exact repair and
a reproducing test in `tests/library_work_astra/test_phase3_repairs.py` (12 failed, 103 passed
on the integrated checkout, `PHASE3_REQUIRE_IMPLEMENTATION=1`). Base: the commit this brief
lands in. No worker runs a model, the resident helper, or touches port 5179 or the live
index. Do not commit; Fable integrates and runs every test.

## claude (Fable 5.1 worker): close AS-01, AS-02, AS-03, AS-06

Read the four open findings in the rerun report (they name file and line) and implement
exactly the repairs Astra specifies. In summary:

- **AS-01, validity not presence.** `_publication_evidence` must validate readable artifacts
  (parse the sidecar), agreeing identity and provenance, finite nonnegative ordered source
  timing, and clips derived from the actual evidence; the production YouTube inspection must
  not accept any citation row. Apply the same rule at completion, restart and pre-existing
  linking. Recovery must inspect recoverable local stages even without a corpus row (the
  reproduction interrupts `episode_to_corpus` before `upsert_yoink` with valid files on
  disk) and, after proving executor termination and acquiring the capture lock, finish
  publication under the original start. **Clips rule (Astra's ruling):** missing clips are
  permitted only when there is no timed evidence; a timestamped screenshot is timed
  evidence. Implement that rule, not `if transcript and not clips` and not `if not timed`.
  Do not manufacture transcript text from screenshots; leave unsupported publication
  incomplete. If you believe screenshot-only captures should complete without clips, say so
  in your report as a proposed contract amendment and still implement the ruling.
- **AS-02, terminal evidence before release.** `complete_capture` must require terminal
  executor evidence on the complete-evidence branch; an `unknown` executor keeps the attempt
  in flight with publication visible. `verify_proof` must check the executor, its
  incarnation, the job/start binding and terminal evidence; absence of a local thread is not
  death. `execute_started` must atomically re-read ownership and state before acquisition,
  recheck after waiting for the lock, and fence publication; restored podcast jobs must
  obtain verified execution ownership before resuming. **Proof default (Astra's ruling on
  Fable's `_backend_call`):** the `CaptureBackend` base `verify_proof` returns `False` unless
  executor completion is established; a backend that can prove more overrides it. Keep
  `_backend_call` for the other four methods (publication fallback, no-op locks,
  conservative recovery) as Astra found appropriate.
- **AS-03, lock failure is not ownership.** Every failed shared-lock acquisition
  (`OSError`, `PermissionError`) is unavailable ownership: standing work releases its
  unstarted reservation and stays eligible without charge; manual work returns a retryable
  failure or waits within a defined bound. Never substitute a Python lock after an OS-lock
  error (`server.py` around 7274, `_ensure_ownership`, `_manual_extraction_ownership`, the
  manual podcast worker). Recheck canonical corpus identity on both dispatcher paths after
  acquiring the lock.
- **AS-06, reverse legacy episode link.** One full-identity check for linking, recovery and
  `episode_to_corpus`, including episodes already linked by `yoink_video_id`, run before any
  overwrite; disagreement or unestablishable identity is a blocked identity conflict, never
  an overwrite. Preserve existing content and deletion tombstones.

Astra's tests are the acceptance target and must not be edited: the 12 in
`test_phase3_repairs.py` must pass together with the existing 103, and the service (111),
dashboard (31), legacy, adapter, podcast and packaging suites must stay green. Adjust an
existing service test only where a repair legitimately changes its assumption, and say
which. Cite the finding id in a comment at each repair. You cannot run a shell: list the
exact pytest commands Fable must run. Read only what you need (`source_subscriptions.py` is
large; use targeted searches) and write code early.
