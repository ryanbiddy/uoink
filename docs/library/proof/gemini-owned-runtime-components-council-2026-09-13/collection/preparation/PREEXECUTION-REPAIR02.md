2026-09-13. Root reviewed the unexecuted documentary collector d2fb3084 and
launcher 8c0a60d9. Their exact bytes and original PINS are preserved under
before-review02. No collection or Git intent-to-add has run.

The first draft incorrectly assumed one proof-manifest shape. Use the exact
existing forms per folder: lifecycle SHA256-MANIFEST.json has count/files;
WhisperX SHA256.json is the row array itself; CPU and factory SHA256.json use
payload_count/files. All row uniqueness, size/hash and frozen-byte checks stay
required. This corrects the collector's interpretation of existing evidence;
it does not change that evidence or any product measurement.

The launcher must durably preserve the actual native exit immediately after
child return, before hashing or parsing any output. Add a fixed CreateNew
FileStream write and Flush(true) for native-exit.raw.txt, then run the existing
postchecks. An unavailable exit is written as null and remains a failure. This
prevents a postcheck exception from losing the already observed native result.

The final archive also includes these unexecuted drafts, repair note, and
PINS. No new test suite is warranted for this documentary format correction.
Root will review the exact delta before the single collection attempt.
