# Claude Code CLI: installed Windows stdio setup

Contract: `phase4-v1-2026-09-08`
([PHASE4-CONTRACT-2026-09-08.md](library/PHASE4-CONTRACT-2026-09-08.md)).
Client evidence:
[PHASE4-PROTOCOL-LIMITS-2026-09-08.md](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md).
This file is the Phase 4 configuration artifact for the supported pair:
**Claude Code CLI 2.1.261 over stdio through `uoink_mcp.py`**. It is not an
acceptance receipt.

The protocol-limits note records the initial investigation. Later actual
client observations supersede its claim that native resource reads are absent:
[observation 01](library/PHASE4-CLIENT-01-2026-09-08.md) and
[supplement/final disposition](library/PHASE4-CLIENT-02-2026-09-09.md).
Product limits come from the contract. Installed-package acceptance remains
separate from these source-staged observations.

## Supported client and scope

| Item | Value |
|---|---|
| Client | Claude Code CLI **2.1.261** (FileVersion `2.1.261.0`; [protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §1, §3) |
| Transport | stdio (the client spawns a child and speaks JSON-RPC on its stdin/stdout; [protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.1) |
| Config scope | **project** — `.mcp.json` at the project root ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3) |
| Server name | `uoink` |
| Interpreter | installed console **`python.exe`**, never `pythonw.exe` |
| Entrypoint | installed `uoink_mcp.py` as its own argument-array element |

Claude Code CLI 2.1.261 manages MCP servers with
`claude mcp add <name> <commandOrUrl> [args...]` or a direct entry in
`.mcp.json` ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3). `--scope project` is what writes the project-root `.mcp.json`. The
installed CLI's `claude mcp add --help` (same 2.1.261 binary the note examined
in §3) defaults `--scope` to `local` if you omit it, so pass `--scope project`
explicitly.

A `.mcpb` bundle is Claude Desktop only. Claude Code CLI 2.1.261 does not
recognize, install, or unpack `.mcpb` files; `claude mcp add bundle.mcpb` fails
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3).

**The resident HTTP helper is not a prerequisite.** Installing the Uoink
candidate is enough to run stdio. `uoink_mcp.py` reads local storage directly
and does not proxy through the helper
([contract](library/PHASE4-CONTRACT-2026-09-08.md), Capabilities / client
artifacts). Do not put a helper URL in this configuration.

## 1. Installed Windows stdio setup

Typical installed tree (resolve these to **absolute** paths on your machine;
do not copy a source-checkout path):

```text
%LOCALAPPDATA%\Uoink\python\python.exe
%LOCALAPPDATA%\Uoink\uoink_mcp.py
```

