# BC-3d: bind owning publication inputs before they become stale

BD-2 withholds acceptance on `00fe216`. Read `PHASE6-BD2-2026-09-08.md`, BD-0
and the BC-3a3 brief. Start from current `cc/living-library`, preserving the
strict raw/Index ticket rule, ledger reconstruction, sidecar edit/removal
protection, WAL export repair and coherent podcast publication.

Close BD2-01 and BD2-02 in the new frozen
`tests/library_work_astra/test_phase6_bd2_acceptance.py`. The capture plan and
podcast transcript can be consumed before ticket creation. A completed newer
publication inserted before mint is then overwritten by the stale input.
The capture reproduction fails; a previously-published podcast control passes;
the separate never-published podcast reproduction fails.

Establish ownership over the exact inputs used by the real owning operation.
Acquire the fence before reading/building mutable inputs, or validate those
exact consumed inputs under the ownership boundary and refuse a dependency
change. Do not mint a current ticket merely because publication is starting.
Do not silently rebuild old cues under a newer base or hash. Preserve current
published rows/files on refusal, proper first publication, repeated identical
publication, empty replacement and crash recovery. The existing Index lock and
SQLite transaction do not protect pre-read files by themselves. Inspect actual
capture call sites, not just the isolated helper test. No new fetch or model.

Never edit any existing test or helper, including the new BD-2 file. No fixture
introspection or test-specific branch. Add implementation tests only if needed
for a repair beyond these reproductions. Report the unchanged omitted-ticket
fixture failures under Ryan's existing ruling; do not reintroduce an exception.

Run the full BD and BD-2 files, BC-3a3 implementation tests, evaluation, BC-2,
podcast corpus bridge, clips, resources, and Phase 3 publication/integration/
recovery with PHASE3_REQUIRE_IMPLEMENTATION=1. Preserve every existing failure
as a failure; distinguish setup incompatibility from a behavior regression.
Write `docs/library/PHASE6-BC3D-GROK-2026-09-08.md` with exact commands, observed
counts, files and limits. Astra verifies both roots and finishes BD-2 afterward.

No live index, port 5179, model execution, API key, paid API, commits, pushes or
subagents. Apply remains false. Use disposable profile/output/temp roots and
resolved dependencies. Write the implementation and report early.
