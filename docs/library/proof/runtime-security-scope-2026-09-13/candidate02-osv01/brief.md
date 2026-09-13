# Query OSV for the uninstalled candidate

Query public OSV metadata for exactly the 144 selected package versions in
`runtime-candidate02-metadata/selection.json`. Preserve that selection's original
bytes and SHA-256. Add one explicitly separate comparison query for upstream
NLTK 3.10.3. The selected local NLTK 3.10.3+uoink.pathsec1 has no corresponding
PyPI release record; an empty OSV response for that local version does not prove
the reviewed local patch or its model-loading paths are safe.

Use only the free OSV querybatch endpoint and full advisory records, following
every returned pagination token. Preserve the exact request body, response body,
HTTP metadata, UTC start/end times and SHA-256 for every attempt. Record HTTP,
transport, parsing and pagination failures honestly; do not silently retry or
turn a partial query into a clean result. The first output directory is
`runtime-candidate02-osv01`, which must not already exist. Retain the executed
collector source and this brief there, then seal all evidence bytes.

Count raw returned advisory entries separately from alias-connected groups.
Retain each id, alias, affected package/range, withdrawal and publication/update
field from full records. Do not suppress duplicate aliases, known upstream
metadata disagreements or a withdrawn record from the raw count. Missing full
records leave grouping and interpretation explicitly incomplete.

Keep the original installed/current-stack audit unchanged at 19 entries and
15 alias groups. The new report covers proposed versions only; it does not
establish resolver compatibility, package availability, binary contents, safe
model deserialization, test success or release readiness. No wheels, models,
binaries, media, paid API, installation, product execution, product/accepted-test
edits, live index, port 5179, website work, push or commit is authorized.
