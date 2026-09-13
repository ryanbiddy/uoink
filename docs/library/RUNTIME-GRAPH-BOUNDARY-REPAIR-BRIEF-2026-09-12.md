# Close the remaining graph-verifier boundaries

The repaired run 6c96f0a3 has 18 independent Astra passes, but three new probes
still demonstrate defects: a lock entry demo[feature]==1.0.0 loses its extra;
JSON with two identical demo keys silently keeps the last version; and the
wheel URL https:// is accepted. The diagnostic is under the integrator checkout's
_scratch/graph12-boundary-review02. Its first launcher stopped during Python
startup because the verification venv's audit environment was missing; the
read-only reader was then run with -I -S -B and an explicit packaging path.

Read Standing rules and both earlier runtime graph briefs. Work in a fresh
Control Room worktree. Copy the proposed checker, new tests, report and proof
directories from C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/6c96f0a3-c02/gemini.
Preserve the copied source/tests/report under _scratch/graph-boundary-original.
All 306 original metadata files match db13e13b byte for byte; preserve them and
their existing manifest unchanged. No fetch, package execution, model loading,
paid API, live index, port 5179, commits, subagents or existing committed test
changes. No production pins/build changes. Write the repairs early.

1. Preserve and validate root extras in text locks; reject duplicate JSON keys
   at decoding time for selections, manifests and PyPI records. Do not silently
   skip invalid underscore-prefixed package entries. Require real HTTPS artifact
   URLs with a host and no credentials, controls or fragment. Validate metadata
   object/list types and duplicate singleton Name/Version/Requires-Python headers.
   Add meaningful negative and positive cases to the unaccepted worker tests.
2. Apply a single bounded path reader before any is_file, stat or read of the
   manifest and consumed evidence. Inspect every ancestor for symlink/reparse
   points before resolving it; reject proof-root links, linked manifests,
   linked ancestors, traversal, alternate data streams and Windows device paths.
   Do not keep reading evidence after a failed integrity check or a requested
   integrity bypass. A local manifest is byte integrity, not upstream identity.
3. Remove the dist-info/METADATA fallback: it is not bound to the exact selected
   wheel. Remove PyPI wildcard fallback. Keep only explicitly enumerated exact
   paths. Require fixed-point extras convergence or return an error if bounded
   iteration is exhausted. Preserve the current 283-edge observation and the
   honest two-wheel-only failures without redefining installed-package success.
4. Narrow the report's statements. This tested proposal does not provide a
   security-cleared graph; it does not prove that none could exist. Torchaudio
   2.11 on captured PyPI constrains this package selection, not every possible
   source migration. NLTK backport work is underway separately. Do not label
   wheel URLs/digests as downloaded binary verification. Preserve earlier report
   bytes and all raw outcomes, and report only what the captured evidence proves.

Run tests/test_runtime_graph.py and tests/test_installer_dependency_lock.py with
a fresh isolated label. Save fresh current/proposal outputs and exact process
exits under a new proof directory; never overwrite previous observations. Write
a one-page verdict in docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md.
Astra will independently run both roots around raw diff / three-way integration.
