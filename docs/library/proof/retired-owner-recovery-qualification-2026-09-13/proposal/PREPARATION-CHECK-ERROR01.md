# Source hash inventory preparation error — 2026-09-13

The first read-only hash inventory command failed during PowerShell parsing: a `foreach` statement was followed directly by a pipeline. Actual tool chunk 59c9e6 returned exit 1 in 0.290549 seconds. No command body, source import, test or native operation ran.

The corrected command first assigns the `foreach` output to a task-specific variable, then serializes that variable. This is a source inventory correction, not a qualification result.
