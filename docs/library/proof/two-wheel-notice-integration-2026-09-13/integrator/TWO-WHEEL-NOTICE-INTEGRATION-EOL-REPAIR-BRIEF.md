# Notice integration byte comparison

2026-09-13. The reviewed eight-path patch applied successfully with git apply --3way. Tool 9788ef then returned 1 because its post-apply byte comparison failed. The source tests had already passed in the proposal overlay; no checkout test or dependent step ran after this failure.

Read-only diagnostic fe96ea found core.autocrlf=true. All four modified files equal their qualified proposal sources after CRLF-to-LF normalization; Git expanded added LF lines during application. The proposal retained mixed line endings. This is an integration byte-comparison failure, not a new failed product test. Preserve the actual failure unchanged.

The next step restores the exact eight qualified after-files from the already reviewed proposal, after confirming every current file still has identical normalized text. Do not reapply the patch or alter its content. Check all eight exact hashes, stage the notice directory with its * -text rule, and add the seven new generator controls unchanged. Existing acceptance tests remain unchanged. Then use a fresh checkout qualification against the actual checkout source: the same 20 Python cases and 10 inert build-block cases. A further failure requires diagnosis before another attempt.

This step grants no full build, package installation, model, network or installed-release credit.
