Prepared 2026-09-13; no proposal03 reader or harness execution has occurred.
The source repair is limited to a depth-three constant, a bounded byte scanner
and one scanner call before JSON decoding. The exact converter schema is
three containers deep at most: root object, tensor object, shape/offset array.
No supported converter output requires an additional level.

The scanner treats structural punctuation only outside quoted strings and
handles each backslash escape before considering the following byte. UTF-8
decoding, quote/escape validity, matching bracket types, duplicate keys and
number validation remain the JSON parser's responsibility. The scanner supplies
an independent allocation-depth bound, not a second general JSON parser. It
checks the existing cooperative deadline at entry, every 1,024 bytes and exit.

All original 76 assertions and case IDs are unchanged by complete AST comparison
after removing only six new case functions. Those additions cover depth three,
depth four before json.loads, punctuation/quotes/backslashes inside strings,
depth after an escaped string, a mid-scan deadline and unmatched closings.
The prospective union is 82 cases; none is counted passed here.

The reader still checks explicit synthetic profile, exact immutable bytes,
size and SHA256 before header interpretation. All 54 names/shapes, F32 bits,
dense offsets, canonical encoding, immutable descriptors and deadline limits
remain unchanged. Real purpose is unconditionally refused. Assigning a profile
or constructing a VerifiedState does not authenticate provenance; the reviewed
harness controls generated data, and a future native caller must revalidate.

Preserve vpr01 as a setup failure with zero cases and vpr02 as a valid-guard
75-pass/1-fail measurement. Their raw exits are all 1. Earlier seals remain:
preparation01 d2bf7531d5f89a50d80d7260e993954b81a56e4c6fa4457d08c770b8c728a0bf;
vpr01 failure 89b90577f401955b4faa0d440118632b2b0cb2e4e7a1a976a702c85d7cbc008b;
preparation02 6c79c477cec73ca3b104ab9e8917ce96166328474ab7373a86cb3fba22a72b8a;
vpr02 failure 771a592fe81078a18285253ddde50651ed54449dfab3202a00fadf659657c7dc.

The inherited launchers and their four-file child read scope are unchanged.
INPUTS.json and the false vpr03 admission template bind the repaired bytes and
82 exact IDs. Root must review the source delta and full new cases before any
execution. No actual artifact, native import, factory, inference, installation,
dependency migration or release acceptance is implied.
