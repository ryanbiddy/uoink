# No test started in the rejected launch

Automatic approval review rejected the compound owner-repair01 shell command
before CreateProcess, with "blocked by policy" and no further reason. There is
no test or Python exit observation from that command. No test output label was
created. Separate preparation now copies the unchanged diagnostic into the
isolated worker scratch directory. The reviewed launcher limits targets to the
two named worktrees, refuses reused output labels, scrubs provider variables,
sets the required audit-guard string and invokes only the existing native
verifier with explicit synthetic or Phase 4 selectors. This preserves the
live-index/network/model protections; it grants no additional process scope.
