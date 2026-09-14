# Latch identity and native-result uncertainty

Independent review found that post-call offset/count validation and direct
identity checks could raise outside the poison handler. A previous clean cache
could then survive that observed uncertainty. The unexecuted e278 port is
preserved under `before-peer-review03/`.

Latch stream poison for failed native identity queries and post-call result
validation before propagating. A caller argument refused before any native work
does not itself poison ownership. Add controls that first confirm a clean head,
observe wrong native seek/read results or identity failure, catch the error, and
verify that final release still refuses without closing the gate. No execution.
