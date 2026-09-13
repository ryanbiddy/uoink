2026-09-13. Astra reviewed the vpr02 valid-guard75/1 failure, exact source repair,
all six new scanner cases and the unchanged launcher. Admit one author vpr03
after verifying proposal03's25 payloads and its ten exact input bindings.

Reader3962d355 adds a structural depth-three bound before JSON parsing, matching
the fixed root/descriptor/array schema. Its byte scan handles quoted strings
and backslash escapes and checks the cooperative deadline every1024 bytes.
The normal parser still rejects invalid syntax, UTF-8 and unmatched structures;
the scan alone is not a complete JSON validator. All76 original assertions stay
unchanged; six new contracts check the boundary, pre-parser rejection, escaped
strings, resumed depth after strings, deadline and excess closing structure.

Use separate admission JSON for label vpr03 and unchanged run-root.ps1. Bind
IG_FORBIDDEN_LIVE before the outer -I -S -B invocation; never access that path.
The generated-input guard, source/hash verification, all actual exit receipts
and prior failures remain required. No real asset, native package, model,
installation, acquisition or inference operation is admitted. If all82 cases
pass, root may repeat the same bytes independently under a fresh label. Any
failure needs preservation and a reviewed repair before another attempt.
