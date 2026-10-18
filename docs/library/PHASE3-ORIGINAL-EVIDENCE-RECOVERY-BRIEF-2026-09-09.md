# Phase 3: recover original retained evidence

Integrator: Astra. Base `a74385c`. This is a recovery of existing synthetic
observations, not a new S21 run. Existing tests and historical measurements
remain unchanged. Parent authority is section 1 of the corrected-tree product
brief and Ryan's instruction to continue through release readiness.

The original AT6 root still holds all eight hash-matching artifacts. Copy the
four absent archive entries byte-for-byte into an explicitly named original
artifact archive. Preserve the original receipt and its hash. The original
held-browser root for feed 64703 has a separate receipt/database on `6d9a819`,
so archive that pair under its actual source SHA, without repeating the older
filename's misleading `1830b7a` association. Verify every available artifact
hash and retain actual mismatches if any.

For the C21 pill image on feed 49557, preserve the original fixture database,
WAL and shared-memory bytes and their before/after hashes. Refuse recovery if
its recorded process is still the same live process or bytes change during
copy. Open only the copied database; produce a closed SQLite backup as a
derived recovery artifact. Retain the original launch log, recorded incarnation
and relevant synthetic sidecars. Compare persisted consent, two enrolled items,
one charged successful capture and its waiting-for-client work state with the
archived image. Label the new JSON as a 2026-09-09 recovery receipt, with no
claim of a contemporaneous exit record, new browser run or original backup.

The retained Claude tool record contains AT6's original shell invocation and
completion output. Extract only that task-specific invocation/result and bind
the projection to its record IDs and source hashes; never archive unrelated
conversation or credentials. Its S21 pipeline used grep and did not record
the Python child's exit status. Do not add an inferred zero exit to the AT6
receipt. Unless an independent actual exit record is found, that test remains
failed. Later successful process probes do not supply the missing child status.

Preserve each recovery's provenance, limits and original bytes, then update
the S21 archive manifest and force-add ignored logs/databases as required.
Review archive hashes and read-only integrity/foreign-key checks before running
the unchanged `test_phase3_acceptance7.py`, `test_phase3_acceptance8.py` and
`test_phase3_acceptance9.py` together through the isolated integrator runner.
Record actual results with the committed recovery SHA. No S21 execution,
network request, live index, port 5179, model process or paid API is permitted.
