# Exact local NLTK metadata accepted for dependency review

2026-09-13. The admitted metadata read passed. Actual tool 0940dd exited zero
in 0.5194125 seconds; the reader took 0.021822099981363863 seconds. Reader,
native and outer exits are zero, stderr is empty, all eleven bound inputs are
unchanged and no guard denial occurred. Root reviewed the complete receipt,
actual tool object and current input hashes in 10b613, exit zero.

The reader hashed the exact previously built wheel before parsing its archive:
6,597,605 bytes, SHA-256
969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8.
Its 512 stored members and 512 RECORD rows satisfy the reviewed layout rules.
Only METADATA and RECORD contents were interpreted. Other members' individual
RECORD digests were not recomputed; this invocation verifies the whole-file
digest and the selected METADATA digest. No wheel member was imported or installed.

The retained METADATA is 3,245 bytes, SHA-256
58ba0717917015b5fd7a2416d52d2ab7952eacfddcbe22797cbb566fba864234.
It is the exact upstream text with only Version changed to
3.10.3+uoink.pathsec1. Name, Python requirement, dependencies and extras match;
Requires-Python remains >=3.10. The graph may admit these bytes through an
explicit local artifact record. It must retain origin owned-built-wheel,
null URL and no public local-version release claim. A later graph using retained
text must report that it did not itself verify the wheel artifact.

Root read the final reader, launcher and protocol before admission. The source
draft, pre-execution refinements, admission, raw logs and actual result remain
in the 23-payload proof, totaling 117,071 bytes. Documentary sealing efd510
returned zero and executed no tests or artifact reads. Seal:
ee428799befd7b04c68f5de81a7eab287d1102bc86fb6e5993d22d8661e6df08.

This closes the exact local NLTK metadata input gap. It does not establish a
compatible complete graph, absence of advisories, native runtime behavior,
installation success or market readiness. The previous failed graph and its
unrelated missing-wheel conditions remain unchanged.
