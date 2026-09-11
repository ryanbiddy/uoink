# Qualify Lightning 2.6.6

Read ASTRA-DEPENDENCY-CLOSURE-REVIEW-2026-09-11.md first. Change only the two exact
pins lightning and pytorch-lightning from 2.6.5 to 2.6.6 in the installer lock.
Inspect build.ps1 for a duplicate version pin and update it only if necessary.
Do not regenerate notices from an unrelated runtime; the final build owns them.

Write docs/library/LIGHTNING-266-WORKER-2026-09-11.md early. Compare each wheel's
METADATA base requirements to all 139 exact pins for Windows Python 3.13, including
activated dependency extras and reverse constraints. Use Astra's already retained
wheel files and primary metadata in the main checkout's
_scratch/dependency-closure-astra-01. Do not use the wrong hashes in Gemini's report.
Record unresolved constraints honestly; metadata parity is not a runtime smoke.

Add a separate regression only if it validates a real installer contract. Run
tests/test_installer_dependency_lock.py, tests/test_installer_files_complete.py,
tests/test_installer_download_accuracy.py and tests/test_packaged_decoder_loader.py
through the main checkout's _scratch/integrator_verify.py and
_scratch/ig-native/Scripts/python.exe. Set IG_FORBIDDEN_LIVE to the literal ordinary
index path before invoking Python. Unset ANTHROPIC_API_KEY. No existing test,
fixture or marker edits. Astra will rerun these checks and qualify the built runtime.

Preserve EVERY attempt and raw result. Never delete _scratch or any logs, reuse
a label, or overwrite a receipt. If a command or new test fails, record its reason
and exact repair in your report before rerunning under a fresh label. Use one
PowerShell process; nested interpolated -Command strings previously broke guards.

No installs, builds, model loads, inference, new media/checkpoint fetch, paid API,
ordinary index access, port 5179, commits or pushes in this worker. No subagents.
Keep all other dependency pins unchanged. This worker may inspect metadata and
code in ZIP archives without importing them. Report the diff and named suite
counts. Astra owns integration, source freeze, final tree, packaging and receipts.
