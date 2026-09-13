# Static inventory reader: synthetic qualification verdict

The corrected reader passed its 36 synthetic cases under isolated stdlib
startup. It is ready for the integrator's exact-source review before one
allowlisted static inventory. This is a parser qualification, not approval of
the default VAD loader, a model-stack migration, or the release.

The reader SHA256 is
`15125eebf629e014a20a200f19a3bc627363170a0375c2d49eaf6ed7e7bfb7d7`.
The actual checkpoint has not been opened, hashed, sized, decompressed, or
parsed by this subagent. Reader `main` and `inspect` were replaced by refusal
stubs during qualification, and an audit hook blocked the checkpoint open.

| Attempt | Passed | Failed | Real process exit | Scope |
|---|---:|---:|---:|---|
| static-preflight01 | 31 | 2 | 1 | First draft; retained failed result |
| static-preflight02 | 36 | 0 | 0 | Corrected reader and documented setup |

Both used the existing `_scratch/ig-native/Scripts/python.exe` with `-I -S -B`.
Each attempt preserves the exact source/setup, stdout, stderr and actual exit.
The original brief and reader are in `draft01` with their first-draft hashes.
The repair brief predates the corrected source and run; exact diffs are in
`static-preflight02`.

The first failure involved synthetic setup: Windows ZipFile normalized a
backslash before the reader saw it. The repaired setup injects the unsafe
filename into the raw local and central headers, preserving the refusal
assertion. The second failure was a reader defect: a declared short deflate
output could conceal additional inflated bytes. The reader now bounds direct
stdlib zlib output and requires exact size, completed stream, no compressed
tail and matching CRC. It also scans the actual bounded central directory
before ZipFile allocates entries. The failed result remains failed.

The corrected cases cover stored/deflated pickle metadata, ZIP64 end records,
literal GLOBAL reporting without resolution, ambiguous/missing pickle members,
unsafe/duplicate/symlink names, encrypted or unsupported archive features,
split archives, actual and advertised directory bounds, member and pickle
size limits, header conflicts, nested overlapping member extents, malformed
or trailing pickle bytes, unsupported protocol, concealed deflate output,
stored payload size and payload CRC. All input containers are small and in
memory; no pickle was deserialized or executed.

The remaining boundaries are explicit. File and path checks detect observed
changes, but require quiescent staging and do not create an atomic snapshot
against a hostile concurrent writer. The deadline is cooperative. Inventory
does not establish complete ZIP/pickle semantics, provenance, tensor shapes,
checkpoint architecture, compatible fixed classes, native behavior, model
quality, conversion viability, or loading safety. Literal class tokens cannot
be promoted into a loader allowlist without a separate reviewed proposal.

The integrator may review this exact reader and run the authorized static
inspection using `-I -S -B`, a fresh run ID and independent shell-exit capture.
Any refusal remains a refusal; there is no format conversion, fallback load,
download or automatic retry. No product/frozen-test edit, provider action,
model execution, diarization, installation, network, staging, commit or push
was performed for this task.
