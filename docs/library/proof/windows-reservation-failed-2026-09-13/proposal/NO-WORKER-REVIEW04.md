# Retire an admitted read lease that never began worker startup

Root found that the derived release callback required an owned worker even for
adapter.ensure_assets and the initial admission-failure ExitStack.close path.
Those paths have a PROTECTED record, no native permit or owner, and a RESERVED
journal. The first source is preserved in before-no-worker-review04; it has not
been executed.

Add a separate no-worker witness only after the exact read set is actually
retired by the existing primitives. Require a current unrevoked RESERVED token,
PROTECTED record, absent permit/owner/worker/pipe, no startup or resume attempt,
and no retained worker associated with those guards. Bind the witness to that
exact record, token and read set. Completion may use it only after the base
lease records RELEASED. It makes no process-exit or job-empty claim. A failed
release cannot mint it, and any startup attempt remains outside this path.

The generated transport remains one generation per port instance. A subsequent
operation uses a fresh generated port and generation against the same retained
registry and its confirmed clean head; this does not reuse a journal generation.
No writer/acquisition service or production namespace is enabled by the change.

Add focused fake controls using the actual adapter.ensure_assets and initial
AdmissionRefusal paths, plus invalid no-worker boundaries and release failure.
Preserve the original 42 test bodies. Also avoid exposing the imported original
TestCase class to discovery in the new test module: import its module instead.
This is pre-execution fixture composition, not a changed behavior assertion.