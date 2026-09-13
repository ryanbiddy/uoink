# Exact B3 expectations before synthetic qualification

The independent reviewer agreed the design before execution: bind original and
patched utils, preserve B2 transcribe bytes, enumerate both repairs in NOTICE,
bind all output members/RECORD, and keep packaging format and unrelated metadata.
On review of the original 62-case protocol, the reviewer requested explicit
utils recipe equality in addition to adding utils to the approved changed set.
That assertion is included in the new exact-output case; no test has run yet.

The inherited protocol has exactly two textual adaptations, recorded in
`retained62-expectation.patch.txt`: the changed-member setup set gains utils.py,
and the version.py assertion expects `1.2.1+uoink.localassets2`. Every other
inherited assertion is unchanged. The six new cases are separate functions
attached to the same TransformContracts class, preserving the original test IDs.
The explicit new utils byte-equality assertion supplements fixed hash checks.

The five recipe files are B2.py.txt (unchanged source), utils.py.txt (reviewed
one-line repair), NOTICE.txt, patch.txt (the two source diffs concatenated),
and member-manifest.json. RECORD is derived from the identities of all 15 other
members, with an empty self row. Its asset identity is inherited without reading
the model. The builder retains ZIP_STORED, fixed timestamp, order, permissions,
WHEEL generator, upstream wheel identity and all existing archive/path limits.

The synthetic runner adds only the new label and denies existing B2 real-wheel
and private-runtime directories in addition to the previous guard restrictions.
Its placeholder asset cannot match the fixed real member manifest; the inherited
negative test must continue to demonstrate that rejection. No actual wheel read,
build or package/model import is authorized by this design note.
