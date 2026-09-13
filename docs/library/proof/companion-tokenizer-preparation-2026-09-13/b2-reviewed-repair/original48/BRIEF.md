# Companion B2 empty-buffer repair — 2026-09-13

Gemini council run `131e52c7-b6e7-4b69-bc74-1283f77391fa` identified the
previously disclosed B1 truthiness boundary: a supplied empty tokenizer buffer
can fall through to an ambient file or missing-file/non-local fallback path.
This task addresses only that finding. The parent handles the other findings.

Preserve all original 24/46/67/52 seals and artifacts. Copy the exact B1 source,
reviewed AST-prefix helper, six original assertions, harness and launcher as
inputs into this new scratch directory. Append four new unittest cases covering
local_files_only true/false crossed with an ambient tokenizer file present/absent.
The new cases override only their fake buffer parser: it records the buffer call
and raises ValueError for b''. Require that error and no file parser, model
allocation or remote fallback. Record actual call events and exception type.
Preserve the original six assertion bodies and helper unchanged.

Use the reviewed import/audit guards and `C:\Python314\python.exe -I -S -B`.
Only the selected constructor prefix executes, with explicit fake namespaces
and temporary synthetic fixtures. No actual dependency, native tokenizer/model,
package/module, build code or network may execute. Scrub provider credentials
from child environment as before; never access the live index or port 5179.

First run `b1-boundary01` against exact B1 with all ten cases. Preserve real
failures and exit status. Write a dated result/repair reason before running
`b2-candidate01` against the exact narrow replacement
`if tokenizer_bytes is not None:`. Keep both arms' ten assertion bodies identical.
If instrumentation fails, preserve it and write a repair brief before any rerun.

After qualification, write a fresh distribution-plan addendum with B2 source,
patch and proposed RECORD/notice hashes; never replace the B1 plan. No production,
dependency, frozen-fixture, pin, staging or tracked-document changes, downloads,
builds, commits or pushes. Root review remains required; this task conveys no
application, runtime or market approval.
