# Uoink v2 MCP server

Status: Sprint 4 backend implemented  
Schema version: 2.1.0  
SDK: official Model Context Protocol Python SDK, `mcp==2.3.0` and `mcp-types==2.3.0`\
Transports: stdio, plus an experimental authenticated local HTTP JSON-RPC helper

## Overview

Uoink serves the same tool registry over both MCP transports:

- Supported stdio registry: **92 tools**.
- Local HTTP/OpenAPI registry: **92 tools**.

Stdio uses the SDK's native dual-era runner. Existing clients can initialize
with `2024-11-05`, `2025-03-26`, `2025-06-18` or `2025-11-25`, then send
`notifications/initialized`. Unsupported handshake versions negotiate
`2025-11-25`. Modern clients can start with `server/discover` or a normal
request such as `tools/list`; every modern request carries this envelope:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}
```

The first request selects the era for that connection. `initialize` selects
legacy even when it carries modern metadata. Changing eras requires a new
connection. Modern results include `resultType` and server identity in `_meta`.
Cacheable results use `ttlMs: 0` and `cacheScope: "private"`. Legacy responses
retain their earlier shapes. `/mcp/v1` retains its legacy HTTP contract and
does not advertise 2026-07-28 HTTP support.

| Stdio refusal | Code or result |
|---|---|
| Malformed JSON or duplicate keys | Bounded null-ID error, `-32700` |
| Invalid envelope or ID, oversized input, modern request on a legacy connection | `-32600` |
| Unknown method | `-32601`, with the method name in error data |
| Malformed arguments or missing/malformed modern metadata | `-32602` |
| Unsupported modern version or initialize on a modern connection | `-32022` |
| Missing/deleted resource | Legacy `-32002`; modern `-32602` with the URI and domain error data |
| Tool domain refusal | `CallToolResult` with `isError: true` and the existing text envelope |

These refusals leave the connection usable. Accepted cancellation sends no
response and releases admission when the operation settles. Ordinary completed
frames have a 65,536-byte limit before the newline; genuine `tools/list`
responses have 262,144 bytes. The incoming method selects that allowance.

Claude Desktop (.mcpb), Claude Code and Cursor use `uoink_mcp.py` over stdio.
It advertises every registry tool with the same name, description, input schema,
title and safety hints as HTTP. Three registry schemas use a top-level `oneOf` (`claim_library_work`, `apply_reshelving`, `set_source_consent`). Claude Code and the Anthropic API reject that shape and Claude Code then shows none of the server's tools, so both stdio and HTTP MCP advertise each as one object whose properties merge the variants. The server still validates every call against the exact frozen registry schema. This includes URL/page/X/Reddit/note/image
capture, writing, scripts, claims, workspaces, facets, monitored playlists,
taste and memory, allowed sites, sources and the Library work queue.
No registry tools are excluded from stdio.

### Tool-capped clients

`UOINK_MCP_TOOLSET=full` is the default. Set `UOINK_MCP_TOOLSET=core` in the
client's MCP server environment to keep the previous **35 tools**. The original
35 remain first, in their original order, in full mode. Cursor is reported to
pass only the first 40 tools to its agent; core mode also helps other clients
with a tool cap. Restart the MCP connection after changing the environment.
Unknown values emit a stderr warning and use full.

For example, add `"UOINK_MCP_TOOLSET": "core"` to the `env` object in Cursor's
`mcpServers.uoink` configuration. Core mode rejects calls to tools outside its
advertised set. Resources and prompts are unchanged in either mode.

### Consent and execution

Both transports dispatch through `uoink_mcp_tools.call_tool`. Dashboard-minted
intent tokens remain required for `pin_shelf`, `undo_library_apply` and
`set_source_consent`; stdio derives the trusted session from the same local
helper token, never from tool arguments. No MCP tool can mint an intent.
Library apply stays off by default. Discovery still requires enabled discovery,
credit confirmation, a daily cap and explicit agent consent. Its dashboard
intents live only in the HTTP process and bind to that request origin and
session, so stdio cannot redeem them. Enable agent discovery in Settings to
use discovery over stdio; supplying an origin or session in tool JSON grants
no authority.

Paid Anthropic generation still requires the explicit generation request and
saved key. Whisper downloads still require approval. Rate limits, private-network
fetch checks, path confinement and service error scrubbing use the same handlers.
Registry tools run one at a time on the stdio event loop, as in v3.9.1, because they share
the Index connection with Library reads; a long capture or model call holds the session
until it returns. Paid discovery runs in a worker thread so other requests and cancellation
still answer.
The existing bounded Library tools keep their two-second deadline, response
budget and AZ-5h admission lifetime through final JSON-RPC serialization.
Only the server-generated tool inventory has a larger 256 KiB frame cap so all
91 schemas fit; inbound requests and tool results retain their existing caps.
Work-queue mutations use their service's lease, transaction and operation-key
bounds; they do not inherit a read timeout that could abandon a committed write.

Local reads and synchronous captures work without the resident HTTP helper.
Monitored playlist polling returns an actionable "Open Uoink first" error when
the helper is down, because subsequent scheduled captures need its workers.
Registering sources and playlists saves local configuration; automatic detection
and capture run while Uoink is open. Discovery picks enter the durable queue;
open Uoink to process them. Stdio never probes an HTTP port for readiness.
The HTTP JSON-RPC surface at `/mcp/v1` remains experimental.

## Tool naming

In v2.1 the six brand-carrying tools were renamed `yoink_*` → `uoink_*`.
Their compatibility window ended with v2.5. Uoink v3 registers and accepts
only the canonical names, so clients using an old name receive
`tool not found`.

| Removed name | Canonical name |
|---|---|
| `yoink_video` | `uoink_video` |
| `yoink_playlist` | `uoink_playlist` |
| `list_recent_yoinks` | `list_recent_uoinks` |
| `search_yoinks` | `search_uoinks` |
| `get_yoink_corpus` | `get_uoink_corpus` |
| `get_yoink_health` | `get_uoink_health` |

The original eight brand-neutral tools are unchanged: `get_job_status`, `cancel_job`,
`analyze_comments`, `classify_hook`, `get_taxonomy`, `get_citation_map`,
`find_mentions`, and `get_transcript_reliability`.

**HTTP auth header:** the canonical header is `X-Uoink-Token`. The legacy
`X-Yoink-Token` header is still accepted on the experimental HTTP JSON-RPC
transport because installed extension builds still use it. That header
compatibility is separate from the removed MCP tool aliases.

## Compatibility matrix

This is the launch-facing compatibility claim. Keep it honest: only clients Ryan smoke-tests before v2 launch are marked officially tested.

| Client | Status | Transport | Notes |
|---|---|---|---|
| Claude Desktop | Officially tested | stdio | Smoke-tested by Ryan before v2 launch. |
| Cursor | Officially tested | stdio | Smoke-tested by Ryan before v2 launch. |
| ChatGPT Desktop | Should work, community-reported | stdio | Standard stdio MCP; not smoke-tested by Ryan. |
| Continue | Should work, community-reported | stdio | Standard stdio MCP; not smoke-tested by Ryan. |
| Cline | Should work, community-reported | stdio | Standard stdio MCP; not smoke-tested by Ryan. |
| Other MCP-compatible clients | Generic stdio fallback | stdio | Use the generic stdio snippet; not individually certified. |

HTTP JSON-RPC is available for local clients that prefer HTTP, but it is experimental and not counted as an officially tested launch transport.

## Transport model

### Stdio

Stdio is the default path for Claude Desktop, ChatGPT Desktop, Cursor, Continue, Cline, and most local-agent clients.

Installed Windows command:

```json
{
  "mcpServers": {
    "uoink": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\Uoink\\python\\python.exe",
      "args": ["C:\\Users\\<you>\\AppData\\Local\\Uoink\\uoink_mcp.py"]
    }
  }
}
```

Portable command, in Uoink releases after 3.12.0. It needs the `uoink` command on the client's PATH and starts the same server. On Windows, a client that cannot start `.cmd` files uses `"command": "cmd"` with `"args": ["/c", "uoink", "mcp"]`. See [Connect your agent](connect-your-agent.md#one-launch-command-for-any-mcp-client).

```json
{
  "mcpServers": {
    "uoink": {
      "command": "uoink",
      "args": ["mcp"]
    }
  }
}
```

Dev command:

```json
{
  "mcpServers": {
    "uoink": {
      "command": "python",
      "args": ["C:\\Users\\<you>\\OneDrive\\Desktop\\Yoink-codex-v2\\uoink_mcp.py"]
    }
  }
}
```

Auth: none. The MCP client launched the subprocess, so the local process boundary is the trust boundary. The tools still validate URLs, slugs, and job IDs before touching disk or the network.

### Experimental HTTP JSON-RPC

The existing helper server also exposes an experimental local HTTP JSON-RPC helper:

```text
http://127.0.0.1:5179/mcp/v1
```

Auth: `X-Uoink-Token: <token>` is required on every HTTP JSON-RPC request.
The helper still accepts the legacy `X-Yoink-Token` header for installed
extension compatibility; this does not restore removed tool names.
`GET /mcp/v1/config` returns config metadata for setup.html and is also
token-gated.

HTTP endpoints:

- `POST /mcp/v1/initialize`
- `POST /mcp/v1/tools/list`
- `POST /mcp/v1/tools/call`
- `POST /mcp/v1` with JSON-RPC `method` set to `initialize`, `tools/list`, `tools/call`, or `ping`
- `GET /mcp/v1/sse` emits a lightweight one-shot `endpoint` event pointing clients at `/mcp/v1`

The HTTP wrapper covers the JSON-RPC POST surface and returns MCP-style JSON-RPC envelopes. Tool call results include both text content and `structuredContent` for clients that support it. It is not a spec-complete SSE or Streamable HTTP implementation; strict HTTP MCP clients may require future transport work. For launch, stdio is the supported path.

## Client config snippets

The installed setup page generates copyable snippets using the actual install path and current token. Do not hand-edit these examples unless you are in dev mode.

Claude Desktop / Cursor:

```json
{
  "mcpServers": {
    "uoink": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\Uoink\\python\\python.exe",
      "args": ["C:\\Users\\<you>\\AppData\\Local\\Uoink\\uoink_mcp.py"]
    }
  }
}
```

Generic HTTP:

```json
{
  "url": "http://127.0.0.1:5179/mcp/v1",
  "headers": {
    "X-Uoink-Token": "<token from setup.html>"
  }
}
```

## Tool reference

All tool names are vendor-neutral, snake_case, and action-first.

### uoink_video

Extract a single YouTube video into a Uoink corpus.

Parameters:

```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "interval": 30
}
```

Return shape:

```json
{
  "ok": true,
  "slug": "video-slug",
  "folder": "C:\\Users\\Ryan\\Desktop\\Uoink\\Topic\\video-slug",
  "corpus_md": "# Video title\n...",
  "screenshots": ["C:\\Users\\Ryan\\Desktop\\Uoink\\Topic\\video-slug\\screenshots\\shot_0001.jpg"]
}
```

Errors:

- `{ "ok": false, "error": "url required" }`
- `{ "ok": false, "error": "URL must be a youtube.com or youtu.be video link" }`
- `{ "ok": false, "error": "<friendly extraction error>" }`

Rate limit: 5 calls/minute per process.

### uoink_playlist

Start async extraction for a YouTube playlist.

Parameters:

```json
{
  "url": "https://www.youtube.com/playlist?list=PLexample123",
  "interval": 30
}
```

Return shape:

```json
{
  "ok": true,
  "job_id": "job_20260511_120000_a1b2c3"
}
```

Errors:

- `{ "ok": false, "error": "playlist URL invalid" }`
- `{ "ok": false, "error": "yt-dlp playlist preview failed" }`
- `{ "ok": false, "error": "playlist has no videos" }`

Rate limit: 5 calls/minute per process.

### get_job_status

Return a full playlist job object. Shape is identical to `GET /jobs/<id>` in `docs/v2-api.md`.

Parameters:

```json
{ "job_id": "job_20260511_120000_a1b2c3" }
```

Errors:

- `{ "ok": false, "error": "job id invalid" }`
- `{ "ok": false, "error": "job not found" }`

### cancel_job

Cancel a running async job. Shape is identical to `POST /jobs/<id>/cancel`.

Parameters:

```json
{ "job_id": "job_20260511_120000_a1b2c3" }
```

Errors:

- `{ "ok": false, "error": "job id invalid" }`
- `{ "ok": false, "error": "job not found" }`
- `{ "ok": false, "error": "job is already finished" }`
- `{ "ok": false, "error": "job cancel failed" }`

### list_recent_uoinks

List recent saved Uoink corpora.

Parameters:

```json
{ "limit": 20 }
```

Return shape:

```json
{
  "ok": true,
  "yoinks": [
    {
      "slug": "video-slug",
      "title": "Video title",
      "folder": "C:\\Users\\Ryan\\Desktop\\Uoink\\Topic\\video-slug",
      "yoinked_at": "2026-05-11T10:15:00"
    }
  ]
}
```

`yoinks` and each item's `yoinked_at` are frozen legacy wire names retained
for client compatibility. New integrations should treat them as stable,
opaque response keys; product copy and human-readable messages use Uoink.

### search_uoinks

Keyword search across saved Uoink markdown corpora.

`match` is optional: `"forgiving"` (default) drops common English words and
matches any remaining word; `"strict"` requires every word, as before.
Both treat punctuation and FTS operators as text and prefix-match the last
word. If all words are stopwords, forgiving search keeps them. Forgiving
results put an exact title first, ignoring case and punctuation, then hits
with every useful word, then partial hits. BM25 orders hits within each group.
Forgiving `score` values are scaled relevance scores: higher is better. They
include coverage and title bonuses and are not raw BM25 magnitudes. Do not
compare their magnitudes with strict, semantic, or hybrid scores.
Scores retain full floating-point precision. With `b = -BM25`, the lexical
component is `0.001 * b / (1 + b)`, plus `0.001` for complete term coverage
and `0.002` for an exact title. Small differences still determine ordering;
rounding to four decimal places would erase many of them.

Results also carry `video_id` and, when source text is available, an optional
`passage`. Quote `passage.text`: `snippet` may contain ellipses. A passage has
either a stored `clip_id` with `start` and `end` in seconds, or `char_start`
and `char_end` (exclusive) in the indexed `content` field. These are Unicode
character offsets, not byte offsets. `timing` describes the stored timing.
Search results include `passage_verified`. When it is `false`, `citation_reason`
explains why no passage, span, or timestamp was returned. A title or metadata
match can still be useful for discovery without supplying a quotable passage.
Keyword passages contain matched text. Semantic passages are the stored chunks
that produced the matches, checked against the current source. Hybrid results
use either verified form. These rules apply to MCP and HTTP search responses.
When a semantic chunk comes from a source with no body text, its offsets refer
to the title and `passage.field` is `"title"`.
Large forgiving clip searches first rank a bounded source candidate pool
(`max(32, limit)` sources), then rank those sources' matching clips.
Small or sparse source pools also search clips whose text is absent from the
source body. `search_library` counts terms across candidate sources' clips
while citing one matching clip, which may contain only some of the terms.
These clip results are a ranked selection, not an exhaustive source listing.

Parameters:

```json
{ "query": "creator strategy", "limit": 10 }
```

Return shape:

```json
{
  "ok": true,
  "results": [
    {
      "slug": "video-slug",
      "title": "Video title",
      "snippet": "...matching markdown text...",
      "score": 4
    }
  ]
}
```

Errors:

- `{ "ok": false, "error": "query required" }`

### search_clips

Search merged transcript windows (45-120 s; a single long source cue keeps
coarse timing and is marked `timing: coarse`) and return a deep link to each
matching moment. Optional `video_id` and `channel` fields narrow the search.
Available on stdio and HTTP/OpenAPI since 2026-09-04 (run E); both call the
same handler.

Optional `match: "forgiving" | "strict"` uses the same defaults and ranking
as `search_uoinks`. Each result includes its stored `clip_id`, `video_id`,
verbatim `text`, and `start`/`end` in seconds where timing exists.

Parameters:

```json
{ "query": "loop engineering", "limit": 20, "channel": "Example channel" }
```

Return shape:

```json
{
  "ok": true,
  "results": [
    {
      "video_id": "abc123DEF45",
      "slug": "video-slug",
      "title": "Video title",
      "channel": "Example channel",
      "start": 64.2,
      "end": 112.0,
      "text": "The matching transcript window...",
      "deep_link": "https://youtube.com/watch?v=abc123DEF45&t=64s",
      "timing": "source_cues",
      "score": 7.3021
    }
  ]
}
```

Errors:

- `{ "ok": false, "error": "query required" }`

### get_evidence_card

Return one item's metadata and up to 20 clips spread across its timeline.
Resolve the item by `slug` or `video_id`; `n_clips` defaults to 10 for the
`full` profile and 6 for `librarian`. Available on stdio and HTTP/OpenAPI
since 2026-09-04 (run E); both call the same handler.

Parameters:

```json
{ "slug": "video-slug", "profile": "full", "n_clips": 10 }
```

`profile` is `full` (default: untruncated clips) or `librarian` (bounded: at
most 6 excerpts of 240 characters plus a total serialized-byte budget, with
truncation markers). The result includes `video_id`, `slug`, `title`,
`channel`, `platform`, `source_type`, `topic`, `yoinked_at`, `url`,
`summary_hint`, `profile`, `evidence_kind`, `excerpts`, `clips`,
`clip_count`, and the total character count across all clips. Every returned
clip has `start`, `end`, `text`, `deep_link`, and `timing`.

Errors:

- `{ "ok": false, "error": "slug or video_id required" }`
- `{ "ok": false, "error": "uoink not found" }`

### get_uoink_corpus

Return the full markdown corpus for a saved uoink.

Parameters:

```json
{ "slug": "video-slug" }
```

Return shape:

```json
{
  "ok": true,
  "corpus_md": "# Video title\n...",
  "folder": "C:\\Users\\Ryan\\Desktop\\Uoink\\Topic\\video-slug",
  "video_id": "abc123DEF45",
  "video_url": "https://www.youtube.com/watch?v=abc123DEF45",
  "source_url": "https://www.youtube.com/watch?v=abc123DEF45",
  "citations": [
    {
      "video_id": "abc123DEF45",
      "kind": "transcript_chunk",
      "seq": 0,
      "timestamp_start": 0.0,
      "timestamp_end": 6.2,
      "text": "Opening transcript chunk...",
      "file_path": null,
      "youtube_deep_link": "https://youtube.com/watch?v=abc123DEF45&t=0s",
      "source_url": "https://youtube.com/watch?v=abc123DEF45&t=0s",
      "source_deep_link": "https://youtube.com/watch?v=abc123DEF45&t=0s"
    }
  ]
}
```

`video_id`, `video_url`, `source_url`, and `citations` are additive fields.
`video_url` is populated only for YouTube items. `source_url` carries the real
public source page for any supported source type. These fields are `null` when
the sidecar does not identify a usable source. `citations` is best-effort and
may be empty if the uoink has not been indexed yet.

Errors:

- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "corpus read failed: ..." }`

