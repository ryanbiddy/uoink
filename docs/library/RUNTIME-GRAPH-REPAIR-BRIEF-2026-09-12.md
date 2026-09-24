# Repair the graph verifier before trusting it

Control Room db13e13b completed its first implementation. Astra independently
ran its named suites: 14 passed. That does not validate the verifier's claims.
Static review found gaps against the original brief. Keep its raw source, tests,
report and 306-file evidence directory unchanged in the original worktree:
C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/db13e13b-ff8/gemini.
This is a documented repair run, not a repeated metadata fetch or product audit.

Copy its four new deliverables into your new worktree, then repair them. Preserve
the original source, tests and report under _scratch/runtime-graph-original before
editing. No commits, subagents, existing committed tests/fixtures, product pins,
build files, model/checkpoint loading, inference, paid API, live index or port
5179. Read Standing rules and ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md first.
Metadata already captured is sufficient: no network fetch in this repair run.

Repair these four groups in scripts/check_runtime_graph.py:

1. Evidence must be complete and bounded. Missing/empty/malformed manifests and
   empty selections cannot pass. Require valid SHA256 values and manifest
   coverage of every JSON/METADATA file consumed. Resolve paths inside the proof
   root before any file access; reject traversal, absolute paths, symlinks and
   duplicate normalized entries. No integrity-bypass option may produce PASS.
   Match selected package/version, wheel filename package/version and METADATA
   Name/Version. Read only exact wheel METADATA, never a wildcard or different
   release's fallback. Reject missing/invalid wheel hashes and URLs. A local
   manifest proves retained-byte integrity, not authenticity on its own.
2. Generate only Windows CPython 3.13 non-free-threaded tags, explicitly specifying
   cp313 ABI and interpreter. Remove host-default platforms and manual older
   interpreter `none` tags. Check both JSON and METADATA Requires-Python; reject
   malformed constraints instead of accepting them. Add regression cases for
   host-platform leakage, cp312-none and malformed/contradictory Python ranges.
3. Propagate requested extras to a fixed point, including cycles. A requirement
   such as uvicorn[standard] activates its optional dependencies. Marker errors
   must be errors, not inactive edges. Reject unsupported active direct-URL
   requirements. Validate selection names, versions and duplicate pins without
   silently dropping entries. Root extras must be explicitly supported or refused.
4. Correct the report. Torch 2.10 is not a fully fixed target when retained
   advisories extend through 2.13. Do not call relaxed constraints capability
   preservation or working alignment. No source-level migration is implemented.
   A wheel-only scan's two missing upstream wheels do not invalidate the prior
   installed graph: those packages were built from source under the existing
   build process. No new Ryan permission is needed merely to document that.
   Torchaudio metadata constrains a matching release; distinguish the current
   package graph from all conceivable source migrations. NLTK 3.10.4 is absent,
   not an approved target. Remove unverified commit references and stale source
   qualification claims. Preserve original reports as rejected evidence.

The original worker's new tests were never accepted and contain invalid synthetic
hashes and claims of complete extras coverage. Correct those new tests to meet
the original brief, archive the original bytes, and add real adversarial cases.
Do not change any test already committed at the frozen base. Run the corrected
tests/test_runtime_graph.py and tests/test_installer_dependency_lock.py. Save
fresh current/proposal JSON outputs with actual command exit codes under a new
review directory; do not overwrite the original raw evidence or SHA256 manifest.
Astra will rerun both suites in your worktree and checkout around three-way
integration. Write code early; final output must name unresolved constraints
and avoid claims of security clearance or successful inference.
