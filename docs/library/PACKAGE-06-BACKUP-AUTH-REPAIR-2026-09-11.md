# Package-06 backup authentication repair

The authorized backup push from 36f29c4 stalled in its owned
git-credential-manager.exe descendant. The remote branch had been verified at
e2349e0 before dispatch. Read-only `gh auth status --hostname github.com`
confirms an active ryanbiddy account in the existing keyring with repo scope;
no token value was retrieved or copied.

Verify the exact stalled Git process's parent, command and creation identity,
then stop only that owned push tree. Preserve its terminal result and failed
transport receipt. Recheck the remote before retrying; never infer success from
the local backup ref, which already advanced to the intended checkpoint.

Retry the same authorized branch push with a process-local Git credential-helper
override: reset inherited helper choices and use `gh auth git-credential`.
Disable terminal/CLI prompts for this invocation so another authentication
problem fails explicitly. Do not change global/repository Git settings, create
credentials, expose tokens, force-push or push any other branch.

The local backup ref may advance only from its verified previous value to the
final documentary checkpoint, with ancestor and worktree checks. Require the
actual push exit and a fresh remote-ref equality check. Preserve attempt one
beside the ZIP as `.backup-attempt01.json`; the final `.backup.json` must retain
both the helper choice and exact local/remote commits. This repairs transport,
not product code. No tests, build, installation or client-model run is repeated.
