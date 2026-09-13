# agw01/agw02 count clarification — 2026-09-13

No source, assertion, test result or prior proof payload changed. This clarifies
an imprecise label in the first frozen proof summary.

| Run | Pytest passed cases | Passed subtests | JUnit `tests` attribute | Actual `<testcase>` elements |
| --- | --- | --- | --- | --- |
| agw01 | 11 | 13 | 24 | 11 |
| agw02 | 144 | 13 | 157 | 144 |

All failure/error/skip counts are zero and all recorded process exits are zero.
The thirteen passed subtests contribute to pytest's JUnit `tests` attribute;
they are not thirteen extra collected cases or extra `<testcase>` elements.
The raw console summaries remain **11 passed + 13 subtests** and
**144 passed + 13 subtests**.

The `junit_entries` fields in `agw-proof/summary.json` mean the XML `tests`
attribute, not element cardinality. Treat that field name as imprecise and use
the explicit columns above. The first proof seal remains unchanged:
`d314a63292d7bc0092c2fc715aeafc6fe65c21de418939f3f4c8b2bf800ee56f`.
This correction is documentary; it prompted no test rerun or fixture edit.
