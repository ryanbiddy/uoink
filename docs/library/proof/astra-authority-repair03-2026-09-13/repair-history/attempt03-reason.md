# Parent review repairs before a third labeled run

Attempt02 passed 46 cases. The integrator identified a remaining canonical
writer publication race: its same-PID branch lacked the short state-lock and
cancellation check used by the distinct-writer branch. Both now refuse a dead
session before publishing writer fields.

Dropping the final borrowed-owner reference could also run its destructor
inside the counted-handle guard. The wrapper now carries that reference to a
local until after leaving the guard. Three new cases cover cancelled canonical
publication and owner destruction with and without an outstanding handle user.
The existing 46 assertions remain unchanged. Previous source and tests are
retained in `before-parent-review-repair` and the attempt02 source archive.

Fresh label: `astra-authority-repair03-03`. No result claimed before execution.
