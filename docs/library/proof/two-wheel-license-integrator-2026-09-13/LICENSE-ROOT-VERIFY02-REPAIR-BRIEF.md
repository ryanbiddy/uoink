# Root notice verification repair — 2026-09-13

Root verifier01 failed in actual tool bdc441, exit1, at its ANTLR root-tree
comparison. Preserve that source and result. The saved GitHub tree request
uses the immutable commit ID; the response sha echoes that requested commit,
whereas the separately saved commit object names tree
f79be338c3ed514d258f7d54e59eaac09a320c49. The earlier equality assumed those
different identifiers would be the same. No notice or captured response changes.

Verifier02 keeps the requested-commit comparison and additionally reconstructs
the canonical Git tree object from the complete nonrecursive saved root entries.
It checks ASCII single-component names, unique Git ordering, allowed modes and
20-byte object identifiers, then compares the computed tree hash to the commit's
tree ID. All earlier payload, response, blob, member and downstream-tree checks
stay intact. This is a documentary verifier repair, not an acceptance-test edit.
One fresh verification is planned; it performs no fetch, artifact read, installed
code execution or package operation. Any remaining failure stays failed.
