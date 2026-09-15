# Phase 2 stage 1 re-acceptance brief 2 (run O), 2026-09-04: Astra on the N-1 repair

Run N rejected `a6725de` on N-1 only (session mapping); M-1 was accepted as repaired and
rule 1 routing ruled appropriate. Since then, on top of `39d958d` (your run N merged): the
orchestrator applied the N-1 repair in one commit (the parent of this brief):
`_library_context` carries `server._library_session_hash()` on every transport, health
included, derived from the backend and never from tool JSON; the one adapter test that had
encoded the bug now asserts the corrected expectation. Integrator receipt: your 16 M/N
reproductions pass; full suite **904 passed, 3 skipped, 1 xfailed**.

Deliverable: append a dated "Run O re-acceptance" section to
`docs/library/PHASE2-ACCEPTANCE-REPORT-2026-09-04.md`. Rerun N-1's six cases, the M cases
and the suite on this tree; review the repair as an independent reviewer, specifically that
no tool JSON field can set or override the session, that token rotation still orphans
unconsumed intents, and that another session is still refused; confirm P2-0..P2-5 hold and
state P2-6's adapter-delivery result; refresh the unverified list (installed client, P2-7).
End with ACCEPT / ACCEPT WITH LISTED EXCEPTIONS / REJECT plus the candidate SHA. Own
worktree; never merge, push, or open the live index; commit if git allows, else leave
files and say so.
