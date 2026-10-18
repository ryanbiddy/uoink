# Re-acceptance brief (run H), 2026-09-04: Astra on candidate `b9c6a05`

Your run F report rejected `5d61bc8` on five cases. Since then, on top of that SHA:

- `df780f1` case 5: `scripts/recall_hook.py` staged in `build.ps1` and `installer/uoink.iss`;
  packaging test requires it (orchestrator).
- Gemini `control-room/77cfe10e-c62-gemini` (one commit): cases 1 and 2 in
  `scripts/librarian/bench_local.py` plus tests; xfail alignment on the librarian-profile
  adversarial test (canonical `truncation` fields), xfail removed.
- Claude `a6d7700`: case 3 (`unavailable_calls`, meter write status, four-counter pricing with
  stored rate provenance, `estimate: true`) and case 4 (Recall budget as a hard bound via
  `Connection.interrupt()` on a timer; real locked-database elapsed-time test).
- Merges `b9c6a05`. Integrator receipt: full suite = **664 passed, 3 skipped, 1 xfailed**
  (SEC-06 only). No conflicts.

Deliverable: append a dated "Run H re-acceptance" section to
`docs/library/ACCEPTANCE-REPORT-2026-09-04.md` (do not rewrite the run F body). For each of
the five cases, rerun your probe P reproduction against this tree and record observed versus
expected. Rerun the full suite and the measurement script against the named copy. Review the
Gemini and Claude diffs as an independent reviewer; reproducible failing cases only. Update
the unverified-release list. End with ACCEPT / ACCEPT WITH LISTED EXCEPTIONS / REJECT and
the candidate SHA. Own worktree; never merge, push, or open the live index; commit if git
allows, else leave files and say so.
