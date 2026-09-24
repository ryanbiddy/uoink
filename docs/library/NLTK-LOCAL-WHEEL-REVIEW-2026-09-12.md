# Astra verdict: labelled local NLTK wheel

The wheel is a reviewed packaging proposal, not an installed security repair.
It contains 512 files. Three patched source files, package VERSION, distribution
METADATA and RECORD change; all remaining payload bytes and dependencies match
the verified upstream wheel. The distribution is 3.10.3+uoink.pathsec1.

Control Room a332397f reached its 20-minute print timeout. Its transport returned
zero/completed, but the worker's guarded result is 33 passed / one failed and no
review report was delivered. Keep PARTIAL. Astra preserved that snapshot and
finished the repair in a separate detached worktree to avoid changing the
original provider workspace. No provider terminal-success claim is adopted.

The original compressed wheel has identical payloads but different bytes under
Python 3.13 and 3.14: 488 member compression sizes differ. Fixed timestamps,
explicit Unix modes and ZIP_STORED now produce identical wheels under both
interpreters, even with an unrelated SOURCE_DATE_EPOCH. The local wheel is
6,597,605 bytes, SHA256
969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8.
Inno will compress the installed payload separately. The larger local wheel is
build input, not an increase of that size in the installed library.

The builder hashes and parses one byte snapshot, propagates filesystem errors,
rejects duplicate/case-ambiguous archive and RECORD entries and duplicate
metadata, and preserves bounded working material instead of recursively deleting
a computed temporary path. It never imports NLTK; a caller's unrelated imports
do not determine whether input validation runs. Path checks do not claim general
protection against every concurrent process with the same user's rights.

Nine new controls against the preserved builder record seven failures and two
passes. Astra worker01 records 41 passes / two failures: one changed error string
and a new probe patched Path.lstat although the code calls os.lstat. The repaired
message and corrected mock receiver retain the same refusal assertion. Corrected
original02 still records seven failures / two passes. Worker02 passes all 43
cases. The sole global-import test now observes a fresh child; the unaccepted
compressed golden hash/size is replaced by the independently verified stored
wheel hash/size. The 512-member, exact source/metadata and RECORD assertions stay.
All earlier tests/artifacts/results are preserved. No committed test was edited.

Checkout verification passes the same 43 cases after raw diff / three-way
integration: worker 12.04 s, checkout 11.72 s, no failures or skips. Before installer
use, bind this exact wheel in build.ps1, update the lock and notices, run the full
combined candidate and collect the new installed receipts. The raw advisory
remains visible; model qualification and release decisions retain Ryan's gates.
