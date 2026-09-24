# Complete tree09: mirror failures close; historical receipt failure remains

The complete partitioned run at `56d9d4cf11f20ff4448b21db172dbf217d02c6d6`
recorded **2,796 passed, one failed and three skipped across 2,800 cases**,
plus **13 passing subtests**. Its overall result remains **FAIL**. Every one
of the 50 Phase 4 cases that failed in tree08 now passed. The original tree08
result remains unchanged; this does not establish the exact cause of its first
ordered failure.

| Partition | Passed | Failed | Skipped | Passing subtests | Pytest time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main | 2,794 | 1 | 3 | 13 | 1,505.07 s |
| Existing media pair | 2 | 0 | 0 | 0 | 4.12 s |

The partitions form the exact disjoint union of the 2,800 collected cases.
The two media cases were deselected only from main and executed in their
established separate process. Only the existing S21 file was excluded.
`--runxfail` remained enabled. All original cases from tree08 are present;
the 71 additions come from new test files. Existing acceptance assertions,
fixtures and markers were unchanged.

The failed case is
`test_as7_c21_at6_receipt_records_process_exit_status`. It still requires the
original historical AT6 child-exit record, which is unavailable. This run cannot
recreate that event, and its failure is not waived. Ryan's disposition remains
under Blockers for Ryan. The skips are the POSIX build-script case and two
symlink cases for which Windows denied creation privileges. Main reported 184
warnings; these remain in its raw log.

The reviewed recorder reconciles top-level cases, subtests, phase reports,
JUnit membership/counts and actual session/pytest/verifier exits. Main exited
one; media and collection exited zero. The durable supervisor recorded child
exit one and the exact aggregate hash. It observed 504 unchanged prerequisite
NLTK source files. The passive mirror observer recorded 174 required captures,
zero observer errors and a completed final receipt. All three explicit import
guard receipts validate. Their scope is each pytest process, not its children;
the existing native verifier guards remained in place.

The sealer exited zero after checking membership, raw reports, observer health,
source identity and clean checkout. Its [62-payload proof](E:/AI/projects/uoink/checkouts/Yoink-library/docs/library/proof/ryan-final-partitioned-09-2026-09-13/SHA256.json)
retains the complete execution records and instruments. This qualifies the
combined source repairs within these test contracts. It provides no new model,
installer, signing, Claude Desktop or market acceptance. The package-08 artifact
still represents its older source. Default VAD security, dependency migration,
the proposed tokenizer derivative and the existing owner decisions remain open.
Website and marketing stay paused.