Use the console interpreter `python.exe`. `pythonw.exe` has no standard
streams and cannot carry JSON-RPC
([contract](library/PHASE4-CONTRACT-2026-09-08.md); [protocol-limits
note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.1: Claude Code expects
strict JSON-RPC 2.0 frames on stdout and treats stderr as diagnostics only).

Keep **command** and **arguments as an array** (or as separate argv tokens
after `--` on `claude mcp add`). Do not concatenate the script path onto the
interpreter string. An installation path that contains spaces must remain one
array element.

Set UTF-8 output on the child. Windows console Python otherwise uses the
legacy code page, which can corrupt stdout frames. The project-scoped example
sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`.

### `claude mcp add` (project scope)

From the project directory, after substituting the two absolute installed
paths. Quote each path so spaces stay in one argv token. The installed
2.1.261 help form is `claude mcp add <name> <commandOrUrl> [args...]` with
`--` before a command that has its own flags
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3;
`claude mcp add --help` on the same binary).

```powershell
claude mcp add --scope project --transport stdio uoink -e PYTHONIOENCODING=utf-8 -e PYTHONUTF8=1 -- "<ABSOLUTE_PATH_TO_INSTALLED_CONSOLE_PYTHON_EXE>" "<ABSOLUTE_PATH_TO_INSTALLED_UOINK_MCP_PY>"
```

That command writes a project-scoped `uoink` stdio entry to `.mcp.json`.

### `.mcp.json` (same project scope)

Reviewed template: [examples/claude-code.mcp.json](examples/claude-code.mcp.json).
Copy it to the project root as `.mcp.json` and replace both placeholders with
the absolute installed paths. Schema against Claude Code CLI 2.1.261:

- top-level `mcpServers` object
- entry name `uoink`
- `"type": "stdio"`
- `"command"`: absolute installed console `python.exe`
- `"args"`: array whose first element is the absolute installed `uoink_mcp.py`
- `"env"`: UTF-8 only (`PYTHONIOENCODING`, `PYTHONUTF8`)

The template contains no credentials, no checkout-specific path, and no
resident-helper URL. Do not add `url`, headers, or tokens.

Project-scope configuration lives in `.mcp.json`
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3).
Start a new Claude Code session in the project after the file is in place so
the CLI spawns the configured stdio child
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.1).

Stdout of the child must stay protocol-clean
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.1).
Uoink already sends diagnostics to stderr. Do not wrap the command in a shell
that prints banners to stdout.

## 2. First bounded query

Use the Phase 4 tools. Do not use `get_uoink_corpus` as overflow
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

1. Call **`search_library`** with a short `query` (default `limit` 5, maximum
   20). Each hit carries item identity, source revision, a safe title/source
   link, evidence kind/timing, an excerpt preview, and revision-bound follow-up
   URIs. `next_step` means more retrieval is available; the result is not an
   exhaustive inventory.
2. Call **`get_library_item`** with exactly one of `video_id` or `slug` from a
   hit. The result is the default Librarian card plus canonical card,
   selected-excerpt, and initial corpus-chunk URIs.

Ask the session in plain language, for example: search the library for a
topic, then open the returned item. Confirm the item identity, source
revision, and a quoted excerpt against what you expect. Canonical URIs come
from these tools; do not invent hashes.

Empty hits are a successful empty result. Missing or unreadable storage is
`library_unavailable`, not an empty library
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

## 3. Native resource reads and the fallback tool

Claude Code CLI 2.1.261 performed actual `resources/read` requests through its
`ReadMcpResourceTool` in the recorded sessions. Keep that built-in tool and
`ListMcpResourcesTool` available when restricting a client session. Ask it to
read the canonical URI returned by uoink; the observed native and fallback
responses matched in full. The session did not request template discovery,
so no template-picker support is claimed by this receipt.

**`read_library_resource(uri)`** remains the supported fallback. It uses the
same URI validation, contents and refusals as native `resources/read`, with
one renderer and identical `contents` text. Both routes were observed for
cards, excerpts, a bounded corpus and a synthetic brief.

After `get_library_item`, use a returned canonical URI (card, excerpt, or
corpus chunk). Do not hand-build hashes or attach a filesystem path. If card
metadata has no source link, a retained bounded corpus may contain the
original Source header; missing card links and text-only timing stay null.

## 4. Native prompt commands

The observed route was `/mcp__uoink__consult-library orbit` and
`/mcp__uoink__reshelve-review <preview_id>`, with actual `prompts/get` traffic.
Use these recorded internal command names when reproducing the receipt.
The alias forms below come from the earlier protocol investigation; they were
not separately exercised in the final session.

Claude Code discovers prompts via `prompts/list` and exposes them as slash
commands ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§3.4):

| Prompt | User alias | Internal name |
|---|---|---|
| `consult-library` | `/uoink:consult-library` | `/mcp__uoink__consult-library` |
| `evidence-brief` | `/uoink:evidence-brief` | `/mcp__uoink__evidence-brief` |
| `whats-new` | `/uoink:whats-new` | `/mcp__uoink__whats-new` |
| `reshelve-review` | `/uoink:reshelve-review` | `/mcp__uoink__reshelve-review` |

The generated command name is `/mcp__<server>__<promptName>`. User aliases
are `/<server>:<promptName>` and `/<server>:<promptName> (MCP)`
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.4).
The final observation used the `/mcp__uoink__<prompt>` form.

Arguments:

| Prompt | CLI tokens after the command | Server arguments |
|---|---|---|
| `consult-library` | one topic token | required `topic` |
| `evidence-brief` | topic token, optional `since` | required `topic`; optional `since` as UTC `YYYY-MM-DD` |
| `whats-new` | optional `days` | optional `days`, canonical decimal 1–30, default `7` |
| `reshelve-review` | one `preview_id` token | required `preview_id` (Phase 2 ID grammar) |

### Whitespace-splitting caveat

Claude Code CLI 2.1.261 splits slash-command input with `split(/\s+/)` and
maps tokens **positionally** onto the prompt's argument list. It does **not**
treat shell quotes as grouping
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.4 and
§7.2).

- `/uoink:evidence-brief agent loops 2026-09-01` binds `topic=agent` and
  `since=loops`, then the date is a leftover. `since` fails ISO validation.
- `/uoink:evidence-brief "agent loops" 2026-09-01` does **not** quote-group:
  `D[0]` becomes `"\"agent"` and `D[1]` becomes `"loops\""`
  ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.4).

Pass **single-token or hyphenated** topics:

```text
/uoink:consult-library agent-loops
/uoink:evidence-brief agent-loops 2026-09-01
/uoink:whats-new 7
/uoink:reshelve-review <preview_id>
```

Other MCP clients may still send arbitrary strings on `prompts/get`; this
whitespace rule is a Claude Code CLI 2.1.261 slash-command constraint, not a
change to the prompt set
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §7.2).

Prompts return a fixed instruction plus fenced evidence. They do not call a
model on the server, mutate the queue, or start capture
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

## 5. Helper-down and restart behavior

Distinguish the client-owned stdio child, the resident HTTP helper, and
storage ([contract](library/PHASE4-CONTRACT-2026-09-08.md), helper
restart/down ruling):

| What stopped | What you should see |
|---|---|
| **Resident HTTP helper** down (or never started) | Stdio library reads **continue**. The helper is not on the stdio path. |
| **Stdio child** restarted | Start a **new Claude Code session** so the CLI respawns the configured child ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.1). Rediscover with `search_library` / `get_library_item`. An unchanged item returns the same quote and source revision. |
| **Stdio child** stopped or launch broken | The next tool call is a **connection/transport failure**, not a domain JSON envelope. A dead process cannot emit `library_unavailable`. Claude Code reports dropped stdio as a transport error; a hang that goes silent for more than ~90 seconds can surface `MCP server ... transport dropped mid-call; response for tool ... was lost` ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.3). |
| **Storage** missing or unreadable while the child still runs | Domain `library_unavailable` within the 2-second service deadline. That is distinct from zero search hits. |

Stdio idle timeout on this CLI is 30 minutes
(`xr = 1800000` ms; [protocol-limits
note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.3). Uoink's 2-second
read deadline is stricter and is a product limit, not a Claude timeout.

Phase 4 advertises `listChanged: false` on tools, resources, and prompts, so
this CLI does not register list-change listeners or poll
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.6).
Refresh is an explicit tool/resource call or a new session.

The actual 2.1.261 client also supports `/mcp`, selecting `uoink`, then
Reconnect. Observation 01 replaced the recorded child and returned identical
complete item envelopes. That fixture configured a 10,000 ms server timeout
and `MCP_TIMEOUT=10000`; a suspended child produced a client failure after
10.003 seconds without a retry. This measured configuration supersedes the
older approximate hang timing for that receipt only; it is not a new default
timeout claim.

Do not target the resident helper to "fix" a stdio session. Do not add a
helper URL after a failure. If the child died, relaunch Claude Code so it
spawns a new one.

## 6. Removal

Project-scope CLI (inverse of `claude mcp add`; [protocol-limits
note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3):

```powershell
claude mcp remove --scope project uoink
```

Or delete the `uoink` object from the project's `.mcp.json`. If that was the
only entry, you may delete the file. Start a new session so the child is no
longer launched.

`claude mcp remove uoink` without `--scope` removes the name from whichever
scope it exists in (installed 2.1.261 `claude mcp remove --help`). Prefer an
explicit `--scope project` for this pair.

Removing the MCP entry does not uninstall Uoink and does not start or stop
the resident HTTP helper.

## What this configuration must not contain

- `pythonw.exe`
- A single string that glues interpreter and script together
- Credentials, tokens, or OAuth headers
- A checkout or worktree path
- A resident-helper URL, HTTP MCP endpoint, or `type` other than `stdio`
- `UOINK_INDEX_PATH` (Recall hook override; it does not redirect stdio
  `DATA_ROOT` in this base)
- A live-index or helper-data path in `env`

Public tunnels, OAuth/cloud connectors, registry publication, and `.mcpb`
installation are outside this pair
([contract](library/PHASE4-CONTRACT-2026-09-08.md);
[protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3).
