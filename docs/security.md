# Uoink security model

Status: launch-facing for the current helper and extension

The Living Library candidate build selects a verified local NLTK path-policy
backport, `3.10.3+uoink.pathsec1`. The fixed wheel, original source, patch and
provenance are retained under vendor/nltk-pathsec. At this source checkpoint,
replacement staging and installation are still pending; package 08 contains
upstream 3.10.3. Keep the original advisory observation alongside any later
installed backport disposition. This patch does not qualify model loading or
resolve the retained Torch and Transformers findings.

> Compatibility note: the canonical auth header is `X-Uoink-Token` and the
> `/token` gate is `X-Uoink-Client: uoink-extension`. The shipped extension
> still has compatibility paths that emit `X-Yoink-Token` or
> `X-Yoink-Client: yoink-extension`, so the helper still accepts both legacy
> forms. No removal version is promised until those callers migrate and a
> compatibility release is ratified.

Uoink is local-first software with two pieces:

- A browser extension that injects UI on YouTube and talks to a local helper.
- A Python helper bound to `127.0.0.1:5179` that downloads public YouTube data, writes local corpus files, serves local thumbnails, and exposes optional MCP tools.

The helper never binds to a public network interface. Browser pages cannot use token-gated routes without the helper token. The token bootstrap trusts the pinned Uoink extension, explicitly configured extension IDs, and the local dashboard/WebView path described below. Software running with the user's filesystem privileges remains outside this browser security boundary.

## Threat model

| Threat | Defended? | Notes |
|---|---:|---|
| Malicious webpage tries to call `127.0.0.1:5179` | Yes | Token-gated endpoints require `X-Uoink-Token` (legacy `X-Yoink-Token` accepted); `/token` requires a custom `X-Uoink-Client` header (legacy `X-Yoink-Client` accepted) and browser CORS/PNA preflight blocks normal webpages from setting it cross-origin. |
| Malicious webpage probes whether Uoink is running | Not treated as secret | `/health` and `/ping` are public liveness probes. They disclose the helper version and coarse readiness: Whisper model availability/load state, index recovery, output-root fallback, aggregate path-integrity counts, a generic path-integrity hint or error, the helper process ID, the supervisor run ID, and the helper-recovery status (no paths, tokens or command lines). Raw exception details stay in `server.log`. |
| Local malware reads files or calls localhost | No | Malware already running as the user can read local files, call local ports, and modify output. Uoink does not try to sandbox against same-user malware. |
| Another installed browser extension calls `/token` | Yes, for direct requests from unlisted extensions | The extension uses POST so Chromium sends its Origin, which must match the allowlist. An originless worker GET with `Sec-Fetch-Site: none` is refused, including from extensions with helper host access. The default ID is `bkcapfidedhfcjpmjabeopfbcjcbmdmi`; local configuration can add trusted IDs. Residual risk: an extension with permission to inject script into the helper dashboard can still read `/token` from that page's own origin. A launch-scoped dashboard bootstrap would close this later. |
| Network attacker | Mostly not applicable | The helper listens only on `127.0.0.1`, not LAN/public interfaces. |
| Anthropic API key disclosure through settings | Mitigated | The key is stored in the OS credential store via `keyring` (service `Uoink` in normal mode; deterministic profile-derived `Uoink-isolated-<hash>` in isolated mode; the v2.1 install migration moves normal entries from legacy `Yoink`), not in `settings.json`, and is never returned by `GET /settings`. |
| ScrapeCreators API key disclosure | Mitigated | The key uses the same isolated credential namespace, username `scrapecreators_key`, with no plaintext or environment fallback. Settings expose only presence and invalid status. Requests send it only in the `x-api-key` header to the pinned host; errors omit credential and vendor exception text. |
| Dependency compromise | Partially | Direct downloads are SHA256-checked in `build.ps1`; the full installer pip graph is exact-version locked and inventory-verified, but distribution artifacts are not hash-locked. |

## Public endpoints

These do not require `X-Uoink-Token`:

- Liveness and recovery: `GET /health`, `GET /ping`,
  `GET /index/backfill-status`, and `GET /diagnose`
- Product metadata: `GET /sources/manifest`, `GET /creators/manifest`,
  `GET /hooks/guide`, `GET /developers/manifest`,
  `GET /openapi/v1/spec.json`, and `GET /.well-known/uoink-mcp.json`
- Suite discovery: `GET /.well-known/suite-service.json` and
  `GET /api/suite/v1/health`
- Local UI shells: `GET /dashboard` and `GET /splash`, plus the dashboard's
  bundled fonts at `GET /brand/fonts/<file>` (only the four shipped WOFF
  files; anything else is a 404)
- Credential bootstrap: `GET /token` and bodyless `POST /token`, with the
  separate custom-header and origin checks described below

`/health` and `/ping` are intentionally public because the extension, setup
page, and YouTube button need to detect whether the helper is running before
auth/token refresh completes. Their response includes the selected Whisper
model and availability/load state, index recovery, output-root fallback,
aggregate path-integrity counts, a generic path-integrity hint or error, and
the scheduler `heartbeat` block (UTC timestamps of the last completed pass,
last successful and failed feed poll, last corpus ingest, tallies, and a
freshness state; the last poll failure is reported as an exception class name
or a fixed phrase only). Since 2026-09-04 it also includes the Living Library
`library` block: a coarse work-queue status (`waiting_for_client`,
`collecting`, `idle`, `recovery_pending`, `unavailable`, `unknown` or
`error`), ready/leased work-row counts, the run revision, the journal recovery
state, a service error code and whether the default-off
`librarian_apply_enabled` setting is on. Counts and states only: no item
titles, shelf names, evidence text or paths. It does not include the helper
token or raw exception text.

`/diagnose` reports writability, tool availability, path-integrity counts,
output-folder fallback and migration readiness. Every HTTP response omits
local filesystem paths, key-dependent checks and warnings, and legacy-key
flags. Page origins, extension origins and clients without local browser
proof also receive no saved-key presence or validity fields. Migration exposes
only the existing `app_data` and `desktop_corpus` readiness booleans. Tool checks report
availability instead of raw version output; probe, credential-store and
migration failures use generic messages, with details in `server.log`.
`/health` and `/ping` retain their existing counts and readiness fields;
neither returns local paths or key-presence flags.

