# B3 real-build preparation verdict

The proposed launchers adapt successful B2 byte-only protocols to the unchanged
qualified B3 utility and its five fixed recipes. Each child has an exact retained
source diff and reason mapping. The shared path/hash/runtime validation helpers
are copied without changes. The new outer launcher has no runtime-copy action;
it reuses the existing private 34-file Python 3.13 runtime and verifies it before
and after the second launch.

The first B3 output hash is unknown. The first command takes no expected-output
override. The second requires root's observed first hash and size, cross-checks
the successful first receipt and preparation seal, and compares exact wheel
bytes. This does not override the builder's fixed upstream identity or recipe
hashes. First and second runs have separate fresh output directories and epochs.

Only sealed text/receipt copying, static parsing and identity comparison occurred
in this preparation. Neither launcher/child ran. No runtime file, upstream wheel,
output wheel, model or asset was read here. Reading earlier runtime/build receipt
text is not a new runtime or artifact observation. The proposed guard remains
the successful B2 profile with exact B3 utility/source bindings; it is scoped
instrumentation, not an OS security boundary. Root's review and actual invocation
are required to produce a real measurement.

The separate combined B3 synthetic archive contains both exact 68-case runs,
the original 56-payload seal, root inputs and peer verdict. Earlier B2/Hub payload
trees remain separate immutable references. No prior seal or production,
dependency, acceptance-test or staging file was modified.
