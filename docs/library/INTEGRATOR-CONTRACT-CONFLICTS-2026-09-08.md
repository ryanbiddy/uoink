# Acceptance fixture conflicts found during integration

Reviewer: Astra, 2026-09-08. Checkout: `dad34eb`. This is a source-inspection
finding, not a passing runtime receipt. Preserve the existing acceptance files.
The implementation work continues; these conflicts grant no waiver for unsafe
publication, cancellation, or test-specific production behavior.

## Phase 4: D13's two observation cases

In `tests/library_work_astra/test_phase4_aw3_acceptance.py:245`, both cases
install the same `blocked_replace` wrapper. It signals entry, waits until the
caller has returned a timeout, performs the actual replacement, and appends
the resulting source bytes to `published`. Only then does the `user_edit`
case write its personal bytes. The visibility case requires `published` to
remain empty; the user-edit case requires those later personal bytes to exist.

A publisher that prevents the post-timeout replacement also prevents this
wrapper from creating the personal bytes. An implementation cannot distinguish
these cases before that replacement through its public inputs. Inspecting the
fixture's closure, branch names, or test identity is not an acceptable repair.
The AV-5m2 draft does inspect the `observe == "user_edit"` closure; that code
will not be integrated. Asynchronous Python exceptions also do not establish
cancellation of a blocked operating-system replacement.

The product obligations remain: prevent abandoned work from mutating a
destination after timeout, retain destination exclusion until termination,
and preserve independent user edits. A revised fixture should arrange the
user edit independently of the forbidden replacement and exercise the actual
cancellable I/O boundary. Ryan must authorize that acceptance-fixture revision
or give another explicit ruling. Neither existing case is relabelled passed.

## Phase 6: required build-time ticket versus legacy helper calls

BD-01 and the BC-3a2 brief require both raw and Index publication entry points
to reject absent build-time ownership. However,
`tests/test_phase6_evaluation.py:1228` calls the raw publisher without a ticket
for successful publication/recovery scenarios. The BD reproduction itself uses
that helper to publish its newer setup snapshot. Several successful Index
replacement/retry calls in `tests/test_phase6_bc2.py` also omit tickets.

An unconditional ticket requirement therefore refuses some fixture setup
before the behavior under review can run. Allowing ticketless empty snapshots
is unsafe: an old empty build can erase a newer publication just as an old
nonempty build can replace it. An exception described as support for the
frozen evaluation helper is not a production contract.

Keep the boundary fail-closed and carry tickets from build start in production
callers. Ryan must authorize updating legacy acceptance setup to acquire and
carry the ticket before building, while preserving every behavioral assertion,
or make another explicit contract ruling. Worker edits to these acceptance
files are not integrated under the current instruction. Runtime counts must
identify any fixture-setup refusals separately from implementation failures;
neither becomes a pass by this inspection.

## Integration disposition

These are additional Ryan decisions under the instruction never to edit
acceptance tests. They do not move the unfinished implementation work into
Ryan's queue. Finish and independently verify the general repairs, retain all
failed observations, and review the resulting safety behavior before proposing
any candidate as blocked only on the fixture rulings and other owner gates.
# Additional fixture conflict: Phase 5 final-wire deadline probe

AZ-5d (Grok `e739a5ec`) is rejected despite 393 passes and four measurement
failures. Its adapter traverses a callback closure to bypass incompatible test
wrappers. Production must call its reader normally.

`test_phase5_acceptance3.py:391` installs a unary `read(args)` wrapper. The
shared `stdio_result` at `test_phase5_acceptance.py:427-431` then invokes that
wrapper with `clock=NOW`. Python raises TypeError before the final-wire probe
runs. Ryan must authorize compatible fixture setup, preserving the deadline
assertion, or provide a ruling. Existing tests remain unchanged. AZ-5d2 removes
the production workaround and adds an independent actual-handler test; it must
report the frozen setup failure separately.
