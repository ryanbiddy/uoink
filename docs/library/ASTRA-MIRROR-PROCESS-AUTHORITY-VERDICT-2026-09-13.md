# Process ownership diagnosis requires repair

Gemini run 213914a5 found concrete unsafe ownership and liveness behavior in
unchanged b62aab3 mirror source. Astra reproduced the worker's six synthetic
observations in its worktree (6 passed in 0.23 s), applied the reviewed raw Git
diff with git apply --3way, then observed the same six outcomes in the checkout
(6 passed in 0.17 s). These probes assert the defects. Their passes are evidence
of current behavior, not product acceptance. The probe is archived under proof,
outside the normal test tree; no product source or existing test changed.

The useful findings are that a Toolhelp parent PID alone admits an older foreign
child, records its own creation time as authority and can send it to the
termination helper; a confirmed process exit can later become unknown; and a
failed creation-time query can fall through to alive. All process and kernel
observations were inert fakes. No actual foreign process was opened or killed.
Whether these defects caused tree08's cascade remains unproved.

The worker report needs three qualifications. Tree08 has fifty mirror failures
plus the historical AT6 gap, not fifty-one mirror failures. Its retention probe
changes global variables but asserts separate unchanged locals, and it never
attaches an owner; its claim that exclusion was observed held is unsupported.
The first two worker attempts remain 4 passed/2 failed and 5 passed/1 failed.
Their logs survive, but the worker overwrote the two earlier probe drafts; exact
source bytes for those attempts were not located. The final six-case source and
all located logs are sealed. The report's proposed fix is a proposal: its unknown
creation-time fallback and missing recheck before acting on a PID need stronger
review. Do not adopt it unchanged.

Proceed under MIRROR-PROCESS-AUTHORITY-REPAIR-BRIEF-2026-09-13.md. Add actual
regressions asserting safe behavior and positive controls for legitimate child
ownership and unknown-child retention. Preserve the original diagnostic evidence.
The separate owner reservation repair continues in its own worktree. Both fixes
need independent verification before any fresh complete tree or package09 build.
Website and marketing work remain paused; this verdict is a release hold.
