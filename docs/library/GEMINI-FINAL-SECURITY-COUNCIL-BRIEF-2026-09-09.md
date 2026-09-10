# Final candidate security council, 2026-09-09

Ryan requested Gemini review before Astra performs an isolated installation.
Read RYAN-APPROVED-CLOSURE-BRIEF-2026-09-09.md and handoff Standing rules first.
Three independent reviews cover the roles below. Write your report early; use
targeted searches; do not commit or edit production/existing tests. A review is
not a security certificate. Astra independently verifies each result.

Never open/stat/hash C:\Users\hello\AppData\Local\Uoink\index.db or probe/bind/
connect port 5179. No paid API, credential access, installer execution, client or
model subprocess, external fetch, account creation, elevation, antivirus/firewall
change or host cleanup. Work in your worktree. State exact source lines,
severity, evidence, actual checks and remaining limits. Verify old findings
against current implementation before repeating them. Do not claim unrun tests.

## Role A: installation boundary

Write docs/library/GEMINI-FINAL-INSTALL-SECURITY-REVIEW-2026-09-09.md.
Review installer/uoink.iss, uoink_install_isolation.py, migrate_install.py,
server.py startup/stop, and INSTALL-RECEIPT-RUNBOOK-2026-09-09.md. Check separate
AppId, previous-directory reuse, malformed flags, marker/profile containment and
reparse points, Restart Manager, autorun/shortcuts, preparation, launch suppression
and uninstall scope. Active package-03 source is 67a274d; SHA256
a89112bb53425cbd9c5c0c662a2f239cbdde069294af9389c90021ddc2af60fe.
Host: Windows Home, no Sandbox, non-elevated token. Assess whether supported
isolated Inno mode at a fresh app/profile under checkout scratch can be observed
safely in the same Windows account without touching ordinary Uoink. Give exact
conditions/blockers; do not execute it. Name suites tests/test_install_isolation.py,
tests/test_install_isolation_repair.py, tests/test_install_isolation_integrator_review.py
and tests/test_inno_final_boundary.py.

## Role B: application and supply-chain security

Write docs/library/GEMINI-FINAL-APP-SECURITY-REVIEW-2026-09-09.md. Read
docs/security.md, SECURITY-REVIEW-2026-09-04.md and its handoff dispositions.
Check current authentication/origin/path boundaries, subprocess argument
injection, default-off egress/AI behavior and isolated credential handling.
Review dependency lock/package proof; identify unverified signing, malware scan
and vulnerability-database coverage. Focus on realistic release blockers and
regressions. No network scan/fetch/model call. Explain same-user isolation and
prompt-injection limits. Name tests/security, tests/test_mcp_slug_security.py
and targeted existing tests for findings. Propose bounded repairs in the report.

## Role C: receipt-test contract correction

Write docs/library/GEMINI-FINAL-RECEIPT-CONTRACT-REVIEW-2026-09-09.md and proposed
raw patch docs/library/patches/ryan-receipt-contract-correction-2026-09-09.patch.
Read RYAN-FINAL-RECEIPT-CONTRACT-DISPOSITION-BRIEF-2026-09-09.md. Review the three
cases in tests/test_install_receipt_c22_kit.py and tests/test_install_receipt_p4_kit.py
against Inno/isolation and scripts/install_receipt/stub_helper.py. Prepare minimal
corrections for /ISOLATED=1 /PROFILE= /PORT=, the current podcast feed route, and
profile/settings.json. Preserve every case and intended behavior assertion,
especially all-scenarios success and apply false. Do not add unused arguments,
duplicate settings or weaken the oracle. Save a proposed patch without leaving
existing test/fixture files changed. Include exact before/after semantics and
whether the fake helper actually models the route it adds. Astra applies only
after independent review. Name both complete receipt test files and current
receipt boundary regressions for verification.
