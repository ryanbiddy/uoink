# Installed package-06 seal input repair

The first export attempt exited one at copy(a.summary, summary.json): the
command supplied `_scratch/installed06-reviewed-summary.json` as a relative
Path, while the copy guard correctly requires a path beneath one of its
absolute approved roots. The serializer had already copied the selected
receipt files; it had not copied the summary, scanned exported bytes for
disposable bearer tokens, or written SHA256.json. That partial export is not
a completed seal. Product observations are unaffected.

Preserve the partial directory at `_scratch/installed06-seal-failed01` after
checking the resolved source and destination remain under this checkout and
contain no reparse entries. Retain the first command, tool-returned failure,
instrument hash and partial-file hashes. Do not delete or overwrite it.

The repair is the invocation: pass the existing summary by its absolute path
under this checkout's `_scratch` directory. Keep the serializer and path guard
unchanged. After preserving attempt one, run the export into its now-fresh
intended proof directory. Require all copy checks, the disposable bearer-token
exclusion scan and final payload hashes. Record this second export separately.

Astra verdict: this is an export-input correction, with no change to installed
bytes, receipt observations, tests or assertions. No source retest, model call,
installation rerun or rebuild follows from it. Earlier raw failures and the
collector's incomplete client credit remain unchanged.
