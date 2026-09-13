2026-09-13. Inspection01 refused the first hash-pinned cached ANTLR wheel with
Unexpected package root. It accepted zero whole-wheel results; the native and
recorded launcher exits are 2, while the surrounding tool reports exit 1.
Preserve the preparation, refusal receipt and actual tool result unchanged.

This separate diagnostic reads only the same 144,613-byte wheel with its exact
historical SHA256, then lists ZIP directory member names outside the two
expected roots. It does not read member payloads, extract, import, execute,
rebuild, fetch or repeat the complete inspection. Names are bounded to 512
characters and the directory to 1,000 entries. Retain the exact tool output.
The finding must be reviewed before changing any package whitelist.
