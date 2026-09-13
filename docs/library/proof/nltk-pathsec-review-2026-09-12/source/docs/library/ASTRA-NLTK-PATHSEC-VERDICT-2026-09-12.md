# NLTK source backport verdict

Accept the repaired source patch and preparation utility for packaging work.
The installer still contains upstream NLTK 3.10.3. This commit does not change
the lockfile, installed runtime, advisory count or release hold.

The patch routes the six named model-artifact APIs through NLTK's path policy,
validates tagger filename components and removes implicit expansion of allowed
directories. Windows directory creation rechecks the resolved pathname; it does
not pin a Windows directory handle. POSIX tagger writes use a verified directory
descriptor and os.open rather than pathsec.open. Those distinctions correct the
worker's broader claims. No model training, loading or inference was qualified.

Astra rejected ecbf6acd's hash-override option, unchecked Windows receipt forms,
fuzzy patch application and incomplete copied-tree verification. The repaired
utility accepts only the fixed patch hash, exact hunks and all three output
hashes. It checks path ancestors before following probes, rejects device/stream
and drive-relative paths, preserves the complete copied file map and creates
the receipt exclusively inside the new destination. These checks do not prove
immunity to every concurrent filesystem change by another process with the same
user's permissions. The patch's three original source files and upstream licence
are preserved under vendor/nltk-pathsec/original for portable preparation tests.

The worker's 28-case proposal needed test corrections before acceptance: its
supposed archive hash check only checked existence, its parent import assertion
depended on unrelated tests, and its outside-training probe lacked a mock.
All proposed originals are retained. No previously committed test changed.
Fresh child probes now use the matching embedded Python, explicit paths and
audit guards that block network, subprocesses, model imports and the live index.
Serialization and training are intercepted before they execute. An explicit
UOINK_NLTK_BASE_SOURCE can supply pristine upstream source after a later runtime
update, independently of the native runtime used for imports.

Astra's first two corrected worker runs and first checkout run each record
37 passes / zero failures / one Windows symlink-permission skip. Ten new
preparation probes against the archived proposal record eight failures and two
passes. One failure is the newly required full-tree hash facility being absent;
the others expose input, copying or path-probe behavior. Do not describe all
eight as independently demonstrated exploits. The final fixture-path refinement
also has 37 passes / zero failures / one skip in worker03 and checkout02. The worker's own
27/1 result and reported earlier failures remain attributed to its report.

Next, prepare an explicitly versioned local wheel, verify its source/RECORD
mapping and hash, update the installer lock/build provenance and notices, and
qualify the staged runtime and complete candidate tree. Preserve pristine input
for the source tests. The original advisory remains visible alongside any later
backport disposition. Torch/Transformers, signing and Desktop release gates
remain open; this source repair does not clear them.
