# Uoink security model

Status: launch-facing for v2.1 (the Yoink → Uoink rename)

> v2.1 alias-window note: the auth header is now `X-Uoink-Token` and the
> `/token` gate header is `X-Uoink-Client: uoink-extension`. The legacy
> `X-Yoink-Token` / `X-Yoink-Client: yoink-extension` names are still accepted
> through Uoink v2.5 (removed in v3) so a not-yet-updated extension keeps
> working. Both forms appear below where relevant.

Uoink is local-first software with two pieces:

- A browser extension that injects UI on YouTube and talks to a local helper.
- A Python helper bound to `127.0.0.1:5179` that downloads public YouTube data, writes local corpus files, serves local thumbnails, and exposes optional MCP tools.

The helper never binds to a public network interface. The main security boundary is therefore local-machine trust: browser pages should not be able to drive the helper without the extension token, but software or browser extensions already running with the user's privileges are treated as trusted local code.

## Threat model

| Threat | Defended? | Notes |
|---|---:|---|
| Malicious webpage tries to call `127.0.0.1:5179` | Yes | Token-gated endpoints require `X-Uoink-Token` (legacy `X-Yoink-Token` accepted); `/token` requires a custom `X-Uoink-Client` header (legacy `X-Yoink-Client` accepted) and browser CORS/PNA preflight blocks normal webpages from setting it cross-origin. |
| Malicious webpage probes whether Uoink is running | Not treated as secret | `/health` and `/ping` are public liveness probes. They reveal only `{ok:true, version}`. |
| Local malware reads files or calls localhost | No | Malware already running as the user can read local files, call local ports, and modify output. Uoink does not try to sandbox against same-user malware. |
| Another installed browser extension calls `/token` | Not fully | v2 accepts `chrome-extension://*` origins so Chromium forks and dev installs work. Published Chrome Web Store extension ID pinning is deferred until the final ID is known and stable. |
| Network attacker | Mostly not applicable | The helper listens only on `127.0.0.1`, not LAN/public interfaces. |
| Anthropic API key disclosure through settings | Mitigated | The key is stored in the OS credential store via `keyring` (service `Uoink`; the v2.1 install migration moves it from the legacy `Yoink` service), not in `settings.json`, and is never returned by `GET /settings`. |
| Dependency compromise | Partially | Direct downloads are SHA256-checked in `build.ps1`; pip packages are version-pinned but not hash-locked. |

## Public endpoints

These do not require `X-Uoink-Token`:

- `GET /health`
- `GET /ping`
- `GET /token`
- `GET /index/backfill-status`

`/health` and `/ping` are intentionally public because the extension, setup page, and YouTube button need to detect whether the helper is running before auth/token refresh completes.

`/index/backfill-status` is intentionally public for the same UI bootstrapping reason. It exposes only `state`, `current`, and `total` counts, not corpus content or file paths.

`/token` returns the per-install helper token and is guarded by:

- `X-Uoink-Client: uoink-extension` (legacy `X-Yoink-Client: yoink-extension` accepted through the alias window)
- `Origin` that is empty or `chrome-extension://*`
- A server-wide 10 requests/minute rate limit

The empty-Origin allowance is deliberate. Some Chromium service-worker fetches observed during Comet testing omit `Origin`. The custom-header+CORS preflight gate is the load-bearing browser CSRF defense.

## Token-gated endpoints

All other helper endpoints require `X-Uoink-Token` (legacy `X-Yoink-Token` accepted):

- Single-video extraction: `POST /extract`
- Playlist jobs and index progress control: `POST /playlist/preview`, `POST /playlist/start`, `GET /jobs`, `GET /jobs/<id>`, `POST /jobs/<id>/cancel`, `POST /index/backfill-cancel`
- Sessions: `POST /session/start`, `POST /session/add`, `POST /session/close`, `POST /session/cancel`, `POST /session/open`, `GET /session/list`, `GET /session/active`
- Settings, AI key testing, and local cost estimates: `GET /settings`, `GET /settings/pricing`, `POST /settings`, `POST /settings/test-key`
- Local files, folders, Skill prompt, and hook taxonomy: `GET /file`, `GET /skill/system-prompt`, `GET /taxonomy`, `GET /recent`, `GET /open-folder`, `GET /open-index`, `GET /open-prompts`
- MCP HTTP JSON-RPC helper: `GET /mcp/v1/config`, `GET /mcp/v1/sse`, `POST /mcp/v1`, `POST /mcp/v1/initialize`, `POST /mcp/v1/tools/list`, `POST /mcp/v1/tools/call`

