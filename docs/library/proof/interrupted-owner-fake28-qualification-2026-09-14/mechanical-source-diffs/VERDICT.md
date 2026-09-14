# Mechanical source deltas verified

2026-09-14. All three raw patches reconstruct the exact frozen derivative bytes and reverse to the exact committed original bytes. Original sources, repair02 derivatives and the new six-case test remain unchanged. This is byte verification only; no candidate import, compilation, test, Python or native-model operation occurred.

| Raw patch | Bytes | SHA-256 |
|---|---:|---|
| durable_lifecycle.py.patch | 15,362 | 657bb42c17632ec3b247b900c1be63d1aa99ac08a9e3b4166907271b14a618f7 |
| generated_adapter_flow.py.patch | 38,974 | d21cc4d81cc754e1f5eea202a64322a53b1692c9c1ade9f54b257f84c469e8a7 |
| generated_journal_setup.py.patch | 5,430 | 4833467b67887da37fffd2c9e2874661b26117db5e2afe523755ae7d9a279133 |

The actual raw-diff returns are 500a85, 4eadf9 and b6428c, each exit 1. That is Git's expected no-index differences status, not exit 0 or a candidate failure. PowerShell 7.6.5 redirected native stdout directly to the patch files. No patch bytes were rewritten.

Each source pair was copied byte-for-byte from the INPUTS-bound committed original and frozen repair02 derivative into fixed original/candidate text paths. SOURCE-BINDINGS.json records the complete original/new hashes and original paths. It also binds the new test at c833cf67 and preserves the rejected test's F09 reference; the rejected test was not reread or edited.

All 12 forward/reverse check/apply commands returned 0. Final passive check 2b970f returned 0 and verified all six reconstructed hashes, all six external source hashes and the new test. RECONSTRUCTION-CHECK.json is 6,551 bytes, SHA-256 346ff375dbef0b01901b1b8c65ca6d2958df31acb223f35865585bb1a533c759. Its actual return is saved in VERIFY-BYTES01-ACTUAL.json.

The 12 disposable text copies were removed only after verification and path checks, leaving the three raw patches, bindings, report, preparers and every actual tool result. No patch was applied to the candidate, committed originals or Git index. This directory is complete for archival; no broader source-review or behavior acceptance is claimed.
