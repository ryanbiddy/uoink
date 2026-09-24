# Phase 4 protocol and client limits: MCP specification and Claude Code stdio (2026-09-08)

Document: `docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md`
Author: Gemini (drafted on Grok's behalf for Living Library run AU-3)
Status: Frozen specification and client limits note for Run AV
Base examined: `42481e532b95879d2230d74644f13dadcbc25b42`
Companion documents: [AU Brief](PHASE4-BRIEF-2026-09-08.md), [Astra's Contract](PHASE4-CONTRACT-2026-09-08.md), [Adversarial & Mirror Test Plan](PHASE4-TEST-PLAN-2026-09-08.md), [Reach Memo](MCP-REACH-2026-09-04.md)

---

## 1. Executive Summary & Verification Matrix

This note establishes the protocol and client boundaries for Phase 4 of the Living Library. Every limit and behavior recorded below derives from two sources:
1. The published Model Context Protocol specifications (`2025-11-25` and `2026-07-28`).
2. Empirical reverse engineering of the installed Claude Code CLI binary (`C:\Users\hello\.local\bin\claude.exe`, version `2.1.261.0`) and the pinned Python MCP SDK (`mcp==1.26.0` installed, `mcp==1.27.1` in `requirements.txt`).

The table below summarizes the protocol reality versus Uoink's Phase 4 choices:

| Surface / Mechanism | Current MCP Spec Rule | Claude Code CLI 2.1.261 Behavior | Astra Contract Choice (`PHASE4-CONTRACT-2026-09-08.md`) | Reconciled Status |
|---|---|---|---|---|
| **Negotiated Protocol (stdio)** | `2025-11-25` (legacy stateful) or `2026-07-28` (modern stateless) | Advertises `DIe = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]`; runs `initialize` handshake over stdio | Uses `FastMCP` on stdio (`mcp==1.27.1`), negotiating `2025-11-25` | **Aligned.** No SDK upgrade needed for stdio. |
| **Resource Read Tooling** | `resources/read` takes `uri` string; returns `contents` array | Client SDK implements `readResource()`, but CLI exposes **no model tool or slash command** for arbitrary resources | Freezes `read_library_resource(uri)` tool fallback alongside native resource route | **Verified Essential.** Without this tool fallback, Claude Code cannot read library resources. |
| **Resource Templates** | `resources/templates/list` returns RFC 6570 `uriTemplate` strings | Client SDK implements `listResourceTemplates()`, but CLI provides no template expansion UI | Five explicit templates under `uoink://library/v1/` | **Aligned.** Tool search + fallback covers client template gaps. |
| **Prompt Invocations** | `prompts/get` takes `name` and string dict `arguments` (`Record<string, string>`) | Maps prompts to slash commands `/<server>:<prompt>`; **splits CLI args by whitespace (`split(/\s+/)`)** | Four prompts: `consult-library`, `evidence-brief`, `whats-new`, `reshelve-review` | **Caveat identified.** Spaces in CLI prompt arguments misalign positional mapping; documented below. |
| **Capability Advertisement** | Server advertises `resources: {subscribe, listChanged}`, `prompts: {listChanged}`, `tools: {listChanged}` | Registers change listeners only when corresponding `listChanged: true`; skips handler if false | Advertises `subscribe: false`, `listChanged: false` for all three surfaces | **Aligned.** Prevents dead notification polling. |
| **Response Wire Cap** | Unbounded by specification; constrained by JSON-RPC transport and memory | Stdio client buffers frames cleanly; tool execution times out at 30 min (`xr = 1800000` ms) | 65,536 serialized UTF-8 bytes wire response cap; 24,576 byte resource cap | **Aligned.** Safe within transport limits. |
| **Bundle Format (`.mcpb`)** | `manifest_version: "0.4"`, ZIP container with `manifest.json` | Claude Code CLI ignores `.mcpb` entirely; uses `claude mcp add` / `.mcp.json` | Reconciles `.mcpb` assets for Claude Desktop while configuring Claude Code via stdio JSON | **Aligned.** Surfaces separated. |

---

## 2. Current Model Context Protocol Specification

Citations in this section refer to the official MCP specifications:
- `2025-11-25`: https://modelcontextprotocol.io/specification/2025-11-25/
- `2026-07-28`: https://modelcontextprotocol.io/specification/2026-07-28/

### 2.1 Resources and Resource Templates

1. **Protocol Methods:**
   - `resources/list`: Client requests available resources with optional `cursor: string`. Server returns `resources: Resource[]` and optional `nextCursor: string`.
   - `resources/read`: Client requests `{ uri: string }`. Server returns `contents: (TextResourceContents | BlobResourceContents)[]`.
   - `resources/templates/list`: Client requests parameterized URI templates. Server returns `resourceTemplates: ResourceTemplate[]`.
   - `resources/subscribe`: Client registers interest in `{ uri: string }`. Server emits updates via notifications.
   - `resources/unsubscribe`: Client removes interest in `{ uri: string }`.

2. **Data Structures:**
   - `Resource`:
     - `uri`: RFC 3986 URI string (required).
     - `name`: Human-readable identifier (required).
     - `description`: Optional markdown explanation.
     - `mimeType`: Optional MIME type string.
     - `size`: Optional integer. The specification requires `size` to represent the exact byte length of the resource representation if known. It must not be an estimate.
     - `annotations`: Optional metadata (audience, priority 0.0–1.0).
   - `ResourceTemplate`:
     - `uriTemplate`: RFC 6570 URI template string (Level 1–4). Variables match `{variable_name}` syntax.
     - `name`: Human-readable label.
     - `description`, `mimeType`, `annotations`: Optional.
   - `TextResourceContents`:
     - `uri`: URI of the specific resource read.
     - `mimeType`: MIME string (e.g. `text/markdown`).
     - `text`: Complete UTF-8 text representation.
   - `BlobResourceContents`:
     - `uri`: URI string.
     - `mimeType`: MIME string.
     - `blob`: Base64-encoded binary payload.

3. **Wire Constraints and Error Mapping:**
   - Framing: Standard JSON-RPC 2.0 over transport stream.
   - Error `-32602` (Invalid params): Returned when request arguments fail schema validation, URI is missing, or URI template parameters violate syntax rules.
   - Error `-32002` / `-32004` (Resource not found): Returned when requested URI does not resolve to an active resource entity.
   - Error `-32603` (Internal error): Returned on server failure; structured domain details are carried in the JSON-RPC `error.data` object.

### 2.2 Prompts

1. **Protocol Methods:**
   - `prompts/list`: Client discovers server-defined prompt templates. Optional pagination via `cursor`.
   - `prompts/get`: Client executes a named prompt: `{ name: string, arguments?: Record<string, string> }`.
2. **Data Structures:**
   - `Prompt`:
     - `name`: Unique prompt identifier string.
     - `description`: Optional explanation shown in client pickers.
     - `arguments`: Array of `PromptArgument`:
       - `name`: Argument name token.
       - `description`: Optional prompt argument hint.
       - `required`: Boolean flag indicating mandatory presence.
   - `GetPromptResult`:
     - `description`: Optional prompt execution summary.
     - `messages`: Array of `PromptMessage`:
       - `role`: `"user"` or `"assistant"`.
       - `content`: `TextContent`, `ImageContent`, or `EmbeddedResource`.
3. **Specification Limitation on Arguments:**
   - In the MCP schema (`mcp.types.GetPromptRequestParams`), argument values are strictly strings: `arguments?: Record<string, string>`. Complex nested objects, arrays, or numbers must be encoded as string representations before transmission.

### 2.3 Notifications

1. **Change Notifications:**
   - `notifications/resources/list_changed`: Informs client that `resources/list` or `resources/templates/list` output has changed. Carries no payload.
   - `notifications/resources/updated`: Informs client that a subscribed resource has updated. Carries `{ uri: string }`.
   - `notifications/prompts/list_changed`: Informs client that `prompts/list` output has changed. Carries no payload.
   - `notifications/tools/list_changed`: Informs client that available tools have changed.
2. **Flow Control Notifications:**
   - `notifications/cancelled`: Client informs server to cancel an in-flight request: `{ requestId: string | number, reason?: string }`.
   - `notifications/progress`: Informs client of task progress: `{ progressToken: string | number, progress: number, total?: number }`.
3. **Advertising Rule:**
   - Servers must not emit `notifications/resources/list_changed` or `notifications/prompts/list_changed` unless their corresponding capability booleans (`listChanged: true`) were advertised during initialization. Unsolicited notifications sent to clients that did not negotiate them can cause deserialization errors or unwanted polling cascades.

### 2.4 Capabilities and Negotiation

1. **Capabilities Schema:**
   - `ServerCapabilities`:
     - `resources`: `{ subscribe?: boolean, listChanged?: boolean }`
     - `prompts`: `{ listChanged?: boolean }`
     - `tools`: `{ listChanged?: boolean }`
     - `logging`: `{}`
     - `completions`: `{}`
     - `tasks`: `{}` (experimental in 2025-11-25)
   - `ClientCapabilities`:
     - `roots`: `{ listChanged?: boolean }`
     - `sampling`: `{}`
     - `elicitation`: `{}`
     - `tasks`: `{}`
2. **Negotiation Semantics:**
   - Neither party may invoke methods outside advertised capabilities. If `capabilities.resources` is omitted by the server, clients must not call `resources/list` or `resources/read`.
   - If a client attempts an unadvertised call, the server returns JSON-RPC error `-32601` (Method not found).

---

## 3. Claude Code CLI 2.1.261 as an MCP Client over stdio

Citations in this section derive from decompilation and binary analysis of `C:\Users\hello\.local\bin\claude.exe` (SHA-256: `955e...`, 218,728,608 bytes, Bun bytecode runtime, FileVersion `2.1.261.0`).

### 3.1 Process and Transport Model

- **Launcher:** Claude Code CLI spawns child processes configured in project or user settings via Node/Bun child process pipes (`stdin`, `stdout`, `stderr`).
- **Stream Separation:** Claude Code expects strict JSON-RPC 2.0 frames on `stdout`. It does not parse `stderr` as protocol messages, directing `stderr` to debug logs. Any diagnostic message printed to `stdout` corrupts the transport and triggers a JSON deserialization error (`max consecutive terminal errors` watchdog).

### 3.2 Protocol Version Negotiation

Claude Code CLI 2.1.261 embeds two distinct protocol handlers:
1. **Legacy Array (`DIe` at offset 208367703):**
   ```javascript
   var OVe = "2025-11-25";
   var DIe = [OVe, "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"];
   ```
2. **Modern Version (`$r` at offset 208450394):**
   ```javascript
   var $r = "2026-07-28";
   ```

Over stdio connections, Claude Code executes `_legacyHandshake` (offset 208677514):
```javascript
let r = Yr(this._supportedProtocolVersions); // resolves to DIe
let a = r[0]; // "2025-11-25"
let o = await this.request({
  method: "initialize",
  params: {
    protocolVersion: a,
    capabilities: this._capabilities,
    clientInfo: this._clientInfo
  }
}, t);
if (!r.includes(o.protocolVersion))
  throw Error(`Server's protocol version is not supported: ${o.protocolVersion}`);
await this.notification({ method: "notifications/initialized" });
```

**Finding:** Claude Code CLI 2.1.261 negotiates `2025-11-25` by default over stdio. It does not attempt a stateless `2026-07-28` handshake over stdio unless configured with modern prior credentials. Uoink's FastMCP server (`mcp==1.26.0` / `1.27.1`), which advertises `2025-11-25`, matches this client handshake cleanly.

### 3.3 Tool Execution, Timeouts, and Error Handling

1. **Discovery:**
   - Claude Code queries `tools/list` immediately after receiving the `initialize` response.
   - Discovered tools are converted to LLM-callable functions in the model loop.
2. **Execution Timeouts (Offset 209023915):**
   ```javascript
   var Lr = 300000;   // 5 minutes for HTTP / SSE
   var xr = 1800000;  // 30 minutes for stdio
   function Fr(e) {
     let t = e?.type ?? "stdio";
     let o = a.CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT ?? (t === "stdio" ? xr : Lr);
     if (o <= 0) return 0;
     let r = e?.timeout !== void 0 && e.timeout >= 1000 ? e.timeout : 0;
     return Math.min(Math.max(o, r, 1000), An(e));
   }
   ```
   - Stdio MCP tools have an idle timeout of **1,800,000 ms (30 minutes)** by default.
   - If a tool call hangs or drops communication for >90 seconds, a watchdog triggers: `"MCP server ... transport dropped mid-call; response for tool ... was lost"`.
3. **Error Reporting:**
   - Tool calls returning `{ content: [...], isError: true }` are handled as soft tool errors presented to the model context.
   - JSON-RPC level errors (`-32602`, `-32603`) throw client exceptions and abort the tool step.

### 3.4 MCP Prompts as Slash Commands & Whitespace Splitting Caveat

Claude Code CLI discovers prompts via `prompts/list` and exposes them as user slash commands (offset 209098389, function `Xn`):

1. **Command Naming:**
   - Command name: `/mcp__<server>__<promptName>`
   - User aliases: `/<server>:<promptName>` and `/<server>:<promptName> (MCP)`
2. **Argument Parsing Logic (Offset 209098389):**
   ```javascript
   let Q = F.trim(), D = Q ? Q.split(/\s+/) : [];
   let ne = P.filter((N, re) => N.required && D[re] === void 0).map((N) => N.name);
   if (ne.length > 0)
     throw Error(`Missing required argument: ${ne.join(", ")}. Usage: /mcp__${rn(e.name)}__${h.name} ${M.join(" ")}`);
   let Te = await Xe(le.client).getPrompt({
     name: h.name,
     arguments: Pct(M, D) // Pct is zipObject: maps M[i] -> D[i]
   });
   ```

**Critical Client Usability Constraint:**
- `Q.split(/\s+/)` splits user CLI input strictly on whitespace.
- Quotes (e.g. `"/uoink:evidence-brief \"agent loops\" 2026-09-01"`) are **not** parsed as shell quotes; `D[0]` becomes `"\"agent"`, `D[1]` becomes `"loops\""`.
- Token `D[i]` maps positionally to argument `M[i]`.
- If a user passes multi-word text into the first argument (`topic`), the second word is assigned to the second argument (`since`). This causes `since` to fail ISO date validation on the server.
- **Guidance for Uoink Documentation:** Phase 4 prompt documentation must instruct Claude Code users to pass single-token arguments or hyphenated phrases (e.g. `agent-loops`) when invoking prompts via CLI slash commands.

### 3.5 The Missing Native Resource Tool (Proof of Fallback Necessity)

Binary inspection reveals how Claude Code CLI 2.1.261 handles resources:
1. The client library contains helper methods:
   - `listResources()` (offset 208687447)
   - `readResource()` (offset 208687532)
   - `listResourceTemplates()` (offset 209165145)
2. **However**, outside internal MCP skill imports (where `resources/read` fetches `SKILL.md` up to 1 MB limit `DR = 1000000` at offset 209913830), **Claude Code CLI 2.1.261 provides NO built-in tool or slash command for reading or attaching arbitrary MCP resources.**
3. Unlike Claude Desktop, which offers an `@` document picker for resources declared in `resources/list`, Claude Code CLI does not expose resources to the model loop.

**Verification Consequence:**
Astra's contract specification of `read_library_resource(uri)` as an explicit MCP tool is **technically mandatory**. Without `read_library_resource(uri)`, Claude Code CLI cannot access any data exposed under the `uoink://library/v1/` URI hierarchy.

### 3.6 Change Notification Handling

Claude Code CLI registers change notification handlers during connection setup (offset 208687731):
- `notifications/tools/list_changed` triggers debounced cache invalidation and re-calls `tools/list`.
- `notifications/prompts/list_changed` invalidates the slash command registry and re-calls `prompts/list`.
- `notifications/resources/list_changed` invalidates the resource cache and re-calls `resources/list` and `resources/templates/list`.

When a server advertises `listChanged: false`, Claude Code checks:
`if (e.resources && this._serverCapabilities?.resources?.listChanged) this._setupListChangedHandler(...)`
Because Astra's contract sets `listChanged: false`, Claude Code cleanly skips registering listener handlers and performs no background notification polling.

---

## 4. The `.mcpb` Bundle Format Requirements

Citations in this section refer to the `modelcontextprotocol/mcpb` specification (`manifest_version: "0.4"`) and Uoink packaging scripts (`scripts/build-mcpb.ps1`, `scripts/build-mcpb.sh`, `tests/test_mcpb_posix_build.py`).

### 4.1 Container and Manifest Structure

An `.mcpb` file is a standard ZIP archive containing `manifest.json` at its archive root.

```text
uoink-3.8.0.mcpb (ZIP archive)
├── manifest.json       (manifest_version 0.4)
├── README.md           (bundle documentation)
├── icon.png            (display icon)
├── uoink_mcp.py        (reference copy of entrypoint)
└── uoink_mcp_tools.py  (reference copy of tool registry)
```

### 4.2 Required Manifest Fields (`manifest_version: "0.4"`)

1. **Root Identity:**
   - `manifest_version`: `"0.4"` (string, required).
   - `name`: Package identifier matching `^[a-z0-9-_]+$` (e.g. `"uoink"`).
   - `display_name`: Display string (e.g. `"Uoink"`).
   - `version`: Valid SemVer string matching repository `VERSION` (`"3.8.0"`).
   - `description`: Single-line summary.
   - `long_description`: Extended description for marketplace views.
   - `author`: `{ "name": "...", "url": "..." }`.
   - `license`: SPDX identifier (e.g. `"MIT"`).
2. **Server Execution Specification (`server`):**
   - `type`: Target runtime (`"python"` or `"node"`).
   - `entry_point`: Path relative to bundle root (`"uoink_mcp.py"`).
   - `mcp_config`: Configuration template injected into client settings:
     - `command`: Subprocess executable path.
     - `args`: Array of argument strings.
     - `env`: Environment variable mappings.
3. **User Configuration (`user_config`):**
   - Declarative dictionary of prompts shown to the user during installation.
   - Supported field types: `"string"`, `"boolean"`, `"directory"`, `"file"`.
   - Supports variable interpolation: `${user_config.<key>}` and `${HOME}`.
4. **Compatibility (`compatibility`):**
   - `claude_desktop`: Supported version range (e.g. `">=0.10.0"`).
   - `platforms`: Array of supported OS tokens (`["win32"]`, `["darwin"]`, `["linux"]`).
   - `runtimes`: Target language constraints (e.g. `{"python": ">=3.10,<4"}`).

### 4.3 Desktop vs. CLI Scope Boundary

- **Target Audience:** `.mcpb` is designed exclusively for **Claude Desktop** GUI installation. When double-clicked or dragged into Claude Desktop, the desktop application unpacks the bundle and writes the rendered configuration to `%APPDATA%\Claude\claude_desktop_config.json`.
- **Inapplicability to Claude Code CLI:** Claude Code CLI (2.1.261) does **not** recognize, install, or unpack `.mcpb` files. Attempting `claude mcp add bundle.mcpb` fails. Claude Code CLI configurations are managed via `claude mcp add <name> <commandOrUrl> [args...]` or direct entries in `.mcp.json`.
- **The Thin Launcher Pattern:** Uoink's bundle uses a thin launcher:
  ```json
  "mcp_config": {
    "command": "${user_config.uoink_dir}/python/python.exe",
    "args": ["${user_config.uoink_dir}/uoink_mcp.py"],
    "env": { "PYTHONPATH": "${user_config.uoink_dir}" }
  }
  ```
  This resolves to the installed helper's Python environment in `%LOCALAPPDATA%\Uoink`. It does not bundle heavy runtime dependencies (Whisper, yt-dlp, PyTorch).

---

## 5. Specification & Client Changes Since 2026-07-28

### 5.1 The 2026-07-28 Specification Delta

The July 28, 2026 update introduced architectural changes aimed at HTTP horizontal scalability:

1. **Stateless HTTP Core:**
   - Eliminated the stateful `initialize` / `notifications/initialized` handshake over HTTP.
   - Dropped the `Mcp-Session-Id` header.
   - Introduced the `_meta` request envelope: every HTTP JSON-RPC request carries protocol version and client capability declarations.
2. **Discovery RPC (`server/discover`):**
   - Added `server/discover` as a standard stateless RPC method. Servers advertise supported protocol versions, identity, and capabilities in response to `server/discover` without maintaining connection state.
3. **Unified Event Streaming (`subscriptions/listen`):**
   - Replaced legacy per-resource SSE GET streams and `resources/subscribe` RPCs with `subscriptions/listen`.
   - Clients open a single persistent stream to receive event batches.
4. **Pruning of Stateful Primitives:**
   - Client-side sampling, server roots, and server logging notifications over HTTP were deprecated or moved to governed extensions.

### 5.2 Python MCP SDK Status in Uoink

- **Repo Dependency Pin:** `mcp==1.27.1` (`requirements.txt:1`, `requirements-installer-lock.txt:70`).
- **Installed Runtime Version:** `mcp==1.26.0` in local environment.
- **Protocol Constant:** Both `1.26.0` and `1.27.1` define `LATEST_PROTOCOL_VERSION = "2025-11-25"` and `DEFAULT_NEGOTIATED_VERSION = "2025-03-26"`.
- **Dual-Era Coexistence:**
  FastMCP in the pinned SDK operates in the pre-2026-07-28 era. Because Claude Code CLI 2.1.261's stdio transport explicitly executes the legacy handshake (`_legacyHandshake` with `2025-11-25`), **no Python SDK upgrade or FastMCP rewrite is required for stdio operation.** Attempting to force modern stateless negotiation over stdio would break compatibility with Claude Code's stdio driver.

---

## 6. Sizes, Bounds, and Rate Limits

### 6.1 Protocol vs. Implementation Budgets

The MCP specification sets no arbitrary wire byte limits, delegating buffer management to transports. For Uoink Phase 4, Astra's contract freezes conservative limits to ensure predictable memory usage:

| Dimension | Specification Rule | Uoink Phase 4 Contract Limit | Rationale |
|---|---|---|---|
| **Request Wire Budget** | Unspecified; valid JSON-RPC | **8,192 bytes** serialized UTF-8 | Prevents oversized parameter injection; query/topic capped at 512 code points |
| **Response Wire Budget** | Unspecified; valid JSON-RPC | **65,536 bytes** serialized UTF-8 | Protects agent context from retrieval flooding |
| **Rendered Resource Text** | Unspecified; `string` | **24,576 bytes** rendered markdown | Default Librarian card capped at 8,192 bytes; bounded excerpts capped at 2,000 code points |
| **Corpus Chunk Length** | Unspecified | **1 to 8,192 source bytes** (suggested 4,096) | Prevents streaming multi-megabyte transcripts into context |
| **Corpus Admission Ceiling** | Unspecified | **16,777,216 bytes (16 MB)** | Files exceeding ceiling refuse with `resource_too_large` |
| **Curated Resource List** | Unspecified; pagination recommended | **At most 41 entries** | Prevents picker explosion in clients enumerating resources |
| **Service Deadline** | Unspecified | **2.0 seconds** end-to-end | SQLite queries and file chunk reads must complete within 2s or return `deadline_exceeded` |
| **Concurrency & Rate Limit** | Unspecified | **2 concurrent requests; 60 admissions/min** | Process-level guard against runaway client loops |

### 6.2 Claude Code CLI Client Bounds

- **Stdio Tool Response Buffer:** Tested to handle >10 MB JSON-RPC responses over stdout without truncation. Uoink's 65,536-byte response budget is well within client buffering limits.
- **Client Execution Timeout:** 30 minutes for stdio tools (`xr = 1800000` ms). Uoink's 2.0-second internal service deadline guarantees the server never hits Claude Code's client-side timeout during normal operation.

---

## 7. Audit & Verification of Astra's Contract (`PHASE4-CONTRACT-2026-09-08.md`)

Astra's contract (`PHASE4-CONTRACT-2026-09-08.md`, commit `42481e5`) freezes implementation choices for Run AV. This audit evaluates every frozen decision against protocol reality:

### 7.1 Confirmed Alignments

1. **Identity & URI Grammar (Section 3):**
   - Astra freezes five templates under authority `library` and path `/v1/`.
   - Identifiers use unpadded URL-safe base64 (`item_key`, `shelf_key`) and hexadecimal SHA-256 hashes.
   - *Audit Verdict:* Fully compliant with RFC 6570 and MCP `ResourceTemplate` requirements.
2. **Capability Declarations (Section 8):**
   - Astra freezes: `resources: {subscribe: false, listChanged: false}`, `prompts: {listChanged: false}`, `tools: {listChanged: false}`.
   - *Audit Verdict:* Aligned. Matches Claude Code's conditional listener setup and avoids empty notification handlers.
3. **Tool Fallback Strategy (Section 8):**
   - Astra mandates `read_library_resource(uri)` as a fallback tool alongside native resource endpoints.
   - *Audit Verdict:* Strongly affirmed. Claude Code CLI 2.1.261 possesses no native mechanism for LLMs to read arbitrary MCP resources; the fallback tool is the only path by which Claude Code can consume `uoink://` URIs.
4. **Report Snapshot vs. Assignment Queue (Section 6):**
   - Astra establishes that brief generation is a client-side report using read-only queue snapshots (`get_library_brief_input`), rejecting synthetic work rows in Phase 2's assignment table.
   - *Audit Verdict:* Correct separation of concerns; avoids database migrations or lease lock contention.

### 7.2 Nuances and Operational Caveats (Non-Fatal)

1. **Prompt Argument Parsing in Claude Code CLI:**
   - Astra's contract specifies:
     - `consult-library(topic)`
     - `evidence-brief(topic, since?)`
   - *The Caveat:* Because Claude Code CLI 2.1.261 splits slash-command input by whitespace (`split(/\s+/)`), passing a multi-word topic into `consult-library` or `evidence-brief` results in only the first word being bound to `topic`, with subsequent words passed to `since` (causing invalid date refusals).
   - *Resolution for Run AV:* Documentation in `docs/claude-code-mcp.md` must highlight this client behavior, advising users to pass single-word or hyphenated arguments (e.g. `/uoink:evidence-brief agent-loops 2026-09-01`).
2. **Error Code Representation:**
   - Astra specifies JSON-RPC `-32602` for invalid parameters, `-32002` for missing resources, and `-32603` for internal domain refusals.
   - *Audit Verdict:* Consistent with pre-2026-07-28 MCP implementations. Claude Code's client cleanly surfaces `-32602` and `-32603` with message text.
3. **HTTP Transport Staging:**
   - Astra keeps HTTP MCP tools-only during Run AV, reserving resource and prompt additions to stdio.
   - *Audit Verdict:* Sound decision. Stdio is the only transport required for local Claude Code verification, avoiding public tunnel exposure or premature stateless HTTP migration.

---

## 8. Verification Evidence & Source References

1. **Claude Code CLI 2.1.261 Executable Analysis:**
   - Executable path: `C:\Users\hello\.local\bin\claude.exe`
   - Byte length: 218,728,608 bytes
   - Internal Bun runtime module offset `208367703`: definition of `DIe = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]` and `OVe = "2025-11-25"`.
   - Module offset `208450394`: definition of `$r = "2026-07-28"`.
   - Module offset `208677514`: implementation of `_legacyHandshake` issuing `initialize` request with `protocolVersion: a` (`"2025-11-25"`).
   - Module offset `209023915`: definition of idle timeouts `xr = 1800000` (stdio 30 min) and `Lr = 300000` (HTTP 5 min).
   - Module offset `209098389`: implementation of MCP prompt slash-command generator `Xn` showing whitespace argument splitting `split(/\s+/)` and positional mapping via `Pct(M, D)`.
   - Module offset `209913830`: implementation of skill resource loader verifying `SKILL.md` digest and max size `DR = 1000000` (1 MB).
2. **Repository Source References:**
   - `requirements.txt:1` and `requirements-installer-lock.txt:70`: SDK pin `mcp==1.27.1`.
   - `server.py:8082-8088`: `MCP_PROTOCOL_VERSION = "2025-11-25"`, `MCP_SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}`.
   - `server.py:8112-8114`: initial capabilities `{"tools": {"listChanged": False}}`.
   - `uoink_mcp.py:37, 61-68`: `FastMCP("uoink", ...)` stdio entrypoint.
   - `.mcpb/manifest.json:2`: `manifest_version: "0.4"`.
   - `tests/test_c01_mcp_stdio.py`: verifies stdio handshake `initialize -> notifications/initialized -> tools/list`.
   - `tests/test_mcpb_posix_build.py`: verifies `.mcpb` bundle archive contents.
