# Native package-08 fixture bootstrap repair, 2026-09-12

The native-gui01 attempt failed before launching Uoink. The new synthetic media
seed ran with Python safe-path enabled, but did not add the verified installed
application directory to sys.path. Importing index therefore raised
ModuleNotFoundError. No fixture file or index write preceded that import. The
owned seed job is empty and its interpreter guard restored. Preserve the failed
result, stderr and original launcher/instruments; it has no GUI credit.

Prepare a fresh native-gui02 profile with the unchanged P4 preparer. A new seed
copy adds only the explicit installed app path immediately before import, then
retains its existing exact index-module path assertion. Installed eligibility,
package hashes, interpreter identity, index/output paths, guard canary, no-model
scope, synthetic data and behavior checks remain unchanged. No existing
acceptance fixture, test or production code is edited. Use new driver, seed and
launcher filenames; do not overwrite the failed attempt or any sealed instrument.

Astra reviews the exact diffs and Python syntax before launch, then repeats only
the unobserved native operation. The GUI must actually display the saved 0:34
cue and identify the untimed line without inventing an offset; save/read a new
synthetic note and inspect its type and readiness. Retain any further failure
before another diagnosis. Never launch Claude Desktop through its invalid
override, contact port 5179, access the live index, fetch media or use a paid API.
