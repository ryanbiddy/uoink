# Runtime dependency repair review

The first edit script used an absent shellingham insertion anchor, so it did
not add the new lock row and stopped before changing notices. The subsequent
worker-01 run has 17 passes and two failures in the new notice regressions.
This is an incomplete product edit, not a fixture problem. Preserve that result.
Repair: insert setuptools before the existing six row in lock/notices and
verify the insertion. No assertion changes. Rerun as setuptools-worker-02.

The notice generator also needs --with-system: pip-licenses 5.0.0 otherwise
excludes setuptools. It now includes system packages then selects exact runtime
lock names, rejecting missing rows before writing. This prevents build-tool
licenses from being presented as shipped runtime components. The three new
checks cover generated output, missing-row refusal and actual trim patterns.

The repaired union passes 19/19 in the worktree and 19/19 in the checkout,
both 0.89 seconds. The original 17/2 result is preserved. Raw patch application
was three-way. All prior tests and assertions remain unchanged. The build now
keeps setuptools and its distutils startup support while removing pip/wheel.

The primary wheel is setuptools-83.0.0-py3-none-any.whl, 1,008,090 bytes,
SHA-256 29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3.
Its root distribution metadata reports MIT and Python >=3.10. No base
Requires-Dist edges are declared. OSV's exact version query returned {} on
September 11; that response is retained without treating it as a whole-runtime
security clearance. The embedded vendored components retain their shipped
licenses; the existing notices style is a package table, not a replacement
for the wheel's license files. The source table explicitly labels this manual
metadata update; the actual build must regenerate and verify the final table.

Accept the bounded repair at source level. The expected final set is now 140
packages. Full-tree verification, final package/runtime graph and installation
remain owed. Proof: proof/setuptools-runtime-2026-09-11/SHA256.json.