### analyze_comments

Run Comment Intelligence on an existing uoink and return structured results. Requires a configured Anthropic API key.

Parameters:

```json
{ "slug": "video-slug" }
```

Return shape:

```json
{
  "ok": true,
  "top_themes": [],
  "mentioned_products": [],
  "notable_disagreements": []
}
```

Errors:

- `{ "ok": false, "error": "anthropic key not configured" }`
- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "not enough comments to analyze" }`
- `{ "ok": false, "error": "<Anthropic or parsing error>" }`

Rate limit: 10 calls/minute per process.

### classify_hook

Run Hook Type classification on an existing uoink and return the category, explanation, confidence, and calibration count. Requires a configured Anthropic API key.

Parameters:

```json
{ "slug": "video-slug" }
```

Return shape:

```json
{
  "ok": true,
  "hook_type": "curiosity_gap",
  "hook_explanation": "The opening withholds the answer while promising a counter-intuitive payoff.",
  "confidence": 4,
  "similar_corrections_used": 2
}
```

`confidence` is the classifier's self-score from 1-5. `similar_corrections_used` is `0` when no past corrections were found, or the number of same-channel, same-topic, or recent correction anchors injected into the prompt.

After the user corrects a classification through `POST /taxonomy/correct`, future calls to `classify_hook` on similar videos receive those corrections as few-shot calibration anchors. The classifier becomes more aligned with the user's judgment over time.

Errors:

- `{ "ok": false, "error": "anthropic key not configured" }`
- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "<Anthropic or parsing error>" }`

