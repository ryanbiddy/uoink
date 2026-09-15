# Approved test corrections: integration verdict

The two exact patches Ryan approved are applied. The mirror group has **180
passed, zero failed**, 125.43 seconds. The ordered discovery/read/resource/prompt
group has **74 passed, zero failed**, 13.53 seconds. These focused observations
close all nine previously reproduced setup failures in their named groups. The
complete committed tree still needs a fresh observation; its historical 13-failure
result remains unchanged.

The applied four-file diff contains 14 insertions and 12 deletions. All **163
assertion syntax trees** and original test function names match parent 721f125.
No product code, expected value, parameter, timeout, skip or xfail changed.
Proof: proof/ryan-approved-fixtures-2026-09-09/SHA256.json, including the raw diff,
per-file hashes/assertion audit, commands, guards, logs and XML.

The three mirror files now intercept the instance methods dispatching writes
and removals to the real child writer. The existing interruptions, release
events, ownership checks and independent user edits reach the intended boundary.
Lifecycle companions still exercise actual child termination and session
ownership. The read test captures the production getter at collection and binds
it for its own test, so an earlier discovery fixture cannot substitute its
private Index. Its original migration and read-promotion checks remain.

Verdict: accept these exact approved setup corrections. They do not resolve the
three receipt-contract cases or reconstruct the missing historical AT6 exit.
Gemini is independently reviewing the receipt proposal and installation/security
boundaries. Any new behavior failure requires its own recorded repair and test.
