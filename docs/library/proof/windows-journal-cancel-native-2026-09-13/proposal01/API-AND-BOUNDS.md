# Native scope retained from writer04

The cancellation helpers perform Python state observations and an already
implemented cursor operation. They add no Windows symbol, prototype or native
query. Both original stop/join and pending-I/O immediate-finalization protection
remain unchanged.

The existing contender still has its exact 103-call declared path. The controller
retains the 16,384-call/60-second cooperative work limits, 1-MiB receipt cap and
64-call/10-second cleanup reserve with bounded wait requests. The original full
derivation is retained in before/API-AND-BOUNDS.md. Cancellation needs one fewer
request/response exchange than drain, but no exact total or hard wall-time bound
is claimed before measurement.

Before/after journal observations are checks in this fixed serial generated
controller. They do not create authority, synchronize arbitrary external callers
or establish a new atomicity guarantee. Existing token/gate/retained-handle rules
continue to govern actual cleanup. Fake tests separately check the new helpers;
their results cannot substitute for an admitted native observation.
