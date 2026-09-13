2026-09-13. The first receipt-comparison command exited 1 before writing INDEPENDENT-CASE-COMPARISON01.json. It expected root's outer-tool-result.json to use exit_code. The preserved root receipt instead names that field actual_outer_tool_exit, whose value is 0. This is a reporting-schema mismatch, not a changed test result.

The read-only diagnostic found all 40 case records identical between author and root; each has 40 passed, 0 failed, matching collector/harness hashes, asserted startup binding and zero audit denials. The root native exit is 0 and input hashes are unchanged. Use the existing actual_outer_tool_exit field in a fresh comparison02 report. Do not modify either original receipt or rerun a test.

The original comparison tool returned chunk b369bd, exit_code 1, wall_time_seconds 0.1635908, with error text: Independent qualification facts mismatch. No comparison01 artifact was created. Its failure is preserved here instead of being relabeled successful.
