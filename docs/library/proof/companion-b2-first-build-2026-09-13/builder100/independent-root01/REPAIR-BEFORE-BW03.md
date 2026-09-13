# Validate the original ZIP filename — 2026-09-13

`bw02` ran the corrected raw-name fixture and still recorded 61 passed, 1 failed,
0 errors, 0 skips; actual exit 1. The same backslash rejection assertion failed.
The fixture now contains backslashes in both local and central filename fields,
so this result is a product defect in the candidate builder.

Python 3.14's ZipInfo also normalizes filenames when reading. Its `orig_filename`
retains the original archive spelling; the utility had validated only the
normalized `filename`. Validate orig_filename first and reject any normalization
change before using filename for membership or RECORD comparison. This rejects
backslashes and other ambiguous original spellings without changing the allowed
member set. The original-name behavior was confirmed by reading the local
Python zipfile source; no dependency or actual wheel was executed.

Preserve the bw02 source, unchanged 62-case protocol, guard and launcher under
`bw02-before-parser-repair`. Apply only the original-name parser check. Extend
the launcher/harness allowed labels to `bw03` and require this repair brief;
keep the guards and all 62 behavior assertions unchanged. Run fresh bw03 and
retain both earlier failures. The bw01 fixture diagnosis remains correct for
the generated input; its initial conclusion did not establish raw-name safety.