Clients that pass the existing splash metadata check still receive the key-readiness
field `anthropic_key_valid` from `/diagnose` without a token, because the
first-run splash needs it. This diagnostic-only check requires no `Origin` header,
`Sec-Fetch-Site: same-origin` or `none`, and a present loopback
`Host` allowed on the helper's port. The field is `true` for a saved key not
marked invalid, `false` whenever `anthropic_key_invalid` is set, even if a 401
cleared the saved key, and absent only when no key is saved and the invalid
flag is off. This preserves the splash's ready, update-key and add-key states
without making an Anthropic request. Even pinned extension origins receive
no such field; a curl-style request without fetch metadata does not qualify.
This compatibility check is separate from token bootstrap: `none` does not
prove extension identity and never authorizes a token mint. An originless
extension worker can satisfy this diagnostic check and see the readiness boolean.

Use authenticated Settings to inspect the output folder or Anthropic key
status. The extension setup page's public Connection checks show no key
checks or local paths and provide no folder action. API-key and automatic AI
analysis controls now live in dashboard Settings > AI features.
The tray no longer shows Degraded solely because a saved key is invalid;
other diagnostic errors still affect it. The dashboard's Settings > Local app status line no longer counts
Anthropic key checks; key status still appears in the dashboard's own key
section, which reads authenticated `/settings`.

The local `uoink doctor` / `--doctor` console report keeps its detailed
diagnostics: output and index paths, tool versions, probe and credential-store
errors, migration details and Anthropic key status. HTTP callers always get
the redacted form, including callers with a token or query parameters asking
for console details.

The manifest, OpenAPI, well-known, and suite-discovery routes expose product
and protocol metadata, not corpus content or credentials. `/dashboard` and
`/splash` serve local UI shells. The dashboard completes the normal token
handshake before requesting user data; the splash readiness check uses the
splash metadata check above.

Both HTML shells, including their trailing-slash and query-string forms,
send `Content-Security-Policy: frame-ancestors 'none'` and
`X-Frame-Options: DENY`. Browsers refuse to embed them in frames, including
frames on the helper's own origin. Open them as top-level pages or native
windows.

`/index/backfill-status` is intentionally public for the same UI bootstrapping reason. It exposes only `state`, `current`, and `total` counts, not corpus content or file paths.

`/token` returns the per-install helper token and is guarded by:

- `X-Uoink-Client: uoink-extension` (legacy `X-Yoink-Client: yoink-extension` remains accepted for shipped-extension compatibility)
- An exact `chrome-extension://<id>` or `moz-extension://<id>` origin whose ID is allowlisted. Missing `Origin` is accepted only with `Sec-Fetch-Site: same-origin` and a present loopback `Host` that passes the helper's Host/port check. `Sec-Fetch-Site: none` cannot substitute for Origin.
- A server-wide 10 requests/minute rate limit

The extension uses a bodyless `POST /token`, with `X-Yoink-Client`,
`credentials: "omit"` and `cache: "no-store"`. In the Chromium 153 probe,
extension-worker GETs omitted Origin and sent `Sec-Fetch-Site: none`; POSTs
sent `Origin: chrome-extension://<id>`. POST therefore lets the helper check
the caller's ID. Token POST rejects nonempty bodies, invalid lengths and
transfer encodings without reading a body. All other POST routes still require
the bearer token before reading input; their body limits are unchanged.

The extension's public manifest `key` fixes its Chromium ID at
`bkcapfidedhfcjpmjabeopfbcjcbmdmi`. This ID is always in the helper's allowlist.
For Edge or development builds with another ID, add trusted IDs through the
comma-separated `UOINK_EXTENSION_IDS` environment variable or the
`extension_ids` setting (a list or comma-separated string). Previously, a
nonempty environment variable replaced the settings list. Now the helper
unions both sources with the pinned ID; an empty setting cannot disable the pin.

After updating an existing unpacked installation, reload the extension once
from the browser's extensions page. If its previous ID differs, extension
storage starts fresh under the pinned ID, including saved extension preferences
and its cached helper token. Reapply those preferences as needed; the extension
fetches the helper token again. The helper's library and captures are unchanged.

Update/reload the extension with the helper: older extension builds that mint
with an originless GET receive HTTP 403 when they next need a token. Existing
cached tokens remain valid until the helper rotates them.

The local-client paths were checked in source before removing the `none`
exception. `GET /token` remains available for helper-served pages with no
Origin, `Sec-Fetch-Site: same-origin` and an allowed loopback Host:

| Client | Origin-bound path and compatibility |
|---|---|
| Browser dashboard | `assets/dashboard/index.html` fetches relative `/token` from the helper's `/dashboard`, keeping the same-origin GET path. |
| Tray WebView2 | `uoink_tray.py` launches `uoink_dashboard.py`, which loads the helper's `/dashboard` URL. It uses the same page and relative fetch; the top-level navigation's `none` metadata is not used to mint a token. |
| Tauri prototype | `tauri-ui/src-tauri/src/main.rs` opens the dashboard as an external helper URL. The installer page does not mint a helper token; the dashboard uses its own helper origin. |
| Extension popup, setup and worker | All use `extension/lib/extract.js` for token bootstrap and refresh, now through POST with the browser-supplied extension Origin. |
| Splash | `uoink_splash.py` loads the helper's `/splash`; relative `/health` and `/diagnose` preserve readiness. Its separate token request already fails because it sends `X-Uoink-Client: uoink-splash`, which the token gate does not accept. The authenticated Open last YouTube action remains unavailable through that path; this task does not broaden the client-header gate. The offline failure HTML does not bootstrap a token. |
| Older WKWebView without fetch metadata | A GET with neither Origin nor `Sec-Fetch-Site` already receives HTTP 403. There is no origin-bound fallback in this client, and it cannot safely use the extension-worker `none` exception. Open the dashboard in a browser that sends same-origin fetch metadata. |

These are source checks and offline request regressions, not native WebView
runtime verification. An explicitly empty or `null` Origin is also refused.
The service worker silently drops runtime messages unless `sender.id` matches
`chrome.runtime.id`; messages from Uoink's own popup and content scripts continue
to work.

