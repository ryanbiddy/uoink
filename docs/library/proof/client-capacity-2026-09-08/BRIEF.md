# Client capacity preflight, 2026-09-08

Read subscription authentication and the Claude Code native /usage screen
without any model request. This is account/client preflight, separate from
the candidate receipt, which still waits for AW-4. Use a fresh empty task
directory, restricted mode, no tools, an explicit empty MCP configuration,
no Chrome, and disabled fixture auto memory. No archived database, product
server, native library prompt, hook or model request is authorized in this
preflight. Do not open /usage-credits, buy credits, upgrade, change billing or
accept paid fallback. Record the exact client version, relevant observed
authentication mode and quota screen, including any freshness limitation.
Exit the preflight client after reading it. A capacity failure remains an
observation; it cannot become a product acceptance result.

Setup repair before the second launch: the first TUI asked to trust the new
folder in the normal client profile; that dialog was declined and the process
exited before any prompt or model request. Use a fresh CLAUDE_CONFIG_DIR under
the user's AgentControlRoom local data directory. Copy only the active
subscription OAuth access credential, omitting its refresh token, plus the
account metadata needed by the client. The observed access expiry has nearly
eight hours remaining. Do not retain or archive credentials, and delete the
temporary credential file after exit. This prevents token rotation and puts
all trust/onboarding/session writes in the disposable profile. Recheck auth
there before using /usage. Existing MCP/client settings are not copied.
