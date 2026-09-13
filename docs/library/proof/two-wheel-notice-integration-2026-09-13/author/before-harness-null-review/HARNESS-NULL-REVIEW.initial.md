# Pre-execution fixture correction

2026-09-13. Static review found that the new Generation-Case function declares expectedError as string, so a null supplied for a success case becomes an empty string. Its initial null-only branch would incorrectly demand an exception from a successful block. The preserved unexecuted draft is before-harness-null-review/run_build_blocks.ps1, SHA-256 13c91edc6f9b5e00b7bfc4e1341f06e6c08e418c2e394f7b318710109c33edb4.

The one-line correction uses string.IsNullOrEmpty to select the unchanged success assertion. The block source, ten case bodies, controlled outcomes and all behavior assertions are unchanged. No tests or candidate block have run; this corrects a new harness seam before its first qualification.
