# BC-3e: bind all consumed capture inputs

Engine: Grok. BC-3d closes the three BD-2 cases, but does not close the
owning-input contract. Read BD-0, BD-2 and the BC-3d brief/report. A new frozen
case in `tests/library_work_astra/test_phase6_bd3_acceptance.py` holds the cue
text and chapters constant while a complete newer owner publishes corrected
`transcript_source`. The older capture acquires the newer base, passes the
cue-core comparison and overwrites the newer provenance. Independent worker
probe: one failed, 9.16 seconds; worker scratch `bd3-provenance-w`.

Repair ownership over every input the capture plan actually consumes, including
cue links and attributed speaker/provenance fields, transcript kind/provider,
source/playback identity, chapters and artifact metadata. Comparing only
start/end/text cannot certify unchanged input. Inspect the real owner and
publisher together. Preserve supported sealed study artifact overrides only
when their consumed inputs remain bound; do not give them an exemption from
ownership. No test-name checks, closure inspection or ticketless exceptions.

Recheck bound mutable dependencies at the actual publication boundary, as
well as after mint; a standalone file check before a later call is not a
lock. Preserve first publication, identical retry, explicit empty replacement,
newer publications, non-owned sidecar edits/removals and crash recovery. A
refusal must preserve the current complete snapshot. If you find another
input dependency defect, add focused implementation coverage and report it.
Never edit any existing test/helper, including the new BD-3 file.

Run every BC-3d suite, all three BD-2 cases, the new BD-3 case and any new
implementation tests, with PHASE3_REQUIRE_IMPLEMENTATION=1. The eleven
unchanged omitted-ticket cases remain failures for Ryan, not regressions to
work around. Write `docs/library/PHASE6-BC3E-GROK-2026-09-08.md` early, with
exact counts/commands, binding fields, timing boundary and limits. Astra
verifies both roots and completes the broader BD-2 review afterward.

No live index, port 5179, model, API key, paid API, commits, pushes or
subagents. Apply remains false. Use disposable roots and resolved dependencies.
