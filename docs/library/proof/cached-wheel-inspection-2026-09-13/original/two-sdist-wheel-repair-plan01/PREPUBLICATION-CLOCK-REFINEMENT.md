# Pre-execution clock refinement — 2026-09-13

The unexecuted first inspector is preserved under `before-publication-clock/`. Add one cooperative clock check after final JSON serialization and before creating the receipt. If serialization crosses the budget, publication refuses instead of writing a successful result. The launcher will preserve the actual native exit and stderr as an instrumentation failure if there is no completed receipt. No wheel or inspector has run, and no behavioral qualification is being relabeled.
