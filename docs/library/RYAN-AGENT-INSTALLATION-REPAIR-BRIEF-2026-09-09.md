# Agent installation corrections, 2026-09-09

Gemini 6a8378f1 found two concrete Inno interactions before any installation.
Astra confirmed both. Inno's [command-line documentation](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)
states that DisableProgramGroupPage=yes ignores /GROUP. The current Pascal
verification procedure also logs a warning and returns after file-check failure,
so Setup's exit alone is insufficient evidence of a verified installation.

Set DisableProgramGroupPage=no and skip that page through ShouldSkipPage, keeping
the existing wizard flow while allowing the explicit isolated group. Make a
failed files-only verification fatal in isolated mode. The ordinary installation
warning behavior remains its existing contract. In the driver, require the fresh
verification log's files-only success, then inspect all four actual isolated
shortcuts and their owned targets/arguments. Preserve Setup's actual exit even
if a later driver check fails. Add the three Claude cloud-routing switches to
the process-local environment cleanup; do not alter global settings.

Retain the driver's fixed checkout boundary. This tool is intentionally for the
authorized agent installation on this host, and no installation from a worker
worktree is required. Generalizing it would widen scope without helping the
receipt. Correct the report's credential namespace in Astra's verdict: production
uses Uoink-isolated- followed by 32 hex characters, not Uoink:isolated:....

Verify the same four isolation/security companion files used for council A plus
the new credential suite and existing installer checks. Parse the PowerShell and
compile the exact Inno script before execution. No acceptance assertion changes,
no Setup launch until the new package is built/sealed and receipt inputs prepared.
Full corrected-tree validation remains required before that new build. The
same-account evidence limit and all live-index/5179/paid API restrictions remain.

Contract review after first check: agent-install-review-c1 has 87 passed / one
failed (12.58 s). The frozen test explicitly requires VerifyInstalledHelper to
remain non-fatal, consistent with the existing installer warning behavior.
Keep that behavior and remove the proposed isolated RaiseException. The driver
still requires the separate files-only success log and fails the receipt on
missing/failed verification, regardless of Setup exit zero. Preserve both the
original failing patch and observation. Re-run the same union plus the existing
final-Inno boundary suite under agent-install-review-c2. No test assertion changes.