Rate limit: 10 calls/minute per process.

### get_taxonomy

Return Hook Type taxonomy rows captured from successful classifications. This is a read-only tool intended for future taxonomy viewing, CSV export, and retention controls.

Parameters:

```json
{
  "channel": "Example Channel",
  "hook_type": "curiosity_gap",
  "limit": 50
}
```

All fields are optional. `channel` is an exact channel-name filter, compared case-insensitively. `hook_type` must be one of the Hook Type categories. `limit` defaults to 50 and is clamped to 1-500.

Return shape:

```json
{
  "ok": true,
  "taxonomy": [
    {
      "video_id": "abc123DEF45",
      "hook_type": "curiosity_gap",
      "hook_explanation": "The opening withholds the payoff while promising a counter-intuitive reveal.",
      "channel": "Example Channel",
      "title": "How creators build durable content systems",
      "classified_at": "2026-05-12T10:30:00"
    }
  ]
}
```

Rows sort by `classified_at` descending.

Errors:

- `{ "ok": false, "error": "channel must be a string" }`
- `{ "ok": false, "error": "hook_type must be a string" }`
- `{ "ok": false, "error": "hook_type invalid" }`

### get_citation_map

Return pre-computed transcript and screenshot citations for a saved uoink.
Each citation includes its public source URL and a source-aware timestamp link
when one is available, so agents can cite the source without reparsing Markdown.

Parameters:

```json
{ "slug": "video-slug" }
```

Return shape:

```json
{
  "ok": true,
  "video_id": "abc123DEF45",
  "transcript_citations": [
    {
      "seq": 0,
      "timestamp_start": 0.0,
      "timestamp_end": 6.2,
      "text": "Opening transcript chunk...",
      "source_url": "https://www.youtube.com/watch?v=abc123DEF45",
      "deep_link": "https://youtube.com/watch?v=abc123DEF45&t=0s"
    }
  ],
  "screenshot_citations": [
    {
      "seq": 0,
      "timestamp": 30.0,
      "file_path": "C:\\Users\\Ryan\\Desktop\\Uoink\\Topic\\video-slug\\screenshots\\shot_0001.jpg",
      "source_url": "https://www.youtube.com/watch?v=abc123DEF45",
      "deep_link": "https://youtube.com/watch?v=abc123DEF45&t=30s"
    }
  ]
}
```

Fields:

- `transcript_citations` contains one entry per transcript chunk from the sidecar.
- `screenshot_citations` contains one entry per screenshot from the sidecar.
- `seq` preserves original order within each citation kind.
- `deep_link` preserves the YouTube watch URL for YouTube items. Podcast
  episodes use the retained episode page with `#t=<seconds>`.

Errors:

- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "uoink has no video_id" }`
- `{ "ok": false, "error": "rate limit exceeded: max 60/minute" }`

Rate limit: 60 calls/minute per process.

### get_uoink_health

Return the extraction health score for a saved uoink. This is the same five-field health dict the popup renders in Recent uoinks.

Parameters:

```json
{ "slug": "video-slug" }
```

Return shape:

```json
{
  "ok": true,
  "video_id": "abc123DEF45",
  "health": {
    "transcript": "ok",
    "screenshots": "ok",
    "comments": "ok",
    "hook": "completed",
    "comment_intelligence": "skipped"
  }
}
```

Health fields:

| Field | Meaning |
|---|---|
| `transcript` | Transcript extraction status. |
| `screenshots` | Screenshot extraction status. |
| `comments` | Comment-fetch status. |
| `hook` | Hook Type analysis status. |
| `comment_intelligence` | Comment Intelligence status. |

Status strings are intentionally compact (`ok`, `missing`, `skipped`, `pending`, `completed`, `failed`, or related backend status strings). UI clients should display the raw value when they do not recognize a newer status.

Errors:

- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "no health data for this uoink" }`
- `{ "ok": false, "error": "rate limit exceeded: max 60/minute" }`

Rate limit: 60 calls/minute per process.

### find_mentions

