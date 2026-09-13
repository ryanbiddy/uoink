# Observe the unreserved owner handoff

Tree08's fifty mirror failures do not reproduce in the fresh seven-case AV5m3
file. Do not repeat the full tree without a repair. Source inspection reveals
a separate concrete race: _VaultIoSession.prepare obtains an owner before it
attaches the session, while another admission can sweep owners with no attached
mutator or exclusive hold. This may release the gate during that gap. Launch
does not revalidate held exclusion before Popen. It is not yet linked to the
original failure cascade.

Run one fresh, named synthetic observation of that handoff on current unchanged
production. Replace only the OS mutex acquire/release operations with inert
recording fakes. Insert a normal _release_proven_dead_owners call between the
real exclusion acquisition and real session attachment. Do not reset product
globals during the assertion, bypass an assertion or launch a process. Assert
that the returned prepared session still holds exclusion. Use fixture teardown
only to terminate the never-launched synthetic session and release its owned
inert gate after the observation.

This is a new diagnostic, not a modified acceptance fixture or an actual kernel
race timing measurement. Preserve source, exact invocation, outcome and the
inert gate event log. A confirmed failure requires a product repair and tests
for both the handoff and conservative retention. Gemini separately investigates
process identity; avoid changing its files or using real process operations.
