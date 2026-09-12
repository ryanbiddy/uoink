# Saved media details: repair accepted for final qualification

Control Room Gemini run 2dae80cc supplied the authenticated item-detail route.
Astra corrected its boundary and display gaps, then verified **58 passed** in
the worker (8.15 s) and **58 passed** in the checkout (7.85 s), with --runxfail.
This accepts the focused repair. A fresh complete tree and package-08 installed
native observation are still required; package-07 cannot qualify this source.

Opening saved video metadata previously requested JSON through the image-only
/file route and received HTTP 415. The new /yoinks/<id>/details route requires
the existing token and obtains the path from the registered item. It checks
lexical containment before metadata probes, rejects symlinks/reparse points,
limits reads to 2 MiB plus one rejection byte, and refuses malformed UTF-8,
non-finite JSON and nesting beyond 64 container levels. Its field projection
also filters nested speaker dictionaries. /file remains image-only.

The dashboard now reports an actual read error and tracks each selection request
by generation, including A-to-B-to-A navigation. Transcript strings show "time
not stored"; timeline spans require actual valid endpoints. Empty speaker objects
create no attribution. Stored start_seconds/end_seconds aliases survive the
projection. Notes retain the earlier source-aware text-readiness repair.

The original checkout independently records **9 failed / 3 passed** under the
worker's twelve new cases. The first worker patch had 47 focused passes but
failed all ten additional boundary/truth probes once their new setup was valid.
The first correction had 56 passes and one depth failure: relying on the process
recursion limit was insufficient. The explicit depth repair produced 57 passes
in both roots. A final projection review found dropped timestamp aliases; its
new case failed before the allowlist repair, followed by the final 58/58 results.
There are 23 new cases across two files. Existing tests and fixtures are unchanged.

The new integrator test preparation had a syntax failure before file creation,
one no-file pytest invocation, and three setup-only failures while required
slug, yoinked_at and corpus_path fields were supplied. Six backend bodies had
not run during those setup failures; four UI assertions had failed. Exact drafts,
diffs, diagnostics and all attempt logs are retained. No assertion was weakened.
The worker's repeated and intermediate runs are retained even where its prose
omitted them. The raw Git patches, three-way apply output and normalized staged/
worker/checkout byte comparisons are in the media-detail12 review seal.

The a25e3be complete partitioned tree is separately sealed: **2,556 passed,
one historical AT6 failure, two skipped**, all 2,559 cases accounted for once.
That result remains FAIL and predates this media repair. The old AT6 receipt
does not contain a process exit status; new successful installs cannot supply
a fact missing from that historical record. Do not edit it or its assertion.

This review covers authenticated saved-file handling and the tested UI behavior.
It does not establish protection from a malicious process with the same user's
filesystem rights, certify the dependency stack, run models or approve release.
The dependency and historical receipt holds remain explicit.
