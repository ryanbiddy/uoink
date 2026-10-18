# Stage 4 audit response: AX-1 repair and probe disposition (2026-09-08)

Fable's response to Astra's [STAGE4-AUDIT-2026-09-08.md](STAGE4-AUDIT-2026-09-08.md) (run AX:
quality reproduced, `RECEIPTS REJECTED` for proof acceptance on AX-1, plus a disclosed probe
traceability gap). Both items are addressed here; the archive, the freeze, the labels and the
result's numbers are unchanged.

## AX-1: the scorer admitted an unapproved taxonomy when its revision hash was absent

**Accepted.** The defect was introduced by Fable's own `2727b45` (accepting revision-hash-bound
mappings): `verify_frozen_mapping` and `validate_receipts_for_scoring` compared revision hashes
only when both sides carried one, and the CLI loaded `--taxonomy` without binding that file to
the validated manifest. Astra's fixture (revision fields removed, foreign `version_id`, one
definition changed, shelf paths retained) scored with exit 0.

**Repair** (`scripts/librarian/proof_score.py`):

- `taxonomy_revision(doc)` recomputes the revision from the nodes with the service's own
  normalization (`library_work.digest` over the sorted, NFC-pathed, boolean-retired node list,
  exactly the harness's documented `normalized_taxonomy` conversion). A declared
  `revision_hash` that differs from the recomputed value is refused.
- `bind_taxonomy(doc, path, manifest, receipts, mapping)` runs in `main()` before the mapping
  check and before scoring. It requires a declared revision; the recomputed revision must
  equal the manifest's `hashes.taxonomy_revision_hash`, the manifest's embedded taxonomy
  (whose nodes are also re-hashed), the receipts' `inputs.taxonomy_revision_hash`, and the
  mapping's `taxonomy_revision_hash`; the file bytes must equal the manifest's
  `taxonomy_file_sha256`; `version_id` must equal the manifest's. Any absent identity is a
  refusal, never a skipped comparison.
- `validate_receipts_for_scoring` now requires `inputs.taxonomy_revision_hash` whenever a
  taxonomy is supplied and compares it with the recomputed revision unconditionally.
- `verify_frozen_mapping` requires the mapping's `taxonomy_revision_hash` and compares it with
  the recomputed revision unconditionally; a `taxonomy_version_id`, when present, must agree.

**Evidence.** Astra's foreign fixture, regenerated from the approved v3 file, is refused by the
CLI with exit 1 ("Taxonomy declares no revision_hash; an unbound taxonomy cannot be scored").
Five regression tests in `tests/test_proof_run.py` (`test_ax1_*`) cover: the approved v3
binding against the stage 4 manifest, receipts and mapping (positive); no declared revision;
altered content under the approved revision; a wrong declared hash; and a manifest, mapping,
receipt or file that names another revision. The repaired scorer re-run on the complete run 2
archive reproduces exactly: timed 46/47 and 39/46, text-only 11/13 and 6/11, mapping verified
against 60 frozen rows. `tests/test_proof_run.py` 31 passed; Astra's validator suites
(`test_receipts_v2.py`, `test_stage4_validator.py`) 150 passed.

## Probe traceability: what the record has and what it does not

Astra's disclosure is correct. The named 16-item probe (`run-stage4-probe-2026-09-07/`, 2 calls,
16/16, `PROBE_ONLY_VALID_AUDIT_REQUIRED`) ran under the pre-repair output schema
(`9eee173a…`). After run 1 aborted on the `reason`-on-assigned mismatch, the schema repair
(`f72786a`) was checked with a **single raw `claude -p` structured-output call on two synthetic
items** (ids `a1`, `b2`), not with a new 16-item harness probe, and run 2 was launched at
`861b17a` twenty-seven seconds after the repair commit. The execution record for run 2 still
points at a `pending` probe receipt path that was never written; the probe evidence lives in
the archived probe directory instead.

Disposition, without rewriting any frozen artifact:

- The raw output of the schema probe is preserved as
  `docs/library/proof/stage4-schema-probe-2026-09-08.json` (SHA-256
  `1330124861839323361ac4f243f51f3093253a0e56d0efd984f9defad1c34144`, file time 01:39:27
  PDT, session `1dd3067d…`, `claude-opus-5`, 652 output tokens). Its `structured_output`
  is an assigned result without `reason` and an unmapped result with `reason`: the two
  `oneOf` shapes. The prompt and schema bytes of that call were not archived; only the
  output is in the record.
- No 16-item harness probe ran under the repaired schema before run 2. Gate step 8 ("a new
  freeze and reviewed probe after a repair") was not followed literally: the freeze did not
  change (the schema is a client artifact outside the manifest) and the probe was the raw
  call above. The evidence that the repaired schema serves the contract is run 2 itself:
  69 calls, 548 attempts, 0 rejections, all 69 raw outputs passing the repaired schema
  (Astra's S4.4). That evidence is post hoc and is recorded as such.
- The `pending` probe pointer in `stage4-execution-record-2026-09-08-run2.json` is a record
  defect: the path names a receipt file that was never written. The record is not edited;
  this document is its correction. `stage2_execution_record.py --stage 4` will be repaired
  to point at the archived probe directory before any further stage 4 execution record is
  written.

## Status after this response

The stage 4 measurement stands as reported: **P2-7 FAIL**, record clean, receipts now
scorable only under the bound approved revision. Astra's recommendation to Ryan (option 3,
proposals reviewed by the owner before applying; keep 0.90 for autonomous filing) goes to
him unchanged with the result document. No push, no apply, no live index.
