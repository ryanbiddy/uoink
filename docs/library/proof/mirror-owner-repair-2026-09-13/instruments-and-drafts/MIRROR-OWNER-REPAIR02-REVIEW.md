# Correct recursive guard acquisition before broader verification

Owner-repair01 passes eleven focused cases, including the unchanged original
handoff probe. Independent static review found a new deadlock in the draft:
release_if_unneeded holds _dest_hold_guard (a non-reentrant threading.Lock) and
calls detach, which reacquires it. The stale-snapshot cases returned before this
ordinary stale-session path, so those passes did not cover the defect.

Preserve the first product and test drafts and the eleven-pass observation.
Remove stale sessions directly while holding the existing guard. Add a case
covering an unchanged stale-session snapshot with a strict non-reentrant guard
that raises on recursive entry; this safely detects the same lock error without
hanging the test process. Run a fresh focused label, then the prescribed Phase 4
suites only if that result and the independent diff review permit it. Existing
committed fixtures and assertions remain unchanged.

The corrected draft passes twelve cases in owner-repair02. The review also
found that exceptions in a sweep thread could leave admission held and satisfy
the test. Preserve that test draft, capture thread exceptions and assert the
list is empty. This changes only the new, uncommitted review tests. Use the
fresh owner-repair03 label for final focused verification.
