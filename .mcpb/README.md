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
4. Restart Claude Desktop. The 91 stdio tools, five library resource
   templates, and nine prompts below appear from the launched child.

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

The launched child is `uoink_mcp.py`. On stdio it advertises **91 tools**,
**five resource templates**, and **nine prompts**. HTTP MCP stays tools-only
and is not what this bundle launches.

The committed [manifest](manifest.json) lists all 91 names. The previous 35
remain first in `tools/list`. Set `UOINK_MCP_TOOLSET=core` for clients with tool
caps, including Cursor. Unknown values warn on stderr and use full.
Claude Desktop users should reinstall the 3.11.2 `.mcpb` and restart Desktop
to get the expanded inventory. Consent gates are unchanged.

Resources and prompts are advertised on **stdio** (templates under
`uoink://library/v1/`). Claude Desktop can attach listed resources through
its `@` picker. Claude Code CLI 2.1.261 has no native resource reader; that
client uses `read_library_resource(uri)` instead
([docs/claude-code-mcp.md](../docs/claude-code-mcp.md)).

### 91 tools

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

**Client-run briefs and cited export (3)**

| Tool | Role |
|---|---|
| `get_library_brief_input` | Prepare bounded input for a client-run brief without changing the library. |
| `publish_library_brief` | Persist an immutable local brief; deduplicate retries by submission key. |
| `export_cited_range` | Read stored transcript cues with citations, speakers and revision pins. |

**Phase 5 (1)** — contract `phase5-v1`

| Tool | Role |
|---|---|
| `get_library_activity` | Report deterministic library activity, shelf churn, and source observations. |

**Research playbooks and discovery (3)**

| Tool | Role |
|---|---|
| `get_playbook_input` | Prepare a cited local packet for one of five research playbooks. |
| `discover_candidates` | Plan or run opt-in ScrapeCreators discovery with explicit credit confirmation. |
| `queue_discovered` | Send up to ten selected discovery results through the normal capture queue. |

**Additional full-mode tools (56)**

| Tool | Role |
|---|---|
| `list_library_work` | List library work. |
| `claim_library_work` | Claim library work. |
| `submit_library_result` | Submit library result. |
| `apply_reshelving` | Apply reshelving. |
| `pin_shelf` | Pin library shelf. |
| `undo_library_apply` | Undo library apply. |
| `list_sources` | List standing sources. |
| `register_source` | Register standing source. |
| `source_status` | Get source status. |
| `set_source_consent` | Set source consent. |
| `analyze_self_channel` | Analyze own channel. |
| `get_schema_version` | Get storage schema version. |
| `get_user_role` | Get user role. |
| `set_user_role` | Set user role. |
| `check_live_status` | Check live video status. |
| `add_monitored_playlist` | Add monitored playlist. |
| `list_monitored_playlists` | List monitored playlists. |
| `remove_monitored_playlist` | Remove monitored playlist. |
| `poll_monitored_playlist` | Poll monitored playlist. |
| `list_monitored_playlist_events` | List playlist events. |
| `get_user_taste` | Get taste memory. |
| `get_user_memory` | Get user memory. |
| `update_user_taste` | Update taste memory. |
| `get_engagement_signal` | Get engagement signal. |
| `classify_facets` | Classify item facets. |
| `query_by_facets` | Query item facets. |
| `get_facet_taxonomy` | Get facet taxonomy. |
| `assemble_workspace` | Assemble workspace. |
| `critique_against_corpus` | Critique against corpus. |
| `list_workspaces` | List workspaces. |
| `get_workspace` | Get workspace. |
| `extract_claims` | Extract claims. |
| `verify_claim` | Record claim evidence. |
| `list_claims` | List claims. |
| `get_claim` | Get claim. |
| `generate_script` | Generate script. |
| `revise_script` | Revise script. |
| `get_shot_list` | Generate shot list. |
| `list_scripts` | List scripts. |
| `get_script` | Get script. |
| `write_tweet` | Write tweet or thread. |
| `write_blog` | Write blog. |
| `list_writing_pieces` | List writing pieces. |
| `get_writing_piece` | Get writing piece. |
| `add_style_anchor` | Add style anchor. |
| `list_style_anchors` | List style anchors. |
| `remove_style_anchor` | Remove style anchor. |
| `uoink_url` | Capture URL. |
| `uoink_note` | Save note. |
| `uoink_image` | Save image. |
| `uoink_x` | Capture X post. |
| `uoink_page` | Capture web page. |
| `uoink_reddit_thread` | Capture Reddit thread. |
| `list_allowed_sites` | List allowed sites. |
| `add_allowed_site` | Add allowed site. |
| `remove_allowed_site` | Remove allowed site. |

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

### Nine prompts

| Prompt | Arguments |
|---|---|
| `consult-library` | Required `topic`. |
| `evidence-brief` | Required `topic`; optional `since` as UTC `YYYY-MM-DD`. |
| `whats-new` | Optional `days`, canonical decimal 1–30, default `7`. |
| `reshelve-review` | Required `preview_id` (Phase 2 ID grammar). Read-only; does not apply or approve. |
| `outlier-posts` | Required `author`; optional `platform`, `since`. |
| `transcript-intel` | Exactly one of `video_ids` (up to 8), `topic`, or `author`; optional `since`. |
| `comment-mining` | Exactly one of `video_ids` (up to 10) or `author`; optional `lens` (`voc` or `demand`). |
| `creator-teardown` | Required `author`; optional `platform`. Needs at least three saved captures. |
| `repurpose-pack` | Required `video_ids` (1–5); optional `kinds` (defaults to `tweet,thread`). |

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

## Privacy

Corpora, screenshots, podcast audio, transcripts, the library index and logs
stay on your computer. Capture fetches the source you request; enabled podcast
watches poll feeds and Auto-ingest can download episodes. Truncated X posts may
use FxTwitter to retrieve full text. Transcription can download models with
consent; **Check now** contacts GitHub.

Optional Anthropic features require your own key and send relevant source text.
Comment Intelligence, Hook Type classification and entity extraction are off by
default. Agent-requested analysis also requires your key. Content returned to
Claude is handled under Claude's policy.

Usage sharing is off by default. If you turn on "Share anonymous usage counts"
in the dashboard, Uoink sends daily tool, known-client, transport, capture and
search counts to usage.uoink.app, with a random install ID and app and system
versions. Reports never contain content, URLs, titles, paths, search text or
account details. Settings shows the next payload and the last ten sent payloads.

Read the [Uoink privacy policy](https://uoink.app/privacy).

## Rebuilding

See [`docs/mcpb-bundle.md`](../docs/mcpb-bundle.md) for the Windows/POSIX
build commands, release notes, and the Desktop-versus-CLI boundary. Output
lands in `dist/uoink-<version>.mcpb`.
