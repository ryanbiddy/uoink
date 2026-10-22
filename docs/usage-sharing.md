# Optional usage sharing

Uoink sends no usage data by default. The dashboard offers a one-time card
with **No thanks** as its default choice. Settings > App > Usage sharing has
**Share anonymous usage counts** and **See what is sent**. The disclosure
shows the next payload with current counts and the last ten acknowledged
payloads, with UTC dates. While sharing is off, it shows a clearly labeled
sample with zero counts and placeholder IDs. Reading this preview does not
create or write a counts file.

If enabled, Uoink sends at most one HTTPS request per 24 hours to
`https://usage.uoink.app/v1/ping`. The report contains only these fields:

```json
{
  "schema": 1,
  "install_id": "a8bca5bb-8c6f-4f8a-9876-c75b25edfc34",
  "report_id": "a4638f94-f8ba-4f25-8cc2-94679893ba96",
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

The IDs above are examples. Each enabled install gets a random UUID4,
unrelated to hardware, accounts, paths or tokens. Turning sharing off deletes
the active ID, counts, pending retry and sent history. Turning it on again
creates a new ID. The last-attempt time remains so toggling cannot bypass
the daily limit. Only an explicit usage-sharing change in `/settings` changes
saved consent. Other settings writers preserve the latest saved choice under
a file lock shared by the helper and stdio processes.

`UOINK_USAGE_SHARING=0` applies to the process whose environment contains it.
Set it for the helper to stop sending, because only the helper runs the sender.
Setting it only for a stdio client stops that process from counting; it does
not disable a helper already running in another environment. The Settings
switch turns off sharing across processes.

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
or network. Events from before the current opt-in are discarded. Normal
process exit allows up to one second to flush queued counts to disk. Forced
termination or a longer disk stall can still lose queued counts.

MCP client counts measure initialization messages. Names map to a fixed list:
Claude Desktop, Claude Code, Cursor, Cline, Continue, Codex, ChatGPT and VS Code.
All other names become `other`. Transport counts measure registered tool calls
over `stdio` or `http`. Both transport keys are always present, including zero
values. Only current registry tool names matching `[a-z0-9_]{3,64}` are sent.
The key limit is 128, covering the 91 registered tools. Each wire count is
an integer from 0 to 100,000. The compact UTF-8 JSON is at most 4,096 bytes.
Tool keys are reduced if needed to fit; omitted counts remain for a later report.

Client names are trimmed and lowercased, then matched exactly:

| Sent label | Accepted host names |
| --- | --- |
| `claude-desktop` | `claude desktop`, `claude-desktop`, `claude`, `claude-ai` |
| `claude-code` | `claude-code`, `claude code` |
| `cursor` | `cursor`, `cursor-vscode` |
| `cline` | `cline` |
| `continue` | `continue` |
| `codex` | `codex`, `openai-codex`, `codex-mcp-client` |
| `chatgpt` | `chatgpt` |
| `vscode` | `vscode`, `vs code`, `visual studio code`, `vscode-insiders`, `vscode - insiders`, `visual studio code - insiders`, `code - insiders` |
| `other` | Every unrecognized name or missing name |

`os` is `windows`, `macos` or `linux`. `os_major` is one to three ASCII
digits or `unknown`. `arch` is `x86_64`, `arm64` or `other`; x86 maps to
`other`. `install_kind` is `installer`, `mcpb` or `source`. `version` is
SemVer with three numeric parts and optional prerelease/build labels.
`period_hours` is finite and clamped to 0 through 100,000.

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
requests. A short transaction saves the snapshot and send generation, then
releases the database before network work starts. The sender waits at most
four seconds for that work, including DNS, and refuses redirects. A second
short transaction applies the result only if consent and the generation
still match. Settings reads, opt-out and other processes' counts can proceed
while the request is in flight.

The network worker is a daemon. Python cannot forcibly cancel a DNS or socket
call already running in that thread. It may finish after the deadline or
after opt-out; its late result cannot change local state. At most one such
worker can be outstanding in a sender process.

Each pending report has its own UUID4 `report_id`, kept across restarts and
daily retries. Pending fields and labels are checked again against the current
allowlists before sending. A `204` means recorded; a `208` means that report
was already recorded. Either acknowledgment subtracts exactly the snapshot's
counts once. Counts recorded meanwhile survive, including when the snapshot
was at the count limit. Other responses leave the snapshot pending.

The receiver remembers report IDs for seven days. The client retires an
unacknowledged snapshot at seven days minus four seconds and removes only
its included counts, so an expired retry cannot count twice. New activity
remains queued. The same rule retires pending reports from older clients
that lack a report ID. These uncertain snapshots do not enter sent history;
some may never have reached the receiver. Previously recorded legacy reports
cannot be deduplicated retroactively.

Any `UOINK_ISOLATED_*` environment variable, or an active isolation binding,
blocks sending. An empty `UOINK_USAGE_ENDPOINT` also blocks sending. Tests
cannot use the default endpoint: an explicit non-production HTTPS override
is required, and the tests mock the POST. No real usage ping is part of
verification.
