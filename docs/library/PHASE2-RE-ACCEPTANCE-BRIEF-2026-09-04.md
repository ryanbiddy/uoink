# Phase 2 stage 1 re-acceptance brief (run N), 2026-09-04: Astra on the M-1 repair

Run M rejected `f53adaf` on M-1 only; P2-0 through P2-5 passed at the service boundary.
Since then, on top of `10e4702` (your report merged): the orchestrator applied the M-1 repair
under rule 1 in one commit (see `git log -1` on the parent of this brief): `_library_dispatch`
in `uoink_mcp_tools.py` translates the adapter's trusted context into `RequestContext` and
calls `fn(index, context, args)` on the real module; health uses the same path; and the
pre-existing `tests/test_openapi_bridge.py` now restores `server._mcp_tools_module`, which it
had replaced permanently (your reproductions were the first later tests to drive the real
handler). Integrator receipt: your six reproductions pass; full suite **894 passed, 3
skipped, 1 xfailed**.

Deliverable: append a dated "Run N re-acceptance" section to
`docs/library/PHASE2-ACCEPTANCE-REPORT-2026-09-04.md`. Rerun M-1's reproductions and the
suite on this tree; review the repair diff as an independent reviewer (session mapping,
operator/user authority derivation, apply-setting sync, the stand-in branch); say whether
the rule 1 routing was appropriate; confirm P2-0..P2-5 still hold; refresh the unverified
list (P2-6, P2-7) and what run O needs. End with ACCEPT / ACCEPT WITH LISTED EXCEPTIONS /
REJECT plus the candidate SHA. Own worktree; never merge, push, or open the live index;
commit if git allows, else leave files and say so.
