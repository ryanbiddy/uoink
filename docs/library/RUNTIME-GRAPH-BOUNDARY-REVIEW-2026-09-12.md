# Astra verdict: runtime graph checker boundaries

Accept the repaired offline checker after independent verification in both roots. Do not
accept either evaluated dependency selection as a security-cleared runtime.

Control Room db13e13b and 6c96f0a3 delivered proposals. Run 85ce8600 reported
completed/exit zero but had none of its required files; it remains incomplete.
Astra preserved all earlier source, reports and outcomes, then completed the
bounded repair in the 6c96f0a3 worktree. The repair brief and takeover brief
explain why these fresh observations were needed.

The checker preserves lock extras, rejects duplicate JSON and singleton METADATA
fields, requires usable HTTPS artifact URLs, stops after failed/bypassed integrity
checks, and reads only enumerated PyPI records and exact wheel metadata paths.
Consumed bytes are rehashed and parsed from the same read. Ancestors are checked
for links/reparse points; unsafe Windows roots are rejected before probing them.
Target overrides cannot mix non-Windows markers with fixed Windows wheel tags.
Exhausted extras propagation is an error. These controls do not claim protection
against every concurrent filesystem race or authenticate downloaded binaries.

Eighteen new boundary cases on the preserved worker checker produce 13 failures
and five passes. After repair, all 36 focused cases pass in the worker: 13 original
worker cases, 18 boundary cases and five unchanged installer-lock cases. Earlier
18- and 30-pass observations are retained. Checkout verification passes the same 36 cases after raw git
diff export and git apply --3way (worker 7.70 s, checkout 6.52 s). No previously committed test is edited.

The current captured selection exits 1: 283 active edges, two source-only wheel
failures, no missing targets/conflicts among inspected metadata. The proposal
exits 1: 275 edges, five conflicts, two missing targets and three wheel failures,
including a yanked Transformers wheel. The original reports omitted some of those
limits and overstated impossibility of a future clean graph. The revised report
states only what these captures establish. NLTK preparation is separate.

Source migration, model qualification and original advisory dispositions remain
open. No production pin, installed runtime, source/media fetch, model execution,
live library, port 5179 or paid provider was used for this repair.
