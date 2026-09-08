# Uoink `.mcpb` one-click Claude Desktop bundle

`.mcpb` (MCP Bundle, formerly DXT / "Desktop Extension") is Anthropic's package
format for one-click MCP server installation in **Claude Desktop**. This doc
covers how Uoink's bundle is designed, built, and released, and documents the
stdio inventory the launched child advertises.

- **Spec:** https://github.com/modelcontextprotocol/mcpb (`MANIFEST.md`, manifest_version `0.4`)
- **Format findings used here:** [PHASE4-PROTOCOL-LIMITS-2026-09-08.md](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) section 4. Every format claim in this file cites that note.
- **Product contract:** [PHASE4-CONTRACT-2026-09-08.md](library/PHASE4-CONTRACT-2026-09-08.md) (tool/resource/prompt inventory and thin-launcher prerequisites)
- **Bundle source:** [`.mcpb/manifest.json`](../.mcpb/manifest.json), [`.mcpb/README.md`](../.mcpb/README.md)
- **Build scripts:** [`scripts/build-mcpb.ps1`](../scripts/build-mcpb.ps1) (primary), [`scripts/build-mcpb.sh`](../scripts/build-mcpb.sh)
- **Output:** `dist/uoink-<version>.mcpb`
- **Claude Code CLI (not this bundle):** [`docs/claude-code-mcp.md`](claude-code-mcp.md)

## Desktop versus CLI scope

Keep these surfaces separate. A `.mcpb` package does not prove Claude Code
installation or any current CLI capability
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

| Client | How Uoink is installed | This `.mcpb` |
|---|---|---|
| **Claude Desktop** | Double-click / drag into Settings → Extensions. Desktop unpacks the bundle and writes the rendered configuration to `%APPDATA%\Claude\claude_desktop_config.json` ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). | **Yes.** Target of this package. `compatibility.claude_desktop` is `>=0.10.0` ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.2). |
| **Claude Code CLI 2.1.261** | `claude mcp add <name> <commandOrUrl> [args...]` or a project-scoped `.mcp.json` entry ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). | **No.** The CLI does not recognize, install, or unpack `.mcpb` files. `claude mcp add bundle.mcpb` fails ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). Follow [`docs/claude-code-mcp.md`](claude-code-mcp.md). |

## What a `.mcpb` is

A `.mcpb` file is a standard **ZIP archive** containing `manifest.json` at its
archive root ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.1). Claude Desktop reads the manifest, prompts the user for any
`user_config` values, and writes the resulting `mcpServers` entry into its own
config — no manual JSON editing ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3).

Uoink's container matches the protocol note's layout
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.1):

```text
uoink-3.8.0.mcpb (ZIP archive)
├── manifest.json       (manifest_version 0.4)
├── README.md           (bundle documentation)
├── icon.png            (display icon)
├── uoink_mcp.py        (reference copy of entrypoint)
└── uoink_mcp_tools.py  (reference copy of tool registry)
```

The two `.py` files are reference copies so `entry_point` resolves
structurally. Runtime always executes the **installed** copies under
`user_config.uoink_dir`.

## Bundle format requirements (`manifest_version` 0.4)

Every field claim in this section is from
[PHASE4-PROTOCOL-LIMITS-2026-09-08.md](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.2. Uoink's committed [`.mcpb/manifest.json`](../.mcpb/manifest.json)
already uses these fields.

### Root identity ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.2)

| Field | Requirement | Uoink value |
|---|---|---|
| `manifest_version` | `"0.4"` (string, required) | `"0.4"` |
| `name` | Package identifier matching `^[a-z0-9-_]+$` | `"uoink"` |
| `display_name` | Display string | `"Uoink"` |
| `version` | Valid SemVer matching repository `VERSION` | `"3.8.0"` |
| `description` | Single-line summary | present |
| `long_description` | Extended description for marketplace views | present |
| `author` | `{ "name": "...", "url": "..." }` | Ryan Biddy / https://uoink.app |
| `license` | SPDX identifier | `"MIT"` |

### Server execution (`server`) ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.2)

- `type`: `"python"` (or `"node"`; Uoink is Python).
- `entry_point`: path relative to bundle root — `"uoink_mcp.py"`.
- `mcp_config`: template injected into client settings:
  - `command`: subprocess executable path
  - `args`: array of argument strings
  - `env`: environment variable mappings

### User configuration (`user_config`) ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.2)

Declarative prompts shown during Desktop installation. Supported field types:
`"string"`, `"boolean"`, `"directory"`, `"file"`. Interpolation:
`${user_config.<key>}` and `${HOME}`. Uoink declares one required `directory`
field, `uoink_dir`, defaulting to `${HOME}/AppData/Local/Uoink`.

### Compatibility (`compatibility`) ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.2)

- `claude_desktop`: supported Desktop version range — Uoink uses `>=0.10.0`.
- `platforms`: OS tokens — Uoink uses `["win32"]`.
- `runtimes`: language constraints — Uoink uses `{"python": ">=3.10,<4"}`.

`compatibility.claude_desktop` is a Desktop range. It is not a Claude Code
CLI version claim ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.2, §4.3).

