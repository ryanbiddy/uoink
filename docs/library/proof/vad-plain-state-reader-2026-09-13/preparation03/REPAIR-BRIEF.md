2026-09-13. Root classified vpr02's 75-pass/1-fail result as a reader robustness
contract defect. The 2,000-level JSON reached parsing and was refused later by
the fixed schema check. Keep that valid-guard failure, all actual exits 1 and
the unchanged 76 assertions. Do not replace its result with a passing label.

Add an explicit structural nesting limit before json.loads. The exact accepted
format requires depth three: the root object, one tensor descriptor object,
and its shape or offset array. Set MAX_JSON_DEPTH to 3. No accepted converter
header needs a fourth container, and the reader admits no schema extensions.

Scan the already size/hash-approved, 32-KiB-bounded header bytes without decoding
or allocating a parsed tree. Count ASCII braces and brackets only outside JSON
strings; recognize backslash escapes so escaped quotes and punctuation do not
change structural depth. Refuse excessive depth or unmatched closing structure
as malformed JSON. The normal JSON parser still validates syntax, UTF-8,
duplicates and numbers after this independent bound. Keep deadline checks before,
during and after the scan. Do not change interpreter recursion settings.

Preserve the earlier reader and harness bytes before editing. Keep all original
76 case bodies and IDs exactly unchanged. Add six isolated cases for the exact
depth-three boundary, depth-four refusal before json.loads, ignored punctuation
and escaped strings, depth after an escaped string, scanner deadline refusal,
and unmatched closing structure. The existing deep-nesting case stays unchanged.

Update source/input bindings and a false vpr03 admission template in this fresh
directory. Send the exact source diff and complete harness before any execution.
No real artifact, runtime, dependency, product, frozen test or installer change
is authorized. Synthetic profiles and result dataclasses remain caller claims;
real purpose remains unconditionally refused.
