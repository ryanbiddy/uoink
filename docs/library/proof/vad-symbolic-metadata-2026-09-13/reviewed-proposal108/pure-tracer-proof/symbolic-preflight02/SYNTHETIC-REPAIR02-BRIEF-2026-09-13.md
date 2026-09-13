# Missing-MARK synthetic setup repair

`symbolic-preflight01` remains failed: 56 passed, 1 failed, actual reader
exit 1. Its source, harness, raw result and launcher receipt are preserved
in that attempt directory. The tracer source is unchanged at SHA256
`f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127`.

The new `missing_mark` case used `document(b']e')`. The document helper
creates a root-dictionary MARK. APPENDS therefore consumed that existing
MARK and correctly refused the resulting dictionary sequence target. The
test did not reach the intended missing-MARK branch.

Replace only that input with `b'\x80\x02]e.'`: initial PROTO 2, EMPTY_LIST,
APPENDS and STOP, with no MARK anywhere. Keep the expected `MARK missing`
assertion and every other case unchanged. This is a new synthetic setup
correction, not a tracer or product defect. Run the same 57 cases under the
fresh `symbolic-preflight02` label, preserving an exact before/after diff.
No checkpoint, artifact adapter, model or product execution is introduced.
