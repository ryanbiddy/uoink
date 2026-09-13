# Fixed VAD plain-state reader proposal

2026-09-13. Build the next missing source component in a fresh scratch proposal.
This is a bounded reader for the proposed converter output. It does not approve
the original checkpoint, conversion, model imports, installation or release.
Do not change product source, pins, existing tests or the fixed factory bridge.

Use the exact 54-key F32 shapes from the reviewed fixed-plan.json
(`37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf`).
Read its bytes and the frozen converter/factory source as text only. Preserve
their hashes. The expected dense tensor data is 5,891,996 bytes. Write actual
stdlib-only source early; a design without implementation is incomplete.

The core accepts one immutable bounded byte snapshot and an explicit externally
approved profile. Hash and size must match before JSON/header interpretation.
The real approval remains absent and refuses before path access or imports.
Synthetic profiles may authorize only locally generated data and must not
authorize the known original checkpoint. No actual converted artifact exists;
do not invent its hash or a real trust anchor.

Parse the eight-byte little-endian header length with a 32-KiB header cap and
6-MiB whole-output cap. Require UTF-8 JSON with unique keys, exact 54 tensors,
F32 dtype, exact fixed shapes and integer offsets. Refuse metadata/class names,
unknown or missing tensors, overlap, gaps, aliases, nonfinite floats, overflow,
trailing data and unsupported padding/encoding. Accept only the canonical
header layout emitted by the frozen converter; preserve finite F32 bits,
including signed zero and subnormals. The exact dense file coverage and element
count must agree before returning an immutable verified-state description.
Use a cooperative deadline across hashing, parsing, scanning and serialization.

Keep the verified immutable bytes alive with their checked slices and fixed
descriptors. This proposal must not expose a general pickle, Torch, Safetensors
native, checkpoint-selected import or class-construction path. Do not execute
the factory. Document the future handoff to fresh CPU/F32 zero-offset tensors
and the still-missing native/import/value checks; a byte reader alone cannot
qualify that handoff. No filesystem wrapper or downloader is required here.

Prepare a synthetic harness covering canonical full-schema output, exact bit
preservation, missing approval before interpretation, wrong hash/size, malformed
JSON and duplicate keys, shape/dtype/type mismatches, gaps/overlap/truncation,
nonfinite encodings and final deadline refusal. Generated data and reviewed
source/JSON are the only inputs. The original artifact and installed runtime
must never be accessed. Preserve source drafts and failures, freeze every
input, and send the full source/harness/launcher for root review before any
execution. Run only under a separately admitted stdlib protocol with live-path
binding and no network, model/native import or subprocess from the child.