## Design decision: thin launcher, not self-contained

The mcpb spec assumes a self-contained bundle (server code + dependencies
zipped together). Uoink's server can't practically be self-contained:
`uoink_mcp.py` imports `server.py`, `uoink_mcp_tools.py`, and dozens of
sibling modules, plus heavy runtime deps (yt-dlp, the MCP SDK, keyring,
Whisper). All of that already ships in the installed Uoink tree at
`%LOCALAPPDATA%\Uoink`.

So Uoink's bundle is a **thin launcher**. The protocol note records this
pattern ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3):

```json
"mcp_config": {
  "command": "${user_config.uoink_dir}/python/python.exe",
  "args": ["${user_config.uoink_dir}/uoink_mcp.py"],
  "env": { "PYTHONPATH": "${user_config.uoink_dir}" }
}
```

That interpolates to the working stdio command
(`server.py::_mcp_stdio_command`):

```
<install>\python\python.exe   <install>\uoink_mcp.py
```

`command` is the installed **console** `python.exe`. Never `pythonw.exe`
([contract](library/PHASE4-CONTRACT-2026-09-08.md)). `args` keeps the script
path as its own array element so spaces in the install path remain one token.

### Thin-launcher prerequisites

| Prerequisite | Bound |
|---|---|
| Installed Uoink tree | Console `python.exe`, `uoink_mcp.py`, sibling modules, and dependencies already on disk. Default install dir is `%LOCALAPPDATA%\Uoink` ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). Install from https://uoink.app/install first. |
| Console `python.exe` | Required for JSON-RPC stdin/stdout. `pythonw.exe` has no standard streams ([contract](library/PHASE4-CONTRACT-2026-09-08.md)). |
| UTF-8 | The stdio child must emit UTF-8 JSON-RPC on stdout; diagnostics on stderr. Windows console Python otherwise uses the legacy code page, which can corrupt frames. Claude Code's reviewed project config sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` ([docs/claude-code-mcp.md](claude-code-mcp.md); [examples/claude-code.mcp.json](examples/claude-code.mcp.json)). The Desktop `mcp_config` currently interpolates `PYTHONPATH` only ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). |
| No resident HTTP helper for reads | Installing the candidate is enough to run stdio. Library reads do not proxy through the helper and do not require it to be running ([contract](library/PHASE4-CONTRACT-2026-09-08.md)). Do not put a helper URL, HTTP MCP endpoint, or port into this bundle's config. |

The bundle stays tiny and cannot drift from the installed interpreter the
user is actually running.

## What the launched stdio child advertises

This bundle launches `uoink_mcp.py` over stdio. That process advertises
**tools, resources, and prompts**. HTTP MCP remains tools-only and is a
different adapter; do not copy the stdio capability object onto HTTP
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

### 29 tools

Count: **25** legacy + Phase 4 `search_library`, `get_library_item`,
`read_library_resource` + Phase 5 `get_library_activity` = **29**.
[`.mcpb/manifest.json`](../.mcpb/manifest.json) already lists those 29 names
in `tools`. The same 29 are registered on stdio.

**Legacy (25):** `uoink_video`, `uoink_playlist`, `get_job_status`,
`cancel_job`, `list_recent_uoinks`, `search_uoinks`, `search_clips`,
`get_evidence_card`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`,
`get_taxonomy`, `get_citation_map`, `get_uoink_health`, `find_mentions`,
`get_transcript_reliability`, `add_podcast_feed`, `list_podcast_feeds`,
`remove_podcast_feed`, `poll_podcast_feed`, `list_podcast_episodes`,
`download_podcast_episode`, `get_whisperx_status`,
`transcribe_podcast_episode`, `episode_to_corpus`.

**Phase 4 (3), contract `phase4-v1-2026-09-08`:**

| Tool | Role |
|---|---|
| `search_library` | Bounded clip-first search (default 5, at most 20 hits) with item-FTS fallback and revision-bound follow-up URIs. |
| `get_library_item` | Exactly one of `video_id` or `slug`. Default Librarian card plus canonical card, excerpt, and initial corpus-chunk URIs. |
| `read_library_resource` | Same URI validation, contents, and refusals as `resources/read`. Tool fallback for a client that cannot attach a template-derived URI. |

**Phase 5 (1), contract `phase5-v1`:** `get_library_activity` — deterministic
library activity, shelf churn, and source observations.

Not on stdio (and not in this bundle's `tools` list): the six Phase 2
work-queue tools (`list_library_work`, `claim_library_work`,
`submit_library_result`, `apply_reshelving`, `pin_shelf`,
`undo_library_apply`) and the four Phase 3 source-subscription tools. Those
remain HTTP/OpenAPI registry-only. Do not treat `get_uoink_corpus` as an
automatic overflow fallback for the bounded library tools.

One-line descriptions for all 29 names live in
[`.mcpb/manifest.json`](../.mcpb/manifest.json) and
[`.mcpb/README.md`](../.mcpb/README.md). The public tool reference is
[`docs/v2-mcp.md`](v2-mcp.md).

### Five resource templates (`uoink://library/v1/`)

