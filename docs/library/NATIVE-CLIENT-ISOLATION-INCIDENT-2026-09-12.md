# Claude Desktop attempt: isolation claim withdrawn

The package-07 Claude Desktop attempt is invalid as an isolated acceptance run.
At 18:15 UTC, Astra inspected the complete startup branch and found that the
packaged application deletes CLAUDE_USER_DATA_DIR unless its own developer
authorization check succeeds. The earlier review found the subsequent setter
but missed that preceding deletion. Do not bypass that check or patch the app.

Logs created under the attempt's dedicated environment directory show the
ordinary Uoink connector command was selected at 16:58:43.965 UTC, followed by
"Server started and connected successfully" and a ListToolsRequest. The
ordinary filesystem connector also has a log. The isolated mcp.json therefore
did not constrain this Desktop run. The installed package-07 Python guard only
protected that separate interpreter; it was never OS-wide containment.

The owned Desktop job cleanup records no remaining processes, a successful
job-empty query and exact restoration of the package-07 guard. Those facts do
not prove the ordinary connector avoided the live index or resident port.
No live database, ordinary authentication store or ordinary connector config
will be opened, hashed or modified to investigate this incident. No new Desktop
launch is authorized through the discarded override. Preserve the original
receipt and failure; the earlier no-native-surface and proven-isolation prose
are superseded. Ryan has been told this explicitly.

Package-08 native launchers must expose only the independently guarded Uoink
dashboard. Remove the Desktop mode from the unused preparation before execution,
preserve its draft/diff, and continue source-bound Uoink native note/media checks.
CLI acceptance remains separate: those observed processes use the actual CLI's
reviewed CLAUDE_CONFIG_DIR and isolated server configuration. This incident does
not retroactively turn those successful CLI exchanges into Desktop GUI evidence.

A future Desktop GUI receipt needs a supported isolation mechanism verified
before launch, or a separate Windows user/VM with no ordinary connector config.
That operating environment and interactive sign-in are still missing. Do not
attempt alternate flags, debugging bypasses, credential copying or a blind rerun.
