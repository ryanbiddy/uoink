# Owned WhisperX packaging verdict — 2026-09-13

The exact `whisperx==3.8.6+uoink.owned1` source wheel passed both the admitted
build/verifier command and root's separate check of the actual wheel bytes.
It is 134,793 bytes, with 22 members and 22 RECORD rows. SHA-256:
`0c23ec175b663eaafe9955ff93b1ccc6e93ed66a61665951baac5799a75c92d4`.

Author tool 405e18 returned zero in 0.9920558 seconds. Both native phases
returned zero, with empty stderr and valid guards. The 46 source inputs, 5
instruments and 34 private runtime files were unchanged. Root tool 6edd74 then
returned zero in 0.1685168 seconds, using the exact manual-layout verifier's
`verify_bytes` function on the actual wheel. Root confirmed all member/RECORD
payloads and the complete byte layout, rechecked 46 source and 5 instrument
files, compared 34 runtime identity rows to the original plan, and recorded
64 bound files unchanged. Root did not read any runtime binary.

This is a source-only distribution and packaging verdict. No wheel member was
imported, nothing was installed or resolved, and no model or native ML runtime
ran. The unavailable `_RUNTIME` gate, asset authority, waveform decoder, filter
banks, factory/session controls and compatible CPU runtime qualification remain
open. Package metadata changes do not establish an installed dependency graph.
The prior 50-case author and root results remain separate inert contract evidence,
not additional tests executed by this build.

This bundle retains exact launcher/guard/recipe source, all raw author build
receipts and both root verifier inputs, the unused copy-preparer draft and its
defect note, and the original 217-payload source/contract manifest. The generated
wheel remains at its original scratch path; its bytes and runtime/model binaries
are excluded from this documentary bundle. The first host-path failure remains
in the referenced source/contract seal.

BUILD-REPORT-AUTHOR.md and SOURCE-COPY-MAP.json preserve the earlier state when
root verification was pending. They are unchanged historical records. The root
receipt and this verdict complete the packaging evidence without rewriting them.
