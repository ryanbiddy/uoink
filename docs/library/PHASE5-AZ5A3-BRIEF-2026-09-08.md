# AZ-5a3: preserve compact evidence and restore pagination

AZ-5a2 (`6e929e1d`, Claude, base `6acab3907c7245601d401327959cee736c730d52`)
is rejected. Its implementation diff is retained unapplied in
[az5a2-claude-2026-09-08.patch](patches/az5a2-claude-2026-09-08.patch).
Apply it with `git apply --3way` against the current checkout base, retaining the
integrated AZ-5b coverage and AZ-5f evaluator repairs when resolving conflicts.
Do not apply the earlier Gemini patch as well.

Integrator verification on 2026-09-08 found 326 passing and 26 failing tests on
the old worker base. All 18 BA-01/BA-03 reproductions pass. The fixture set is
27/28: `test_activity_denominator_and_pagination` returns **12 rows, expected 20**.
The corrected fixture-only measurement at 16:25 PDT recorded these sizes through
the reader and `_calculate_transport_bytes` (serialized adapter representation;
this helper does not exercise a real stdio child):

| Fixture | Raw JSON bytes | Serialized transport bytes | Returned creator rows |
|---|---:|---:|---:|
| Empty 31-day interval | 51,668 | 58,289 | 0 |
| 25-creator pagination | 57,704 | 64,411 | 12 (required: 20) |

The BA-2 measurement-document assertion also fails: retained raw sizes are
59,281/59,190 bytes; observed raw sizes are **58,694/58,369 bytes**. These are raw
JSON sizes, not actual adapter wire sizes. The other failures include repairs
already integrated after this worker's base and BA-09/10/11 still assigned to AZ-5d.

Repair the mandatory descriptor size and summary compaction so the fixture retains
its 20 creator rows while all BA-01/BA-03 reproductions remain green. Preserve
all metric families, exact support counts, separately addressable denominator
relations, provenance and continuations. Never edit acceptance assertions. Any
shared descriptor must resolve within the packet; the contract's compact evidence
selector is `{metric_id,role}`. Verify every consumer before relying on the enclosing
metric's ID instead. AZ-5a2 hashes only the first evidence page and declares that
scope; inspect whether this meets the contract and do not claim a population hash.

Run the commands and suites in [the AZ-5 brief](PHASE5-AZ5-BRIEF-2026-09-08.md),
including the 28 fixture tests, the 18 BA-01/BA-03 cases, AZ-5c/5b/5f regressions,
and the registry/stdio/docs inventories. BA-09/10/11 remain AZ-5d work; retain their
failures separately. Record raw JSON and actual serialized adapter bytes for the
empty 31-day fixture and the 25-creator fixture, together with retained row counts.
AZ-5g will refresh final measurement documents after AZ-5d; never overwrite the
historical failed observation or describe its size as current.

Measurement environment repair: the integrator's first standalone invocation of
the worker's measurement helper stopped at MCP SDK import, before measurements.
Its redirected profile omitted pywin32's paths. Resolve `site.getusersitepackages()`
before redirecting APPDATA, and include that directory plus its `win32`, `win32/lib`
and `pythonwin` subdirectories in PYTHONPATH. This brief authorizes that corrected
fixture-only measurement. Retain the import failure as a failed setup attempt.

Use a fresh worktree from current `cc/living-library`. Write early; no subagents.
No model execution, paid API, ANTHROPIC_API_KEY, live index or port 5179.
Set PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH to the worktree and resolved dependencies.
Keep librarian_apply_enabled false. No commits or pushes; Astra verifies and integrates.
