# Static symbolic adapter qualification

`adapter-preflight02` completed 24 passed, 0 failed, actual qualification
exit 0 in 0.058231 seconds. The launcher explicitly set the forbidden-live
environment string before isolated Python startup; the child asserted it.
All input archives and pickle payloads were synthetic bytes in memory.
The few `main` calls used inert inspection, argument-parser and receipt-path
fixtures. Their return values were tested; they were not actual checkpoint
reader process invocations. No real model, tensor, checkpoint or live index
was accessed by this qualification.

Adapter source SHA256:
`0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc`.
The source hash is identical before and after both attempts.

The integrator independently reviewed the exact adapter and all 24
assertions, copied the adapter, harness and two baseline sources into
`_scratch/astra-symbolic-adapter01`, and ran the same cases under isolated
Python. That independent run recorded 24 passed, 0 failed in 0.061465
seconds, actual qualification exit 0, with all four input hashes unchanged
and the startup binding asserted. Its raw plan, outcome, exit receipt,
source copies and wrapper are preserved in the outer proof.

The exact AST comparison verifies the reviewed tail-reader definitions and
pure-tracer definitions with only the documented changes: tracer helper
rename, in-memory symbolic handoff after payload validation, overall clock
checks, TraceRefusal handling, and fresh receipt/scope/status labels. The
fixed input path and immutable expected artifact hash remain unchanged,
as do ZIP/member/size/CRC bounds and the 256-KiB final receipt cap.

Behavior cases verify stored and deflated metadata, unchanged prior inventory
fields, inert targets, rejection before symbolic tracing for wrong digest,
CRC, size and trailing bytes, duplicate/cyclic/unsupported symbolic input,
escaping or ambiguous ZIP members, overall time limits, fresh receipt paths,
output overflow, and the existing success/refusal/error/receipt-failure
return values. The pure tracer's separate 1-MiB compact-output bound does
not widen the reader's final 256-KiB serialized receipt bound.

The first executed attempt remains failed: `adapter-preflight01` recorded
23 passed, 1 failed, exit 1 in 0.056542 seconds. Its new generic static audit
mistook the unchanged baseline `re.compile` call for Python compilation.
The documented repair exempts only that exact qualified regex call while
retaining full AST equality and all other prohibited-call checks. The same
24 case IDs pass in the corrected attempt. No adapter code changed.

Before execution, independent review also corrected two new setup issues:
an expected refusal substring and a read-log assertion that included ZIP
tail discovery. Those drafts remain preserved. The whole-file hash pass
and opaque ZIP metadata-tail scans can read bytes belonging to storage
members. No storage member is selected, decompressed or interpreted; only
validated data.pkl bytes reach the tracer. The synthetic read log explicitly
distinguishes earlier tail overlap from the payload handoff stage.

This proposal assumes quiescent staging and preserves the reader's before/
after identity and modification checks. It does not turn the underlying
file into an immutable snapshot. The symbolic output remains a final
literal-container graph and per-object instruction sequence, without
historical argument snapshots or evaluated constructor/BUILD semantics.
A real cycle, unsupported structure, deadline or output overflow must be
recorded as refusal. None can be relabeled as a model trial or acceptance.

The adapter has not been invoked on the checkpoint. Root review of this
exact source and the independent verdict remains necessary before a single
labeled static inspection. That inspection would still authorize no model
load, conversion, tensor construction, inference, architecture/configuration
verification or release acceptance. All prior inventory and tracer seals
remain unchanged.