Stdio advertises these five templates (`resources/templates/list`) and a
curated `resources/list` (at most 41 entries). All five return
`text/markdown`. Authority is `library`, version path `/v1`
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

| Template after `uoink://library/v1/` | Meaning |
|---|---|
| `items/{item_key}/cards/{source_revision}/{selection}/{card_hash}` | Default Librarian card; all three bindings checked. |
| `items/{item_key}/excerpts/{source_revision}/{excerpt_id}` | One original excerpt, at most 2,000 Unicode code points. |
| `items/{item_key}/corpus/{corpus_revision}/{offset}/{length}` | Bounded original-corpus chunk. `corpus_revision` is SHA-256 of the complete stored file. |
| `shelves/{shelf_key}/{taxonomy_revision}/{projection_revision}/{shelf_revision}/{offset}` | Shelf definition and a page of current members. |
| `briefs/{date}/{brief_hash}` | One persisted client-produced brief; date is UTC `YYYY-MM-DD`. |

Canonical URIs are returned by discovery. Clients should not manufacture
hashes. Claude Desktop can attach listed resources through its `@` picker.
Claude Code CLI 2.1.261 implements `readResource()` / `listResourceTemplates()`
in its SDK but exposes no model tool or slash command for arbitrary resources;
that pair uses `read_library_resource(uri)`
([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §3.5;
[`docs/claude-code-mcp.md`](claude-code-mcp.md)). That CLI gap is not a
Desktop-bundle defect.

### Four prompts

Stdio advertises these four names (`prompts/list` / `prompts/get`):

| Prompt | Arguments |
|---|---|
| `consult-library` | Required `topic`. |
| `evidence-brief` | Required `topic`; optional `since` as UTC `YYYY-MM-DD`. |
| `whats-new` | Optional `days`, canonical decimal 1–30, default `7`. |
| `reshelve-review` | Required `preview_id` (Phase 2 ID grammar). Reads an existing preview; does not call `apply_reshelving`. |

Prompts return a fixed instruction plus fenced data. They do not call a
model on the server, start capture, or mutate the queue
([contract](library/PHASE4-CONTRACT-2026-09-08.md)).

## Building

```powershell
# Windows (primary)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-mcpb.ps1
```
```bash
# POSIX
bash scripts/build-mcpb.sh
```

Both scripts:
1. Validate `manifest.json` is valid JSON.
2. Assert the entry command matches the working stdio command
   (`…/python/python.exe … uoink_mcp.py`) and `entry_point == uoink_mcp.py`.
3. Stage `manifest.json`, `icon.png`, `README.md`, and reference `.py` files.
4. Pack with the official `mcpb` CLI if present (`npm i -g @anthropic-ai/mcpb`),
   otherwise fall back to ZIP + rename to `.mcpb` (identical container;
   [protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.1).

Output: `dist/uoink-<version>.mcpb`.

## Releasing

Attach `dist/uoink-<version>.mcpb` only after release approval. MCP Registry
publication is separate launch work and requires a reviewed `server.json`;
this repository does not ship one today.

## Verifying an install

This procedure is Claude Desktop. It does not install or accept Claude Code
CLI ([protocol-limits note](library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3). For Claude Code, use [`docs/claude-code-mcp.md`](claude-code-mcp.md).

1. `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-mcpb.ps1`
   → confirm `dist/uoink-<VERSION>.mcpb` exists
   (the script derives `<VERSION>` from the repo `VERSION` file).
2. Double-click it in Claude Desktop → accept the install dir → restart.
3. In Claude, confirm the 29-tool list (25 legacy + the three Phase 4
   library reads + `get_library_activity`), the five `uoink://library/v1/`
   templates, and the four prompts (`consult-library`, `evidence-brief`,
   `whats-new`, `reshelve-review`). A smoke call such as
   `list_recent_uoinks` still works. Bounded library reads
   (`search_library` / `get_library_item`) do not require the resident HTTP
   helper to be running.
4. If it fails, run `python.exe uoink_mcp.py --doctor` from the install dir; the
   `mcp_stdio` self-check drives the same handshake (see
   [`surface-maps/mcp-stdio.md`](surface-maps/mcp-stdio.md)).
