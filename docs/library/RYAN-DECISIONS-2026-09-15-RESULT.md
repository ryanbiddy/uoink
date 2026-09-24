# Ryan decisions result - 2026-09-15

Status: items 1-5 complete in Codex's worktree, based on `1ca39c0`.
Ryan's decisions were relayed by Fable for 2026-09-15 09:30 PDT.
The diff is uncommitted; Fable owns integration and publication (item 6).

## Per-item result

1. AT6: added `xfail(strict=True)` with the unrecoverable historical receipt
   gap reason; the original assertion remains. It is not a release blocker.
   File: `tests/library_work_astra/test_phase3_acceptance7.py`.
   Test: 11 passed, 1 xfailed, exit 0 (1.35s).
2. Controller10: applied exactly the two approved `SessionClosed` substitutions
   at lines 128 and 300. The original failed result remains historical.
   File: `docs/library/proof/controller-custody10-failed-2026-09-14/author/test_controller_resume_publication.py`.
   Test: 10 passed, 104 subtests passed, exit 0 (0.34s); run once, track frozen.
3. Signing: recorded `SigningCertificateThumbprint=none`, unsigned 3.8.0,
   retained repaired signing path and deferral to 3.9.
   Files: `docs/security.md` and the three shared decision records below.
   Test: documentation only; no signing or build run.
4. Desktop: recorded Ryan's local standard-account setup and personal sign-in.
   If setup and verification are incomplete at packaging, use "tested with
   Claude Code" and list Desktop as unverified.
   Files: the three shared decision records below.
   Test: documentation only; Desktop was not launched.
5. Stack: retained Torch 2.8.0 / WhisperX 3.8.6; disclosed the default PyAnnote
   `weights_only=False` VAD loader, unchanged from 3.7.0, and local-only model
   files as mitigation. Migration is planned for 3.9. No further D3/D4.
   Files: `docs/security.md`, the shared records and the archive index below.
   Test: documentation only; no model/runtime execution. Track archived in place.

## Shared records and new files

- `docs/library/RELEASE-OWNER-DECISIONS-2026-09-12.md`: all five decisions and Fable's ownership.
- `docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md`: only "Blockers for Ryan" changed.
- `docs/library/RELEASE-NOTES-LIVING-LIBRARY.md`: only "Open release decisions and limits" changed.
- New: `docs/library/ARCHIVED-RUNTIME-TRACK-2026-09-15.md`, with retained commit index.
- New: `docs/library/RYAN-DECISIONS-2026-09-15-RESULT.md` (this file).

## Validation and handoff

Both files ran once with Python 3.14.6 and `python -B -m pytest -p no:cacheprovider <file> -q -ra`.
`PYTHONDONTWRITEBYTECODE=1`; `PYTHONPATH` was this worktree; plugin autoload was disabled.
AS-7 also used `PHASE3_REQUIRE_IMPLEMENTATION=1`. No complete-tree run occurred.
`git diff --check` passed; exact controller edits and section boundaries were checked.
Eight files changed, including this report. No proof files were created or deleted.
No commit, push, merge, Control Room dispatch, Desktop launch or new review loop.
No live index access, port 5179 contact or `ANTHROPIC_API_KEY` assignment.
Open questions: none for items 1-5. Ryan's Desktop verification remains pending;
Fable handles the packaging fallback and publication. Codex stops here.
