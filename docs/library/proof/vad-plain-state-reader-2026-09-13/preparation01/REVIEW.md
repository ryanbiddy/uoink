Prepared 2026-09-13 for root source review. No proposed reader, harness,
converter or factory has been executed, and no real artifact has been read.
The 76 case IDs in EXPECTED-CASES.json are proposed coverage, not passed tests.

The reader accepts one immutable bytes snapshot under a synthetic profile. It
checks the approved size and SHA256 before reading the header, then requires
the frozen converter's exact 54-key F32 schema, dense offsets and canonical
JSON/padding. The plan-derived header is 4,704 bytes; the complete proposed
encoding is 5,896,708 bytes, including 5,891,996 data bytes. The shape literal
and LSTM expansion match the retained fixed-factory text by static AST review.
Finite binary32 values stay as bytes, including signed zero and subnormals.

ApprovalProfile and its evidence_sha256 field are caller-supplied claims.
They do not authenticate provenance. The reviewed harness supplies authority
only for bytes it generates locally. A caller can also construct VerifiedState
directly; it is an immutable result container, not an authorization capability.
A future native caller must revalidate the snapshot, exact external approval,
schema and checked ranges rather than trust the dataclass type or its fields.

Real purpose is unconditionally rejected before inspecting the supplied
snapshot. Assigning REAL_PROFILE cannot change that branch. There is no actual
converted artifact, accepted real digest, filesystem wrapper, downloader or
model-loading API in this proposal. The historical original-checkpoint digest
is explicitly refused as a synthetic output identity.

The child harness executes only the exact proposed stdlib reader and generated
fixtures. Its guard admits four copied text inputs, denies writes, network,
process creation and new imports, and lexically rejects metadata access under
the live Uoink directory. It verifies its input bytes and wrappers at completion.
The launcher scrubs provider credentials by rebuilding the child environment,
uses C:\Python314\python.exe -I -S -B, and records the actual child exit before
validating guard, case membership and counts. The PowerShell wrapper separately
records the actual outer exit. Neither launcher has been run.

The time budget is cooperative: checks surround bounded parsing and serialization
and occur between 64 KiB hash/scan chunks. It does not preempt an operation already
in progress. JSON allocation is limited by the 32 KiB header cap; the whole input
is capped at 6 MiB and must already be an exact bytes object. There is no claim
that this supplies a process memory limit or a general Safetensors reader.

Two prequalification edits are preserved with their original drafts and diffs:
numeric deadline range validation before math.isfinite, plus exact purpose type;
and established Windows device-prefix handling in the metadata guard. No behavior
assertion was weakened. Source, input bindings and templates were then generated
by a data-only copy/hash/AST preparer. No later reader or harness change occurred.

After root admits a fresh synthetic run, retain every raw result even on failure.
Any repair requires a written reason, preserved before bytes and a fresh label.
Synthetic success would qualify this selected bytes-only contract. It would not
qualify a real checkpoint conversion, Torch tensors, the factory, inference,
native imports, staging, installer, dependency migration or market readiness.
