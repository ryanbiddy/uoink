# Group A source-review correction — 2026-09-13

Review the stable-directory identity repair using only the five files in `docs/library/proof/stable-directory-correction02-brief-2026-09-13/INPUT-SELECTION.json`. Write a source critique of **at most 600 words**. This is a smaller correction of the failed Gemini review from Control Room run `2b39a17c-9418-4cfe-85d8-ecc07d7cdde2`. The earlier review remains failed; no product measurement is repeated.

The earlier report misquoted source, named eight nonexistent tests, and supplied incorrect coverage metadata. Its failed status remains preserved. Group B remains unaccepted and is outside this review. Existing qualification results are unchanged; no receipts are selected here, so do not independently certify test counts, timings or native outcomes.

Read A-01 through A-05 completely: two implementation files, their two changesets, and the eleven new test bodies. The fixed selection contains **65,576 bytes**; its 1,286 catalog slots include terminal empty LF-split slots. Paths, byte counts and hashes belong only in the frozen input map; do not reproduce them in your report or coverage output. If a file differs from that map, stop and report the exact input ID. Read bounded numbered ranges, keep track of what was actually displayed, and revisit any truncated range. Do not treat catalog counts or unrendered empty slots as proof of reading.

Assess these concrete questions:

1. Does the directory-only comparison permit mutable size while preserving exact type, valid size, physical identity, final path and link/directory checks? Are its call sites limited to directory checks, while regular-file equality and size checks remain strict?
2. Do the changes preserve reparse/delete-pending refusal and retained-handle or journal uncertainty handling? Identify a specific changed-source defect if one exists. State missing external context instead of inventing an exception, helper or guarantee.
3. Do the eleven actual test bodies reach those changed paths and meaningfully distinguish permitted directory growth from forbidden identity/file changes? Verify every test method you name against A-05 text. Its imported fixture implementation is not selected, so distinguish visible test-body logic from unreviewed fixture behavior and unexecuted tests.

Use actual symbols and references such as `A-01:169–181`. **Do not quote or reconstruct code, use fenced code blocks, invent method names, or copy hash/path/byte tables.** For each finding give the concrete trigger, effect and source lines; otherwise state that no actionable defect was found within the selected source. Separate findings from unmeasured limits. Do not claim formal proof, exhaustive coverage, malicious-code containment, an OS sandbox, hard latency, restart/power-loss behavior, native model safety or release acceptance.

Write exactly these two new outputs in your worktree:

- `docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.md`: the critique, at most 600 words including headings and notes.
- `docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.coverage.json`: a JSON array with exactly five objects in A-01 through A-05 order. Each object has only `id` and `viewed_ranges`. Each range is an inclusive pair of one-based integers actually viewed. Leave unread portions uncovered; do not add hashes, paths, counts, status labels or inferred coverage.

This is read-only source work. No tests, imports, compilation, native calls, subprocess qualification, model/asset/support-binary reads, network/fetch, package installs, credentials, API spend, live index or port 5179. Existing Antigravity subscription access only. Do not edit inputs, accepted fixtures, product code, the failed report, website or marketing; do not commit or push. The integrator will check the complete report, every cited symbol/range and the coverage against this fixed map before accepting any review conclusion.
