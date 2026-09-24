# Proof audit brief (run R), 2026-09-05: Astra audits the P2-7 receipts

Under ORCHESTRATION-V1 rule 4 and your `PROOF-PLAN-2026-09-05.md` "Run-Q audit checklist".
The proof ran; receipts are in `docs/library/proof/run-2026-09-05/receipts.json` (sha256
`2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`), harness log beside it,
scorer report beside it, and the orchestrator's result document in
`docs/library/PROOF-RESULT-2026-09-05.md` with five rulings made during execution.

Deliverable: `docs/library/PROOF-AUDIT-2026-09-05.md`. Rerun `tests/validate_proof_receipts.py
--require-real` and `scripts/librarian/proof_score.py` on the archived receipts yourself;
replay the evidence checks on the 34 accepted held-out assignments; verify zero applies and
the before/after state from the receipts; audit input bytes, usage receipts and the wall
attribution; then rule on each of the five orchestrator rulings (accept, or state the
reproducible reason not to), on the service gap (quote word cap not enforced by
`library_work.py`), and on the scoring rule (mapped ancestor versus exact path versus
ancestor-tolerant) as the gate definition going forward. State plainly whether P2-7 is
ACCEPTED AS MEASURED (receipts valid, gate FAIL recorded) or REJECTED (receipts not
trustworthy), plus the candidate SHA. Then, as the plan owner, write the Phase 2 stage 2
contract sketch in `docs/library/PHASE2-STAGE2-SKETCH-2026-09-05.md`: taxonomy induction
from the 225 unmapped cards, refusal-rule strengthening, sibling cues, and what one more
measured pass must show. No model execution; never the live index; own worktree; commit if
git allows, else leave files and say so.
