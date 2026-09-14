# Repair the passive root checker, not the subject

Root check01 exited1 at e37b46 before completion. It assumed the preserved
historical expected-list object used `expected_cases`; the actual fixed schema
uses `ordered_cases` with count46. No candidate was imported or run.

Preserve check-completion-fake59-root01.mjs and its actual result unchanged.
Create check02 by replacing that one field lookup with `old.ordered_cases` and
explicitly checking `uoink.lifecycle-expected-cases.v1` and count46. Every source,
fixture, expected list, diff and behavior assertion remains unchanged. Run this
passive checker once under a fresh check02 result name. It still must prove the
full forward/reverse deltas and exact original46/new13 list before admission.
