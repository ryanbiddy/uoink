# Failed writer-exclusion02 copy inventory

Overall result: **FAILED**. The saved actual829f4f has outer exit1; exit.json records controller exit1 and receipt_valid=false. The contender's error32 and the child's local completion do not establish controller or journal completion. The completed diagnosis preserves the missing CLEARED frame and the remaining uncertainty about the exact differing identity field.

COPY-INVENTORY.json pins 122 payloads, 1,595,351 bytes, for ordinary byte-preserving copies. Each row gives a repository-relative source, distinct destination, byte count and SHA-256. The 1-MiB cap applies to each file; the largest is the 227,171-byte controller receipt. No copies or candidate executions were performed by this inventory task.

| Group | Files | Bytes |
| --- | ---: | ---: |
| Original proposal01, including origins and draft | 36 | 510,607 |
| Current proposal02, including actual admission | 32 | 405,100 |
| Actual generated run02 | 36 | 636,266 |
| Source review01, including preparation failure | 6 | 12,976 |
| Source review02 | 4 | 9,623 |
| Completed diagnosis01 | 5 | 17,122 |
| Two root actual objects and ROOT-REVIEW.md | 3 | 3,657 |

The inventory verified all 36 original pins against proposal02's preserved ORIGINAL-PROPOSAL01-MEMBERS.json, refused reparse points throughout the selected ancestor chains, bounded every file and rechecked each source hash after reading. Ordinary entries decoded as UTF-8 text without NUL bytes. The sole model.bin is the exact 60-byte generated ASCII fixture, SHA-256 `e0a9fc9e76fc24578e81900fcb506dc23fa39c17dcb7313e83c382d731ed1f27`. The only journal is the 1,566-byte generated run journal, SHA-256 `440b6e028d3ab6a63a9bdafedc7ddd4784fcd77b5cee9aa640362c6408aa9c91`; it was hashed opaquely here. No support binary or real model artifact was opened.

Use the fixed rows only, with a fresh destination and exact before/copy/after hash verification. Refuse changed membership, bytes, hashes or reparse components. Preserve this inventory and note separately alongside the copied payloads. The paths and observed filesystem checks do not claim a race-proof handle lease. Root's existing copier and index verifier can consume the list; no new copy framework is needed.

Proposal03 is outside this failed-run bundle. The diagnosis's passive-command and displayed-output transcriptions remain labeled as such; they are not invented raw tool objects or new native observations. No record is omitted from the six named directories or the three named root files.
