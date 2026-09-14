The first notes staging helper stopped at its final worker-before byte comparison
(798ce0/1) without writing either notes file. Diagnosis d1e7d0/0 proves the clean
worker checkout differs only by UTF-8 CRLF conversion: candidate51,896 bytes at
957db525, worker52,645 bytes at29409858. The complete declared three edits and
final paragraph reconstruction had already matched the proposed bytes.

Preserve that helper and actual. The separate02 helper changes only the worker
before guard: bind its observed SHA256 and verify valid UTF-8 and normalized
text equality before copying the already reviewed proposal into the worker.
Canonical notes still change only through the later raw Git diff/apply.
This is a documentary transport preparation repair, not a subject test rerun.
