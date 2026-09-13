Preserved independent source review, 2026-09-13. No D1 execution, edits or artifact access occurred during this review.

One pre-activation repair:

- Original run-root.ps1:15, SHA256 75b8058874a0389ccdd02f63815b1430b543967e5ad232904bbb86b7a0073a23: inherited PSNativeCommandUseErrorActionPreference=true, combined with ErrorActionPreference=Stop, can interrupt expected exits 1/2/3 before actual-exit.json is written. Explicitly disable that preference or catch and record the native exit. Qualify with an inert nonzero child.

Otherwise, source review found:

- Both closed gates precede artifact operations/helper execution.
- Fixed helper, inventory, decision and source bindings are checked.
- Interpretation stays at 1,002 selected bytes; whole-input hashing/CRC remains bounded.
- Partial/late output cannot produce accepted completion.
- Quiescence, audit limitations and cooperative deadlines are accurately stated.

Reviewed launcher bf865aff26515aa54e09ae046e53e6c9fb5efb688ccec676b170e8313af851e4 and child 577b1a22ebe5490ba28f5a56a46e5b3d3f5b85e077de3c1cafad6205aeb29a90. This record preserves the review's findings; the new synthetic protocol is not yet measured.
