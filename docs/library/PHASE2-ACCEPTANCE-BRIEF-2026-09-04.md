# Phase 2 stage 1 acceptance brief (run M), 2026-09-04: Astra on candidate `f53adaf`

Under ORCHESTRATION-V1 rule 4. Candidate `f53adaf` = run J (substrate `7893034`, adapters
`34871ed`, Gemini tests `6c5a2ae`) + run K reconciliation (`1437e55`, `8cda314`, `1d79e9e`)
+ run L rulings (`54843b6`, `ee31165`) + the bridge fixture fix `8f43313`. Contract
`phase2-v1.2-2026-09-04`. Integrator receipt: full suite = **888 passed, 3 skipped, 1 xfailed**
(SEC-06). Independent evidence on this tree: Gemini 33 + R1-R5 tests, Claude 20 audit
tests, your 68 checks.

Deliverable: `docs/library/PHASE2-ACCEPTANCE-REPORT-2026-09-04.md`. For gates P2-0 through
P2-5 in `PHASE2-CONTRACT-2026-09-04.md`: observed versus expected on THIS tree with the
command and number you saw. Rerun the suite and the independent tests yourself. Rerun the
migration gate against a disposable duplicate of the named copy (sha256
`2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`): schema 26 -> 27,
repeat-open unchanged, integrity checks, zero initial work/assignments. Review the Claude
adapters (`uoink_mcp_tools.py`, `server.py` intent route, `uoink_mcp.py`) as an independent
reviewer: parity, privileges, default-off apply. Review every integration edit by the
orchestrator (`8f43313`, the relocation of your checks into `tests/library_work_astra/`).
Reproducible failing cases only. List what stays unverified (P2-6 installed client, P2-7
proof) and what run N needs to close them. End with ACCEPT / ACCEPT WITH LISTED EXCEPTIONS
/ REJECT plus the candidate SHA. Own worktree; never merge, push, or open the live index;
commit if git allows, else leave files and say so.
