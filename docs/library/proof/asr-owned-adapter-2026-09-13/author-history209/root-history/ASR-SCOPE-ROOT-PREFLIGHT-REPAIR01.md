2026-09-13. Root preparation verification attempt 2d8c38 exited 1 in
0.2046689 seconds before the diagnostic ran. The generic index verifier accepts
only committed docs/library/proof paths; this preparation is under _scratch.
Its path assertion refused the command. No diagnostic or child ran.

The fresh preflight uses PowerShell to verify the reviewed preparation manifest
hash, all 55 listed payload hashes and lengths, exact file membership and total
bytes in this one known directory. It does not change any sealed source or
weaken a behavior assertion. Diagnostic execution remains a separate action
after that check. Preserve the original failed tool result as a failure.
