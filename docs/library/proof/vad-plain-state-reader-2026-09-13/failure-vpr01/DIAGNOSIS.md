2026-09-13: vpr01 is an unqualified setup failure, not a reader test failure or
a passing measurement. Actual child exit, launcher/outer exit and invoking
PowerShell exit were all 1. No case function ran: the failure occurred while
constructing the parameter registry before the case execution loop.

The child stderr identifies qualify_reader.py line 263:
`'{}'.encode('utf-16-le')`. Python lazily imports encodings.utf_16_le to perform
that fixture encoding. The reviewed guard allowed only modules loaded before
its installation; this codec was not preloaded, so it correctly refused the
new import. This is fixture construction, not interpretation of supplied model
data. The reader module had been defined, but verify_bytes was not invoked.

The child emitted no JSON report. The launcher saved actual-exit.json with the
real child exit 1 before attempting to parse stdout. That parse then raised
JSONDecodeError; its traceback is preserved in the outer stderr. The missing
guard summary cannot be treated as a valid guard receipt. The child traceback
does preserve the precise denied event: import:encodings.utf_16_le.

Proposed minimal setup repair for separate root review: replace the computed
fixture expression with the exact UTF-16LE literal b'{\x00}\x00'. This keeps
the generated fixture bytes and all 76 behavior assertions unchanged while
removing the lazy codec import. It does not require a broader import allowlist.
No repair has been applied and no second run has been launched.

The original 26-payload manifest d2bf7531d5f89a50d80d7260e993954b81a56e4c6fa4457d08c770b8c728a0bf
and its payloads remain immutable. Execution directories and this failure
diagnosis are separate additions. The raw run, actual exits, exact copied
inputs, admission and outer logs will be sealed separately from preparation.
