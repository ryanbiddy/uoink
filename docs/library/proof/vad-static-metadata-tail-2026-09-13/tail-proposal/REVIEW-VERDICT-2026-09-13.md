# Literal-token tail reporting verdict

`static-tail-preflight01` completed with 17 passed, 0 failed and measured
process exit 0 under `-I -S -B`. The new reader is ready for the root's
exact-source review before any separately labeled static artifact read.

New reader SHA256:
`67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5`.

Approved before-reader SHA256:
`f27b91e610284e26975038ff6826f2190758b1d4c53a402db3c2d0386cc4d40d`.

The source change adds a list holding the last 64 matching identifier-token
occurrences, in opcode order and including duplicates. It applies the existing
STRING_OPS filter and IDENTIFIER regex with a 96-character maximum. The oldest
sample is removed before appending at capacity. Only two output fields are
added: `identifier_string_tail_samples` and `string_tail_sample_limit`.

Synthetic comparison covers more than 64 tokens, exactly 64, shorter/empty
lists, repeated occurrences, duplicate order, stored and deflated pickle data,
the 96-character/regex boundary, ignored non-string arguments, GLOBAL and
STACK_GLOBAL reporting without resolution, and unchanged malformed/trailing/
unsupported-protocol/missing-pickle refusals. For every accepted comparison,
the full revised parser output equals the approved output after removing only
the two tail fields. The first-64 samples are also asserted directly.

The final static check requires the whole reader AST to differ only by that
exact tail bookkeeping and return-field addition. Input reads, hash gate,
fixed paths, acceptance predicates, size/output bounds, opcode counting,
GLOBAL capture and model behavior remain unchanged. Neither reader's `inspect`
or `main` ran, and an audit hook prohibited opening the actual checkpoint.
All test containers and pickle literals stayed in memory; no pickle was
deserialized and no checkpoint-selected global was imported.

The 80-payload run03 proof remains intact and was fully verified before this
task. The new sample is additional reporting for a separate proposal; it does
not supersede run03, prior refusals or original seals. The sample is not a
complete metadata inventory and assigns no key/value meaning, architecture,
configuration, tensor schema or loader authority to its literal tokens.

The root may review one future exact-hash-bound static inspection using this
reader, with a fresh run ID and independently captured exit. This subagent
performed no actual artifact read, reader-main execution, product/test/docs
change, model/provider execution, installation, staging, commit or push.
