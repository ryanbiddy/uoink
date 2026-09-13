# Optional Hub keyword repair: root verdict

Root accepts the one-line inert source repair for its narrow forwarding contract.
Author and root each reproduce four passed/four TypeError errors on the unchanged
baseline, then eight passed with zero errors, failures or skips on the patch.
Actual child exits are one and zero; both corrected guards are valid and input
hashes remain unchanged. The root comparison wrapper exits zero because those
recorded outcomes match its declared checks; that does not turn the baseline
child's failure into a pass.

The proposed utils.py removes only the obsolete local_dir_use_symlinks keyword.
Its 4,897 bytes have SHA256
ecec29ad34688e2d559218685672c3c2f1086f524d78bcfd53e633a5739d5b19.
The helper still forwards local-only policy, destination, revision, cache and
token arguments to a fake callable bound to the captured candidate Hub signature.
No Hub implementation, package, model, fetch or real wheel build ran here.

All original invalid-guard attempts and the insufficient compile-filename repair
remain preserved. A path-only diagnostic reproduced denied lexical <unknown>
reads during failure formatting. The corrected unittest formatter records raw
frames and exception type/message without source lookup; all eight assertion
bodies and file allowlists remain unchanged. Read review97/VERDICT.md for the
six earlier outcomes and their limits.

This proposal is separate from the reproducible, uninstalled B2 wheel. The next
combined derivative is localassets2; its source, recipe and packaging require
their own review and qualification. Runtime, installation and market acceptance
remain open. Production source and the full-tree result are unchanged.
