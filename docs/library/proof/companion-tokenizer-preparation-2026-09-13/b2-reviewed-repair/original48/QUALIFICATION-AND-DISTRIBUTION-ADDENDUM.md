# Companion B2 qualification and distribution addendum — 2026-09-13

B2 passes the original six constructor contracts and four new empty-buffer
contracts: **10 passed, 0 failed, 0 errors, 0 skips**, actual exit 0. The same
ten cases against B1 produced **6 passed, 4 failed, 0 errors, 0 skips**, actual
exit 1. B1's six original contracts still passed; its four new failures remain
in the archived traces. No prior result has been replaced or expanded in scope.

The only B1-to-B2 product-code change is `if tokenizer_bytes is not None:`.
The B2 source SHA-256 is
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.
The four new cases cross local-only true/false with an ambient file present/absent.
Each supplies b'' and an explicit fake buffer parser that rejects it. B2 records
only `tokenizer.bytes`, raises the fake parser's ValueError and leaves model and
tokenizer attributes unassigned. B1 instead substitutes an ambient file, raises
FileNotFoundError without invoking the buffer parser, or allocates then invokes
the non-local fallback. The per-case receipts retain those differences.

All six original assertion bodies, their setup and the AST-prefix helper are
unchanged. New cases have their own buffer-parser override. The harness combines
two TestCase classes, records the new boundary observations and uses fresh labels;
its import finder, audit hook, offline environment, credential scrubber and
selected-code boundary are unchanged. Harness/launcher diffs are included for
review. The inherited harness opening docstring still says six; the suite's
explicit count, case IDs and raw receipts establish ten actual cases.

Both runs used Python 3.14.6 with `-I -S -B`, no preloaded or postloaded heavy
packages, no import/audit violations and the finder installed at completion.
They executed only the selected constructor prefix with fake dependency seams.
No actual tokenizer, model, native dependency or complete package was imported
or executed. The fake parser establishes routing/order behavior; it does not
establish an actual tokenizer library's malformed-input exception contract.

The original distribution plan remains unchanged. This fresh addendum proposes
the revised source for the same unbuilt, unpublished
`1.2.1+uoink.localassets1` distribution identity. It does not replace an existing
wheel under that name: no B1 or B2 wheel has been built. Its planned transcribe.py
hash, derivative notice and RECORD change; version.py, METADATA version, WHEEL
metadata, all other members, license, 16-member count and ZIP recipe remain as
planned. `proposed-member-manifest-B2.json` lists the revised exact text hashes
and leaves the output wheel hash unset.

`B1-to-B2.patch.txt` is the narrow one-line source delta. The initial
`upstream-to-B2.patch.txt` also records the already-existing whole-file LF-to-CRLF
difference between retained upstream and B1/B2 source bytes. It is preserved.
Use the separately named `upstream-to-B2-normalized.patch.txt` to review the
logical aggregate delta, and enforce exact final B2 bytes/hash during any future
preparation. This additional normalized diff is a presentation change, not a
source or test repair. The proposed notice binds its aggregate patch hash; the
manifest binds the exact output source hash.

The exact upstream wheel/input identity verified in the B1 plan is still
applicable. This addendum did not reopen a wheel or read the bundled ONNX asset.
The existing model-member declaration and its unobserved runtime scope remain
explicit. The original one-line frozen installer-test expectation proposal is
unchanged, requires the reserved review and has not been applied. All original
24/46/67/52 seals and payloads were verified unchanged before preparation and
again when sealing.

Root must review this new proposal before derivative preparation or application.
The former acceptance of B1's six-case scope does not automatically accept B2,
the distribution build, native/full-module behavior or market readiness. The
copied council report is evidence of the empty-buffer finding; its other findings
are outside this repair's disposition.

Commands from the checkout root:

```powershell
C:\Python314\python.exe -I -S -B _scratch\companion-b2-empty-buffer01\prepare.py
C:\Python314\python.exe -I -S -B _scratch\companion-b2-empty-buffer01\launch.py b1-boundary01
C:\Python314\python.exe -I -S -B _scratch\companion-b2-empty-buffer01\launch.py b2-candidate01
C:\Python314\python.exe -I -S -B _scratch\companion-b2-empty-buffer01\addendum-and-seal.py
```

The dated B1 repair reason was written before the B2 arm. Each launcher plan
retains its exact child command, timestamps and scrubbed variable names without
credential values; results preserve actual exits and unchanged input hashes.
No product/frozen-fixture/pin/staging changes, downloads, builds, commits or
pushes occurred.
