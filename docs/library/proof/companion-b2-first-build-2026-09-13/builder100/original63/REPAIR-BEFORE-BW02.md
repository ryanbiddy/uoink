# Synthetic ZIP filename fixture correction — 2026-09-13

`bw01` ran 62 cases: 61 passed, 1 failed, 0 errors, 0 skips; actual child and
launcher exit 1. Guards remained active with no violations. The failure was
`test_member_backslash_refused`: Windows ZipInfo converted the supplied backslash
to a slash while constructing the synthetic archive. The parser therefore
received the existing permitted `faster_whisper/audio.py` name and correctly
accepted it. The fixture had not represented its named boundary.

Preserve this run and its exact builder/test bytes under
`bw01-before-fixture-repair`. The correction changes only synthetic ZIP setup:
after serialization, replace the same-length filename in the local and central
headers with an actual backslash. Keep member data and RECORD bytes unchanged.
The original ValueError assertion and all other behavior assertions stay as
written. No production/accepted fixture or builder source changes are needed.

Run the corrected 62-case protocol as fresh `bw02`, retaining the actual bw01
failure. This is not a real wheel rerun or model test. The earlier bounded-read
source-review correction already passed its growing-input and identity tests
in bw01; its before/diff/reason remain separate.