Page scripts cannot drive the extension's in-page controls. The Uoink buttons
on YouTube, Reddit and X articles act only on real user clicks
(`event.isTrusted`), so `HTMLElement.click()`, `dispatchEvent` and other
scripted clicks from the page, other extensions or userscripts do not start a
capture. YouTube in-page copy goes only through the extension's offscreen
document: the content script makes no page `navigator.clipboard` call and adds
no DOM textarea, so the page cannot read the corpus text from the DOM. If the
copy fails the button says "Copy blocked" and a notification offers Try again.
`openTab` requests from content scripts open only Uoink's own extension pages,
`https://claude.ai/new`, `https://chatgpt.com/` and the local dashboard
(`http://127.0.0.1:5179/dashboard`); anything else is refused with
`{ok: false}`.

## Token-gated endpoints

All other helper endpoints require `X-Uoink-Token` (legacy `X-Yoink-Token` accepted):

- Single-video extraction: `POST /extract`
- Playlist jobs and index progress control: `POST /playlist/preview`, `POST /playlist/start`, `GET /jobs`, `GET /jobs/<id>`, `POST /jobs/<id>/cancel`, `POST /index/backfill-cancel`
- Sessions: `POST /session/start`, `POST /session/add`, `POST /session/close`, `POST /session/cancel`, `POST /session/open`, `GET /session/list`, `GET /session/active`
- Settings, AI key testing, and local cost estimates: `GET /settings`, `GET /settings/pricing`, `POST /settings`, `POST /settings/test-key`
- Saved discovery receipts: `GET /discovery/runs/<run_id>`. Resolves one dated,
  byte-capped run file and reconciles its capture state. No provider call,
  key access, credit spend or new capture occurs on this read.
- Discovery consent and balance testing: `POST /discovery/intent` and
  `POST /discovery/test-key`. Both check browser origins: when supplied, Origin
  must be loopback HTTP on the helper's port, and Sec-Fetch-Site must be
  same-origin or none. Extension and web origins are refused. An HTTP client
  holding the helper token can omit Origin and fetch metadata and mint an
  intent; these browser checks do not prove a human click. Intent minting is
  limited to 30 per minute. The five-minute, single-use token binds the exact
  operation, origin and helper session. No MCP tool can mint an intent.
- Discovery save recovery: `POST /discovery/runs/save` requires the helper
  token and the same browser-origin checks. It accepts only a run ID and
  retries a normalized receipt retained in helper memory, with no provider,
  credential, ledger or capture-queue access. It refuses to overwrite a
  conflicting file; repeated completed saves return the existing receipt.
- Research generation: `POST /playbooks/run`. Like Writing Studio, it requires
  the helper token; an explicit request with a saved Anthropic key authorizes
  one paid call, including a connected agent's authenticated request. It accepts
  only a playbook name and its scope arguments,
  builds the bounded library packet on the server, and sends the fixed
  instruction and fenced data through the existing Anthropic Messages client.
  It records usage as `playbook_<name>` and returns draft text with citation
  warnings. Saving is a separate `POST /writing/draft` action and warnings do
  not block it. Local MCP packet reads never call Anthropic.
