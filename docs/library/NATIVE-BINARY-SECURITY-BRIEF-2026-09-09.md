# Native binary security follow-up, 2026-09-09

Read-only Gemini council review on candidate 7109182. No edits to product, tests,
existing proof, build/cache or staging. Write only a concise report at
docs/library/GEMINI-NATIVE-BINARY-SECURITY-2026-09-09.md in your worktree. Do not
commit. No subagents. Use primary documentation and public release metadata only.
Do not query credentials, set API keys, use paid API, run a model/diarization,
download source media, touch the ordinary Uoink index, probe port 5179, install
software, elevate, change security settings or run original helpers. Public
dependency release metadata and checksum files are in scope; no executable runs.

Astra's fresh complete tree uses the sealed bundled LGPL FFmpeg on its private
PATH. One new failure appears at tests/test_long_video_v324.py's existing
test_screenshot_phase_end_to_end: it generates its synthetic video with libx264,
which this LGPL build does not include. The exact final failure is pending.
Do not edit that test, mask its failure, or claim fixture generation passed.
Recommend a separate hash-verified GPL test tool on private PATH to supply that
existing requirement, while the shipping package remains LGPL. Astra owns that
environment repair, independent tests and actual installed decoder observations.

Investigate three bounded issues:

1. build.ps1 pins FFmpeg n7.1-184-gdc07f98934 from BtbN's 2025-01-31 build.
   https://ffmpeg.org/security.html lists later 7.1.1/7.1.2 and 8.x security fixes.
   Determine the exact old version/configuration and primary-source-supported
   update choices. Locate a current immutable BtbN Windows x64 LGPL release
   archive and its official checksum, preferably a stable supported release
   branch. Also locate the matching GPL test-only archive/checksum. Prefer a
   modest supported upgrade, but do not assume a dated pin is security-current.
   Supply exact release URLs/names/checksums only if actually observed. Distinguish
   confirmed fixed vulnerabilities, unknown applicability and unverified binaries.
2. The embedded runtime is CPython 3.11.9, with 142 Python-3.11 Windows pins.
   Check official CPython security support and Windows binary availability for a
   compatible security update. Explain constraints of switching Python minor
   versions and native wheels. Do not silently propose an unavailable official
   embeddable security release or call the old binary fully audited.
3. Review the existing build-time hash checks and new package-04 inventory in
   the checkout. Explain what integrity establishes and what it does not. Give
   a concise practical recommendation for the next candidate and remaining
   release decisions. No broad claim of complete safety or exploit reproduction.

Any upstream vulnerability count must name its scope; do not add unrelated CVEs
or treat all advisories as exploitable. No decompilation/fuzzing claim. Finish
the report early and state missing evidence. Astra will verify your primary
citations and any proposed version/hash update before integration. No tests are
required for a read-only report; list the source paths and metadata inspected.
