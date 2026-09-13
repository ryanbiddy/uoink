# Partial, untrusted selected-root static projection

The existing strict trace remains refused. The integrator's diagnostic
reported a five-node cycle entered through a known training root, with a
content-field edge and parent-field closing edge. Its reader and outer exit
were 2. That path is explicitly nonexclusive and does not identify an
OmegaConf class or prove that selected aliases avoid the cycle. Preserve the
158-payload seal and both actual refusals unchanged.

This is a separate diagnostic projection, not recovery of an accepted
artifact. Independent review of this design and its concrete bounds must
precede implementation. No checkpoint or model operation is authorized for
this agent. Use fresh scratch files and the exact reviewed diagnostic source
at SHA256
`15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd`.

## Invocation and strict result

Keep parsing, all existing grammar/resource checks, fixed path/hash,
ZIP/member/CRC validation and the original first-gray-edge whole-graph
rejection unchanged. Only the fixed reader requests the optional projection,
after validating the in-memory pickle payload, by passing an explicit flag
and the original reader's absolute 30-second deadline to the tracer.
Direct strict-tracer calls retain their current default behavior.

The tracer catches only its already established reference-cycle refusal to
prepare additional diagnostic data, then re-raises that same exception.
The overall status remains refused, the original reason remains Reference
cycle refused, and reader exit remains 2. Projection errors never become
accepted fallback. Existing cycle-witness reporting remains available.

## Independent closure validation

Select only values of present literal root keys already in SELECTED_ROOTS:
architecture, hyper_parameters, pyannote.audio, specifications and state_dict.
Do not add root scope, infer missing defaults or interpret those labels as
verified architecture or configuration.

Build one union closure using a fresh iterative DFS with its own colors and
completed-node heights. Follow every recorded edge: container key/value/item
references, symbolic targets, argument tuples, recorded BUILD or mutation
state, and persistent-ID operands. Do not prune opaque symbolic nodes or
reuse the earlier failed walk's colors. A selected alias into any cycle
refuses the whole projection. Check the entire closure before constructing
any output; a prefix that happens to validate must never be emitted.

Apply the existing limits to this independent closure: at most 20,000 nodes,
100,000 examined edges, depth 64 and 256 tensor descriptor records. Existing
parser bounds for strings, collections, stack, memo and opcode counts have
already applied to the complete parsed graph and remain unchanged. Count
depth from the original root: each selected value starts at depth 2, so a
selected value's completed height plus one must be at most 64. This avoids
granting an extra level through projection. Shared DAGs must use completed
child heights, not just current stack depth.

Every closure/descriptor/output loop checks the original trace budget and
the original reader deadline; this scope creates no fresh time allowance.
Expired time, a missing selected set, cycle, excessive depth, invalid
descriptor arity, resource excess or internal diagnostic error yields a
small fixed projection-refused marker with no projected values.

## Data boundary and output

After complete closure validation only, emit present selected-root labels,
their value references and a flat node table restricted to the selected
union. Build tensor argument descriptors only for nodes in that union using
the existing exact literal target and six/seven-argument rule. Preserve
storage, offset, size, stride, requires_grad, backward_hooks and optional
metadata as references only. Do not call the old all-node descriptors()
or general output() routines after the strict refusal, scan omitted
descriptors, construct tensors, resolve targets or apply BUILD semantics.

Unselected root entries and nodes unreachable from selected values stay
omitted. An acyclic value shared with an omitted/training root may still be
reachable from a selected value and therefore appear. Disclose that semantic
ownership and provenance are unknown; root filtering cannot prove that all
training-origin data is excluded. A shared cycle always refuses projection.
No generic training-root graph or arbitrary extra root is emitted.

Label any emitted projection partial_untrusted_selected_root_projection.
State explicitly that the artifact remains refused, no whole-artifact graph
is accepted, and architecture, configuration, semantics, provenance, tensor
compatibility and model compatibility remain unverified. Preserve the prior
final-reference-graph limitation: no global event ordering or historical
constructor/BUILD argument snapshots are inferred.

Keep the existing 1-MiB compact static-output bound for the projection, plus
the unchanged 256-KiB final serialized receipt cap. If the combined receipt
exceeds 256 KiB, discard the projection data and report a fixed projection
byte-limit refusal while preserving the original strict cycle reason/exit.
If retaining the other diagnostic fields still exceeds the cap, emit a
small cycle-refusal receipt with that projection-limit marker and no graph.
Never expand either cap or truncate a projected node graph into apparent
success. Nonprojection receipt behavior remains unchanged.

## Synthetic qualification and review

Before any implementation, obtain independent agreement on these bounds
and closure rules. Then preserve the exact baseline, source diff and all
new attempts. Reuse old behavior/refusal checks unchanged where their scope
still applies; document replacement of only source-equality predicates that
are intentionally superseded by this new diagnostic scope.

Synthetic-only cases must cover: an omitted cycle with a separate valid
selected closure; selected aliases that reach that cycle; aliases shared
between selected roots; an acyclic value shared with an omitted root; cycles
through BUILD, arguments and persistent operands; shared-DAG longest depth
with the original root level included; no selected roots; invalid selected
tensor descriptors; exclusion of omitted descriptors and unknown values;
partial-output refusal on every validation/resource/time failure; both output
caps; and unchanged overall cycle status/reason/exit 2. All sources, artifacts
and model targets remain inert. Use explicit forbidden-live startup binding,
isolated Python and the existing audit guards. Root alone may perform a
single labeled actual static inspection after exact-source review.
