# Selected-root projection qualification

The first executed synthetic attempt, `projection-preflight01`, completed
63 passed, 0 failed in 0.433264 seconds, actual qualification exit 0.
The forbidden-live startup binding was asserted and source/harness hashes
were unchanged. No actual checkpoint or real reader input/output path was
used. All model targets, pickle payloads, ZIPs and receipt fixtures were inert.

The integrator independently reviewed the design, source delta and new
harness cases, including the inherited setup adaptation. Its exact-copy
run in `_scratch/astra-selected-projection01` completed 63 passed, 0 failed
in 0.047207 seconds, actual qualification exit 0, with all five input hashes
unchanged. Its plan, raw output, exit receipt, source copies, wrapper,
wrapper generator and outer console log are preserved in the fresh proof.

Source SHA256:
`0b62dcac9962ee0620ed8c8af6deca169ce5aeab215994b637f5902dd79ddb73`.
Harness SHA256:
`6e0a19710f0a899f3d68dbff9d5d741118879d7c94fa0f42114b37208109e01a`.

Independent design review preceded implementation. Source review then found
a deadline gap before qualification: full receipt serialization could cross
the original reader deadline after a projection was attached. The unexecuted
draft is preserved. The documented repair checks after serialization and
discards every projected value if the deadline expired, keeping the original
strict cycle reason and exit 2. The synthetic clock/serialization case verifies
this boundary. The first unexecuted 61-case harness is also preserved; review
added two focused post-parse node/edge-limit cases before the 63-case run.

The suite retains 35 earlier behavioral/boundary assertions, with only
documented keyword-seam adaptations, plus one projection-scope AST check
and 27 new cases. Earlier source-equality predicates remain historical;
they are not relabeled as passing against this new scope. AST normalization
checks code outside the designated new blocks, whose implementation relies
on independent source and focused behavior review.

The projection validates one complete union of the existing selected roots
using fresh colors and completed-node heights. Every symbolic target,
argument, BUILD/mutation and persistent-reference edge is followed. Selected
aliases into a cycle refuse the entire projection. Depth includes the
original root. The tested node/edge/descriptor/output/time limits yield no
projected values on failure. Selected-only descriptor construction retains
hooks and optional metadata references without evaluating them; omitted
descriptors and unreachable values are not scanned into the projection.

A valid projection is explicitly partial and untrusted. An acyclic value
shared with an omitted root can still appear when reachable from a selected
root, so semantic ownership and provenance remain unknown. No extra root
scope, inferred defaults, evaluated constructor/BUILD state, tensor contents,
architecture verification or loader authority is introduced.

The original whole-artifact reference-cycle refusal remains in force even
when a selected projection is produced. Both the 1-MiB compact projection
cap and the 256-KiB final serialized receipt cap remain unchanged. The
combined-receipt test verifies removal of the entire graph on overflow,
including fallback to a small strict-cycle refusal receipt when needed.

The earlier real `symbolic-cycle01` remains refused: reader and outer exit
2, 0.029370 seconds, with the same recorded artifact digest. Its saved
witness reports five node IDs/kinds, a content-field edge and a parent-field
closing edge, entered through a known training-root path. That path is
nonexclusive; it establishes neither an OmegaConf class nor absence of
selected aliases. This proposal uses saved receipts only. The original
158-payload seal and every earlier failed/refused attempt remain unchanged.
No actual selected-root projection has been performed by this agent.
