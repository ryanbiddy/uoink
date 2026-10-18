# Integrator corrections to the NLTK preparation proposal

Gemini ecbf6acd reports 27 passes and one symlink-privilege skip. Do not accept
that result as complete boundary coverage. Preserve its six proposed files and
all four attempts before these local repairs in the worker worktree.

Remove the newly introduced expected-patch-hash override. It permits arbitrary
patches, while the applier accepts target paths outside the destination and does
not require every expected output. Validate the fixed patch hash before creating
any destination. Use exact paths/hunks with all three expected output hashes;
no fuzzy search, optional hash bypass or incomplete success is permitted.

Validate source, destination and receipt paths before filesystem probes that
follow links. Reject drive-relative Windows paths, alternate streams, device
names, traversal and linked/reparse ancestors. Keep receipts strictly inside the
new destination, away from copied files, with exclusive creation. Copy regular
files without following links; compare the complete copied tree to its input
hash map before patching and preserve unchanged files. Record the map without
claiming it independently authenticates upstream source. Static path validation
does not establish protection against every concurrent same-user filesystem race.

The preparation tests currently all depend on this machine's staging path.
Vendor the three exact original source files and their upstream licence for
portable preparation tests. Keep full NLTK import/routing tests explicitly
staging-dependent. Retain the originals' source hashes. Do not import or execute
the vendored source when preparing it.

Repair the unaccepted test module's isolation: preserve the inherited audit
guard in child PYTHONPATH, refuse model/network operations in children, mock
training/serialization even in negative cases, and do not assert that unrelated
earlier tests imported no ML module. Replace the archive-exists assertion with
real byte comparisons. Existing committed tests remain unchanged. Add negative
cases for each observed preparation gap, with inside-boundary controls.

Run the repaired worker suite and new boundary cases under a fresh isolated
label, then the same checkout suites after raw diff/three-way integration.
Preserve failures and document repairs before reruns. No models/checkpoints,
training, inference, diarization, new fetch, paid API, live index, port 5179,
production pin/build edits or successful release claim in this step.

Before accepting these new tests, separate the original NLTK source fixture from
the installed native runtime path. UOINK_NLTK_BASE_SOURCE may name a preserved
unpatched source tree after a future installer update; the existing staged
upstream source remains the default for this observation. The matching embedded
runtime remains a separate path. Child audit code enforces network, model and
live-index restrictions directly under -I -S rather than relying on startup
discovery through PYTHONPATH. Record the final test-file refinement and its
both-root results. It does not alter a frozen acceptance test or a past outcome.
