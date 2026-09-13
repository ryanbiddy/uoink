# Add the independent byte verification — 2026-09-13

Before sealing, root supplied two more narrow text records: `verify_cached_wheels_root02.ps1` and `TWO-WHEEL-ROOT-BYTE-VERIFY02-ACTUAL.json`. Tool `4ea139` exited 0 after independently checking both whole-wheel hashes, every ZIP member and RECORD row, selected text, and all 28 preparation inputs before/after. The source and actual result are now explicit source-plan entries. The documentary sealer does not invoke that verifier or reopen a wheel.

The original four-payload preparation and its plan, sealer, protocol and verdict are preserved under `before-independent-root-addition/`. The new plan has 72 source paths instead of 70. The only sealer changes are the exact documentary source count/byte total and their reported copy counts. No inspection, artifact or qualification was rerun, and no old result was changed.

An initial unexecuted text replacement of `70` with `72` also altered digits inside the fixed proxy-tools hash. That draft is retained as `before-count-replacement-refinement.ps1`. Before execution or freezing, the sealer was reconstructed from the original source using exact count expressions; the original wheel hash is unchanged in the corrected source. The final diff must contain only the planned count/size changes. This was a preparation error, not a wheel or test result.
