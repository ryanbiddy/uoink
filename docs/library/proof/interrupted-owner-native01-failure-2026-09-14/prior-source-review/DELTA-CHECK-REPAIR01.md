# Passive diff-check correction

The first text-only reconstruction check, actual 8367bf (exit 1), refused an empty line in dummy_bootstrap.diff. No candidate was run or changed. Diagnostic 66d2bb (exit 0) found exactly one empty line, line 164, after the final hunk's three context lines. The frozen diff and source remain unchanged.

The next separately recorded check permits only that terminal empty line, and only after the final hunk's declared old/new counts have been consumed. All hunk offsets, original/context lines, counts and reconstructed new lines remain exact. This corrects the review instrument's treatment of a trailing separator; it does not change candidate assertions or represent a subject failure or rerun.
