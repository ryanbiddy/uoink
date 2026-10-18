# Gemini final process-authority review

Review the committed mirror repair747fb6b in your isolated Control Room worktree.
Read ASTRA-AUTHORITY-REPAIR03-VERDICT-2026-09-13.md and the current source first.
Both roots passed the same233 Phase4/owner/authority cases. This is a fresh,
bounded independent review before the combined candidate is qualified.

Write docs/library/COUNCIL-AUTHORITY-FINAL-REVIEW-2026-09-13.md early, then finish
it with the exact source blob/hash, scope, verdict and any concrete findings.
Review three boundaries: process identity held from relationship proof through
mutation; concurrent handle use/closure and borrowed Popen lifetime; cancellation
and destination exclusion while discovery/launch/termination overlap. Read the
new tests to understand covered cases, but reason from production control flow.
The accepted ff67b84 owner repair must remain intact.

Do not execute native process tests or modify source, tests, fixtures, markers,
receipts, pins or evidence. This run is source review only. If you find a defect,
give a specific call sequence, affected lines, consequence and smallest repair;
separate observed tests from unexecuted reasoning. If no actionable defect is
found, say so within this review scope. Do not certify the whole release or
relabel historical failed measurements. At most three substantive findings;
avoid stylistic suggestions and broad speculative redesign.

Source reading and the one-page report are the entire task. No subagents,
network/software/model downloads, runtime or installed application execution,
paid API, live-index access, port5179, website, marketing, commit, push or merge.
Never read credentials. librarian_apply_enabled stays false. The separate
runtime security, signing, historical and client gates remain open.
