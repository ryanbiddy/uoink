# Where else Uoink can plug in (research, 2026-10-30)

This list covers launchers, OS automation, hardware, browsers, notes apps, AI
directories and package stores. It skips what already ships: the ~50
`uoink connect` MCP recipes, the Chrome extension, the Obsidian mirror, and the
new [Raycast extension](../integrations/raycast/README.md).

**Update, same day:** built in this branch, not yet submitted. Native
integrations for Flow Launcher, Alfred and Obsidian are in
[`integrations/`](../integrations/README.md). winget and Homebrew manifests are
in [`packaging/`](../packaging/README.md). The agent-kit plugin's README and
LICENSE blockers are fixed. Paste-ready submissions are in
[`docs/submissions/`](submissions/README.md).

Effort is an estimate: **S** = days, **M** = 1–2 weeks, **L** = new toolchain,
signing or packaging work. Rows marked *search-only* were not confirmed against
official docs, because this session's network blocked many doc sites. Re-check
them before you build.

Two facts shape most rows:
- Uoink listens only on `127.0.0.1`. A cloud service can't call it. Uoink can
  still push data out to a cloud API, such as Readwise or Notion.
- Windows Uoink is an unsigned Inno Setup install with no package identity.
  That blocks Windows features that need an MSIX identity (Share target, App
  Actions, contained ODR).

## Recommended order

