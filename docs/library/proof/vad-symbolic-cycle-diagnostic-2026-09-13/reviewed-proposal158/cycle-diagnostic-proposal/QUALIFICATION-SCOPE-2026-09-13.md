# Fresh diagnostic qualification scope

The original adapter harness and its 24-case outcomes remain frozen in the
108-payload proof. This new harness reuses its 23 behavioral and source-boundary
cases unchanged. Its one composition predicate was specific to assembling
the reader and tracer before diagnostic reporting existed. That predicate
remains preserved as unregistered historical code in the new harness and
unchanged in `before/qualify_adapter.py`; it is not claimed to pass against
an intentionally changed reporting instrument.

Replace it with one exact reporting-delta AST check: remove only the two
diagnostic constants and helpers, restore the original exception body,
remove diagnostic-only root arguments, restore the original first-gray-edge
refusal and remove the appended cycle refusal context. The remaining AST
must equal the reviewed adapter exactly. Add 12 focused witness cases.
The planned fresh run therefore has 36 cases, not a relabeled original 24.

The normalization proves equality of code outside those designated
diagnostic blocks. It does not prove the contents of the removed witness
helpers, exception constructor, gray-edge handler or main context body.
Those blocks require the independent source review and focused behavior
checks; do not describe the normalization as a proof of their implementation.

The duplicate-edge case directly tests the role helper's explicit occurrence
index on plain records. It does not invent a claim that DFS would reach a
later duplicate gray edge before rejecting an earlier identical gray edge.
Actual parser cases separately cover self-loops and a two-node cycle.
The malformed diagnostic case replaces only witness generation with a
raising synthetic function and verifies that refusal remains in force.
Byte-limit qualification temporarily tightens the diagnostic-only cap to
128 bytes; all original acceptance and output bounds remain unchanged.
