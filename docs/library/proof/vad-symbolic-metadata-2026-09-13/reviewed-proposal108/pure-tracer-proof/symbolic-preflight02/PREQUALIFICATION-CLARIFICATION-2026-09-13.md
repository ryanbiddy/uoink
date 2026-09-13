# Evidence-scope clarification before the first synthetic run

The independent reviewer inspected the first source at SHA256
`301201a7419727d2c877ce6d419466f41fb093c6e6d72156da3c7f5d612cd3b8`
and found no target-execution path, checkpoint I/O, silent duplicate overwrite
or obvious graph-bound bypass. This was source review, not test acceptance.

The reviewer identified an interpretation limit: node references preserve
final literal-container structure and per-symbolic-object operation order,
but do not capture opcode byte offsets or global cross-node event order.
They cannot reconstruct argument/state snapshots at hypothetical execution
times. The grammar and output note will state that limit explicitly before
qualification. No temporal evaluation or constructor/BUILD application is
added. The initial brief/source are preserved in `draft01`.
