# MCP tool annotations

All 32 stdio tools have a title and explicit MCP hints. HTTP tools with the same
names carry identical titles and hints in `uoink_mcp_tools.TOOL_REGISTRY`.

Hints describe successful calls and their possible effects, including queued
work. Idempotent reads can return different results after the library changes.
Capture and feed-fetch operations use `destructiveHint=false` as required by the
3.8.1 brief. Operations that cancel, delete or replace saved analysis,
transcripts or published corpora use `destructiveHint=true`.

| Tool | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Reason |
|---|---|---|---|---|---|---|
| `uoink_video` | Capture video | false | false | false | true | Fetches the requested video and saves a corpus; another capture can fetch new source data. |
| `uoink_playlist` | Capture playlist | false | false | false | true | Fetches a playlist and starts a new capture job. |
| `get_job_status` | Get job status | true | false | true | false | Reads local job state. |
| `cancel_job` | Cancel job | false | true | true | false | Cancels work; repeating cancellation does not restart it. |
| `list_recent_uoinks` | List recent captures | true | false | true | false | Reads saved corpus metadata. |
| `search_uoinks` | Search captures | true | false | true | false | Searches the local library. |
| `search_clips` | Search transcript clips | true | false | true | false | Searches stored transcript windows. |
| `get_evidence_card` | Get evidence card | true | false | true | false | Reads saved metadata and excerpts. |
| `get_uoink_corpus` | Get saved corpus | true | false | true | false | Reads a local Markdown corpus. |
| `analyze_comments` | Analyze comments | false | true | false | true | Calls Anthropic with the saved key and replaces stored comment analysis. |
| `classify_hook` | Classify hook | false | true | false | true | Calls Anthropic with the saved key and replaces stored hook analysis. |
| `get_taxonomy` | Get hook taxonomy | true | false | true | false | Reads stored taxonomy rows. |
| `get_citation_map` | Get citation map | true | false | true | false | Reads stored transcript and screenshot citations. |
| `get_uoink_health` | Get capture health | true | false | true | false | Reads saved extraction health. |
| `find_mentions` | Find entity mentions | true | false | true | false | Searches saved entity mentions. |
| `get_transcript_reliability` | Get transcript reliability | true | false | true | false | Reads stored reliability spans. |
| `add_podcast_feed` | Add podcast feed | false | false | true | true | Registers a unique feed URL and enables future network polling; repeated registration reuses it. |
| `list_podcast_feeds` | List podcast feeds | true | false | true | false | Reads registered feed rows. |
| `remove_podcast_feed` | Remove podcast feed | false | true | true | false | Deletes the feed and tracked episodes; repeating leaves them absent. |
| `poll_podcast_feed` | Poll podcast feed | false | false | false | true | Fetches the feed and records discoveries; repeated polls can find new episodes. |
| `list_podcast_episodes` | List podcast episodes | true | false | true | false | Reads tracked episode rows. |
| `download_podcast_episode` | Download podcast audio | false | false | true | true | Downloads episode audio; reuses an existing nonempty canonical file. |
| `get_whisperx_status` | Get transcription status | true | false | true | false | Inspects local WhisperX availability and settings. |
| `transcribe_podcast_episode` | Transcribe podcast episode | false | true | false | true | Queues transcription that can replace a transcript and download models with consent. |
| `episode_to_corpus` | Publish podcast corpus | false | true | true | false | Publishes deterministic local files and replaces the episode's prior corpus and index snapshot. |
| `get_library_activity` | Get library activity | true | false | true | false | Reads local activity and source observations. |
| `search_library` | Search library | true | false | true | false | Returns bounded local search results. |
| `get_library_item` | Get library item | true | false | true | false | Reads a saved item's evidence card and resource URIs. |
| `read_library_resource` | Read library resource | true | false | true | false | Reads a bounded local library resource. |
| `get_library_brief_input` | Prepare library brief input | true | false | true | false | Reads and hashes brief inputs without acquiring a lease or changing data. |
| `publish_library_brief` | Publish library brief | false | false | true | false | Creates an immutable local brief; submission_key deduplicates retries. |
| `export_cited_range` | Export cited transcript range | true | false | true | false | Returns stored cues and citations without fetching, transcribing or saving. |

The MCPB 0.4 manifest tool schema permits only `name` and `description`.
Titles are therefore advertised by the live MCP servers, not the bundle's tool
inventory. See the [official schema](https://github.com/anthropics/mcpb/blob/main/src/schemas/0.4.ts).

Verify the wire metadata with:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_c01_mcp_stdio.py
```

The test launches this worktree's `uoink_mcp.py`, initializes an MCP session,
lists all tools over stdio, checks the metadata against HTTP and this table,
and calls a local read tool against an isolated empty index.
