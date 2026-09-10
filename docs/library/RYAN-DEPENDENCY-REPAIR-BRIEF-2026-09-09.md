# Installer dependency repair, 2026-09-09

The archived audit identifies 55 alias-connected issues in seven pinned packages.
Independent PyPI metadata confirms Pillow 12.3.0, NLTK 3.10.3, cryptography 50.0.1
and MCP 1.28.1 are published with compatible Windows Python 3.11 wheel tags.
This verifies availability, not a working dependency graph. Gemini's claim that
ordinary transcription bypasses every checkpoint loader is incorrect: WhisperX
3.8.6 defaults to PyAnnote VAD and loads its packaged assets/pytorch_model.bin.
Retain that path in the remaining-risk analysis. No actual model run is allowed.

Gemini: implement only the four proposed pin updates in a private worktree.
Write source early. Update build.ps1's direct Pillow/MCP pins, the four full-lock
entries and exact-version unit assertions in test_installer_dependency_lock.py.
The latter two assertions must still require exact versions, now the reviewed
security targets. Do not change acceptance behavior assertions, skip cases,
weaken lock inventory checks, or edit the receipt fixtures. Update current build
documentation/notice version rows where these pins are stated. Do not regenerate
the installer, modify shared staging or shared verifier environments, download
models/media, query keys, use paid API, or touch the live index or port 5179.

Astra will resolve the proposed graph using a disposable Python 3.11 environment
before acceptance, then build and verify the packaged inventory and actual image/
MCP behavior. Your worktree checks: tests/test_installer_dependency_lock.py,
tests/test_installer_files_complete.py, tests/test_installer_download_accuracy.py,
tests/test_docs_live_contracts.py. Use the guarded native runner from the checkout
with --root your worktree and a fresh label. Existing native runtime versions do
not prove compatibility of the new Windows 3.11 package. Preserve all outcomes.

Write docs/library/RYAN-DEPENDENCY-REPAIR-WORKER-2026-09-09.md with exact diff,
commands and observed counts. No commit. Integration uses raw diff / three-way
apply and independent checks in both roots. Do not declare a clean vulnerability
audit: Lightning 2.6.5 remains upstream-unfixed, and WhisperX 3.8.6 constrains
Torch 2.8 and huggingface-hub below 1.0 (incompatible with Transformers 5.x).
Those remaining findings require precise applicability and release notes.

Resolution instrument repair: dependency-resolve-01 exited 1 before contacting
PyPI because the minimal copied Python lacked its _socket extension. Preserve the
trace. For dependency-resolve-02 copy the embeddable runtime's complete top-level
.pyd/.dll set as well as interpreter and standard-library ZIP. Repeat the same
dry resolution in that new disposable directory; no product source or installed
site-packages is imported or modified. This corrects the resolution instrument,
not a package compatibility failure.

Resolution instrument repair 2: the complete interpreter in dependency-resolve-02
reached PyPI, then antlr4's metadata build could not import setuptools.build_meta.
The embeddable _pth ignores pip's temporary build-environment path injection.
Preserve exit 2. For dependency-resolve-03 install only the build's pinned
setuptools 83.0.0, wheel 0.47.0 and packaging 26.2 into that disposable runtime,
and use --no-build-isolation as the actual installer build does. Resolve the same
proposed graph; this retry does not change any dependency target or product test.