| # | Do this | Effort | Why |
|---|---|---|---|
| 1 | **Turn the agent-kit plugin into a Claude directory submission** | S–M | Anthropic's directory [no longer accepts `.mcpb`](https://claude.com/docs/directory/publish); a local MCP server must ship inside a plugin bundle. `agent-kit/plugins/uoink` has no README or LICENSE, and its `.mcp.json` runs `${LOCALAPPDATA}\Uoink\python\python.exe`, which is Windows-only. Both block validation ([checklist](https://claude.com/docs/plugins/pre-submission-checklist.md)). Fix: README of at least 40 words, LICENSE, and a launch command on PATH, for example a new `uoink mcp` subcommand. |
| 2 | **Get Uoink's Glama score** | S | The awesome-mcp-servers [PR #16963](https://github.com/punkpeye/awesome-mcp-servers/pull/16963) is waiting on it. Re-run the build per `docs/GLAMA-BUILD.md`. |
| 3 | **Submit the extension to Edge Add-ons** (and the prepared Chrome Web Store package) | S | The same MV3 package works; Edge supports `offscreen`. Free, certified in up to 7 business days. Ends sideloading on Windows' default browser. |
| 4 | **Quick directory round** | S each | Goose: PR an entry to [`servers.json`](https://raw.githubusercontent.com/aaif-goose/goose/main/documentation/static/servers.json); it already lists local apps that must be running. Cline: open an issue with a 400×400 logo ([rules](https://raw.githubusercontent.com/cline/mcp-marketplace/main/README.md)). GitHub MCP registry: ask for onboarding in [discussion #1257](https://github.com/github/github-mcp-server/discussions/1257). mcp.so and PulseMCP: submit forms (*search-only*). |
| 5 | **winget manifest** | S–M | No popularity or signing bar in the [validation docs](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/doc/Validation.md). Inno Setup installers are supported. Risks: the silent install must not prompt, and the unsigned installer could trip antivirus or unwanted-software checks. |
| 6 | **Flow Launcher plugin** (Windows' Raycast) | S | Python over JSON-RPC, the same language as Uoink. Gives inline search results, open-at-timestamp and capture. Listed by PR to `Flow.Launcher.PluginsManifest`; about 272 plugins. |
| 7 | **PowerToys Command Palette extension** | M | Biggest Windows launcher audience. Search page with an excerpt detail pane, a capture form and recent items. C#/.NET. Distribution via WinGet (an Inno Setup EXE is the documented path) plus a Gallery PR (94 entries). |
| 8 | **Obsidian community plugin** | M | Search and "insert timestamped quote" inside the editor, on **Mac and Windows** (the mirror is Windows-only). `requestUrl()` can reach `127.0.0.1:5179`. Automated review; the README must disclose network use ([policies](https://raw.githubusercontent.com/obsidianmd/obsidian-developer-docs/main/en/Community%20directory/Developer%20policies.md)). Decide how the plugin gets the token first. |
| 9 | **"Send to Zotero"** from Uoink | S–M | Zotero 10's local API (`localhost:23119`) creates a citable item with a child note of timestamped quotes after the user clicks Allow ([source](https://raw.githubusercontent.com/zotero/zotero/main/chrome/content/zotero/xpcom/server/server_localAPI.js)). No store, best researcher fit. The Zotero 10.0 date is *search-only*. |
| 10 | **Apple Shortcuts pack** | S | `.shortcut` files that call the CLI: the Share sheet, Services menu, Finder Quick Actions and Spotlight on Mac. No native code. |

## Next tier

| Target | Effort | Notes |
|---|---|---|
| Alfred Script Filter workflow | S | Inline hits, ⌘ to cite, ⌥ for timestamp. Replaces today's Run Script recipe. Users need the paid Powerpack. |
| Stream Deck plugin | M | Keys for "uoink clipboard URL" and "open latest", plus a status key. Node/TS SDK. Marketplace review is about 4–10 working days (*search-only*). Fits creators. |
| Wox plugin | S | One Node or Python plugin covers Windows and Mac. Smaller audience. |
| Bookmarklet + `/capture-intent` page | S | Works in any browser. The helper captures server-side, so the token never reaches the page. Needs a CSRF design. Chrome 142+ prompts before public pages reach localhost (*search-only*). |
| Readwise highlight push | S–M | Quotes become highlights using `time_offset`, and Readwise syncs them to other apps. Users need a paid Readwise account. API details *search-only*. |
| Cursor Marketplace plugin | S–M | Reuses the #1 work once the launch command is cross-platform. |
| Firefox (AMO) build | M | Needs `background.scripts` and no `offscreen`; a separate test matrix. |
| PopClip extension (Mac) | S | Select a URL and click "Uoink it". The user pastes the token into an option. Paid app. |
| Mobile inbox | M | An iOS Shortcut appends URLs to `iCloud Drive/Uoink/inbox.txt`, and the helper polls it. Covers articles and threads, which the YouTube playlist bridge doesn't. |
| Homebrew tap (own) | S | The Mac build is notarized, so a cask installs cleanly. The official cask repo needs 225 stars and a repo at least 30 days old ([policy](https://raw.githubusercontent.com/Homebrew/brew/main/docs/Acceptable-Casks.md)). |
| Logi Actions SDK | M–L | MX Creative Console and the Actions Ring. C# examples. |
| Product Hunt launch | M | Earns the stars that Cline, Homebrew and Scoop look for. Best after signing and the Mac release. |

## One project, several unlocks

A signed **sparse package identity** next to the Inno install would unlock the
Windows Share target, App Actions on Windows, and contained ODR registration
together. Cost it once as one project (L), not three times.

Two smaller enablers help every launcher and hardware integration:
- A helper endpoint that asks the browser extension for the active tab. Windows
  has no OS API for the current tab.
- A registered `uoink://` URL scheme to open an item at a timestamp.

## Skip for now

| Target | Reason |
|---|---|
| ChatGPT Apps / app directory | Needs a public HTTPS server. |
| Mac App Store | Guideline 5.2.3 forbids downloading YouTube media, and the sandbox rules out the CLI on PATH ([guidelines](https://developer.apple.com/app-store/review/guidelines/)). |
| Notion plugin | Notion can't reach localhost. A one-way "Send to Notion" push is possible later. |
| Descript, Heptabase, Capacities | No usable local import, or the API is closed or retiring. |
| Docker MCP Catalog | A container can't see the Windows library without volume mounts. |
| Power Automate Desktop, Keypirinha, ueli, Listary | Enterprise-only, unmaintained, or no plugin API. |
| Premiere Pro panel | Adobe [disallows `http://` on macOS](https://raw.githubusercontent.com/AdobeDocs/uxp-premiere-pro/main/src/pages/resources/recipes/network/index.md). Revisit for Windows-only. |
| Microsoft Store (EXE) | Needs a Microsoft-trusted signing certificate. Revisit with MSIX. |

## Housekeeping found along the way

- `docs/mcpb-bundle.md` says the repo doesn't ship `server.json`. It does, and
  Uoink 3.11.2 is live in the official MCP Registry.
- `server.json` and `.mcpb/manifest.json` list Windows only, so the
  notarized Mac build isn't represented.
- `docs/release/BRIEF-3.8.1-DIRECTORY-READY.md` targets the deprecated
  `.mcpb` directory route.
- The GitHub repo shows 0 stars. Cline, Homebrew and Scoop use popularity as a
  gate.

## Not verified

These came from search snippets only:
- Smithery, PulseMCP, mcp.so, LobeHub, Chocolatey, Product Hunt and Microsoft
  Store submission details.
- Whether the OpenAI plugin directory accepts local servers.
- Whether VS Code installs `mcpb` registry packages.
- The Readwise `time_offset` field.
- Alfred Gallery rules.
- Stream Deck review times.
- Whether Shortcuts can reach `http://127.0.0.1`.

Before you build the Obsidian or bookmarklet token handoff, read `server.py`'s
`/token` setup route.