Find every uoink in your corpus that mentions a specific entity: person, tool, product, topic, company, or other named thing.

Parameters:

```json
{
  "entity": "Claude",
  "limit": 50
}
```

`entity` is required. `name` is accepted as an alias by the backend. `limit` is optional, defaults to 50, and is clamped to 1-200.

Optional `match` defaults to `"forgiving"`: it matches useful words in recorded
entity names, with exact normalized names and complete names ahead of partial
names. An exact source title ranks first; ties use newest mentions first.
`"strict"` keeps the original exact, case and punctuation insensitive entity
lookup. This tool searches recorded entity names, not transcript text.
Each row includes `mention_id`, `video_id`, and the stored `timestamp` in
seconds. `context` is an entity annotation. When it matches a stored clip,
the optional `passage` supplies that clip's ID, verbatim text, and timing.
When it matches indexed prose, `passage` supplies character offsets instead.
`timestamp` and `deep_link` retain the annotation's stored time even when it
is unverified. Verified timing is separate in `timestamp_seconds` and `passage`.

Return shape:

```json
{
  "ok": true,
  "mentions": [
    {
      "video_id": "abc123DEF45",
      "slug": "video-slug",
      "title": "Video title",
      "channel": "Example Channel",
      "source": "transcript",
      "timestamp": 12.5,
      "context": "Claude is the AI we'll use for this workflow.",
      "deep_link": "https://youtube.com/watch?v=abc123DEF45&t=12s"
    }
  ]
}
```

Entities are extracted automatically from each uoink's transcript using the configured Anthropic API key. Matching is case-insensitive and punctuation-tolerant through the normalized entity key. If no Anthropic key is set, entity extraction is skipped at uoink time; older uoinks without entity rows will not appear in results until re-uoinked.

Errors:

- `{ "ok": false, "error": "entity name (string) is required" }`
- `{ "ok": false, "error": "rate limit exceeded: max 60/minute" }`

Rate limit: 60 calls/minute per process.

### get_transcript_reliability

Return stored transcript reliability spans for a saved uoink by YouTube `video_id`.

Parameters:

```json
{ "video_id": "abc123DEF45" }
```

Return shape:

```json
{
  "ok": true,
  "video_id": "abc123DEF45",
  "reliability": {
    "status": "completed",
    "model": "tiny",
    "threshold": 0.5,
    "span_count": 2,
    "spans": [
      {
        "start_word_idx": 124,
        "end_word_idx": 126,
        "confidence": 0.37,
        "reason": "proper_noun_suspect",
        "text": "example phrase",
        "start": 42.1,
        "end": 43.4
      }
    ],
    "computed_at": "2026-05-28T12:34:56"
  }
}
```

`status: "not_computed"` means the yoink exists but reliability detection has not run yet. The MCP tool is read-only: it never downloads the local Whisper model. Users compute reliability from the dashboard setting or the HTTP `POST /reliability/<video_id>/compute` endpoint.

Errors:

- `{ "ok": false, "error": "video_id required" }`
- `{ "ok": false, "error": "uoink not found" }`
- `{ "ok": false, "error": "rate limit exceeded: max 60/minute" }`

Rate limit: 60 calls/minute per process.

### add_podcast_feed

Register an RSS or Atom feed. The helper automatically polls enabled feeds for
metadata after their stored interval elapses. Audio processing stays off unless
`auto_ingest` is explicitly set for that feed; it defaults to `false`.

Parameters:

```json
{
  "feed_url": "https://show.example/feed.xml",
  "poll_interval_min": 60,
  "auto_ingest": false
}
```

The interval must be between 15 and 1440 minutes. The scheduler checks for due
feeds every 30 seconds. `auto_ingest: true` applies to episodes discovered
after opt-in and authorizes automatic MP3 download, local transcription, and
corpus publishing. It does not authorize a first-time Whisper model download.
Use the dashboard or `POST /podcasts/feeds/set-auto-ingest` to change the flag
for an existing feed.

### list_podcast_feeds

List registered feeds, their latest discovered episode, poll state, and error
state. Pass `{ "enabled_only": true }` to omit disabled feeds.

### remove_podcast_feed

Delete a feed and its tracked episode rows.

```json
{ "feed_id": 12 }
```

Local MP3, transcript, and already-published corpus files are not deleted by
this operation.

### poll_podcast_feed

Fetch and parse one feed now through the same path used by watch mode, retaining
up to 50 new episode records. The request uses stored ETag and Last-Modified
values on later polls.

```json
{ "feed_id": 12 }
```

RSS and Atom episode page URLs are retained separately from opaque GUIDs and
audio enclosure URLs.

### list_podcast_episodes

List tracked episodes, newest first.

```json
{ "feed_id": 12, "status": "downloaded", "limit": 100 }
```

All fields are optional. `status` may be `new`, `queued`, `downloaded`,
`transcribed`, or `ignored`.

### download_podcast_episode

Download one episode enclosure as an MP3 with the local yt-dlp and ffmpeg
runtime. The call is synchronous and idempotent when the canonical MP3 already
exists.

```json
{ "episode_id": 42 }
```

Audio stays flat under `<data_root>/Podcasts/<feed-slug>/`.

### get_whisperx_status

Report whether the local WhisperX runtime is available, the selected model,
supported models, and the diarization default. This read-only call neither
downloads a model nor starts transcription.

### transcribe_podcast_episode

Queue one downloaded episode for local transcription and return immediately
with a durable job ID.

```json
{
  "episode_id": 42,
  "model": "base",
  "language": "en",
  "diarize": false,
  "consent_given": false
}
```

Models are `tiny`, `base`, `small`, `medium`, `large`, and
`large-v3-turbo`; `base` is the default. CPU inference uses int8. Exactly one
podcast transcription runs at a time, on a below-normal-priority worker on
Windows. Call `get_job_status` with the returned `job_id` for queued, running,
writing, completed, or failed progress. An interrupted non-terminal podcast
job queues again after helper restart. A first model download returns
`consent_required: true` unless `consent_given` is explicit.

### episode_to_corpus

Publish a completed transcript into the shared local corpus.

```json
{ "episode_id": 42 }
```

The operation writes Markdown and a dashboard-readable sidecar into a stable
per-episode folder, indexes the transcript for FTS and corpus-contract reads,
adds `source_url#t=<seconds>` citations, and stores the
`podcast_episodes.yoink_video_id` link. The stable ID is
`episode_<sha1(feed URL + GUID)[:11]>`. Repeating the call returns the same
identity and repairs partial prior writes without duplicating rows or files.

### get_library_activity

Report deterministic library activity, shelf churn, and source observations.

```json
{
  "interval": {
    "start": "2026-09-01T00:00:00.000Z",
    "end": "2026-09-08T00:00:00.000Z"
  },
  "date_basis": "capture_time"
}
```

The operation returns pure aggregation over saved items, shelf movements, and source observations, bounded by half-open UTC intervals, survivor baseline proof, and explicit provenance.

### search_library

Bounded clip-first search of the saved library (default 5, at most 20 hits)
with verified clip or item-text passages when available (Phase 4, contract
`phase4-v1-2026-09-08`, run AV-1).

Optional `match: "forgiving" | "strict"` defaults to forgiving search.
Forgiving results put exact titles and complete word matches before partial
matches across clips and item text. Strict mode keeps clip-first retrieval.
Timed hits also include `clip_id`; existing `item_id`, `excerpt_id`, source
revision, excerpt URI, and `start`/`end` fields identify the exact evidence.
When no passage can be verified, the result has `passage_verified: false`
and a `citation_reason`, with no passage or excerpt link. A source match
outside its clips can carry an exact character span without a timestamp.

The dashboard, `/memory/search`, and `/api/corpus/v1/search` accept the same
optional `match` parameter and default to forgiving. The dashboard selects
Best match when a query starts. Date sorting stays available, and Exact words
selects strict mode. Clearing the query returns to newest-first browsing.

```json
{ "query": "agent harness", "limit": 5 }
```

Each hit carries the item id, source revision, safe title and link, evidence
kind and timing, a bounded preview and revision-bound card and excerpt URIs
for `read_library_resource`. A `next_step` says when more retrieval is
needed; the result never claims an exhaustive search.

### get_library_item