- Local files, folders, Skill prompt, and hook taxonomy: `GET /file`, `GET /skill/system-prompt`, `GET /taxonomy`, `GET /recent`, `GET /open-folder`, `GET /open-index`, `GET /open-prompts`
- MCP HTTP JSON-RPC helper: `GET /mcp/v1/config`, `GET /mcp/v1/sse`, `POST /mcp/v1`, `POST /mcp/v1/initialize`, `POST /mcp/v1/tools/list`, `POST /mcp/v1/tools/call`
- Living Library user-intent confirmation: `POST /library/intent`. Mints the five-minute `user_intent_token` that `pin_shelf` and `undo_library_apply` require. Beyond the token it enforces an origin gate (`Origin`, when present, must be a loopback `http` origin on the helper's own port; `Sec-Fetch-Site`, when present, must be `same-origin` or `none`; extension and web origins are refused), strict JSON decoding (no NaN, Infinity or duplicate keys) and a 30 requests/minute limit. No registry tool, MCP client or client-supplied actor string can mint this token; it exists so a pin or undo is a user's own confirmation of a displayed delta.

Requests to `POST /tools/<name>`, `POST /mcp/v1*`, `POST /playbooks/run`, `POST /discovery/*` and `POST /library/intent` are decoded strictly: NaN, Infinity and duplicate object keys are rejected with HTTP 400 before any argument is used. The six Living Library tools additionally validate every request against their frozen JSON Schema on every transport and return only the contract's error envelope, never raw database exceptions or local paths. Playbook reader failures use the same standard envelope; unexpected failures and Anthropic errors never expose raw exception text or keys.

The token is accepted only in the `X-Uoink-Token` header (or the legacy
`X-Yoink-Token` compatibility header). Query-string token auth is intentionally
unsupported so tokens do not leak into browser history, server logs, or HTTP
debug tools that capture URLs.

## CORS and Private Network Access

For allowed origins, the helper sends:

```http
Access-Control-Allow-Origin: <allowed origin>
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Uoink-Token, X-Uoink-Client, X-Yoink-Token, X-Yoink-Client
Access-Control-Allow-Private-Network: true
```

The following YouTube page origins remain allowed because shipped content
scripts still need direct helper reads:

- `https://www.youtube.com`
- `https://m.youtube.com`
- `https://youtube.com`

Capture, session-add requests and routine health polling use the extension
service worker. However, `content.js` still calls `STC.getSettings()` directly
to choose the screenshot picker after capture. The shared capture-error
fallback also calls `/health` directly when the service worker cannot classify
the error. Removing page-origin CORS/PNA permission requires moving those
remaining calls to the service worker first. Public diagnostic redaction
applies to these origins too.

Extension CORS uses the same ID allowlist as `/token`, for both
`chrome-extension://<id>` and `moz-extension://<id>`. Unlisted or malformed
extension origins receive no CORS or Private Network Access permission. Origins
with paths, ports, credentials, query strings or fragments are refused.

`Access-Control-Allow-Private-Network: true` is required by Chromium's Private Network Access rules when a public HTTPS origin preflights a request to loopback.

## POST hardening

Except for the bodyless `/token` bootstrap described above, all POST routes
require the bearer token before reading the request body. JSON POST routes
then enforce the following limits (`POST /images` has its own raw-image body
validation and size limit):

- `Content-Type: application/json` is required.
- `Content-Length` is capped at 64 KB.
- Top-level JSON must be an object.

Protocol validation failures return `4xx` JSON errors. Handled application failures generally follow the existing Uoink pattern of HTTP 200 with `{ "ok": false, "error": "..." }`.

## URL and identifier validation

The dashboard's `openExternal` boundary classifies external opens by caller
provenance into three kinds. Unknown kinds are refused:

1. **Remote or server-supplied URLs**, except captured source links, use the
   default `remote` policy: HTTPS only, with the host `uoink.app` or a
   subdomain of it. Uoink help links use this policy too. A remote URL does
   not gain product or source permission by matching one of those destinations.
2. **Fixed product links** use `product` and an exact origin-and-path
   allowlist: `https://github.com/ryanbiddy/uoink`, its
   `/blob/main/CHANGELOG.md`, `/releases`, and `/issues` pages;
   `https://claude.ai/new`; `https://claude.ai/download`;
   `https://twitter.com/intent/tweet`; and `https://youtube.com`.
   No query or fragment is allowed except the tweet intent's dashboard-built
   `text` and/or `url` parameters, each at most once. For example,
   `https://claude.ai/new?next=https://evil.com` is refused.
3. **Captured-content source links** use `source`: HTTP or HTTPS only, with
   no userinfo or non-default port. This covers `data-source-link` anchors
   for `#yoinkSourceLink`, inline Markdown, reader timestamps, and Activity
   source names. All IP-literal hosts are refused, including loopback
   (`127.0.0.0/8`, `::1`), `0.0.0.0`, private ranges (`10/8`, `172.16/12`,
   `192.168/16`, `fc00::/7`), and link-local ranges (`169.254/16`, `fe80::/10`).
   `localhost`, `*.localhost`, `.local`, and `.internal` hosts are refused
   after removing trailing dots. The URL parser canonicalizes alternate IP
   spellings before the check. Hostname resolution and redirects are not
   checked by this dashboard URL policy.

All three kinds reject embedded credentials, control characters, backslashes,
and malformed URLs before calling the native URL opener or `window.open`.
Refused opens show a blocked-link toast; a successful copy cannot overwrite
it with a success toast. Delegated click and middle-click handlers check raw
link attributes, including links rendered after startup. Browser tabs use
`noopener,noreferrer`.

The fixed Startup action has one local exception: the exact `/splash` URL on
the dashboard's own loopback origin, without a query or fragment. Remote and
source links cannot use this exception. Open YouTube goes through the product
allowlist; it makes no `/open-last-youtube` request, so the helper cannot open
or focus a window before this check.

Capture API validation is separate from the dashboard's link-opening policy:

- Strict video capture recognizes YouTube, X/Twitter, TikTok, and Instagram
  host and path shapes. Each accepted URL is canonicalized before it reaches
  the extraction pipeline.
- YouTube video IDs must match ASCII `^[A-Za-z0-9_-]{6,}$`; X status IDs and
  handles, Instagram Reel/post paths, and TikTok hosts are checked by their
  platform-specific validators.
- Generic video, web-page, and podcast capture accepts HTTP(S) only. Embedded
  credentials and malformed ports are rejected, explicit ports are preserved,
  and bracketed IPv6 is rejected by the generic-video and page validators.
  Podcast feed normalization preserves bracketed IPv6, but fetching it is
  refused by the network policy below.
  IP literals are currently permitted only at the syntax-normalization step:
  IPv4 in generic-video and page URLs, and IPv4 or IPv6 in podcast feed URLs.
  A normalized URL is not permission to fetch it; network admission refuses
  these literals before connecting or starting an extraction engine.
- Podcast feed polls, the stdlib page fetcher (including Writing Studio's
  fallback), and thumbnail downloads share the standing-source fetcher's
  public-network checks. IP literals are refused, including public IPs and
  alternate numeric IPv4 spellings. Localhost names are also refused. Every
  resolved address must be public: private, loopback, link-local, shared-address,
  reserved, unspecified and multicast targets are refused. An IPv6 answer
  that carries an IPv4 address (IPv4-mapped `::ffff:0:0/96`, NAT64
  `64:ff9b::/96` or 6to4 `2002::/16`) must also pass the IPv4 check, and the
  NAT64 local-use prefix `64:ff9b:1::/48` is refused. A hostname that cannot
  be IDNA-encoded, such as one with an empty or over-long label, is refused
  before any lookup. Name and IP-literal checks use the IDNA form, so
  fullwidth spellings of `localhost` or an IP address count as those.
  Percent-encoded hosts are refused, because the HTTP client and yt-dlp
  decode them before connecting. DNS is checked for the exact host name the
  connection is made for, case and trailing dot included, and a URL whose
  connection host differs from its parsed host is refused. DNS is checked again for
  each fetch. Redirect targets are revalidated on every hop and
  must pass the HTTP(S), credentials, port, fragment and host-encoding checks.
- Podcast enclosure downloads and generic yt-dlp metadata extraction first
  follow a checked GET redirect chain, close the response without reading
  the body, and pass its final URL to yt-dlp after `--`. A failed check or
  unreachable destination prevents the subprocess from starting. This adds
  a request before extraction, with the podcast fetcher's User-Agent for
  enclosures and the page fetcher's User-Agent for generic URLs. The header
  is sent on every redirect hop. A host that rejects that request cannot be
  captured through these paths. `/extract/any` returns HTTP 400 with the
  refusal or preflight error, including response timeouts and HTTP protocol
  errors. Fixed YouTube hosts,
  including YouTube Music, and the strict X/Twitter, TikTok and Instagram
  paths retain their existing yt-dlp flow without this extra GET. That
  exemption covers only the strict validators' canonical URLs. Any other URL
  on those hosts, such as a `/live/status` probe that falls back to the
  relaxed validator, takes the checked GET. YouTube
  metadata requests keep their original URL and shared rate limiter.
- Crawl4AI page capture checks the initial URL and its DNS answers against
  the same public-network policy before starting the renderer, including
  Writing Studio requests that bypass the site allowlist. A refusal stops
  capture without falling back to another engine. If the renderer fails
  after admission, the stdlib fallback checks its own requests and redirects.
- Local and intranet sources that previously worked through these fetchers
  now fail, including saved feeds polled by the scheduler. Refused thumbnails
  are omitted; previously downloaded podcast audio remains usable. Localhost
  fixture servers require explicit transport/resolver injection in tests.
  The standing-source S20/S21 harnesses can still inject their exact loopback
  host through `_reject_private_ip` and `_check_resolved_host`; literal-host
  rejection belongs to the latter check. No setting or environment variable
  disables these checks in production.
- Connections made by these fetchers (feed polls, the stdlib page fetcher,
  thumbnail downloads and the checked GET before yt-dlp) are pinned: each hop
  dials only the addresses that passed the check for it, in resolver order,
  and never resolves the name again, so a DNS answer that changes after the
  check (DNS rebinding) cannot move the connection. The Host header, TLS SNI
  and certificate hostname verification still use the original host name.
  These fetches connect directly and do not use system or environment proxy
  settings, because a proxy would resolve the name again.
- Requests made inside the Crawl4AI browser renderer and by yt-dlp after
  admission are not covered: those engines resolve names themselves, so they
  are not pinned and remain exposed to DNS rebinding. For these engine-owned
  requests, redirect targets are not revalidated by Uoink, nor are subresource
  requests. Those engines are not network-sandboxed by these checks.
- Playlist IDs must match ASCII `^[A-Za-z0-9_-]{2,}$`; playlist processing is capped at 10 videos.
- Session IDs must match `^[A-Za-z0-9_-]{1,64}$`.
- Job IDs must match `^job_[A-Za-z0-9_-]{1,96}$`.
- Folder names come from `slugify()`, which emits ASCII path segments and guards Windows reserved device names.

## `/file` sandbox

`GET /file?path=<absolute-path>` serves screenshot thumbnails to the popup. It is token-gated and intentionally narrow:

- The path must be absolute.
- Raw and resolved paths containing a `..` segment are rejected.
- Symlinks are resolved before sandbox checks.
- The resolved file must be under the Uoink output root (`Desktop\Uoink`, or a legacy `Desktop\Yoink` corpus not yet moved, via Windows known-folder resolution by default; or `UOINK_OUTPUT_DIR` / legacy `YOINK_OUTPUT_DIR` when explicitly set in dev/support mode).
- The path must exist and be a regular file.
- Files larger than 10 MB are rejected.
- Only `.png`, `.jpg`, `.jpeg`, and `.webp` are served.
- Magic bytes must match the extension-derived MIME type.
- Responses use `Cache-Control: private, max-age=300`.

## Corpus import sandbox

To import a backup through `POST /corpus/import` or the local CLI
`--import-corpus <file>`, copy the export JSON into the active output folder's
`_exports` directory and supply its absolute path. Both entry points enforce
this boundary; the CLI also rejects relative paths and backups in other folders.
Subdirectories are allowed. Other output locations and sibling folders such as
`_exports-old` are outside this boundary, even if `/file` can serve their images.

The helper rejects relative paths and `..` segments, resolves the file and
export directory, then checks containment before probing or reading the file.
File symlinks and directory junctions cannot point outside `_exports`, and
`_exports` itself cannot resolve outside the output root. Invalid paths, missing
files, unreadable files and invalid exports return HTTP 400, or JSON with
`ok: false` from the CLI; error responses do not echo local paths. The Host
allowlist, token requirement and JSON body limits still apply before HTTP import
processing.

Export format and conservative merge rules are unchanged. A local index rebuild
with an explicit root still restores the newest export under that root's
`_exports`; HTTP callers cannot override the root in their request body.

## Anthropic API key storage

Comment Intelligence, Hook Type, Entity Extraction, Writing Studio saved-key generation, and explicit research playbook runs are optional BYO-key features. Comment Intelligence and Hook Type also run on demand when a connected agent calls their MCP tools, and agents can ask Writing Studio to generate with the saved key, whatever the automatic-analysis settings. Normal Uoink extraction and local playbook packets work without an Anthropic key.

Starting in v2.0, the key is stored through Python `keyring`:

- Service (normal mode): `Uoink` (renamed from `Yoink` in v2.1; the first-run install migration copies the entry and deletes the legacy one)
- Service (isolated mode): `Uoink-isolated-<hash>` where `<hash>` is a deterministic 32-character hex digest of the canonical validated profile path (`hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]`). This separates profile credentials even when sharing loopback ports and preserves credential identity across port changes. Path resolution errors do not select an alternate credential namespace.
- Username: `anthropic_key`
- Windows backend: Windows Credential Manager
- macOS backend: macOS Keychain

`settings.json` stores only public booleans and key status flags. `GET /settings` returns `anthropic_key_set: true|false`, never the key itself.

Isolated mode credential semantics:

- Read, write, and delete operations in isolated mode operate strictly on the profile's isolated service namespace (`Uoink-isolated-<hash>`).
- Isolated reads fail closed when no key is present: they never fall back to the ordinary `Uoink` service or legacy `Yoink` service.
- Two profiles sharing a loopback port do not share credentials.
- A profile that changes ports retains its credential identity because the namespace is derived solely from the canonical profile path.
- In isolated mode, plaintext `anthropic_key` migration from the isolated `settings.json` writes exclusively to the isolated service namespace.
- Destructive operations such as Anthropic 401 invalid-key resets clear only the isolated profile's credential entry, never mutating or clearing ordinary `Uoink` credentials.
- Normal (non-isolated) mode retains existing `Uoink` storage with `Yoink` read fallback and one-time install migration.

Migration behavior:

1. On helper startup, if legacy `%LOCALAPPDATA%\Uoink\settings.json` (or an isolated profile's `settings.json`) contains plaintext `anthropic_key`, Uoink attempts to move it into keyring.
2. On successful migration, the plaintext field is removed from `settings.json`.
3. If keyring is unavailable, migration is skipped and logged; Uoink does not silently create a new plaintext fallback.

Anthropic 401 responses destructively clear the saved key from keyring (scoped to the active service namespace) and mark `anthropic_key_set` false until the user saves a key again.

## Persistence files

Installed Windows builds store helper state under `%LOCALAPPDATA%\Uoink\` (migrated from `\Yoink\` on first launch — see "Install migration" below):

- `settings.json` - feature toggles and public key status only; no API key.
- `index.db` - local SQLite library index for uoink metadata, FTS5 search text, jobs, taxonomy rows, citation maps, and health scores. Contains no API keys, calls no remote endpoints, and never leaves the user's machine.
- `jobs.json.migrated` - legacy job records after first Sprint 15 migration into `index.db`.
- `taxonomy.json.migrated` - legacy Hook Type records after first Sprint 15 migration into `index.db`.
- `token.txt` - random helper token generated with `secrets.token_urlsafe(32)`.
- `server.pid` - best-effort helper process id for Stop Uoink.
- `server.log` - local diagnostic log.
- `models\whisper\` - optional local Whisper model cache for other model sizes, downloaded only when the user asks from the dashboard. Since 3.12 the default `base` model ships read-only in the install folder (`{app}\models\whisper-bundled\base\`; on macOS `Uoink.app/Contents/Resources/models/whisper-bundled/base/`), pinned to a Hugging Face revision and SHA-256 checked at build time. A downloaded copy of the same size takes precedence.
- `.migration-complete` / `.migrated-from-yoink` - markers written by the v2.1 install migration (see below).

Corpus, sidecar, settings, and migration writes use temp-file-and-replace patterns where practical. Corrupt `index.db` is quarantined as `index.db.corrupt-<timestamp>` and rebuilt from on-disk corpora through a local backfill scan. Legacy corrupt `jobs.json` or `taxonomy.json` migration input is logged and left in place rather than crashing the helper.

Machine error details pass through `_sanitize_error` before a job stores them or
an extraction/session response returns them. Paths become `<path>`, URLs with
userinfo become `<url>`, and recognized API keys and labelled credentials become
`[redacted]`. This includes quoted paths with spaces, Windows drive and UNC paths,
Unix paths, API-key fields and authorization headers. Each line is sanitized
separately, with spaces and tabs compacted. Machine details retain line breaks
between `Command:`, `Exit code:` and tool output, so extension notifications can
still select the last `ERROR:` line. Credential labels require `:` or `=`, except
CLI flags such as `--password` and `Bearer`/`Basic` auth schemes, which also accept
a space or tab. CLI flags include prefixed forms such as `--video-password`, and
they also accept `--flag=value` and the comma of a Python or JSON argument list,
as in `'--token', 'value'` (the form `str()` of a subprocess error prints).
For failed or timed-out subprocesses with an argument list, credential values
are replaced before the command is joined or quoted. Both `--flag value` and
`--flag=value` redact the entire argument, including spaces and line breaks.
The same flag names are recognized in free-text diagnostics.
A quoted value in free text runs to its matching unescaped quote,
the one followed by whitespace, the end of the line or only closing punctuation
(such as `', ` or `']'`), so commas, escaped quotes and apostrophes inside it are
redacted too; a quoted value without such a closing quote is redacted to the end
of its line. An unquoted value runs to the next whitespace. Ordinary diagnostics
such as "This video requires a GVS PO Token which was not provided." are
preserved. Free-text credential matches do not cross line breaks.
Spaces within unquoted directory names are supported when a separator follows.
Once a path starts, redaction consumes its full non-whitespace suffix, including
apostrophes, colons and repeated separators such as doubled backslashes.
Quoted absolute paths redact through the end of their line unless the last
same-quote closer follows a filename with an extension and the remaining text
is a complete diagnostic phrase, such as `failed`, `wasn't found` or `is locked`.
For example, `file '/home/x.json' wasn't found` becomes `file <path> wasn't found`,
but `file '/home/james' smith failed` becomes `file <path>`. This also removes
ambiguous names such as `James' O'Brien`, tails with no separators or dots,
and any later paths on that line. Windows drive and UNC paths follow the same
rule. Several quoted paths and intervening words can become one `<path>`.
The rule can also hide the rest of a command or diagnostic line after a quoted
path, including placeholders for URLs or credentials already redacted there.
Unterminated paths and paths cut off by the 65,536-character input cap redact
to the end of the available line. Redaction never crosses a line break.
Unquoted spaced directories can contain colons, such as `james' smith:family`.
Unquoted paths end at whitespace after the final component, preserving separate
path placeholders and trailing diagnostic text. Retry details keep their
200-character limit.
Sanitizer input is capped at 65,536 characters before splitting lines or
running regexes. Redaction then runs before the existing 6,000-character
failed-subprocess detail and 3,000-character other-exception limits. Longer
diagnostics keep only their prefix, as before; the full text remains in
`server.log`. Timeout details use separate `Command:` and `Timeout:` lines.
The sanitizer does not read credentials to perform these replacements.

URLs (`scheme://...`) become `<url>` as a whole before path redaction. A drive
letter or `/` directly after a letter or digit does not start a path, so text
such as "download/network issue" or "and/or" is unchanged and phase errors
match their sanitized detail.

The failure handlers that record a machine error detail (single-video and
playlist extraction, session capture, the retry queue and podcast
transcription) write the raw text, including command lines and tool
stderr/stdout, only to the local `server.log` through a file-only logger. The
job's `error` and `error_detail`, a podcast episode's transcript error and a
deferred podcast publish error store only sanitized text. For a podcast
transcription failure, the job's `error`, the episode's transcript error and the
console line are a one-line summary: a failed subprocess is recorded only as its
type and exit status (`CalledProcessError: exit status 1`), a subprocess timeout
as `TimeoutExpired: timed out after N seconds`, and other exceptions as their
sanitized text. A deferred podcast publish error (`corpus_error` in the job
result, and its console line) uses the same summary. The podcast job's
`error_detail` keeps the exception type and the sanitized machine detail; for a
subprocess error that includes the redacted command line and, for a failed
subprocess, its redacted output. The console line each of the other
handlers logs for the failure uses fixed or sanitized text; podcast
transcription and deferred-publish tracebacks also go only to `server.log`.
Optional subtitle-fetch and comments-worker failures follow the same rule:
raw exceptions and yt-dlp output go to the file-only logger, while the console
gets a sanitized summary. A comments failure no longer prints yt-dlp's last
stderr line to the console. Subtitle-refusal detection and comments status
updates are unchanged.
Other helper log lines are unchanged and still go to both the console and
`server.log`; some include local paths, the output folder or a tool's last
error line. Review `server.log` before sharing it: it can contain the paths and
credentials removed from dashboard errors. This change does not purge
historical job records or existing logs.

## MCP security model

Uoink supports MCP over stdio and an experimental local HTTP JSON-RPC helper.

- Stdio MCP is the officially supported launch transport. The MCP client launches `uoink_mcp.py` (a back-compat `yoink_mcp.py` shim re-exports it through the alias window) as a local subprocess, so the trust boundary is the spawning local client.
- HTTP JSON-RPC under `/mcp/v1` is token-gated with `X-Uoink-Token` (legacy `X-Yoink-Token` accepted). It supports direct JSON-RPC POST calls but is not a spec-complete SSE or Streamable HTTP MCP implementation.

MCP tools reuse the same backend validation for URLs, slugs, job IDs, file paths, and Anthropic key behavior. The six deprecated `yoink_*` tool aliases are no longer listed or accepted; clients must use the canonical `uoink_*` names.

## Dependency and installer integrity

`build.ps1` pins runtime package versions and verifies SHA256 for directly downloaded artifacts:

- Python embeddable
- ffmpeg
- `get-pip.py` from an immutable reviewed PyPA `get-pip` commit

Installer-installed Python packages (`yt-dlp`, `Pillow`, `mcp`, `keyring`,
`pystray`, `pywebview`, `pythonnet`, `faster-whisper`, and `whisperx`) and
their complete transitive graph are exact-version constrained by
`requirements-installer-lock.txt`. The build verifies the final installed
inventory against that lock after removing separately pinned build tooling,
unused path-bound console launchers, generated bytecode, and the staged-smoke
token. Builds do not reuse pip's wheel cache, and compiler-input timestamps
are normalized before Inno Setup runs. Full pip distribution hash locking
remains a future hardening item.

Transcript reliability detection is local-only and uses `faster-whisper` word
probabilities. Since 3.12 the default `base` weights ship with the app, read-only
and loaded by directory path (`scripts/whisper_model_pin.json` pins the revision
and every file's SHA-256; the build refuses a mismatch). The automatic
capture-time check uses local files only and never authorizes a download;
`ensure_model` is the explicit user-triggered download path for other sizes. On
Windows a downloaded model is cached under `%LOCALAPPDATA%\Uoink\models\whisper`
and is never uploaded.

Speaker labeling is a separate WhisperX/pyannote path in `whisper_runner.py`.
When diarization is requested, it loads alignment and speaker models, then
passes the local audio path to the pipeline. Those loaders may download model
files, including from Hugging Face; the cached-only transcription-model check
does not cover them. The speaker pipeline selects
`pyannote/speaker-diarization-community-1` when the installed WhisperX accepts
`model_name`. A token from `HF_TOKEN`, `HUGGINGFACE_TOKEN` or
`HUGGING_FACE_HUB_TOKEN` is passed to the loader when supported. Uoink records
whether speaker labeling succeeded; a failure returns the transcript without
claiming successful diarization.

Uoink 3.10.0 keeps Torch 2.8.0 and WhisperX 3.8.6. Default voice activity
detection (VAD) loads through PyAnnote's checkpoint loader with
`weights_only=False`, the same path used in 3.7.0. This permits checkpoint code
to run during loading; the mitigation for this release is local-only model
files. Migration to a safer loading path remains planned.

Uoink 3.10.0 ships unsigned: `SigningCertificateThumbprint=none`. Signing is
skipped for this release; the signing path remains available for a future release.
Windows SmartScreen warnings are expected for unsigned builds.

## macOS status

Uoink 3.11.2 ships a Mac preview for Apple Silicon. The app and DMG are signed
with a Developer ID under the hardened runtime, with no entitlements, then
notarized by Apple and stapled. Uoink does not use the App Sandbox. API keys
are stored in the macOS Keychain via `keyring`. Login startup is a per-user
LaunchAgent (`~/Library/LaunchAgents/com.ryanbiddy.uoink.plist`) that stays
off until you enable it in settings. `docs/mac-install.md` records the current
user-facing status, and `docs/mac/BUILD.md` the build, signing and
qualification pipeline.

## Install migration (v2.1)

On first launch the new helper runs a one-time, local-only migration
(`migrate_install.py`): it **copies** (never moves) `%LOCALAPPDATA%\Yoink\` to
`\Uoink\`, copies the saved Anthropic key from the legacy `Yoink` credential
service to `Uoink` (then deletes the legacy entry), and rewrites the HKCU `Run`
autostart value from `Yoink` to `Uoink`. The legacy folder is left intact for a
7-day grace period and only hard-deleted after a verified, healthy `\Uoink\`.
No data leaves the machine; the registry/keyring writes are gated to the
installed layout so a dev run from the repo never mutates the real machine. A
failed keyring step is non-fatal; check authenticated Settings for key status.
Public `/diagnose` does not report whether a legacy key exists or migrated.
The Desktop corpus (`Desktop\Yoink\`) is migrated only on explicit user opt-in via the extension
popup (`POST /migration/move-desktop-corpus`), never automatically.

## What Uoink does not collect

Uoink has no cloud library or account system. Extraction and files stay on the user's machine.

Uoink sends no usage data by default. If you turn on "Share anonymous usage counts", it sends daily counts to usage.uoink.app: calls by tool name, known MCP clients, stdio or HTTP calls, captures by source and result, and library searches. Reports include a random install ID, app version, operating system and major version, processor type, install type and hours counted. They never include content, URLs, titles, paths, search text, usernames, IP addresses or account details.

Counts use a separate local SQLite file, not the library index. Only the helper
sends HTTPS reports, at most once every 24 hours, with a five-second timeout.
Isolated installs never send. Tests require an explicit non-production endpoint
override. No tokens or API keys are used for usage sharing.

The dashboard and extension use bundled Inter, Bungee and JetBrains Mono
fonts. They make no Google Fonts requests to `fonts.googleapis.com` or
`fonts.gstatic.com`.

The dashboard makes no features-manifest request to
`https://uoink.app/api/features-manifest`, on load or when switching views.
The Features view, remote catalogue loader, and bundled fallback catalogue
have been removed. Uoink help links open only when the user clicks them.

Optional AI features use the user's Anthropic key for enabled automatic
analysis, key tests, or explicit on-demand actions, including connected-agent
requests and `POST /playbooks/run`. Playbook runs send the fixed instruction
and bounded library packet described above. YouTube downloads still contact
YouTube, and yt-dlp may contact YouTube-owned endpoints as part of uoink
extraction.

## Engagement memory (v2.5 S2)

Uoink v2.5 records local engagement events (`opened`, `search_hit`, `search_click`, `paste`, `cite`, `recent_open`) in the `engagement_events` SQLite table so the library can surface what the user actually returns to. **These events are local-only and never leave the machine.** They are not transmitted to Anthropic when BYO-key AI features run; the `value_score` formula and time-decay computation happen entirely in `index.py`. The events do not include any YouTube-side identifiers beyond the `video_id` already stored alongside the saved uoink. Deleting a saved uoink does not automatically purge its engagement rows -- delete the SQLite file under `%LOCALAPPDATA%\Uoink\` to clear the full local history.

## Transcript reliability detection (v2.5 A1)

Transcript reliability detection does not call Anthropic or any third-party API. It reuses the local video/audio during extraction when possible, or re-downloads audio from YouTube for a user-triggered reliability compute. Whisper inference runs on the user's machine.

## Claim extraction + verification (v3 A2, Loki-inspired)

Uoink v3 ships **claim extraction + verification assistance** inspired by [Libr-AI/OpenFactVerification](https://github.com/Libr-AI/OpenFactVerification) ("Loki"). See `vendor/loki/VENDOR.md` for the pinned-commit design reference + license attribution.

**Posture: assistance only.** Uoink never auto-asserts a truth verdict on a claim. The MCP tools and SQLite layer enforce this -- the `alignment_signal` enum on each evidence row is restricted to `supports | contradicts | mixed | inconclusive`. There is no `true` / `false` / `lie` value. The user judges the verdict from the surfaced evidence.

**Compute path.** Per the locked compute policy, the calling agent does the LLM decomposition + verification-query work using its own model via MCP (`extract_claims` + `verify_claim` tools). The helper validates the structure and persists. BYO-key on-server compute is scaffolded by the `mode` enum but not implemented in this PR -- same posture as S1's `/facets/backfill`.

**Outbound surface.** The verification step (step 4 of the Loki pipeline) is the *first new outbound surface* in A2: when an agent retrieves evidence for a claim, it uses its own web-search tooling under the user's direction. The helper records the resulting source URLs + quotes verbatim. The helper itself does not initiate any web requests for claim verification.

**Opt-in by default.** A new settings flag `claim_verification_enabled` (default `false`) gates batch / auto-extract flows. Single-claim verification through the endpoint is always available because a single explicit verification is consent enough.

## Reporting

If you find a vulnerability, please open a private GitHub Security Advisory or report it to **hi@uoink.video**. Do not open a public issue with reproduction details until a fix is shipped.

## ScrapeCreators outbound requests

Discovery is off by default, as is `scrapecreators_agent_calls_enabled`.
Paid calls need enabled discovery, a saved key, exact credit confirmation,
room under the daily cap (25 by default), and either a dashboard intent or
agent opt-in. HTTP supplies origin/session context outside tool arguments;
stdio cannot borrow a dashboard token. Queueing needs the same intent or agent
opt-in, but no provider key or credits. The registry limits discovery to six
calls per minute and queueing to 30.

The adapter pins HTTPS to `api.scrapecreators.com` and its endpoint allowlist.
The base URL is not configurable, and all redirects are refused. Each request
has an 8-second timeout and an 8 MB response cap. Only one request can be in
flight per process, with at least one second between sends and at most three
requests per run. A 429 or 5xx stops the run without an automatic retry.
Credits count requests sent, including failures, in a local UTC daily ledger.
A 401/403 preserves the key and marks it invalid; the settings lock and key
comparison keep a late response from invalidating a replacement credential.

API key storage uses username `scrapecreators_key` in `Uoink` or the
profile-specific `Uoink-isolated-<hash>` service. Isolated storage fails closed.
There is no plaintext or environment-variable fallback. Requests send only
the creator identifier/search terms, pagination parameters, key header and
Uoink user agent; library content is not sent. No ScrapeCreators thumbnails
are loaded. Run files retain the submitted query, handle or channel_id, run
identity, provider, endpoint, mode, platform, fetch time, credit counts, daily
cap, page/item coverage, normalized candidates and metrics, computed baselines,
queue receipts, capture state and standard error envelopes, including failed
runs. Raw vendor responses and API keys are not saved in these files. Files
are byte-capped and atomically replaced; the daily purge removes records older
than 90 days. Local packets read at most 24 run files within 30 days. Newly
saved empty failed runs are marked in their filenames and skipped before this
read budget, preserving older eligible snapshots and keyword fallback.
Picked URLs are revalidated before entering `pending_yoinks`, and saved runs
are never interpreted as capture instructions.
If the initial run save fails, the response keeps the candidates and adds
`save_failed: true`. A copy stays in helper memory until saved or the helper
exits. The dashboard offers a local save retry and blocks queueing or another
paid run while that receipt is unsaved. Capture reconciliation distinguishes
deleted, unavailable and cancelled captures from actual failed attempts;
active pending, running and publishing rows remain queued.
Normalized pages are retained before local library lookups. A failed lookup,
failure-counter write or final daily-total read cannot discard fetched rows.
An unreadable daily total returns `credits_today: null` with an error; the
next paid request still requires a successful ledger check before sending.
