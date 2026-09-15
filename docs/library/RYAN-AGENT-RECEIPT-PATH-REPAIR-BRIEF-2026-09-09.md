# Agent receipt path correction and observation review, 2026-09-09

Before executing Setup, Astra found that the reviewed driver's receipt root was
inside the checkout. Phase 4's original installed provenance oracle correctly
rejects modules and sys.path entries inside the forbidden checkout. Do not relax
that oracle or pass a narrower forbidden-checkout path. No installer was run.

Change the driver's fixed allowed parent to
`E:\AI\projects\uoink\installation-receipts`, outside the checkout. Require a fresh
child directory with spaces in its name, retaining every path/reparse check,
package hash, non-elevated identity, ordinary-effects comparison and actual
shortcut assertion. No ordinary data or credentials are copied. The existing
same-account limitation remains explicit. The source repository remains
`E:\AI\projects\uoink\checkouts\Yoink-library` and must remain the exact forbidden
checkout for installed Phase 4 checks.

Review the proposed observation wrapper at the source checkout's
`_scratch/agent_receipt_observe.py` and corrected
`scripts/install_receipt/agent_install.ps1` before running either. The wrapper
selects the new package seal through the compatibility manifest loader's data
directory; all original integrity checks remain. For preparation only, use the
existing skip_ordinary_user_check API under Ryan's installation delegation, with
actual USERPROFILE retained and same-account identity recorded. Never describe
that as throwaway-account or OS containment. Actual install and reinstall effects
must exist before original installed C22/P4 stages run. No synthetic-mode switch
may be used to obtain installed credit.

Gemini: read both exact source files at those absolute paths, their original kit
APIs and the agent installation verdict. Perform read-only review; no Setup,
helper, browser, client, keyring, model or network fetch. No paid API. Do not
alter tests or product files. Produce
`docs/library/GEMINI-AGENT-RECEIPT-PATH-REVIEW-2026-09-09.md` in your worktree with
file hashes, concrete defects and a bounded verdict. Parse PowerShell and Python
without executing them. Astra independently repeats these parse/hash checks and
reviews the original kit call paths before using the wrapper. If a defect needs
repair, retain the proposal and document the correction before execution.
