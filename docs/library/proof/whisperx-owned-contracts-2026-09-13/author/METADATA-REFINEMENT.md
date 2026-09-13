2026-09-13. Before writing the metadata validator, source review found a mismatch:
the frozen METADATA Summary uses the owned proposal wording, while its
pyproject description retains the upstream feature description. In this fresh
preparation only, set the copied pyproject description to the exact existing
owned Summary. Preserve the original pyproject and recipe bytes, update the
new recipe's pyproject hash, and record the one-line delta. The original frozen
proposal and all Python source bytes remain unchanged. No test was run or
behavioral assertion changed.

A second source-only check found the repository URL spelling differed only in
the final component's case: pyproject used `whisperx`, METADATA used `whisperX`.
Preserve the unexecuted builder/verifier and first copied metadata inputs under
drafts/metadata-case01. Align the copied pyproject with the existing immutable
source URL spelling and require both validators to derive Project-URL from
that exact field. Repository identity and fetched scope do not change. Update
only the copied pyproject binding and the two instrument recipe pins. No code
was executed and no test outcome exists.
