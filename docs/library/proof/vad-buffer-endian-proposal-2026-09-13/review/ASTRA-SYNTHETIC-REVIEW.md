# Independent generated-buffer qualification

2026-09-13. Astra read the complete frozen comparator, synthetic harness,
launcher and numerical-basis note, and reviewed the separate source verdict.
Run the same two inputs once in fresh _scratch/astra-buffer-basis-synthetic01
using C:\Python314\python.exe -I -S -B and the explicit forbidden-live path
binding. Pin both copied inputs and compare hashes after execution. Preserve
native and actual outer exits, stdout and stderr. No automatic rerun.

The harness reads only these two files after stdlib startup and uses generated
constant bytes. Its audit rejects other file accesses, unlisted imports and
network/native/process operations. The 37 cases check both orientations,
inclusive eight-ULP boundaries, malformed inputs, signs, nonfinite values,
ordering, operation-order variants and ambiguous decision refusal. The source
has no I/O. No real model/storage read or profile activation is part of this run.

The numerical assumptions remain conditional. In particular, the Hamming
cosine error bound is not established for every historical backend; matching
these saved buffers cannot prove they were never changed. Applying an
orientation to other storages remains a separate explicit assumption. A
synthetic pass provides no historical writer authentication or model/runtime
acceptance and does not widen the fixed tolerance.
