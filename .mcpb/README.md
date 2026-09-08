# Uoink — Claude Desktop MCP bundle

This bundle connects **Claude Desktop** to Uoink's local MCP stdio server in
one click, so you don't have to hand-edit `claude_desktop_config.json`.

It is **Claude Desktop only**. Claude Code CLI 2.1.261 does not recognize,
install, or unpack `.mcpb` files; `claude mcp add bundle.mcpb` fails
([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3). Configure Claude Code with project-scoped stdio JSON instead — see
[`docs/claude-code-mcp.md`](../docs/claude-code-mcp.md). A `.mcpb` package
does not prove Claude Code installation or any current CLI capability.

## Install (Claude Desktop)

1. Install Uoink first from **https://uoink.app/install** (Windows 10/11).
   That install places console `python.exe`, `uoink_mcp.py`, sibling modules,
   and runtime dependencies under `%LOCALAPPDATA%\Uoink` (or the directory you
   chose). You do **not** need the resident HTTP helper running for library
   reads.
2. Double-click `uoink-<version>.mcpb` (or drag it into **Claude Desktop →
   Settings → Extensions**).
3. When prompted for the **Uoink install directory**, accept the default
   (`%LOCALAPPDATA%\Uoink`) unless you installed Uoink somewhere else.
4. Restart Claude Desktop. The 29 stdio tools, five library resource
   templates, and four prompts below appear from the launched child.

## What this bundle is (and isn't)

It's a **thin launcher**. Claude Desktop unpacks the ZIP, prompts for
`user_config`, and writes the rendered `mcpServers` entry into its own config
([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.1, §4.3). At runtime it runs the working stdio command:

```
<install>\python\python.exe  <install>\uoink_mcp.py
```

That command is the **installed console** `python.exe` (never `pythonw.exe`)
with `uoink_mcp.py` as its own argument-array element, so spaces in the
install path stay one token
([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
§4.3; [contract](../docs/library/PHASE4-CONTRACT-2026-09-08.md)).

The bundle itself only carries `manifest.json`, `README.md`, `icon.png`, and
reference copies of the two entry modules so `entry_point` resolves
structurally. It does **not** bundle a second Python runtime or heavy
dependencies (yt-dlp, the MCP SDK, keyring, Whisper). Runtime always uses the
installed copies.

### Thin-launcher prerequisites

| Requirement | Why |
|---|---|
| Installed Uoink tree | Thin launcher; no bundled interpreter. Default `${HOME}/AppData/Local/Uoink` is `%LOCALAPPDATA%\Uoink` on a standard Windows install ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md) §4.3). |
| Console `python.exe` | JSON-RPC stdio needs standard streams. `pythonw.exe` cannot carry the protocol ([contract](../docs/library/PHASE4-CONTRACT-2026-09-08.md)). |
| UTF-8 stdout | The child must emit UTF-8 JSON-RPC on stdout; diagnostics go to stderr. Windows console Python otherwise uses the legacy code page. Claude Code's project config sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` ([docs/claude-code-mcp.md](../docs/claude-code-mcp.md)). |
| No resident HTTP helper for reads | Installing Uoink is enough to run stdio. `uoink_mcp.py` reads local storage directly and does not proxy through the helper. Do not put a helper URL in this configuration. |

If you'd rather configure the server by hand, or use Cursor / Cline / Continue,
see https://uoink.app/developers. For **Claude Code CLI**, do not use this
`.mcpb`; follow [`docs/claude-code-mcp.md`](../docs/claude-code-mcp.md).

## What stdio advertises

The launched child is `uoink_mcp.py`. On stdio it advertises **29 tools**,
**five resource templates**, and **four prompts**. HTTP MCP stays tools-only
and is not what this bundle launches.

Count: **25** legacy tools + Phase 4 `search_library`, `get_library_item`,
`read_library_resource` + Phase 5 `get_library_activity`. The committed
[`.mcpb/manifest.json`](manifest.json) lists those 29 names.

Resources and prompts are advertised on **stdio** (templates under
`uoink://library/v1/`). Claude Desktop can attach listed resources through
its `@` picker. Claude Code CLI 2.1.261 has no native resource reader; that
client uses `read_library_resource(uri)` instead
([docs/claude-code-mcp.md](../docs/claude-code-mcp.md)).

### 29 tools

**Legacy (25)**

| Tool | Role |
|---|---|
| `uoink_video` | Extract a single YouTube video into a Uoink corpus. |
| `uoink_playlist` | Start asynchronous extraction for a YouTube playlist. |
| `get_job_status` | Return the full status object for an async Uoink job. |
| `cancel_job` | Cancel an async Uoink job and leave partial outputs on disk. |
| `list_recent_uoinks` | List recent saved Uoink corpora. |
| `search_uoinks` | Keyword search across saved Uoink markdown corpora. |
| `search_clips` | Full-text search over transcript windows, each hit with a deep link. |
| `get_evidence_card` | Evidence card: metadata, source URL, summary hint, quotable clips. |
| `get_uoink_corpus` | Full markdown corpus for a saved uoink by slug (legacy; not a library overflow fallback). |
| `analyze_comments` | Comment Intelligence on an existing uoink (uses your Anthropic key). |
| `classify_hook` | Classify the hook type for an existing uoink. |
| `get_taxonomy` | Return captured Hook Type taxonomy rows, optionally filtered. |
| `get_citation_map` | Transcript + screenshot citation map for a saved uoink. |
| `get_uoink_health` | Per-section extraction health score for a saved uoink. |
| `find_mentions` | Mentions of an entity across saved uoinks, with timestamped links. |
| `get_transcript_reliability` | Stored transcript reliability spans for a saved uoink. |
| `add_podcast_feed` | Register a podcast RSS or Atom feed, optional Auto-ingest. |
| `list_podcast_feeds` | List registered podcast feeds. |
| `remove_podcast_feed` | Remove a podcast feed and its tracked episode rows. |
| `poll_podcast_feed` | Fetch one podcast feed now and retain newly discovered episodes. |
| `list_podcast_episodes` | List tracked podcast episodes with optional filters. |
| `download_podcast_episode` | Download one episode's MP3 locally with yt-dlp and ffmpeg. |
| `get_whisperx_status` | Report local WhisperX availability and supported models. |
| `transcribe_podcast_episode` | Queue one local podcast transcription; return a durable job id. |
| `episode_to_corpus` | Publish a completed podcast transcript into the local corpus. |

**Phase 4 bounded library reads (3)** — contract `phase4-v1-2026-09-08`

| Tool | Role |
|---|---|
| `search_library` | Bounded clip-first search (default 5, at most 20 hits) with revision-bound follow-up URIs. |
| `get_library_item` | Resolve one saved item (`video_id` or `slug`) and return its Librarian card plus canonical resource URIs. |
| `read_library_resource` | Read one `uoink://library/v1/` URI with the same contents and refusals as `resources/read`. |

**Phase 5 (1)** — contract `phase5-v1`

| Tool | Role |
|---|---|
| `get_library_activity` | Report deterministic library activity, shelf churn, and source observations. |

The six Living Library work-queue tools and the four Phase 3 source-subscription
tools stay HTTP/OpenAPI-only. They are not in this bundle's stdio inventory.

### Five resource templates (`uoink://library/v1/`)

All return `text/markdown`. Canonical URIs come from discovery; do not invent
hashes.

| Template after `uoink://library/v1/` | Meaning |
|---|---|
| `items/{item_key}/cards/{source_revision}/{selection}/{card_hash}` | Default Librarian card, all three bindings checked. |
| `items/{item_key}/excerpts/{source_revision}/{excerpt_id}` | One original excerpt (at most 2,000 code points). |
| `items/{item_key}/corpus/{corpus_revision}/{offset}/{length}` | Bounded original-corpus chunk. |
| `shelves/{shelf_key}/{taxonomy_revision}/{projection_revision}/{shelf_revision}/{offset}` | Shelf definition and a page of current members. |
| `briefs/{date}/{brief_hash}` | One persisted client-produced brief. |

### Four prompts

| Prompt | Arguments |
|---|---|
| `consult-library` | Required `topic`. |
| `evidence-brief` | Required `topic`; optional `since` as UTC `YYYY-MM-DD`. |
| `whats-new` | Optional `days`, canonical decimal 1–30, default `7`. |
| `reshelve-review` | Required `preview_id` (Phase 2 ID grammar). Read-only; does not apply or approve. |

## Bundle format (`manifest_version` 0.4)

Format claims below are from
[PHASE4-PROTOCOL-LIMITS-2026-09-08.md](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
section 4. They are not a Claude Code CLI acceptance claim.

- A `.mcpb` file is a plain **ZIP** archive with `manifest.json` at its
  archive root ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
  §4.1).
- Required root identity fields: `manifest_version` `"0.4"`, `name`,
  `display_name`, SemVer `version`, `description`, `long_description`,
  `author`, `license` ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
  §4.2).
- `server`: `type` `"python"`, `entry_point` `"uoink_mcp.py"`, and
  `mcp_config` `{command, args, env}` interpolating
  `${user_config.uoink_dir}`
  ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
  §4.2, §4.3).
- `user_config.uoink_dir` is a `directory` field (supported types: `string`,
  `boolean`, `directory`, `file`). Its default interpolates `${HOME}`
  ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
  §4.2).
- `compatibility` names `claude_desktop` `>=0.10.0`, `platforms` `["win32"]`,
  and `runtimes.python` `>=3.10,<4`
  ([protocol-limits note](../docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md)
  §4.2). That Desktop range is not Claude Code CLI acceptance.

## Rebuilding

See [`docs/mcpb-bundle.md`](../docs/mcpb-bundle.md) for the Windows/POSIX
build commands, release notes, and the Desktop-versus-CLI boundary. Output
lands in `dist/uoink-<version>.mcpb`.
