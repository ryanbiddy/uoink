# Exact-artifact static-reader compatibility verdict

`static-compatibility-preflight01` passed 89 checks with 0 failures and real
process exit 0 under `-I -S -B`. The reader is ready for the integrator's
exact-source review before any further actual static inventory.

Reader SHA256:
`f27b91e610284e26975038ff6826f2190758b1d4c53a402db3c2d0386cc4d40d`.

The 89 checks comprise 42 unchanged prior parser/reporting cases, 35
version-0 compatibility and retained-rule cases, 10 expected-digest cases,
and two static scope checks. The static checks compare the original 42-case
source and result assertions unchanged, then require the entire reader AST
to differ only by the explicitly authorized version exception and pre-parse
hash gate. The old 45-case reporting harness and its passing receipt remain
preserved; its three reporting-only AST equality assertions were not
misrepresented as checks of this intentional compatibility change.

The new exception requires needed version 0, made version 0, disk 0, stored
method and flags 2056 exactly. Negative cases cover all other low versions
1 through 9, high versions, non-stored methods, altered made/disk fields,
missing/extra/encryption-related flags, and retained name/size/CRC/pickle
rules. The actual inspection function must compare the completed full-file
SHA256 with the fixed previously observed digest before directory parsing.
There is no CLI/environment override or adoption of a changed digest.

Both prior actual inspections remain **refused**, measured reader exit 2;
the integrator-reported outer exec exit 1 is recorded separately. The same
17,719,103-byte artifact digest appears in both historical receipts. Neither
run reached pickle inventory, and neither is a passed artifact check or
failed model run. No actual checkpoint was reopened or copied during this
repair, and reader `inspect`/`main` did not execute. The qualification used
only in-memory containers and literal pickle bytes with checkpoint-open and
process/network/native audit refusals in place.

The original 27- and 47-payload seals remain intact. This scope preserves the
47-payload archive, its nested original seal and run01 evidence, plus run02's
receipt, exact root launcher and four launch logs. Before/after source,
repair brief, exact diffs, synthetic stdout/stderr and real exit are included.
The bounded upstream source note corroborates a version-0 stored writer
encoding but does not identify this artifact's writer, origin or architecture.

The integrator suggested retaining a last-32 identifier-token sample after
this exact reader had already qualified. Per that instruction, the reader
was left unchanged: it still retains only its existing first-64 identifier
samples. No additional tail-token reporting is claimed.

The future inspection remains metadata-only. Opcode tokens cannot authorize
a class allowlist, fixed architecture, tensor loading, conversion, inference
or a release. No product/frozen-test change, installed-runtime action, model
or provider execution, staging, commit or push occurred. The only upstream
access was read-only source browsing; no upstream code was executed.
