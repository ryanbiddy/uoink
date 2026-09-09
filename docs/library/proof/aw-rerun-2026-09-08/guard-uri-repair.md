# Client-fixture guard repair, 2026-09-08

The preparation guard rejects a safe SQLite `file:` URI because it passes
the URI directly to `Path.resolve()`. A synthetic database whose name contains
a space reproduces this: **one failed in 1.19 seconds**, checkout scratch
`aw-guard-uri-01`. This is an instrumentation setup failure, not a product
refusal or client observation. The archived copy and model were not used.

Before a rerun, decode local SQLite file URIs to filesystem paths, reject
remote authorities, and then apply the same resolved fixture containment
rule. Keep the live-index and network guards. Rerun the original unchanged
safe-URI case, plus negative cases for an outside path, encoded traversal and
a remote authority. Use a fresh output label and retain the first failure.
No existing acceptance assertion is changed.

The repaired run produced **four passed in 0.36 seconds**, scratch
`aw-guard-uri-repaired`. It includes the unchanged original safe-URI case
and all three negative cases. Both invocations are retained in the adjacent
preparation-checks archive.
