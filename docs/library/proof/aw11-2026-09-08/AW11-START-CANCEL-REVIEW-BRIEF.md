# Final B6 startup/cancellation review

After B6 finishes and final source hashes are recorded, inspect the interval
between prepared-session registration and assignment of the Popen result.
The B6 brief already requires launch-in-progress retention. Determine whether
cancellation can release ownership and then let the original launcher start
or lose an untracked child. This is a hypothesis to check, not a reported
failure. An idle child that receives no mutation commands is not evidence of
post-timeout publication.

Use a controlled Popen wrapper or prepared-session boundary in disposable
fixtures. Record actual subprocess identities, session admission state,
retention and gate state. Keep the original caller and any competing caller
distinct. Correct outcomes include refusal of a cancelled launch before
Popen, or retained ownership with bounded cleanup once launch resolves.
Do not equate `_dead` (admission cancellation) with physical process death.
Terminate only children created by this diagnostic, through original session
references even if Mirror no longer retains them. Do not retry a failed
observation without a documented repair and new brief.

Also inspect B6's newly added unbound local-helper fallback. Its brief permits
reuse only inside the same admitted operation. After the originating thread
starts a Mirror session, a different thread with no operation context must not
use the shared Mirror object's current session to replace or delete an intent.
Observe actual disposable intent bytes before and after both operations, with
the original session retained for cleanup. This tests the helper boundary
explicitly named in B6; it is not a claim that a normal public resync bypasses
its outer exclusion. Preserve the same-thread helper controls in AW-4/AV-5m3.
