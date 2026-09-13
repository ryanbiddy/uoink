2026-09-13. The exact fixed-state reader proposal passed the same 82 synthetic
cases in the author and independent root runs. Both used identical reader,
harness, input bindings, launchers and generated fixture identity. Each had a
valid guard, unchanged inputs, complete case membership, no heavy imports or
unexpected events, and actual child, launcher and invoking tool exits 0.
This is 82 distinct cases repeated twice, not 164 distinct cases.

| Run | Recorded result | Guard | Actual exits |
| --- | --- | --- | --- |
| vpr01 | Setup failure; zero case functions executed | Denied codec import; no complete guard report | All 1 |
| vpr02 | 75 passed, 1 failed, 0 skipped | Valid | All 1 |
| vpr03 author | 82 passed, 0 failed, 0 skipped; 0.744954 s | Valid | All 0 |
| vpr04 independent root | Same 82 passed, 0 failed, 0 skipped; 0.739920 s | Valid | All 0 |

vpr01 exposed a missing explicit UTF-16LE codec preload while constructing a
fixture; the secondary launcher JSONDecodeError is retained. That instrument
repair preserved all original assertions. vpr02 exposed a missing structural
JSON depth bound. The reader now checks depth before parsing, respecting strings
and escapes, with a fixed maximum of three containers matching the accepted
schema. All original 76 assertions remain unchanged; six scanner cases were
added. The preparer's separate LF/CRLF assumption failure, before source and
documented repair are also retained. No failed result was relabeled passed.

The qualified reader is SHA256
3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c;
the harness is 354bb3341b23dd37f8d04f3254fdbbbf4f715e7a08220abe6dbe04075924945f.
The plan remains 37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf.
The locally generated fixture is 5,896,708 bytes, SHA256
31b6222a3c31569e81da0597dc3ef339511cdee543114001cd989b6fddfba1d1.

This verdict covers the synthetic, immutable-bytes reader only. There is no
actual converted artifact or accepted real trust anchor. Real purpose remains
unconditionally refused; assigning REAL_PROFILE cannot enable it. Caller-created
ApprovalProfile/evidence fields and freely constructed VerifiedState objects do
not authenticate authority. A future native caller must revalidate the actual
immutable snapshot against external approval and construct fresh CPU/F32 tensors
under a separately reviewed bridge. Tensor value/layout checks, native imports,
factory execution, inference, installation and release remain outside this proof.

Six original seals and their exact listed payloads are preserved in separate
children. Preparation copies exclude later run directories outside their seals.
The independent root child contains all 28 observed inputs and receipts.
COPY-MANIFEST.json binds every copied member to its original disk path and bytes;
VALIDATION.json records the independently recomputed case/source comparisons.
The outer manifest binds every archive payload. All content is documentary text;
no real model, checkpoint or runtime binary is included or executed here.
