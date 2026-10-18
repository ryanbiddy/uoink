# Runtime compatibility work, 2026-09-12

Ryan has asked Astra to continue fixing the release rather than stop at the held
review kit. This run supplies the missing exact dependency graph. It does not
repeat the earlier security audit or claim to qualify model behavior.

Read ORCHESTRATION-HANDOFF-2026-09-08.md's Standing rules and
ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md first. Base: c5d33a4. Work only in
your Control Room worktree. No commits, subagents, acceptance-test changes,
model downloads, checkpoint loading, inference, diarization, source/media fetch,
paid API, ordinary client launch, live index access or port 5179 access. Do not
set API credentials. Write the first deliverable early.

Implement scripts/check_runtime_graph.py and new tests/test_runtime_graph.py.
The script must inspect saved PyPI JSON and wheel METADATA without importing any
package or executing setup/build hooks. Parse PEP 508 requirements, extras and
markers for Windows x64 CPython 3.13. Report the exact selected versions, active
edges, missing packages, conflicting constraints, wheel availability and hashes.
Reject incomplete evidence, incompatible wheel tags and yanked releases. A
graph can pass only if every active edge and selected wheel is supported by the
captured metadata. Keep graph compatibility separate from advisory disposition,
binary import compatibility, model safety and inference quality. Use packaging,
which is already available; do not invent a dependency solver or silently choose
an older release to pass. Allow an explicit proposed selection JSON as input.

Capture current official PyPI JSON for the current selected stack and plausible
fixed candidates under docs/library/proof/runtime-graph-01-2026-09-12/. Metadata
and wheel METADATA reads from official PyPI are allowed. Retain URLs, UTC times,
SHA256 and actual failure results. Do not download large binaries. First inspect
the retained security report's real constraints. In particular, independently
check Torch, Torchaudio, Torchvision, TorchCodec, WhisperX, Transformers, Hub,
PyAnnote, Lightning, NLTK and faster-whisper. Do not assume matching Torchaudio
releases exist. Verify the Python 3.13 Windows wheel tags and Requires-Python.

Produce docs/library/RUNTIME-GRAPH-01-2026-09-12.md with the current graph result,
the proposed fixed graph result, and a concrete minimum compatibility patch if
the proposal conflicts. Reference exact upstream files/versions for any proposed
change, preserve transcription/alignment/VAD capabilities, and separate a
metadata-only proposal from an implementation or successful inference test.
No edits to production pins, WhisperX, existing tests, build.ps1, installer/,
release notes or the handoff in this run. Do not suppress advisories or declare
release readiness. If no complete graph exists, state the unsatisfied constraints
and required upstream/source changes precisely.

Run new tests plus tests/test_installer_dependency_lock.py. Cover marker/extras
closure, conflicting pins, missing/yanked/wrong-platform/wrong-Python wheels,
tampered/mismatched evidence and truthful failure status. Keep network captures
outside unit tests. Existing tests remain byte-identical. Astra will inspect the
code and execute both suites in your worktree, integrate git diff through
git apply --3way, and execute the same suites in the checkout.

Use the mandatory local writing-craft guidance for authored prose. Final output:
files changed, exact commands/counts, observed graph result and remaining gaps.
