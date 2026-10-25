# MCP tool annotations

All 91 stdio tools have a title and explicit MCP hints. HTTP tools with the same
names carry identical titles and hints in `uoink_mcp_tools.TOOL_REGISTRY`.

Hints describe successful calls and their possible effects, including queued
work. Idempotent reads can return different results after the library changes.
Source recapture can replace an existing corpus and metadata, so those capture
tools use `destructiveHint=true`, including queued playlist captures. New notes
and images create separate items. Operations that cancel, delete or replace
saved analysis, transcripts or published corpora also use `destructiveHint=true`.

| Tool | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Reason |
|---|---|---|---|---|---|---|
| `uoink_video` | Capture video | false | true | false | true | Fetches the requested video and saves a corpus; another capture can fetch new source data. Recapture can replace the existing source snapshot. |
| `uoink_playlist` | Capture playlist | false | true | false | true | Fetches a playlist and starts a new capture job. Recapture can replace the existing source snapshot. |
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
| `remove_podcast_feed` | Remove podcast feed | false | true | true | false | Archives and disables a source-linked feed; deletes a legacy unlinked feed and its tracked episodes. Published corpora remain. |
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
| `get_playbook_input` | Prepare research playbook input | true | false | true | false | Reads local research evidence and computes metrics; no model, network or writes. |
| `discover_candidates` | Discover capture candidates | false | false | false | true | Spends confirmed ScrapeCreators credits and saves candidates; requires enabled discovery and agent consent or a dashboard intent. |
| `queue_discovered` | Queue discovered posts | false | false | true | true | Enqueues selected URLs for normal capture; skips existing picks and spends no ScrapeCreators credits. |
| `list_library_work` | List library work | false | true | false | false | Lists work and expires stale leases, updating their stored state. |
| `claim_library_work` | Claim library work | false | true | false | false | Claims, renews, releases or cancels leases; another claim can lease more work. |
| `submit_library_result` | Submit library result | false | false | true | false | Stores a validated result; submission_key deduplicates retries. |
| `apply_reshelving` | Apply reshelving | false | true | false | false | Creates a new preview or replaces labels from an approved preview; apply is off by default. |
| `pin_shelf` | Pin library shelf | false | true | true | false | Changes user shelf decisions with a dashboard intent; operation_key deduplicates retries. |
| `undo_library_apply` | Undo library apply | false | true | true | false | Replays an inverse label operation with a dashboard intent and a deduplicated operation_key. |
| `list_sources` | List standing sources | true | false | true | false | Reads source summaries and consent states. |
| `register_source` | Register standing source | false | false | true | true | Registers metadata detection for future network polling with capture off; duplicates reuse the source. |
| `source_status` | Get source status | true | false | true | false | Reads source observations and reservations without starting work. |
| `set_source_consent` | Set source consent | false | true | true | true | Enables future captures or cancels unstarted reservations with a dashboard intent; receipts deduplicate retries. |
| `analyze_self_channel` | Analyze own channel | true | false | true | false | Reads local channel performance and format history. |
| `get_schema_version` | Get storage schema version | true | false | true | false | Reads local schema versions. |
| `get_user_role` | Get user role | true | false | true | false | Reads the saved role and dashboard emphasis. |
| `set_user_role` | Set user role | false | true | true | false | Replaces the saved role; repeating the same role leaves that choice unchanged. |
| `check_live_status` | Check live video status | true | false | true | true | Fetches remote video metadata without capturing it. |
| `add_monitored_playlist` | Add monitored playlist | false | false | true | true | Registers a unique playlist for future polling; duplicates reuse it. |
| `list_monitored_playlists` | List monitored playlists | true | false | true | false | Reads registered playlists. |
| `remove_monitored_playlist` | Remove monitored playlist | false | true | true | false | Removes or archives a playlist and its monitoring; repeating leaves it removed. |
| `poll_monitored_playlist` | Poll monitored playlist | false | false | false | true | Fetches new observations under source consent; scheduled captures need the helper. |
| `list_monitored_playlist_events` | List playlist events | true | false | true | false | Reads stored playlist discoveries. |
| `get_user_taste` | Get taste memory | false | false | true | false | Reads taste memory and regenerates the local file if absent, including a configured vault mirror. |
| `get_user_memory` | Get user memory | false | false | true | false | Reads user memory and creates its local skeleton if absent. |
| `update_user_taste` | Update taste memory | false | true | true | false | Replaces one taste section and regenerates local memory and a configured vault mirror. |
| `get_engagement_signal` | Get engagement signal | true | false | true | false | Reads local engagement scores and event counts. |
| `classify_facets` | Classify item facets | false | true | true | false | Replaces supplied facet values and adds deduplicated tags using the agent's classifications. |
| `query_by_facets` | Query item facets | true | false | true | false | Reads local items matching facet filters. |
| `get_facet_taxonomy` | Get facet taxonomy | true | false | true | false | Returns the supported facet enums. |
| `assemble_workspace` | Assemble workspace | false | true | true | false | Reads a corpus slice and can replace the saved workspace's selected items. |
| `critique_against_corpus` | Critique against corpus | false | false | false | false | Returns grounding or appends the agent's supplied critique to the workspace log. |
| `list_workspaces` | List workspaces | true | false | true | false | Reads saved workspaces. |
| `get_workspace` | Get workspace | true | false | true | false | Reads one workspace and its critique log. |
| `extract_claims` | Extract claims | false | false | false | false | Stores agent-supplied claims; another call can add claims. |
| `verify_claim` | Record claim evidence | false | true | false | false | Stores evidence and updates a claim's alignment and status without deciding truth. |
| `list_claims` | List claims | true | false | true | false | Reads saved claims. |
| `get_claim` | Get claim | true | false | true | false | Reads one claim with its evidence. |
| `generate_script` | Generate script | false | false | false | false | Returns grounding or stores an agent-supplied script as a new row. |
| `revise_script` | Revise script | false | false | false | false | Returns revision grounding or saves a new script version. |
| `get_shot_list` | Generate and save shot list | false | true | true | false | Derives a deterministic shot list and replaces the script's prior shot list. |
| `list_scripts` | List scripts | true | false | true | false | Reads stored scripts. |
| `get_script` | Get script | true | false | true | false | Reads one script and its saved shots and citations. |
| `write_tweet` | Write tweet or thread | false | false | false | true | Returns grounding or saves a draft; explicit direct generation can call Anthropic with the saved key. |
| `write_blog` | Write blog | false | false | false | true | Returns grounding or saves a blog draft; explicit direct generation can call Anthropic with the saved key. |
| `list_writing_pieces` | List writing pieces | true | false | true | false | Reads saved writing pieces. |
| `get_writing_piece` | Get writing piece | true | false | true | false | Reads one saved writing piece. |
| `add_style_anchor` | Add style anchor | false | false | false | true | Saves a style anchor and can fetch its URL with private-network checks. |
| `list_style_anchors` | List style anchors | true | false | true | false | Reads saved style anchors. |
| `remove_style_anchor` | Remove style anchor | false | true | true | false | Deletes a style anchor; repeating leaves it absent. |
| `uoink_url` | Capture URL | false | true | false | true | Fetches the requested URL through the universal extractor and saves its corpus. Recapture can replace the existing source snapshot. |
| `uoink_note` | Save note | false | false | false | false | Saves a local text note; repeated calls can create additional notes. |
| `uoink_image` | Save image | false | false | false | false | Decodes supplied image bytes and saves a local image capture. |
| `uoink_x` | Capture X post | false | true | false | true | Fetches and saves X text when X text capture is enabled. Recapture can replace the existing source snapshot. |
| `uoink_page` | Capture web page | false | true | false | true | Fetches an allowed public page and saves it; private-network checks remain enforced. Recapture can replace the existing source snapshot. |
| `uoink_reddit_thread` | Capture Reddit thread | false | true | false | true | Fetches a public Reddit thread and saves filtered comments. Recapture can replace the existing source snapshot. |
| `list_allowed_sites` | List allowed sites | true | false | true | false | Reads the saved site allowlist. |
| `add_allowed_site` | Add allowed site | false | false | true | true | Adds a unique host pattern, authorizing later page fetches; repeats reuse it. |
| `remove_allowed_site` | Remove allowed site | false | true | true | false | Removes a site pattern; repeating leaves it absent. |

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
