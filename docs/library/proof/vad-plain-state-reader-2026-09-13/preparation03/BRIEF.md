Implement only the fixed plain-state byte reader and prepare its synthetic
qualification for root review. No reader, test, factory, model import or native
model operation will run during preparation. No actual checkpoint or converted
artifact will be opened. Real approval remains absent.

Bind the fixed converter plan SHA256
37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf,
the frozen converter b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b
and the fixed factory text. Derive exactly 54 sorted F32 descriptors with
1,472,999 elements and 5,891,996 dense data bytes. The converter serializes JSON
with ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False,
then adds only the necessary 0–7 ASCII spaces to an eight-byte boundary.

The core accepts an exact bytes object and an explicit immutable approval
profile. Reject absent/real/unrecognized approval before looking at the supplied
snapshot. Synthetic profiles are externally reviewed statements for generated
fixtures, not self-authenticating provenance; they cannot authorize the known
original checkpoint. No real hash is invented. Size and SHA256 gates precede
header or JSON interpretation. Bound the file to 6 MiB and header to 32 KiB.

Reject duplicate JSON keys, metadata/classes, unknown/missing tensors, non-F32,
shape/type mismatches, invalid integer offsets, gaps/overlap/aliases, truncation,
trailing data, unsupported encoding/padding and nonfinite binary32 encodings.
Require exact converter-canonical header bytes and dense coverage. Preserve
finite bits, including signed zero and subnormals, in the original immutable
snapshot. Return fixed immutable descriptors and checked slice access.

Use one cooperative time budget across chunked hashing, bounded JSON parsing,
header serialization, bit scanning and final immutable result creation. It is
not a hard preemptive deadline. Prepare tests for these boundaries, an exact
input manifest, a child guard with no writes/network/process/heavy imports, and
a launcher using the already-known C:\Python314\python.exe -I -S -B. Freeze and
send all source before root admits a fresh synthetic label. No filesystem
wrapper, dependency, downloader, product/pin/test edit or release claim follows.