Resolve one saved item by `video_id` or `slug` (exactly one) and return its
default Librarian evidence card unchanged plus canonical card, excerpt and
initial corpus-chunk URIs.

```json
{ "slug": "some-saved-item" }
```

If corpus-chunk admission fails, that is reported separately while the card
stays usable.

### read_library_resource

Read one `uoink://library/v1/...` resource URI (card, excerpt, corpus chunk,
shelf page or brief) with the same validation, contents and refusals as the
stdio `resources/read` method: the fallback for a client that cannot attach a
template-derived URI natively (Claude Code CLI 2.1.261 has no native resource
reader).

```json
{ "uri": "uoink://library/v1/items/<item_key>/cards/<source_revision>/<selection>/<card_hash>" }
```

Refusals use the Phase 4 domain envelope (`invalid_request`,
`resource_not_found`, `resource_deleted`, `revision_unavailable`,
`resource_too_large`, `library_unavailable`, `deadline_exceeded`,
`rate_limited`, ...). Stdio also advertises five resource templates and nine
prompts: the four frozen library prompts (`consult-library`, `evidence-brief`,
`whats-new`, `reshelve-review`) plus the five research playbooks below.
HTTP stays tools-only.

### get_playbook_input

Prepare evidence for a research report from saved captures. The server computes
metrics and citation keys; the connected client writes the report. This read
requires no API key and makes no model or network calls.

```json
{"playbook":"outlier-posts","arguments":{"author":"Example creator","platform":"youtube"}}
```

Both fields are required. `arguments` is an object with the same string values
accepted by the matching stdio prompt:

| Playbook / prompt | Arguments |
|---|---|
| `outlier-posts` | Required `author`; optional `platform`, `since`. |
| `transcript-intel` | Exactly one of `video_ids` (at most 8), `topic`, `author`; optional `since`. |
| `comment-mining` | Exactly one of `video_ids` (at most 10), `author`; `lens` is `voc` (default) or `demand`. |
| `creator-teardown` | Required `author`; optional `platform`. Needs at least 3 saved captures. |
| `repurpose-pack` | Required `video_ids` (1–5); optional `kinds`: `tweet`, `thread`, `linkedin`, `script`, `newsletter` (default `tweet,thread`). |

Pass `video_ids` and `kinds` as comma-separated strings. `author` is 1–200
code points. Unicode Cc control characters are rejected; format characters
such as joiners are accepted. `topic` is an FTS query of at most 512 characters.
`platform` accepts `youtube`, `tiktok`, `instagram`, `reddit`. `since` is a UTC
capture date (`YYYY-MM-DD`), never a future date. Unknown arguments are refused
before storage access; missing or deleted captures are refused.

Success returns `{ok, playbook, instruction, packet, packet_hash}`. The packet
uses contract `playbooks-v1-2026-10-15` and includes bounded coverage, items and
refs. `packet_hash` hashes canonical `items` and `refs`; it excludes generation
time. Reads share the library's 2-active, 60-per-minute guard and 2-second
deadline, with a 64 KB response budget. Refusals use the Phase 4 error envelope,
including `invalid_request`, `rate_limited`, `deadline_exceeded` and
`internal_error`; stdio tool failures set `isError: true`.
Argument-schema failures on `POST /tools/get_playbook_input` return HTTP 400
with that same `invalid_request` envelope.

Transcript packets retain at most 12 chapters and 2 KiB of escaped chapter
text per capture before applying the packet budget. Omitted chapters count
toward `coverage.dropped_for_budget` and `coverage.budget_drops.chapters`.
The same cap applies to prompts and tools, leaving room for transcript clips.

`prompts/get` accepts each playbook name directly and returns two user messages:
the fixed instruction, then a packet fenced as
`<untrusted_uoink_library_context>`. Source text is data, never instructions.
Reports cite `[cap:]`, `[m:]`, `[t:]`, `[cm:]`, `[ctx:]` and, when a saved
discovery snapshot exists, `[sc:]` keys. Metrics state their as-of time;
non-caption transcript quotes are approximate. Repurposed drafts retain their
credit lines. These reads do not capture, publish, apply changes or run discovery.

### discover_candidates

Run a one-shot ScrapeCreators lookup with your own saved key. Discovery and
connected-agent spending are both off by default. First request a free plan:

```json
{"mode":"creator","platform":"youtube","handle":"ExampleCreator","pages":1}
```

It returns `{ok, needs_confirmation:true, credits_planned, credits_today,
daily_cap}` without a network call. Repeat the same arguments with
`"confirm_credits":1` to authorize that many requests. The value must equal
`pages`; each request sent counts even if it fails. The daily cap defaults to
25 credits (configurable from 1 to 500), resets in UTC, and applies to all callers.

`mode` is `creator` or `keyword`. Creator platforms are `tiktok`, `instagram`,
`youtube` and `youtube_shorts`; supply one `handle` (1–100 characters, leading
`@` stripped) or a YouTube `channel_id` (`UC` plus 22 characters). Keyword mode
accepts `tiktok` or `youtube` and a `query` of 1–200 characters. `pages` is 1–3,
default 1. There is no automatic retry.

A paid call requires `scrapecreators_enabled`, a usable saved key, credit room,
and either `scrapecreators_agent_calls_enabled` or a `user_intent_token` minted
by a dashboard click. The dashboard token lasts five minutes, is single-use,
and binds the operation, origin and helper session. MCP tools cannot mint it;
stdio calls need the agent setting. Confirming a credit count alone does not
enable agent spending. The registry limit is six calls per minute, including plans.

Runs return `run_id`, provider, endpoint, `fetched_at`, credits, coverage,
`baselines` and up to 60 normalized candidates. Each baseline identifies its
`platform`, `source_type`, metric, median, sample count `n` and confidence.
Candidate lifts use their own group's median: YouTube videos and Shorts have
separate baselines. The convenience field `baseline` holds the sole group
when there is exactly one; it is `null` for mixed or empty results.
Each candidate has a stable `key`,
canonical URL, platform, video ID, creator handle or channel ID, caption,
publication time, duration, nullable engagement metrics, lift, label,
`in_library`, state and `pending_id`. YouTube keyword results include videos
and Shorts. No thumbnails are fetched or saved. Upstream failures retain a
partial run with `last_error`; unexpected failures use the standard
`internal_error` envelope without exception text.

Runs live in `DATA_ROOT/discovery/runs/<YYYY-MM>/<run_id>.json`, with atomic
writes and a 256 KiB file cap. The daily purge removes runs older than 90 days.
Local `outlier-posts` and `creator-teardown` packets reuse the newest matching
snapshot per handle/channel ID and platform within 30 days as `[sc:]` rows.
They read at most 24 run files per packet, filtering creator filenames by
target first; remaining reads may include matching authors in keyword runs.
Creator snapshots take precedence over keyword matches regardless of age;
keyword rows are used only where that platform has no creator snapshot.
Videos and Shorts stay separate. A newer successful empty creator run replaces
the older snapshot and blocks keyword fallback for that platform. Failed runs
with no candidates are ignored; newly written empty failure receipts carry a
`-failed` run-ID suffix and are excluded before the file-read budget, so repeated
failures cannot crowd out the older snapshot or keyword fallback. Partial
results from a later-page failure remain eligible. These local reads spend no credits.

For YouTube, pass the local author/channel display name as the playbook's
`author`. Uoink also matches discovery rows using the channel ID or handle in
the newest matching YouTube capture's sidecar `channel_url`. This joins
channel-ID creator runs and keyword `channel/UC...` rows to ordinary captures;
the ID does not replace the local display name in the playbook selector.
If the saved channel URL has neither an ID nor a handle, matching falls back
to the supplied author. All identities share the 24-file read limit.

### queue_discovered

Pick saved candidates for the normal capture queue:

```json
{"run_id":"<run_id returned by discovery>","keys":["<candidate key>"]}
```

`keys` contains 1–10 selections. This tool requires the agent discovery setting
or a fresh dashboard intent bound to these picks. It needs no ScrapeCreators
key, makes no ScrapeCreators request and spends no credits. Its registry limit
is 30 calls per minute.

