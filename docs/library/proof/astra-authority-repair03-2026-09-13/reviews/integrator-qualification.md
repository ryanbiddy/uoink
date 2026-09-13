# Authority repair03 integration qualification

Astra independently reviewed the final process source, SHA256
67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23,
and the retained 39-case assertions plus ten additional handle controls.
The final writer publication checks cancellation under the state lock. Borrowed
Popen ownership survives every handle user, with destruction outside the handle
guard. Child discovery pins both process objects through relationship proof and
uses the retained child handle for mutation. Pending discovery keeps exclusion
and defers cancellation cleanup. Native calls do not hold the state lock.

The independent synthetic run astra-authority-repair03-independent01 passes
49 cases in 0.65 seconds, pytest and verifier exit 0. No further actionable
authority defect was found in this review. This permits the broader real
Phase 4 qualification specified by the repair03 brief; it is not release or
full-tree acceptance. Previous held proposals and failures remain unchanged.

Use run_process_authority_repair03_verification.ps1 with fresh labels
astra-authority-repair03-worker-phase4-01 and
astra-authority-repair03-checkout-phase4-01. The scope is all Phase 4 files in
tests and tests/library_work_astra, accepted owner admission cases and all five
authority files. Run sequentially, worker first, then raw binary Git diff and
three-way apply, then checkout. Frozen committed tests must have no diff.

Use the existing guarded verifier, offline flags and provider-environment scrub.
No models, live index, port 5179, new fetch, install, website, marketing or push.
Stop on a failure, retain the outcome and write its repair brief before retrying.
