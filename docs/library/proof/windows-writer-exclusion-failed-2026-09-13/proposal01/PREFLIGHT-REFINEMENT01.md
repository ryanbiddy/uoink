# Pre-execution contender cleanup refinement

The first helper draft is retained under before-review01. Source inspection found
that the preserved graceful-exit observer marks worker.unconfirmed when its wait
fails. Using that flag to suppress a further stop would skip the desired exact
stop attempt after a successfully created contender timed out. Track whether the
constructor actually returned: its own failure cleanup remains untouched, while
a later failed wait gets one explicit retained-job/process stop attempt. A stop
wait is not clean-release evidence; uncertainty and guards remain held.

Also state journal noninheritance through the actual distinct input read-set
membership, rather than comparing original handles with newly duplicated output
handles (different handle numbers alone are not a proof of what was duplicated).
No run, failed measurement or native observation occurred. This is a correction
to an unexecuted source draft before review.