The token is accepted only in the `X-Uoink-Token` header (or the legacy `X-Yoink-Token` header during the alias window). Query-string token auth is intentionally unsupported so tokens do not leak into browser history, server logs, or HTTP debug tools that capture URLs.

## CORS and Private Network Access

For allowed origins, the helper sends:

```http
Access-Control-Allow-Origin: <allowed origin>
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Uoink-Token, X-Uoink-Client, X-Yoink-Token, X-Yoink-Client
Access-Control-Allow-Private-Network: true
```

Allowed web origins are YouTube pages used by the content script:

- `https://www.youtube.com`
- `https://m.youtube.com`
- `https://youtube.com`

Extension origins are accepted as `chrome-extension://*`. This is broad by design for v2 dev/fork compatibility; extension ID pinning should be revisited after Chrome Web Store publication.

`Access-Control-Allow-Private-Network: true` is required by Chromium's Private Network Access rules when a public HTTPS origin preflights a request to loopback.

## POST hardening

All POST routes are authenticated before reading the request body. After auth:

- `Content-Type: application/json` is required.
- `Content-Length` is capped at 64 KB.
- Top-level JSON must be an object.

Protocol validation failures return `4xx` JSON errors. Handled application failures generally follow the existing Uoink pattern of HTTP 200 with `{ "ok": false, "error": "..." }`.

## URL and identifier validation

- Video URLs are parsed with `urllib.parse.urlparse`, checked against an explicit YouTube host allowlist, and canonicalized to `https://www.youtube.com/watch?v=<id>`.
- Video IDs must match ASCII `^[A-Za-z0-9_-]{6,}$`.
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

## Anthropic API key storage

Comment Intelligence, Hook Type, and Entity Extraction are optional BYO-key features. Normal Uoink extraction works without an Anthropic key.

Starting in v2.0, the key is stored through Python `keyring`:

- Service: `Uoink` (renamed from `Yoink` in v2.1; the first-run install migration copies the entry and deletes the legacy one)
- Username: `anthropic_key`
- Windows backend: Windows Credential Manager
- macOS backend: macOS Keychain

`settings.json` stores only public booleans and key status flags. `GET /settings` returns `anthropic_key_set: true|false`, never the key itself.

Migration behavior:

1. On helper startup, if legacy `%LOCALAPPDATA%\Uoink\settings.json` (or a pre-rename `\Yoink\settings.json` migrated into it) contains plaintext `anthropic_key`, Uoink attempts to move it into keyring.
2. On successful migration, the plaintext field is removed from `settings.json`.
3. If keyring is unavailable, migration is skipped and logged; Uoink does not silently create a new plaintext fallback.

Anthropic 401 responses destructively clear the saved key from keyring and mark `anthropic_key_set` false until the user saves a key again.

## Persistence files