Success returns `{ok, run_id, queued, skipped, candidates}`. `queued` entries
contain `key` and `pending_id`; skipped entries contain `key` and one of
`in_library`, `already_queued`, `unsupported_url`, `unknown_key`. Active picks
are deduplicated, including concurrent calls from the helper and stdio server:
SQLite checks for an active URL and enqueues it in one write transaction.
A new explicit pick after a
failed or cancelled attempt enqueues a fresh row and replaces the saved
`pending_id`; it does not spend ScrapeCreators credits. Enqueued picks are saved
as `state:"queued"` in the run file. The existing `pending_yoinks` retry worker
captures them with the usual transcript, comments and screenshots. Picks are
due immediately, using the same local timestamp format as the retry worker.
Argument-schema failures on `POST /tools/discover_candidates` and
`POST /tools/queue_discovered` return HTTP 400 with the standard
`invalid_request` envelope before tool dispatch.
`GET /discovery/runs/<run_id>` requires the helper token and returns
`{ok:true, run}`. It reconciles `captured` or `failed` state against the library
and queue, saves the refreshed receipt, and never starts a capture or provider
call. It works with discovery and agent spending off. Queue calls also
reconcile the run before evaluating picks.

### get_library_brief_input

Prepare bounded input for a client-run daily brief (Phase 4 second increment,
run AV-2). Brief generation belongs to the client: Uoink never runs a model or
a scheduler for it. For a UTC `date` (not in the future) and a Phase 2
`run_id`, the tool returns `job_key`, `input_hash`, the bound queue digest,
run revision, taxonomy/projection revisions and latest covered operation
sequence, capture and event counts, coverage, up to 20 work-status rows and up
to 5 default Librarian cards, at most 24,576 bytes. Read only: no lease, no
mutation. The client tracks its own job (`prepared`, `running`, `submitted`,
`stale`, `failed`, `waiting_for_client`) and keeps the packet.

```json
{ "date": "2026-09-08", "run_id": "run-2026-09-08" }
```

### publish_library_brief

**Local write.** Persist one client-produced brief for a job prepared by
`get_library_brief_input`. The server rebuilds the packet against current
library data (a changed queue, source or deletion is `stale_brief`), requires
`job_key` and `input_hash` to match the packet, binds each citation (at most
20; item id, source revision, card hash, excerpt id, a 1-500 code point quote
that occurs in that excerpt after NFC/whitespace normalisation, evidence kind
and time bounds) to the supplied cards only, and stores an immutable artifact
plus receipt under `DATA_ROOT/reach/briefs/`. The document is at most 8,192
UTF-8 bytes; the whole request at most 65,536 bytes. An identical retry on the
same `submission_key` returns the recorded receipt; changed content under that
key is `idempotency_conflict`; a competing artifact for a job that already has
one is `brief_conflict`. Missing usage is stored as unavailable, never as zero
tokens or a cost. The brief is readable at
`uoink://library/v1/briefs/{date}/{brief_hash}` and appears in the curated
resource list as the latest valid brief; a cited or sampled item that is
deleted or changes makes it unavailable immediately. It cannot apply labels or
alter the assignment queue.

```json
{
  "job_key": "<64 hex>", "input_hash": "<64 hex>",
  "input_packet": { "...": "the packet returned by get_library_brief_input" },
  "submission_key": "brief-2026-09-08-1",
  "document": "# Daily brief\n...",
  "citations": [{ "item_id": "...", "source_revision": "<64 hex>", "card_hash": "<64 hex>",
                  "excerpt_id": "<64 hex>", "quote": "...", "evidence_kind": "timed_clip",
                  "start": 12.0, "end": 40.0 }],
  "usage": null
}
```

### export_cited_range

Read-only cited export (Phase 6 second increment, run BC-2, contract
`phase6-v1`). Select exactly one of a cue-aligned time range (`start` and
`end` must equal the first selected cue's start and the last selected cue's
end; at most 120 s and 200 cues) or a current `excerpt_id`; optional
`source_revision` / `media_revision` pins refuse `revision_unavailable` on
change. The result carries the verbatim stored cue text, per-cue speaker
labels with their provenance (diarization run or source metadata), the
overlapping chapters, safe source and seek links (a `youtube` seek only for a
verified YouTube item; podcasts record `seek_kind: "none"`), the item's
source and media revisions and evidence refs. Every referenced original
artifact is validated by bytes before anything is quoted; a missing input is
`library_unavailable`, corrupt bytes or bindings `invalid_source_data`. The
read is one coherent SQLite transaction with a final source/media recheck,
admitted on the shared Phase 4 guard (2 s deadline, 4 active, 60/minute) with
the same wire budgets (24,576 rendered bytes, 65,536 wrapped bytes). Nothing
is fetched, transcribed or saved; text-only items refuse `not_timed` with
`next_step: get_library_item`, and coarse (paragraph) timing refuses
`coarse_timing` with `next_step: read_library_resource`.

```json
{ "video_id": "<item id>", "start": 60.0, "end": 125.0 }
```

```json
{ "video_id": "<item id>", "excerpt_id": "<64 hex>", "source_revision": "<64 hex>" }
```

## Rate limits and abuse mitigations

- `uoink_video`: 5 calls/minute per process.
- `uoink_playlist`: 5 calls/minute per process.
- `analyze_comments`: 10 calls/minute per process.
- `classify_hook`: 10 calls/minute per process.
- `list_recent_uoinks`: 60 calls/minute per process.
- `search_uoinks`: 30 calls/minute per process.
- `search_clips` and `get_evidence_card`: 30 calls/minute per process.
- `get_citation_map`: 60 calls/minute per process.
- `get_uoink_health`: 60 calls/minute per process.
- `find_mentions`: 60 calls/minute per process.
- `get_transcript_reliability`: 60 calls/minute per process.
- Podcast feed mutations and `episode_to_corpus`: 30 calls/minute per process.
- `list_podcast_feeds`, `list_podcast_episodes`, and `get_whisperx_status`: 60 calls/minute per process.
- `download_podcast_episode`: 10 calls/minute per process.
- `transcribe_podcast_episode`: 5 calls/minute per process.
- Other read-only tools (`get_uoink_corpus`, `get_job_status`, `get_taxonomy`) are not rate-limited.

Rate-limit errors return friendly tool payloads, for example:

```json
{ "ok": false, "error": "rate limit exceeded: max 5/minute" }
```

HTTP JSON-RPC remains protected by `X-Uoink-Token`; the helper still accepts
the legacy `X-Yoink-Token` header for installed extension compatibility.
Stdio MCP relies on the spawning client trust boundary. All tools keep v1/v2
URL, slug, and job validation.

## Compatibility notes

The launch-facing compatibility matrix is near the top of this document. HTTP JSON-RPC is route-smoked and available for local clients that prefer HTTP, but it is experimental. The first launch story should emphasize stdio because that is the path Ryan will certify for Claude Desktop and Cursor.

## Client-side helpers needed from Claude Code

None for Sprint 4. `extension/lib/extract.js` does not need new helpers to surface MCP status. The setup page uses existing `STC.getToken()` plus authenticated fetch to `GET /mcp/v1/config`.

## Open questions

- Should v2.1 persist MCP call logs or agent activity indicators in the popup? Out of scope for Sprint 4.

## Additional tools available in full mode

### list_library_work

List Librarian assignment work for a run: counts by work state and manifest disposition, the run revision, one cursor page of items, and whether staged work is waiting for a subscribed client. Expires stale leases while listing; the server never runs the Librarian itself.

Arguments: `run_id`, `state`, `limit`, `cursor`. The registry schema in `tools/list` defines required fields and bounds.

### claim_library_work

Lease Librarian work for a client (action=claim returns up to twelve single-item packets, each with one evidence card and an attempt token), or renew, release or cancel the client's own current attempt. Leases run 60-900 seconds and never past one hour after the first claim; a row is exhausted after three.

### submit_library_result

Submit one Librarian result for one leased work row: an assignment of one to three shelf memberships with quoted evidence, or an explicit unmapped, unsupported or error outcome. Validated and stored; nothing is applied to current labels. An identical retry under the same submission_key returns the recorded response.

Arguments: `work_id`, `client_id`, `attempt_token`, `submission_key`, `schema_version`, `video_id`, `source_revision`, `taxonomy_revision`, `packet_hash`, `result`, `usage`. The registry schema in `tools/list` defines required fields and bounds.

### apply_reshelving

