# Proposed interception-boundary correction: review verdict

**Suitable for Ryan's approval; not applied or executed.** The three-file
proposal moves failure injection to the production methods that send writes
to the isolated child. It preserves all **150 assertion syntax trees**, all
cases, timing budgets, Events, user edits and final byte/ownership checks.
The existing test files remain byte-identical to their pre-proposal state.

Patch: `patches/ryan-proposed-io-fixture-boundary-2026-09-09.patch`, 4,298 bytes,
SHA-256 `d64bde5d71b4349cb498bf267e6dda9b73a67f1f673b85889e9ac0c32e256929`.
The companion JSON audit binds the original three files and proposed content.
This is a review artifact, not an applied acceptance-fixture change.

The eight failures all depend on callbacks patched into the parent process's
`os.replace`/`Path.unlink`. The product executes those syscalls in a separate
child. The parent callbacks therefore cannot inject the interruption they
require. The proposed patch changes only which operation the existing callbacks
wrap: `Mirror._io_replace` and `Mirror._io_unlink`. Those methods carry the
real child session and file identity. The callbacks still receive the actual
allocated source/destination path and call the real product operation.

For D12 and the orphan purge case, injected replace/cleanup exceptions occur
on the existing production dispatch path, leaving the actual recorded temporary
file for the unchanged ownership assertions. For D13, the parent callback can
block before dispatch; after cancellation, its call to the real method must
refuse through the expired session. The unchanged tests still check that no
late bytes become visible and that independent user edits survive. Existing
child-lifetime tests continue to cover blocking inside the actual child.

This does not establish that all eight will pass. No proposed test ran. If
authorized, apply the exact patch, record it in the conflicts log, run the full
three acceptance files and all lifecycle companions, then run the complete tree
on a committed candidate. Preserve every failure. Any remaining behavior defect
gets a product repair; this proposal authorizes no further fixture revisions.

Approval is required because Ryan's 2026-09-09 ruling expressly froze further
fixture changes. The general request to finish the release does not override
that specific restriction. No approval is being inferred from this review.
