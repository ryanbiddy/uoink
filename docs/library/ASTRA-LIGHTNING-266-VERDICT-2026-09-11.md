# Lightning integration verdict

Accept Gemini b9ce127d's two exact pin changes after independent review. The four
named installer/decoder suites pass in both roots: 16 tests in 1.25 seconds in
the worktree and 16 in 1.30 seconds in the checkout. No existing test changed.
Raw diff integration used git apply --3way. This is a source change; the new
installed inventory remains unobserved until the replacement build.

Astra verified both wheel hashes against primary PyPI metadata and inspected
both repaired saving.py implementations. A disposable overlay on the retained
Python 3.13.15 runtime has three passed checks: each namespace accepts a benign
in-memory data-module description and rejects untrusted instantiator/class
paths, and WhisperX/PyAnnote imports succeed. No checkpoint is unpickled and no
model or transcription runs. The audit hook refused one socket.bind attempt
during imports. The probe does not record that attempt's address; it cannot
support a claim of zero attempted network activity. No bind was permitted.

The full metadata traversal finds 281 satisfied edges and two unsatisfied
preexisting setuptools edges from Torch and CTranslate2. All changed Lightning
edges are satisfied, but the worker's whole-graph closure claim is rejected.
The installer deliberately strips setuptools. Follow the separate runtime
dependency repair brief before the final tree; do not hide this finding.

The existing OSV fixed-event inconsistency and other advisories remain. A fresh
audit must retain its actual output and distinguish upstream source fixes from
scanner status. Package-05 and all old measurements remain historical.

Proof: proof/lightning266-2026-09-11/SHA256.json. The first failed graph traversal
is documented separately; the second collects both missing edges. Worker command
history and both of its successful repeated runs are preserved. Its post-report
repeat was unnecessary verification, not a distinct repaired measurement.
