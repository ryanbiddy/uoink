2026-09-13. Before any qualification, root reviewed the first patch and required
every load parameter to be bound to the trusted runtime profile. The first draft
left GPU/default compute, device index, threads and task selection available
after checking only the model path and VAD. Preserve that draft under
drafts/root-review01 and add assert_load_parameters before construction. Remove
the default compute-selection branch. This is a source correction, not a test
rerun or an accepted runtime outcome.

Root separately authorized the proposed local version 3.8.6+uoink.owned1 and an
owned explicit-whitelist recipe. The original MANIFEST.in body is unavailable;
the new recipe must not guess or inherit its contents. All 16 Python source
files, LICENSE, README and pyproject are now matched by exact bytes, Git blob
IDs and size to the already captured complete release tree. The earlier
SOURCE-BINDINGS wording describes their original capture provenance; the later
RELEASE-BLOB-BINDINGS and ADDITIONAL-RELEASE-BINDINGS add release identity.

Two initial reporting commands were imperfect: a read-only PowerShell inventory
had an empty-pipe ParserError (tool 9a69cc, exit 1), corrected by assigning its
rows before serialization (e20634, exit 0). The first copy summary printed null
total_bytes because Measure-Object did not project OrderedDictionary values;
the exact 15-file JSON binding measured 110,814 bytes (618dff, exit 0). No source
execution or test ran. The first diff used absolute paths and emitted Git
line-ending warnings; preserve it and generate the final relative-path diff
with core.autocrlf=false. Before-file bytes remain unchanged.
