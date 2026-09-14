# Group A correction brief materialization — 2026-09-13

Prepare a documentary copy only. The canonical brief changes one sentence to say that the earlier review remains failed and no product measurement is repeated. The original eight preparation files remain unchanged, including the failed map preparation, its line-count diagnostic, repair note and successful preparation receipt.

After reviewing the exact script and its hash, root may run materialize.ps1 once with that hash as ReviewedScriptSha256. It refuses existing destinations, verifies the fixed source bytes before writing, and creates:

- `docs/library/proof/stable-directory-correction02-brief-2026-09-13`: the original eight files under `original-preparation/`, the unchanged input map at the root, canonical brief, exact wording diff, this plan, script, attributes and copy receipt, followed by a SHA256.json manifest.
- `docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-BRIEF-2026-09-13.md`: the same canonical brief bytes.

The expected proof has 15 payloads plus its manifest. The script compares every destination byte hash, exact proof membership, the external canonical brief, and all inputs after copying. It reads the five selected existing text inputs only to verify the pinned map; it does not duplicate those sources. Each read is capped at 65,536 bytes. These are checks of named files in a quiescent workspace, not atomic or hostile-code protections. Partial output is retained on failure; the script never deletes, overwrites, dispatches, commits or pushes.

The selection remains A-01 through A-05: 65,576 bytes and 1,286 LF-split catalog slots, including terminal empty slots. The report limit remains 600 words. Coverage contains only exact selected IDs and actually viewed ranges. Group B remains unaccepted. No suite, import, compilation, model/native operation, support binary or artifact is authorized by this copy.

This proposal and script are unexecuted. A future actual tool result belongs outside the proof until root records it separately; no placeholder result is generated here.
