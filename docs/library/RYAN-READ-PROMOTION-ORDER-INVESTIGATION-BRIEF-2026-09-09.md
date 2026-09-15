# Read promotion: ordered failure investigation — 2026-09-09

Complete checkpoint 8fc6a40 has 2,254 passed / ten failed / three skipped /
one xfailed, 573.49 seconds. The additional failure is
tests/test_existing_index_read_open.py::test_read_open_does_not_migrate_then_explicit_backend_promotes:
the ordinary getter returns a different Index object. The same new file passed
in the focused read union and the isolation integration union. All previous
cases remain present, and the original nine failures stay failed.

Astra will reproduce the ordering with the unchanged discovery-route fixture
followed by the new read-opening file. Legacy route tests assign server._get_index
directly; determine whether that callable remains substituted when the new test
expects production promotion. Preserve exact functions, source locations and
both observations. No fixture or behavior assertion changes are authorized by
this brief. Do not add production behavior whose only purpose is to detect or
undo a test monkeypatch.

If the original production path fails in a fresh process, repair that path and
add an independently bounded regression. If an un-restored test substitution is
the cause, retain the failed full-tree result and document a precise proposed
setup correction and assertion-preservation audit. No edit or waiver is inferred
from the diagnosis. Existing restrictions, native runtime and guards apply.
