# Strict inert protocol-2 metadata tracing proposal

The completed literal inventories do not establish root dictionary
associations, configuration values, Specifications state or tensor-descriptor
arguments. This fresh scratch proposal addresses that static-analysis gap.
No actual checkpoint trace, conversion, export, model load or inference is
authorized for this subagent. Existing readers, receipts and seals remain
unchanged. This grammar and refusal policy precede implementation and tests.

## Nonexecution and proposed integration

The tracer accepts already bounded pickle bytes, uses `pickletools.genops`
only for syntax, and creates plain tagged data records with integer references.
GLOBAL is a literal reference record. REDUCE, NEWOBJ, BUILD and BINPERSID
become instruction records; none of their targets, hooks, persistent IDs or
state are imported, called, constructed, resolved or applied. There is no
pickle loader, recursive evaluator, tensor construction or storage-file read.

The proposed later adapter must retain the approved fixed input path,
whole-artifact SHA256 gate, ZIP directory/name/extent/compression bounds,
single-pickle selection, exact payload-size/CRC checks and existing literal
inventory. Only its validated in-memory `data.pkl` bytes may reach this tracer.
The expected artifact digest remains
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
This task first qualifies the pure bytes-to-symbols tracer; any adapter and
its exact code must receive independent review before an actual static trace.

## Grammar

Exactly protocol 2 is supported: one initial PROTO 2, one final STOP, no
trailing bytes, and a single literal-dictionary root on an otherwise empty
stack. Only these 31 observed opcode names are permitted:

```text
APPEND APPENDS BINFLOAT BINGET BININT BININT1 BININT2 BINPERSID BINPUT
BINUNICODE BUILD EMPTY_DICT EMPTY_LIST EMPTY_TUPLE GLOBAL LONG_BINGET
LONG_BINPUT MARK NEWFALSE NEWOBJ NEWTRUE NONE PROTO REDUCE SETITEM
SETITEMS STOP TUPLE TUPLE1 TUPLE2 TUPLE3
```

Primitive values, literal lists/tuples/dictionaries and symbolic instruction
records occupy a bounded node table. Stack/memo entries hold node IDs; memo
aliases stay references to the same node, including later recorded mutation.
Memo indices may be assigned once only. Dictionary keys must be immutable
primitive strings, finite numbers, booleans or None. Numeric-equivalent keys
such as True, 1 and 1.0 share one duplicate-detection key. Duplicate keys and
memo writes are refused instead of overwritten.

APPEND(S) mutates only a literal list or records a sequence operation on a
tagged REDUCE/NEWOBJ result. SETITEM(S) mutates only a literal dictionary or
records a mapping operation on such a tagged result. Tagged operations are
not interpreted as actual object/container semantics; mixed mapping/sequence
operations on one symbolic object are refused. REDUCE and NEWOBJ require a
literal GLOBAL target and literal tuple arguments. BUILD records one state
reference on a symbolic result, without applying attributes; a second BUILD
is refused. BINPERSID records its operand reference without resolving it.
OrderedDict receives no special executed or inferred container semantics.

After parsing, iterative graph validation rejects all cycles, including memo
alias cycles, and excessive depth. It validates the entire traced graph,
including roots omitted from output. No recursive evaluation is used.

## Output schema and limits

Output includes only present root associations whose literal keys are
`architecture`, `hyper_parameters`, `pyannote.audio`, `specifications` or
`state_dict`, plus a flat reference graph reachable from those values.
Other root values, including optimizer/training state, are omitted. No absent
configuration field becomes a default. An empty selected set is refused.
Labels are literal associations, not verified semantics or model identity.

The schema is `selected_root_associations` (key/value_ref pairs), `nodes`
(id/kind plus primitives, item/entry references or symbolic target/argument/
operation references), `tensor_reducer_descriptors`, and explicit false
architecture/configuration/model-compatibility claims. A tensor descriptor
is only a source-labeled argument record for an exact literal
`torch._utils _rebuild_tensor_v2` REDUCE with six or seven tuple arguments.
It retains storage, storage_offset, size, stride, requires_grad,
backward_hooks and optional metadata references; absence remains absence.
It does not validate shape compatibility, storage identity or tensor contents.
Specifications remains a tagged NEWOBJ/BUILD graph with raw assigned state;
no fields or current source defaults are synthesized. Raw checkpoint records
remain separate from any later source interpretation.

Initial bounds: 2-MiB input, 250,000 opcodes, 20,000 nodes, 100,000 edges,
4,096 stack entries, 128 active MARKs, 16,384 memo entries/indices,
4,096 items/entries/operations per collection, graph depth 64, 64-KiB UTF-8
bytes per string and 2-MiB total string bytes, 512 bytes per GLOBAL literal,
256 tensor descriptor records, 1-MiB output and a cooperative 30-second
budget. Every loop over input/graph/output checks bounded work or time.
Only finite floats and bounded builtin integer values are recorded.

Unsupported opcode/target/key forms, malformed stack/marks/memo, odd mapping
items, duplicates, cycles, ambiguous mutations, excess resources, missing
root metadata or invalid descriptor arity produce refusal, never partial
acceptance. The exact cause and attempt remain preserved before any repair.

Synthetic qualification uses only small literal pickle bytes under
`-I -S -B`. Malicious-named GLOBAL/REDUCE/NEWOBJ targets must remain plain data
with no side effects. Cases must cover association/reference correctness,
memo mutation, descriptor hooks/metadata, absence preservation, STOP/trailing
bytes, structural refusals, numeric duplicate keys, cycles and every resource
boundary. An independent reviewer must inspect the source before any artifact
trace. If strict nonexecution/bounds cannot be maintained, the proposal stops
with a concrete gap; it cannot silently broaden into a deserializer.
References describe final literal-container structure and per-object tagged
operation order. They do not record opcode offsets or global event order and
are not snapshots of arguments/state at hypothetical execution times. No
constructor or BUILD state is evaluated. Any later proposal needing temporal
semantics must treat that as an explicit gap rather than infer it here.
