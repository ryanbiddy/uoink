# Fixed converter passes independent synthetic checks

2026-09-13. Accept the converter's synthetic qualification in
`proof/vad-fixed-converter-synthetic02-2026-09-13`. Author and Astra each pass
the same 82 cases with zero failures, unchanged inputs, empty stderr and no
unexpected audit events. Author time is 2.147786 seconds; Astra time is
2.195469 seconds. Native, qualification and root outer exits are 0. The
separate final source reviewer found no remaining actionable issue within
this scope. All 81 proof payloads match disk and Git before this commit.

Astra read the complete converter, ZIP parser, harness and launcher before
executing the exact five copied inputs under isolated, no-site, no-bytecode
Python. The checks exercise all 54 tensor entries and 23 storage groups,
including 32 distinct ranges in shared storage 16, both fixed buffers, finite
edge bit patterns, opaque malicious pickle text, CRCs, archive extents,
unsupported forms, malformed metadata and resource bounds. The generated
output contains 5,891,996 dense F32 data bytes with deterministic headers and
unchanged selected bit patterns. No pickle is interpreted or model constructed.

The first two author attempts remain startup refusals, each native exit 1
with no cases run. Their import-loader and lazy-codec setup repairs are
documented, and all drafts and receipts remain. Behavior assertions and
converter bytes were unchanged across those three executions. Earlier
ancestor-path and whole-wrapper deadline repairs preceded qualification.

The real profile remains absent and its entry point refuses before file
access. Synthetic qualification does not establish original byte order,
archive-version bytes, historical numerical equivalence or native reader
compatibility. The dormant wrapper assumes quiescent owned directories;
its path checks and cooperative timeout do not protect against every hostile
concurrent Windows path change or interrupt a blocking filesystem call.

Next: review a fixed-buffer consistency basis for byte order, prepare the
exact profile and migration protocol, then resolve the reserved model/runtime
decision before actual conversion. The historical model notice, trusted new
artifact identity, factory bridge, native numerical checks and installation
remain open. No production source, model artifact or installed runtime changed.
Website and marketing remain held.

The first proof-copy verification failed with actual exit 1: its 75-record
manifest omitted VERIFICATION.json, which had been written after sealing.
No test was rerun. Proof02 retains the complete original directory and its
manifest as payload, plus the written documentary repair. Its 81-record
manifest covers every file except itself. The first rejected root copy is
preserved unchanged at _scratch/astra-vad-converter-rejected-copy01. The
original failed verification is not a converter failure or a passing seal.