Preview the exact reshelving delta for a run (mode=preview, the default), or apply a locally approved, unexpired preview by its delta hash and operation key (mode=apply). Apply is refused while librarian_apply_enabled is off, which is the shipping default, and stops at 15 percent churn without a trusted human approval.

### pin_shelf

Pin, unpin or move one item on a shelf as a user decision that the Librarian may not override. Requires a user_intent_token minted by the dashboard confirmation route; no client actor string grants that authority.

Arguments: `video_id`, `shelf_id`, `action`, `expected_projection_revision`, `operation_key`, `user_intent_token`, `reason`. The registry schema in `tools/list` defines required fields and bounds.

### undo_library_apply

Undo one recorded library apply by replaying its stored inverse as a new, itself reversible, journal operation. Only the apply that produced the current projection revision can be undone, and a user_intent_token from the dashboard is required.

Arguments: `apply_id`, `expected_projection_revision`, `operation_key`, `user_intent_token`. The registry schema in `tools/list` defines required fields and bounds.

### list_sources

List standing sources (podcast RSS feeds, YouTube channels and playlists) with consent state, enrollment, today's UTC start allowance and detection health. Read-only; keyset pagination.

Arguments: `kind`, `consent_state`, `include_archived`, `limit`, `cursor`. The registry schema in `tools/list` defines required fields and bounds.

### register_source

Register a standing source for metadata detection only. Creates the source with capture off and a due detection cursor; no network call, no capture. A duplicate returns the existing source unchanged (created=false).

Arguments: `kind`, `url`, `display_name`, `poll_interval_min`. The registry schema in `tools/list` defines required fields and bounds.

### source_status

One source's current summary, one page of observed items with capture and classification state, and every in-flight reservation. Read-only: never enrolls, polls or starts work.

Arguments: `source_id`, `item_limit`, `item_cursor`. The registry schema in `tools/list` defines required fields and bounds.

### set_source_consent

Turn standing capture on or off for one source. Requires the expected source revision (and cursor revision when enabling), an operation key and a user_intent_token minted by the local dashboard confirmation; the stored receipt is returned on an identical retry. On: at most 25 back-catalog items once, then new items, 10 starts per UTC day. Off: releases unstarted reservations.

Arguments: `source_id`, `consent_state`, `expected_revision`, `expected_cursor_revision`, `operation_key`, `user_intent_token`. The registry schema in `tools/list` defines required fields and bounds.

### analyze_self_channel

Aggregate the user's own saved videos (those tagged is_self via channel-name recognition) into hook evolution, format evolution, performance trend by month, and a top-performers list. Pass `handle` to scope to one of the user's registered channels; omit for the union across every registered channel. `limit` caps the top_performers list (default 10, max 100). Pure local read.

Arguments: `handle`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_schema_version

Report the data-shape versions Uoink writes + the supported read-range. v2.5 substrate: cross-version aggregators (Channel Decoder, Niche Corpus) check this before assuming v2 fields are present in older rows/sidecars. Read-only, no arguments.

### get_user_role

Report the user's persisted role (creator | researcher | marketer | mixed) + the dashboard emphasis (primary/secondary chip order + default sort) the helper computes from it. Read-only.

### set_user_role

Persist the user's role choice. Drives Library default sort + filter-chip emphasis on the dashboard. Bounded enum -- one of creator | researcher | marketer | mixed.

Arguments: `role`. The registry schema in `tools/list` defines required fields and bounds.

### check_live_status

