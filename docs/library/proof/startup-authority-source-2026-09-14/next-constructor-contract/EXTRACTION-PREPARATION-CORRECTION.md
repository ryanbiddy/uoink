The first documentary excerpt assembly (SOURCE-EXCERPTS-READ07-ACTUAL.json) exited 0 but flattened the single nested PowerShell ranges for the guard and adapter, producing invalid reversed excerpts. It is retained as an invalid preparation result and is not used by the contract.

The replacement used explicit start:end strings and checked range bounds. It exited 1 in SOURCE-EXCERPTS-READ08-ACTUAL.json (chunk 721b77): the requested factory endpoint 321 exceeded the file's 319 complete lines. EXTRACTION-ERROR-READ09-ACTUAL.json and EXCERPT-RANGE-DIAGNOSIS10-ACTUAL.json preserve the diagnosis. The corrected factory range is 306–319.

SOURCE-EXCERPTS-READ11-ACTUAL.json (91493f, exit 0) produced the selected SOURCE-EXCERPTS.json and SOURCE-BINDINGS.json from unchanged source hashes. These are documentary extraction corrections only; no candidate, native operation or test was run, and no product input was changed.
