# B2 wheel-builder review candidate — 2026-09-13

The final utility passes **62 synthetic cases, zero failures/errors/skips** in
`bw03`, with actual child and launcher exits 0. Its SHA-256 is
`ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f`.
The corrected protocol SHA-256 is
`4850a083264e305871b81a9ae5a16390b63950ce9b9efca630c7aa89fd153417`.
Root must review these exact bytes before any invocation on a real wheel.

The production entry fixes the upstream filename, size and hash and accepts no
hash override or fixture bypass. Four recipe files have fixed sizes and hashes:
B2 source, notice, aggregate patch and expected member manifest. It validates ZIP
paths/types, the exact member set, metadata fields and all RECORD rows, changes
only the planned members, verifies the expected output map, and writes fixed
ZIP_STORED bytes into a fresh destination with provenance. No dependency resolver,
package import, upstream build hook or network is used.

The tests exercise malformed ZIP names, collisions, signatures, links/types,
compression/encryption flags, member/total-size limits, RECORD and metadata
errors, path/output boundaries, fixed identity refusal, recipe/source tampering,
unchanged members, deterministic serialization and output tamper detection.
The asset inside every synthetic archive is a short explicit placeholder. The
fixed real member manifest rejects that placeholder. Calls to the production
build entry use only synthetic wrong-name/size/hash files and cannot reach the
successful real-artifact branch. No actual upstream wheel, installed package
or model asset was opened, copied, decompressed or executed during these tests.

Three issues remain visible in the evidence history:

- Before qualification, root identified unbounded read_bytes calls following
  stat checks. The utility now uses capped reads, regular-file handle checks,
  fixed recipe sizes and observed identity/stability comparisons. The original
  source and exact repair diff/reason are preserved. A synthetic growing stream
  verifies a single cap-plus-one read and refusal; oversized/changed-handle
  cases also pass.
- `bw01` recorded 61 passed and one failed backslash test, actual exit 1. Windows
  normalized the name while the fixture was written. The documented fixture
  correction changes only local/central filename bytes; its ValueError assertion
  remains unchanged.
- `bw02` also recorded 61 passed and one failure, exit 1. The corrected fixture
  exposed normalization during ZIP reading. The product repair validates
  ZipInfo.orig_filename and rejects a change before using normalized names.
  `bw03` then passed the same corrected 62-case protocol. Both earlier failures,
  before-source bytes, traces, commands and real exits remain intact.

All runs used Python 3.14.6 with `-I -S -B`. The import/audit guard stayed active,
with no heavy packages or forbidden artifact/network/process/native-library
attempts. Provider credentials were scrubbed by variable name and offline flags
were set; no credential values were logged. No accepted checkout fixture,
source pin, shared staging, product source or prior seal was edited.

These are bounded preparation tests. ZipFile allocates central-directory objects
before the utility checks member count; bounded input limits that exposure, and
the production entry checks the exact wheel hash first. File stability checks
require quiescent paths and do not provide atomic protection against a hostile
same-user Windows process. Real-wheel member verification, two independent real
artifact builds, packaging/inventory installation, full-module/native behavior
and release acceptance remain unperformed. The expected output-wheel hash is
still unknown; synthetic deterministic bytes do not fill that receipt.

Commands from the checkout root are preserved in the launcher plans:

```powershell
C:\Python314\python.exe -I -S -B _scratch\companion-b2-builder01\prepare-inputs.py
C:\Python314\python.exe -I -S -B _scratch\companion-b2-builder01\launch.py bw01
C:\Python314\python.exe -I -S -B _scratch\companion-b2-builder01\launch.py bw02
C:\Python314\python.exe -I -S -B _scratch\companion-b2-builder01\launch.py bw03
C:\Python314\python.exe -I -S -B _scratch\companion-b2-builder01\seal.py
```

The independent B2 constructor results are separately preserved in the combined
70-payload archive `companion-b2-combined-review01`, manifest SHA-256
`28a7d1d8601ffb26b65cba2d4a9cb05774aa465ba5b312b1c36a8ec40256f955`.
Both ten-case B2 runs there match source/protocol hashes and ordered case IDs.
