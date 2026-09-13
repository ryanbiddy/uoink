# Pre-execution fixture correction

2026-09-13. Static review found that the new Generation-Case function declares expectedError as string, so a null supplied for a success case becomes an empty string. Its initial null-only branch would incorrectly demand an exception from a successful block. The preserved unexecuted draft is before-harness-null-review/run_build_blocks.ps1, SHA-256 4267d8a44fb2ff7381cbdfee0bfc3d661e737575bbae04d2dcb7c14e29e45733.

The one-line correction uses string.IsNullOrEmpty to select the unchanged success assertion. The block source, ten case bodies, controlled outcomes and all behavior assertions are unchanged. No tests or candidate block have run; this corrects a new harness seam before its first qualification.

The initial unsealed version of this note contained an incorrect draft hash. HARNESS-NULL-REVIEW.initial.md retains that typo; the value above is the hash actually returned by the read-only command, with no source or measurement change.
