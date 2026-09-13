# Archive transport correction — 2026-09-13

The first Git staging verification found an index-byte mismatch for
`count-clarification/agw-count-clarification.json`. Without local attributes,
Git normalized the archived CRLF bytes. The disk file and all original seals
were unchanged. This was an archive transport failure, not a test failure.

Observed Git blob IDs before this repair:

- Staged index: `2b7280eb6336045946955273e8cd645b662b35e6`
- Raw disk bytes, using `git hash-object --no-filters`:
  `ce46cdbb2509b8b828a51ac57a29252519a3a1e0`

The prior 115-payload outer manifest is preserved outside the proof at
`_scratch/asset-guard-a-archive-transport01/SHA256.BEFORE.json`, SHA-256
`a61eea24b1347d261fc76f2f39b1b9380bf248c43ffd768c555a5819abb47bdc`.

This repair adds `.gitattributes` with `* -text` and reseals the outer archive.
All previous 115 payload bytes, including the nested original 24- and
29-payload seals, stay unchanged. The independent results remain 144 passed
cases plus 13 passed subtests in each root, with zero failures/errors/skips.
No source, assertion or runtime result changed and no tests were rerun.

The parent must re-add the archive under these attributes and verify every
staged blob against the revised outer manifest before committing. This repair
does not itself stage or commit anything.
