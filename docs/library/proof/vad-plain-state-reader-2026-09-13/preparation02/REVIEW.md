This is the unexecuted vpr02 instrument repair. The single new harness import
preloads encodings.utf_16_le before the existing import guard closes. It does
not extend the guard afterward. The original fixture expression, reader bytes,
all case bodies and all 76 case IDs remain identical; a complete AST comparison
after removing that one Import node verifies this scope.

The original vpr01 result remains an invalid setup run: child, launcher/outer
and invocation exits 1, zero cases executed, denied lazy codec import, followed
by the launcher's secondary JSONDecodeError. It is sealed separately at
../vad-plain-state-reader-vpr01-execution/SHA256.json,
SHA256 89b90577f401955b4faa0d440118632b2b0cb2e4e7a1a976a702c85d7cbc008b.
The original preparation remains at ../vad-plain-state-reader-proposal01/SHA256.json,
SHA256 d2bf7531d5f89a50d80d7260e993954b81a56e4c6fa4457d08c770b8c728a0bf.

BRIEF.md, SOURCE-BINDINGS.json, the converter/factory context and both launchers
are unchanged copies from preparation01. REPAIR-BRIEF.md supplies this fresh
instrument-only scope. INPUTS.json binds the repaired harness; the false
ROOT-ADMISSION.TEMPLATE.json names unused label vpr02 and awaits root review.
No passing count is claimed for either preparation.

Real purpose remains unconditionally refused. Synthetic profile/evidence fields
and freely constructible VerifiedState objects do not authenticate provenance.
Only the reviewed harness controls generated fixture authority; any future
native caller must revalidate against an external real approval. This repair
does not authorize actual artifacts, package imports, models, downloads,
installation, inference, dependency changes or market acceptance.
