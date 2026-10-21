# Optional usage sharing

Uoink sends no usage data by default. The dashboard offers a one-time card
with **No thanks** as its default choice. Settings > App > Usage sharing has
**Share anonymous usage counts** and **See what is sent**. The disclosure
shows the next payload with current counts and the last ten successful
payloads, with UTC dates. A pending retry shows the same JSON that failed.

If enabled, Uoink sends at most one HTTPS request per 24 hours to
`https://usage.uoink.app/v1/ping`. The report contains only these fields:

```json
{
  "schema": 1,
  "install_id": "a8bca5bb-8c6f-4f8a-9876-c75b25edfc34",
  "version": "3.10.0",
  "os": "windows",
  "os_major": "10",
  "arch": "x86_64",
  "install_kind": "installer",
  "period_hours": 24.0,
  "mcp_clients": {"claude-code": 1, "other": 1},
  "transports": {"stdio": 4, "http": 1},
  "tools": {"search_library": 3, "uoink_video": 2},
  "captures": {"youtube": {"ok": 1, "failed": 1}},
  "searches": 3
}
```

The ID above is an example. Each enabled install gets a random UUID4,
unrelated to hardware, accounts, paths or tokens. Turning sharing off deletes
the active ID, counts, pending retry and sent history. Turning it on again
creates a new ID. The last-attempt time remains so toggling cannot bypass
the daily limit. `UOINK_USAGE_SHARING=0` forces sharing off.

Reports never include content, URLs, titles, file paths, search text, usernames,
IP addresses or account details. HTTPS still exposes the connection IP to
the receiving service. Receiver access logs and retention are outside this
repository and need to follow the product's no-IP-retention policy.

## Counting across processes

The helper and stdio processes share `usage-counts.sqlite3` in the settings
folder. This is a separate counts file, not the library index. SQLite
transactions lock updates across processes on Windows, macOS and Linux.
This avoids adding an HTTP route or reading a token to record stdio counts.

Callers put fixed labels on a queue of at most 1,024 entries. A daemon worker
does the disk work. A full queue or a failed write drops the count and logs
only a fixed message at debug level. Tools and captures never wait for disk
or network. Events from before the current opt-in are discarded.

MCP client counts measure initialization messages. Names map to a fixed list:
Claude Desktop, Claude Code, Cursor, Cline, Continue, Codex, ChatGPT and VS Code.
All other names become `other`. Transport counts measure registered tool calls
over `stdio` or `http`. Only registry tool names are accepted. Tool counts
have at most 64 keys; counts saturate at 100,000, the receiver's limit. The complete compact JSON
must stay below 4,096 bytes. Tool keys are reduced further if needed to fit.

Captures use eight source labels: `youtube`, `x`, `reddit`, `page`, `podcast`,
`image`, `note` and `other`. Results are `ok` or `failed`. Nested capture paths
count once. A live stream queued for later is not a finished capture.
Searches count requests without retaining their arguments. Opening the library
or memory list without search text does not add a search. A library search that
uses both item and clip indexes counts once.

## Sending and failure handling

Only the helper starts the sender, on a daemon thread. It checks the daily
gate once a minute and waits at least 24 hours after enabling before its first
attempt. The attempt time is saved before the request, including failed
requests. The timeout is five seconds, and redirects are refused.

A failed payload can be retried once in the next daily window. If both
attempts fail, its counts remain for a new report in a later window. A
successful send subtracts only the counts included in that payload. Events
queued during the send stay available for the next report.

Any `UOINK_ISOLATED_*` environment variable, or an active isolation binding,
blocks sending. An empty `UOINK_USAGE_ENDPOINT` also blocks sending. Tests
cannot use the default endpoint: an explicit non-production HTTPS override
is required, and the tests mock the POST. No real usage ping is part of
verification.
