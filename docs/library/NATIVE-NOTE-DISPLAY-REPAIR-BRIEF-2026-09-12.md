# Repair source-aware native note presentation

Ryan requested native GUI checks and fixes. Astra observed the actual installed
package-07 dashboard through @oai/sky on 2026-09-12, using a new isolated profile
on port 18484. Creating a note through Sources / Jot a note succeeded: the
Library count changed from three to four, the new card appeared, and opening it
displayed the exact saved AMBER text. Two product defects remain:

1. The new note is labeled "Saved note video source." / "note video". The
   detail shows video screenshot, speaker and re-transcription fields that do
   not describe a plain note. The existing P4 text-only X fixture similarly
   displays "x video". The latter fixture's file path is outside the helper's
   output root; that separate file refusal is correct and must remain.
2. The successfully saved native note card displays "NEEDS ATTENTION" because
   absent screenshots/comments are treated as missing media assets. Applicable
   real failures must remain visible; inapplicable assets should not imply a
   failed note save. Trace the producer of health fields before changing UI.

A third observed detail may share the source-type cause: after the note text is
loaded and its file reads "ready", Local facts still says "checking saved
files" and Saved details says "saved details need another moment". Diagnose
whether omitted sidecar data produces a permanently misleading loading state.

Original observations and ten PNG screenshots remain outside the checkout in
E:/AI/projects/uoink/installation-receipts/Agent Install 07/native-gui01/dashboard.
Read only 09-note-in-library.json, 10-native-note-detail.json and the corresponding
PNGs if needed. Do not access that profile's database, auth, running processes or
other files. Astra owns installed instrumentation and evidence collection.

## Gemini assignment

Write docs/library/NATIVE-NOTE-DISPLAY-WORKER-2026-09-12.md early. Inspect
assets/dashboard/index.html (mediaLabelFor, renderYoinkDetail/related detail
functions and healthException), server.py compute_health, and notes.py. Repair
the source-type handling consistently using existing canonical source types.
Keep video, podcast, live and image behavior correct. Do not invent unavailable
assets, cues, speakers or successful capture states. Do not weaken file-path
containment or add a fetch. Keep the patch focused on these observed defects;
this is not the broader desktop redesign.

Add new behavioral regressions using real note capture/health behavior and the
existing Node-backed dashboard test approach where useful. Existing tests,
assertions, fixtures and marks are immutable. If one conflicts, document its
exact requirement instead of changing it. Preserve every failed attempt and
write the diagnosis and precise repair before any rerun under a fresh label.

Run tests/test_notes_capture.py, tests/test_dashboard_v324_ui.py,
tests/test_dashboard_capture_outcomes.py, tests/test_dashboard_sources_api.py,
tests/test_dashboard_browser_recovery_ux.py and your new focused regressions
through these external main-checkout tools:
E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py and
E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe.
Set IG_FORBIDDEN_LIVE to the literal ordinary index path, PYTHONDONTWRITEBYTECODE=1
and PYTHONPATH to your worktree; strip paid API/provider variables without
printing values. The worker must not run the full tree, a helper, a GUI, a model,
an installer or a build. No live index (including stat/hash), port 5179, network
fetch, paid API, diarization, new dependency, source download, commit, push or
subagent. Apply remains false. Do not alter the handoff or release notes.

Astra reproduces the new regressions on original source, verifies the repair in
your worktree, exports the raw binary diff, applies it with git apply --3way,
repeats the named suites, commits and updates the handoff. A product change then
requires a new complete tree, package-08 build/seal and installed native check.
Do not relabel package-07's observed display failures as passed.