Installed Windows builds store helper state under `%LOCALAPPDATA%\Uoink\` (migrated from `\Yoink\` on first launch — see "Install migration" below):

- `settings.json` - feature toggles and public key status only; no API key.
- `index.db` - local SQLite library index for uoink metadata, FTS5 search text, jobs, taxonomy rows, citation maps, and health scores. Contains no API keys, calls no remote endpoints, and never leaves the user's machine.
- `jobs.json.migrated` - legacy job records after first Sprint 15 migration into `index.db`.
- `taxonomy.json.migrated` - legacy Hook Type records after first Sprint 15 migration into `index.db`.
- `token.txt` - random helper token generated with `secrets.token_urlsafe(32)`.
- `server.pid` - best-effort helper process id for Stop Uoink.
- `server.log` - local diagnostic log.
- `.migration-complete` / `.migrated-from-yoink` - markers written by the v2.1 install migration (see below).

Corpus, sidecar, settings, and migration writes use temp-file-and-replace patterns where practical. Corrupt `index.db` is quarantined as `index.db.corrupt-<timestamp>` and rebuilt from on-disk corpora through a local backfill scan. Legacy corrupt `jobs.json` or `taxonomy.json` migration input is logged and left in place rather than crashing the helper.

## MCP security model

Uoink supports MCP over stdio and an experimental local HTTP JSON-RPC helper.

- Stdio MCP is the officially supported launch transport. The MCP client launches `uoink_mcp.py` (a back-compat `yoink_mcp.py` shim re-exports it through the alias window) as a local subprocess, so the trust boundary is the spawning local client.
- HTTP JSON-RPC under `/mcp/v1` is token-gated with `X-Uoink-Token` (legacy `X-Yoink-Token` accepted). It supports direct JSON-RPC POST calls but is not a spec-complete SSE or Streamable HTTP MCP implementation.

MCP tools reuse the same backend validation for URLs, slugs, job IDs, file paths, and Anthropic key behavior. Deprecated `yoink_*` tool aliases resolve to the canonical `uoink_*` handlers with no change in validation.

## Dependency and installer integrity

`build.ps1` pins runtime package versions and verifies SHA256 for directly downloaded artifacts:

- Python embeddable
- ffmpeg
- `get-pip.py`

Pip-installed packages (`yt-dlp`, `Pillow`, `mcp`, `keyring`) are version-pinned but not hash-locked yet. Full pip `--require-hashes` is a future hardening item.

The installer is unsigned for launch unless a code-signing certificate is added. Windows SmartScreen warnings are expected for unsigned builds.

## macOS-specific security posture

- **Keychain Storage:** The Anthropic API key is stored securely in the macOS Keychain under the service name `Uoink` (username `anthropic_key`; migrated from the legacy `Yoink` service on first launch), mirroring the security posture of Windows Credential Manager.
- **Gatekeeper & Notarization:** The `.dmg` packaging pipeline codesigns `Uoink.app` and notarizes the installer with Apple's developer notarization service to prevent Gatekeeper warnings and protect against tampered downloads.
- **LaunchAgent Isolation:** Auto-start behavior is handled by a standard LaunchAgent running in user-space (`~/Library/LaunchAgents/com.ryanbiddy.uoink.plist`). The helper runs under the active user's standard permissions, requiring no root or administrator privilege escalation.
- **Cross-Platform Sandbox:** The `/file` sandbox boundary behaves identically on macOS, resolving paths cross-platform via Python `Path` and restricting file access exclusively to the configured `~/Desktop/Uoink/` output root directory.

## Install migration (v2.1)

On first launch the new helper runs a one-time, local-only migration
(`migrate_install.py`): it **copies** (never moves) `%LOCALAPPDATA%\Yoink\` to
`\Uoink\`, copies the saved Anthropic key from the legacy `Yoink` credential
service to `Uoink` (then deletes the legacy entry), and rewrites the HKCU `Run`
autostart value from `Yoink` to `Uoink`. The legacy folder is left intact for a
7-day grace period and only hard-deleted after a verified, healthy `\Uoink\`.
No data leaves the machine; the registry/keyring writes are gated to the
installed layout so a dev run from the repo never mutates the real machine. A
failed keyring step is non-fatal and surfaced in `/diagnose` as "re-enter your
Anthropic key" rather than a silent empty key. The Desktop corpus
(`Desktop\Yoink\`) is migrated only on explicit user opt-in via the extension
popup (`POST /migration/move-desktop-corpus`), never automatically.

## What Uoink does not collect

Uoink has no Uoink cloud service, account system, telemetry endpoint, or hosted analytics. Extraction and files stay on the user's machine.

Optional AI features send selected comment/hook context to Anthropic only when the user provides an API key and enables those features. YouTube downloads still contact YouTube, and yt-dlp may contact YouTube-owned endpoints as part of uoink extraction.

## Reporting

If you find a vulnerability, please open a private GitHub Security Advisory or report it to **hi@uoink.video**. Do not open a public issue with reproduction details until a fix is shipped.
