# Independent review of the optional signing path

Review source commit d24cc33. Read RELEASE-SIGNING-REPAIR-BRIEF-2026-09-12.md,
ASTRA-SIGNING-REPAIR-REVIEW-2026-09-12.md and the handoff's Standing rules first.
The code is a new optional build mode, not a signed or approved release.

Inspect build.ps1, installer/uoink.iss, scripts/installer_signing.ps1,
scripts/sign_installer.ps1 and tests/test_installer_signing.py. Look for ways an
unsigned, untrusted, wrong-publisher or untimestamped artifact could be reported
as verified; callback quoting and parameter injection; stale uninstaller/receipt
reuse; preflight side effects; build compatibility and misleading documentation.
Review the retained Inno refusal evidence, including its two failed wrappers.
Do not change existing tests, create/use certificates, touch trust stores,
invoke a real signer, compile/install a release, launch clients, read the live
index, contact port 5179, call paid APIs or load any model/checkpoint. No commits
or subagents. The signed success path remains unobserved.

Run tests/test_installer_signing.py, tests/test_installer_dependency_lock.py and
tests/test_build_guide_accuracy.py in an isolated test profile. You may inspect
the retained integrator runner under the proof directory; use a fresh label and
scrub provider credentials from child environments. Write findings early to
docs/library/GEMINI-SIGNING-REVIEW-2026-09-12.md. Produce a bounded, reproducible
finding with source lines for each defect. If needed, add a NEW test file for
reproductions; no production edits in this review. Report actual counts and
distinguish observed behavior from hypotheses. Do not call this certification.
