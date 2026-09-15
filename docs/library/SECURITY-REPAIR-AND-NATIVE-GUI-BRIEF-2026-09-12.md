# Repair remaining security findings and observe the native client

Ryan requested fresh security fixes through Control Room and native GUI checks
on 2026-09-12. Start at candidate 0a1f923. The package-07 full tree already has
2,540 passes, one historical AT6 receipt failure and two skips. Preserve that
result and all existing evidence; an unavailable historical child exit cannot
be supplied by a new run. This brief authorizes new work, not a repeated claim
that the completed qualification passed every gate.

## Gemini: remaining dependency repairs

Read ASTRA-DEPENDENCY-CLOSURE-REVIEW-2026-09-11.md, requirements-installer-lock.txt,
docs/security.md and the current release notes. Write
docs/library/SECURITY-REPAIR-WORKER-2026-09-12.md early. Use primary upstream
metadata and advisory records to check whether the retained Torch, Transformers,
NLTK and Lightning findings have a compatible repair today. Preserve fetched
metadata, retrieval times, URLs and raw counts under a new proof directory.
Do not suppress an advisory or treat an alias correction as a product repair.

Evaluate the complete Windows Python 3.13 dependency constraints, including
WhisperX, audio/vision/codec packages, extras and Hugging Face Hub. A newer version
alone is not a compatible graph. The default PyAnnote VAD loads a checkpoint
even with speaker attribution disabled; account for that path. Hashes cannot
protect against arbitrary same-user malware or make unsafe serialization safe.

Implement a small compatible upstream update or a defensible first-party repair
when its behavior can be verified without loading a model. Keep current product
features and behavior assertions. If a required version conflicts with a frozen
test assertion, document the exact conflict and proposed diff without changing
the test. If no verified repair exists, provide the concrete constraint and
remaining exposure; do not substitute speculative monkeypatches or a clean
security claim. Do not remove functionality to make a scan green.

Allowed worker changes: necessary first-party production/build/dependency files,
new meaningful regression tests, and this worker's report/evidence. No edits to
existing tests, fixtures, assertions or marks. Do not change the handoff or
release notes; Astra integrates those. No global package installation or shared
runtime mutation. Metadata and package-wheel inspection is allowed; no model or
checkpoint download, execution, inference, new source fetch, diarization or paid
API. No live index access (including stat/hash), port 5179, ordinary app launch,
credential access, commits, pushes or subagents. Keep apply disabled.

Run these existing suites through the external main-checkout tools
E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py and
E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe:
tests/test_installer_dependency_lock.py,
tests/test_installer_files_complete.py,
tests/test_installer_download_accuracy.py,
tests/test_packaged_decoder_loader.py,
tests/security/test_security_findings.py.
Also run any new focused regression. Set IG_FORBIDDEN_LIVE to the literal
ordinary index path, PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH to your worktree;
strip paid API/provider variables without printing their values. No other suite
is authorized in the worker. Preserve every command and result under fresh
labels. Before a retry, record its diagnosis and bounded repair in the report.

Astra independently reviews and runs the named suites in the worker, exports
the raw binary diff (including new files), applies it with git apply --3way,
repeats checkout suites and commits. Changed packaged source then requires a
new full tree, package seal and installed qualification before delivery.

## Astra: native observation

The Windows computer-use skill exposes @oai/sky through node_repl. Its app
inventory succeeds. Earlier absence of native support in Cua does not establish
that all Windows GUI tools are unavailable. Correct that scope in the handoff.

Before launching Claude Desktop, establish an isolated user-data/config path
from installed application code or supported documentation. Do not launch its
ordinary MCP configuration: it may connect to the prohibited live helper. Do
not copy auth files, reuse consumed P4 fixtures as a fresh receipt, change
ordinary client configuration or automate a sign-in/security dialog. If the
isolated GUI needs sign-in, leave that specific user action pending and finish
the independent security work.

Use a fresh named operator profile and reviewed installed stdio guards if the
client supports isolation. Observe tool discovery, evidence retrieval, a local
citation, opening a brief and a stored synthetic chapter/range where supported.
Keep fixtures visibly synthetic and avoid external media fetch. Save original
screenshots and factual outcomes; unsupported or unobserved rows stay explicit.
Separate native UI observations from the existing 44 successful CLI tool calls.