Probe a URL to find out if it is a live broadcast without extracting. Returns one of: not_live | live | upcoming | post_live | was_live. The agent uses this to decide between immediate extraction and 'wait until the broadcast ends' (the helper's live_stream_behavior setting handles the latter for /extract; this tool is the read-only probe path).

Arguments: `url`. The registry schema in `tools/list` defines required fields and bounds.

### add_monitored_playlist

Register a YouTube playlist URL to monitor for auto-uoinks. Idempotent on UNIQUE playlist_url. poll_interval_min default 5, range 1-1440.

Arguments: `playlist_url`, `name`, `poll_interval_min`. The registry schema in `tools/list` defines required fields and bounds.

### list_monitored_playlists

List registered playlists newest-first.

Arguments: `enabled_only`. The registry schema in `tools/list` defines required fields and bounds.

### remove_monitored_playlist

Delete a playlist + cascade its discovery events.

Arguments: `playlist_id`. The registry schema in `tools/list` defines required fields and bounds.

### poll_monitored_playlist

Poll one playlist (yt-dlp --flat-playlist) + diff against last_seen_video_ids + auto-queue new videos via the existing pending_yoinks retry worker. Returns the new[] discovery list so the dashboard can show it under a 'from mobile playlist' label distinct from rate-limit retries.

Arguments: `playlist_id`. The registry schema in `tools/list` defines required fields and bounds.

### list_monitored_playlist_events

List per-discovery events. Optional filters: playlist_id, status (discovered | queued | extracted | failed). Newest first.

Arguments: `playlist_id`, `status`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_user_taste

Return the consolidated TASTE.md (preferred hooks/formats, avoid list, top performance anchors). Generated from engagement events + persisted taste anchors. Read-only, no arguments.

### get_user_memory

Return the user's free-form USER.md notes (Channels I admire, My channel(s), Topics, Workflow notes). Hand-edited markdown -- the consolidator never overwrites this file. No arguments.

### update_user_taste

Set one taste anchor section (preferred_hooks | preferred_formats | avoid) and re-consolidate TASTE.md. `content` is markdown that replaces the section body verbatim -- bullets recommended.

Arguments: `section`, `content`. The registry schema in `tools/list` defines required fields and bounds.

### get_engagement_signal

Return the time-decayed value_score for one video plus per-event-type counts and last event timestamp. Events live entirely on the local SQLite index (zero outbound). Weights are documented in index.py (_ENGAGEMENT_WEIGHTS); decay half-life is 30 days.

Arguments: `video_id`. The registry schema in `tools/list` defines required fields and bounds.

### classify_facets

Persist agent-classified facets + free-form tags for a video. Model-agnostic: the calling agent does the LLM work using its own model; this tool validates against bounded enums and writes to the row. The server fills performance_tier (channel-relative) and length_bucket (from duration) if you don't pass them.

Arguments: `video_id`, `format`, `performance_tier`, `length_bucket`, `production_style`, `topic`, `hook_type`, `tags`. The registry schema in `tools/list` defines required fields and bounds.

### query_by_facets

Filter saved yoinks by facet values (format / performance_tier / hook_type / topic / length_bucket / tag). All filters AND-combined; newest first.

Arguments: `format`, `performance_tier`, `hook_type`, `topic`, `length_bucket`, `tag`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_facet_taxonomy

Enum lists for the v2.5 facet axes (used for filter chips).

### assemble_workspace

v3 P4 build workspace: pull a corpus slice for planning a video. Ranks yoinks by S1 facets (format match), performance tier (over > average > under), and S2 engagement value_score. Returns the slice + audience questions from comments + optional self-channel snapshot (if your_channel is set) + optional taste anchors (if S4 memory layer is available). Pure local read; the calling agent does any LLM analysis downstream. If `workspace_id` is provided the slice is persisted onto that row.

Arguments: `format`, `topic`, `hook_target`, `your_channel`, `n_examples`, `workspace_id`. The registry schema in `tools/list` defines required fields and bounds.

### critique_against_corpus

v3 P4 critique tool. Two-phase: call WITHOUT `findings` to retrieve the assembled context (corpus slice + audience questions + taste anchors) -- the agent does the LLM analysis on that context. Call WITH `findings` (structured JSON object with hook_strength, structural_deviation, pacing_issues, missing_audience_hooks per ROADMAP P4) to persist the analysis to the workspace's critique log. Model-agnostic default; BYO-key mode accepted but not yet implemented on-server.

Arguments: `workspace_id`, `draft_text`, `findings`, `mode`. The registry schema in `tools/list` defines required fields and bounds.

### list_workspaces

v3 P4: list build workspaces newest-first. Read-only.

Arguments: `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_workspace

v3 P4: fetch one workspace + its full critique log (every draft + findings combination the agent has persisted).

Arguments: `id`, `workspace_id`. The registry schema in `tools/list` defines required fields and bounds.

### extract_claims

v3 A2 (Loki-inspired): persist agent-extracted claims for a video. LOCKED FRAMING -- the calling agent does the LLM decomposition; this tool validates + writes. Each claim is {claim_text, check_worthiness? (0.0-1.0), context?}. NEVER auto-asserts truth verdicts -- surfaces checkable claims so the user can decide which to verify.

Arguments: `video_id`, `claims`, `mode`. The registry schema in `tools/list` defines required fields and bounds.

### verify_claim

v3 A2: record evidence for one extracted claim. alignment_signal MUST be one of supports / contradicts / mixed / inconclusive. NEVER 'true' / 'false' / 'lie'. The user judges the verdict from the surfaced evidence.

Arguments: `claim_id`, `evidence`, `mode`. The registry schema in `tools/list` defines required fields and bounds.

### list_claims

v3 A2: list extracted claims. Filter by video_id and/or status (extracted | verified | not-attempted).

Arguments: `video_id`, `status`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_claim

v3 A2: fetch one claim by id, with stored evidence.

Arguments: `id`, `claim_id`. The registry schema in `tools/list` defines required fields and bounds.

### generate_script

v3 P5 script studio: two-phase generator. Call WITHOUT `script` payload to retrieve grounding context (workspace metadata + assembled corpus slice + audience questions + optional taste anchors + optional self-channel snapshot). The calling agent does the writing using its own model. Call WITH `script` (a structured object with hook + beats + body + cta + source_yoinks citations) to persist as a new versioned row. parent_script_id chains revisions. An optional hook_type_lens biases the opening toward one of the 9 hook styles.

Arguments: `workspace_id`, `script`, `mode`, `parent_script_id`, `hook_type_lens`. The registry schema in `tools/list` defines required fields and bounds.

### revise_script

v3 P5: revise an existing script grounded in critique findings. Two-phase like generate_script -- without `revised_script` returns previous + grounding for the agent to act on; with `revised_script` persists as a new version (parent_script_id auto-set to the prior id).

Arguments: `script_id`, `critique_findings`, `revision_target`, `revised_script`, `mode`. The registry schema in `tools/list` defines required fields and bounds.

### get_shot_list

v3 P5: derive (and persist) a default shot list from a script's beats + the parent workspace's S1 format facet. Per-beat row with format-specific cue suggestions. The calling agent can override by supplying shot_list directly in generate_script.

Arguments: `script_id`. The registry schema in `tools/list` defines required fields and bounds.

### list_scripts

v3 P5: list scripts newest-first. Optional workspace_id filter scopes to one workspace's history.

Arguments: `workspace_id`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_script

v3 P5: fetch one script by id.

Arguments: `id`, `script_id`. The registry schema in `tools/list` defines required fields and bounds.

### write_tweet

Two-phase tweet/thread generator. Phase 1 (no `body`) returns grounding (source yoink + creator credit + style anchors + Voice DNA prompt). Phase 2 (`body` present) persists + scans for canned phrases + returns structured warnings (soft warn -- NEVER auto-blocks). Creator credit is required in the body.

Arguments: `source_yoink_id`, `angle`, `target_length_chars`, `generate`, `compute_mode`, `kind`, `output_mode`, `hook_type_lens`, `style_anchor_ids`, `body`, `source_credit_line`, `skip_voice_dna_this_time`, `suppress_credit`, `tags`, `parent_id`. The registry schema in `tools/list` defines required fields and bounds.

### write_blog

Two-phase blog generator. Same shape as write_tweet but Phase 2 accepts title, dek, tags, and expects markdown body with a Source section. Soft-warn canned-phrase scan; creator credit non-suppressible.

Arguments: `source_yoink_id`, `angle`, `target_length_words`, `generate`, `compute_mode`, `kind`, `hook_type_lens`, `style_anchor_ids`, `body`, `title`, `dek`, `tags`, `source_credit_line`, `skip_voice_dna_this_time`, `suppress_credit`, `parent_id`. The registry schema in `tools/list` defines required fields and bounds.

### list_writing_pieces

List generated pieces newest-first. Optional `kind` (tweet|thread|blog) + `yoink_id` filters.

Arguments: `kind`, `yoink_id`, `limit`. The registry schema in `tools/list` defines required fields and bounds.

### get_writing_piece

Fetch one piece by id.

Arguments: `id`, `piece_id`. The registry schema in `tools/list` defines required fields and bounds.

### add_style_anchor

Add a Substack-style voice anchor (URL or raw pasted text). User names each. Cap at 10 -- returns 422-shaped error when exceeded. URL ingestion extracts prose via the helper's page extractor (Universal Site PR); falls back to NULL raw_text when the extractor isn't bound yet.

Arguments: `name`, `source_type`, `source_value`. The registry schema in `tools/list` defines required fields and bounds.

### list_style_anchors

List style anchors + their active flag + the helper's 10-anchor cap.

Arguments: `active_only`. The registry schema in `tools/list` defines required fields and bounds.

### remove_style_anchor

Delete a style anchor.

Arguments: `anchor_id`, `id`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_url

Capture any http(s) URL through the helper's universal extractor. Known video platforms use the full media pipeline; other sites use the metadata and transcript fallback.

Arguments: `url`, `interval`, `long_video_mode`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_note

Save a text note as a first-class local corpus item.

Arguments: `text`, `title`, `author`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_image

Save a base64 PNG, JPEG, or WebP as a local image corpus item. No cloud OCR or vision service runs.

Arguments: `image_base64`, `mime`, `filename`, `caption`, `source_url`, `author`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_x

Capture an X post and the author's earlier chain as a local corpus item. Requires x_text_capture_enabled, which defaults on.

Arguments: `url`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_page

Capture an allowed page as a yoink. Crawl4AI runs ON-DEVICE when available (JS render + screenshot); stdlib fallback otherwise (static HTML + markdown synthesis, no screenshot). Allowlist-gated -- add the host via add_allowed_site first if it's not in the defaults (youtube.com, youtu.be, x.com, twitter.com). Result auto-persists as a yoink with source_type='page'.

Arguments: `url`, `render_mode`, `include_screenshot`, `follow_links_depth`. The registry schema in `tools/list` defines required fields and bounds.

### uoink_reddit_thread

Fetch a thread via its public .json (no API key, no OAuth), flatten the comment tree with a depth limit and a score threshold, and persist it as a yoink with source_type='reddit_thread'. Renders as Post -> Top comments -> nested replies so search and facets work on the conversation. Runs on-device; no allowlist gate.

Arguments: `url`, `depth_limit`, `score_threshold`. The registry schema in `tools/list` defines required fields and bounds.

### import_list

Queue every video from a list source for normal capture: a HackerTube playlist (`/p/<slug>`), category (`/c/<id>`), area (`/a/<id>`), video, or the whole collection best first; a Hacker News thread (read through the Algolia HN API); a Reddit thread (public .json); or a YouTube playlist (yt-dlp flat listing, no API key). Reads one batch of at most 50 videos, skips anything already in the library, and adds the rest to the background download queue, which captures one video per pass. `offset` with the returned `next_offset` works through big lists, such as a playlist of 2,000 episodes, 50 at a time. `preview_only` counts without queueing. Each imported capture gets a source tag (`hackertube`, `hn thread`, `reddit thread`, `youtube playlist`) and keeps its note, such as HackerTube's "why HN likes it", which For You uses to rank unopened imports against your taste.

HackerTube data is ODC-By 1.0: credit HackerTube (hackertube.org) and the open-index/hacker-news dataset. Uoink stores the credit line with every HackerTube item.

Arguments: `url`, `limit`, `offset`, `preview_only`. The registry schema in `tools/list` defines required fields and bounds.

### list_allowed_sites

List the user's allowed hostnames. Default seeds (youtube.com, youtu.be, x.com, twitter.com) are pre-added by migration 0015 and removable like any other entry.

Arguments: `active_only`. The registry schema in `tools/list` defines required fields and bounds.

### add_allowed_site

Add a hostname or wildcard pattern (`*.docs.example.com` matches all sub.docs.example.com subdomains). Idempotent on UNIQUE url_pattern. Plain hostnames also match their subdomains (so 'example.com' matches 'www.example.com').

Arguments: `url_pattern`. The registry schema in `tools/list` defines required fields and bounds.

### remove_allowed_site

Remove a hostname or wildcard pattern from the allowlist.

Arguments: `url_pattern`. The registry schema in `tools/list` defines required fields and bounds.
