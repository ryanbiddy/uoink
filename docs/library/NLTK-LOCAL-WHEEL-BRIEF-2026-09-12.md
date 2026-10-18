# Package the accepted NLTK source patch as a labelled local wheel

Read Standing rules and ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md. Source preparation
is accepted at 4aec8ff; packaging is not. Work only on the bounded preparation below.
No production lock, build.ps1, installer/staging, installed app, existing tests or
accepted patch changes. No subagents, commits, paid API, live index, port 5179,
package imports, resource/model downloads, training, inference or diarization.
Write the utility early; do not spend the run waiting on background copy tasks.

1. Add scripts/build_nltk_pathsec_wheel.py. Accept an existing upstream wheel and
   a fresh output directory. Pin nltk-3.10.3-py3-none-any.whl to SHA256
   ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c.
   There is no expected-hash override. Use the accepted preparation utility on a
   fresh extracted package. Construct nltk-3.10.3+uoink.pathsec1-py3-none-any.whl.
   Update package VERSION, distribution directory and METADATA Version, preserve
   licence and dependency metadata, recompute every RECORD row, and remove any
   upstream RECORD signature. Use deterministic zip timestamps/order/modes.
   Validate zip members and original RECORD hashes/sizes; reject duplicates,
   traversal, symlinks/reparse paths, device/UNC/ADS paths, destination reuse and
   malformed metadata. Do not execute setup hooks or import NLTK. No network in
   the utility. Record input/patch/output hashes, changed members and provenance.
2. You may retrieve only this software wheel from its previously captured primary
   package URL, with byte count and SHA256 verified before parsing or extraction:
   https://files.pythonhosted.org/packages/b6/6d/ebd2af4640b12168fdf0cb74b6118df2f32a2f62ec7e0c06fbfd80706639/nltk-3.10.3-py3-none-any.whl
   Expected size 1,798,643 bytes. This permits no new media or model fetch. Preserve
   pristine extracted upstream source in your scratch directory for the integrator.
   Build twice in two fresh output directories and compare wheel bytes. Preserve
   every attempt with its exit and actual output; failed runs require a diagnosis
   and repair note before a fresh label. Put the proposed wheel and JSON provenance
   under vendor/nltk-pathsec/dist/ without changing production pins.
3. Add tests/test_nltk_local_wheel.py using synthetic archives for parser negatives
   and the exact upstream artifact as an explicitly optional integration fixture.
   Mock no acceptance assertions and edit no existing tests. Run that suite plus
   tests/test_installer_dependency_lock.py through the integrator's guarded wrapper
   in E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/run_media_verify12.py.
   Tests must remain portable after the runtime is upgraded. Write one page at
   docs/library/NLTK-LOCAL-WHEEL-REVIEW-2026-09-12.md with exact commands/counts,
   member diff, version/RECORD review and remaining staged-runtime qualification.
   Packaging success does not suppress the original advisory or grant release
   clearance. Astra will review, test both roots and integrate via raw git diff.
