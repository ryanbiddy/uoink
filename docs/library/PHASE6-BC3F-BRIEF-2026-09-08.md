# BC-3f: enforce capture dependencies inside publication

Engine: Grok. Read BD-0, the BC-3e brief/report and the BD-4 review before
editing. Write `docs/library/PHASE6-BC3F-GROK-2026-09-08.md` early; a run
without the report is incomplete. BC-3e is integrated at `d792875` as
intermediate work. Both roots produced 167 passes and the same eleven
omitted-ticket failures. Its eight implementation tests and BD-3 pass.

The new frozen `tests/library_work_astra/test_phase6_bd4_acceptance.py`
reproduces a remaining ownership defect. After every standalone owner check,
a pending caption correction B arrives at `Index.publish_media_snapshot`
entry. The publisher overwrites it with held caption A. The semantic probe
failed in 6.37 seconds; this is content loss, not a formatting discrepancy.

Carry the immutable dependency binding, original ticket and exact owned
paths through the publication operation. Validate consumed capture inputs
inside the Index/raw publication boundary before any publication write, and
again immediately before the final sidecar replacement. Inspect the entire
operation, including its ledger/corpus writes and rollback. Another check
in the caller before invoking the publisher cannot close this defect.
Refuse conflicts, removals or changed consumed inputs without replacing the
current sidecar or complete newer snapshot. Do not infer a new ticket or
silently adopt changed dependencies. Recheck owning podcast dependencies at
the corresponding actual boundary if they share the same gap.

Preserve first publication, identical retry, explicit empty replacement,
sealed study overrides with bound consumed inputs, non-owned sidecar edits
and removals, crash recovery, and the Phase 3 S16 empty-citation seam. Add
focused implementation tests for late edits inside the publisher, including
the final carrier boundary. No existing test/helper edits, fixture inspection,
ticketless exceptions or global caller-name checks.

Run the complete BC-3e union plus BD-4 and new implementation tests:

```text
tests/test_phase6_bc3a3.py
tests/test_phase6_bc3e.py
tests/library_work_astra/test_phase6_bd_acceptance.py
tests/library_work_astra/test_phase6_bd2_acceptance.py
tests/library_work_astra/test_phase6_bd3_acceptance.py
tests/library_work_astra/test_phase6_bd4_acceptance.py
tests/test_phase6_evaluation.py
tests/test_phase6_bc2.py
tests/test_podcast_corpus_bridge.py
tests/test_clips.py
tests/test_library_resources.py
tests/library_work_astra/test_phase3_publication.py
tests/library_work_astra/test_phase3_integration.py
tests/library_work_astra/test_phase3_recovery.py
```

Use PHASE3_REQUIRE_IMPLEMENTATION=1, disposable profile/output/temp roots
and resolved installed dependencies. Preserve the eleven frozen omitted-ticket
failures for Ryan; they do not excuse this implementation defect. Report exact
commands, counts, the transaction/file boundary and remaining limits. Astra
verifies both roots and completes the broader BD-2 review afterward.

No live index, port 5179, models, API key, paid API, commits, pushes or
subagents. Apply remains false. Do not rerun the study or fetch new material.
