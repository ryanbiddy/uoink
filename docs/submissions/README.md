# Submission kit

A row is ready unless it says **Blocked** or **Needs**, which name what has to
happen first. Each step needs your accounts, so none of it has been submitted.
Times are estimates for the hands-on part.

| # | Where | Time | Status |
|---|---|---|---|
| 1 | [Cline MCP Marketplace](#1-cline-mcp-marketplace) | 5 min | Ready |
| 2 | [GitHub MCP Registry](#2-github-mcp-registry) | 5 min | Ready |
| 3 | [mcp.so and PulseMCP](#3-mcpso-and-pulsemcp) | 10 min | Ready |
| 4 | [Glama score, then awesome-mcp-servers](#4-glama-then-awesome-mcp-servers) | 15 min | **Blocked** on Ryan running the Glama build |
| 5 | [Raycast Store](#5-raycast-store) | 30 min | **Needs** Ryan's Raycast handle (author 404), then a test run on a Mac |
| 6 | [Homebrew tap](#6-homebrew-tap) | 10 min | Ready |
| 7 | [winget](#7-winget) | 20 min | Ready |
| 8 | [Flow Launcher store](#8-flow-launcher-store) | 20 min | Ready after a test run on Windows |
| 9 | [Edge Add-ons](#9-edge-add-ons) | 30 min | Ready; needs a helper release for the new ID |
| 10 | [Alfred Gallery](#10-alfred-gallery) | later | Use the workflow for a while first |
| 10b | [Obsidian community directory](#10b-obsidian-community-directory) | 20 min | Ready after a test run in a vault |
| 11 | [Claude directory](#11-claude-directory-and-goose) | — | **Blocked** on one decision |
| 12 | [Goose extensions directory](#11-claude-directory-and-goose) | — | **Blocked** on the same decision |

---

## 1. Cline MCP Marketplace

Open a [new submission issue](https://github.com/cline/mcp-marketplace/issues/new?template=mcp-server-submission.yml)
and attach [`logo-400.png`](logo-400.png). Before you submit, give Cline the repo's
`llms-install.md` and watch it set Uoink up once.

> **GitHub Repo URL:** https://github.com/ryanbiddy/uoink
>
> **Reason for addition:** Uoink saves the YouTube videos, podcasts, articles,
> X posts and Reddit threads you study as Markdown on your own machine, with
> timestamped transcripts, screenshots and comments. Its local MCP server gives
> Cline 91 tools to search that library and cite the exact timestamp, capture
> new links, and save notes, so answers come from sources the user actually
> saved instead of guesses. It's free, MIT licensed, and local-first: no account,
> no cloud, and library reads need no API key. Windows 10/11, plus a macOS 15+
> preview for Apple Silicon. `llms-install.md` covers setup.

## 2. GitHub MCP Registry

Uoink is already in the official MCP Registry (`io.github.ryanbiddy/uoink`).
Ask for onboarding in [discussion #1257](https://github.com/github/github-mcp-server/discussions/1257):

> Hi! Could `io.github.ryanbiddy/uoink` be onboarded to the GitHub MCP Registry?
> It's published in the official MCP Registry (3.11.2 is latest). Uoink is a
> free, MIT, local-first research library: it saves YouTube videos, podcasts and
> articles as Markdown with timestamped transcripts, and its stdio MCP server lets
> agents search them and cite the exact moment. Repo:
> https://github.com/ryanbiddy/uoink. Thanks!

## 3. mcp.so and PulseMCP

Both use web forms. Paste the same values:

- **Name:** Uoink
- **URL:** https://github.com/ryanbiddy/uoink
- **Website:** https://uoink.app
- **Short description:** Save the YouTube videos, podcasts and articles you
  study. Your AI searches them and cites the timestamp.
- **Description:** Local-first MCP server with 91 tools over a Markdown library
  on your own disk: search transcripts and articles with timestamped citations,
  capture YouTube, X, Reddit, podcast and web links, save notes, and write from
  your own sources. Free, MIT, no account. Windows, plus a macOS preview
  (Apple Silicon).
- **Transport:** stdio (also HTTP at `127.0.0.1:5179/mcp/v1` with a local token)
- **Tags:** youtube, transcripts, podcasts, research, knowledge-base, local-first

PulseMCP also reads the official registry, so Uoink may show up there on its
own. Check first.

## 4. Glama, then awesome-mcp-servers

[PR #16963](https://github.com/punkpeye/awesome-mcp-servers/pull/16963) can merge
once Glama shows a score. Re-run the Glama build per
[`docs/GLAMA-BUILD.md`](../GLAMA-BUILD.md), wait for the score, then comment on
the PR:

> Glama now shows a score for Uoink: https://glama.ai/mcp/servers/@ryanbiddy/uoink. Ready for another look. Thanks!

Check that link against the real Glama page before posting.

## 5. Raycast Store

On your Mac, with Uoink installed:

```sh
cd integrations/raycast
npm install
npm run dev        # try every command, plus @uoink in AI Chat
npm run lint       # also checks your author handle against raycast.com
```

1. `ryanbiddy` isn't a Raycast handle yet: `npm run lint` gets a 404 for it.
   Sign in at [raycast.com](https://www.raycast.com), then set `author` in
   `package.json` to your handle.
2. Take three screenshots with Raycast's **Capture Window** command, ticking
   **Save to Metadata**: Search Library with results, an item's detail, and a
   capture toast. Use a library with no private material.
3. `npm run publish`. It opens the pull request to `raycast/extensions` for you.

## 6. Homebrew tap

```sh
gh repo create ryanbiddy/homebrew-uoink --public
git clone https://github.com/ryanbiddy/homebrew-uoink && cd homebrew-uoink
mkdir Casks && cp <uoink>/packaging/homebrew/Casks/uoink.rb Casks/
git add Casks && git commit -m "Add Uoink 3.11.2" && git push
brew install --cask ryanbiddy/uoink/uoink   # check it
```

Then add `brew install --cask ryanbiddy/uoink/uoink` to the README's Mac steps.

## 7. winget

Follow [`packaging/README.md`](../../packaging/README.md#winget-windows). The
manifests are in `packaging/winget/manifests/r/ReplayRyan/Uoink/3.11.2/`.
Pull request title: `New package: ReplayRyan.Uoink version 3.11.2`.

## 8. Flow Launcher store

1. Test it: copy `integrations/flow-launcher` into
   `%APPDATA%\FlowLauncher\Plugins\Uoink`, restart Flow, type `uk`.
2. Create `ryanbiddy/Flow.Launcher.Plugin.Uoink` and copy that folder's
   contents to its root, including `.github/`. Pushing to `main` publishes
   `v1.0.0` with `Flow.Launcher.Plugin.Uoink.zip`.
3. Fork [Flow.Launcher.PluginsManifest](https://github.com/Flow-Launcher/Flow.Launcher.PluginsManifest)
   and add `plugins/Uoink-ecf47e06-d970-405f-9f97-462583fdb44c.json`:

```json
{
  "ID": "ecf47e06-d970-405f-9f97-462583fdb44c",
  "Name": "Uoink",
  "Description": "Search your local Uoink library of saved videos, podcasts and articles, open the exact moment, copy citations and uoink new links.",
  "Author": "ryanbiddy",
  "Version": "1.0.0",
  "Language": "python",
  "Website": "https://uoink.app",
  "UrlDownload": "https://github.com/ryanbiddy/Flow.Launcher.Plugin.Uoink/releases/download/v1.0.0/Flow.Launcher.Plugin.Uoink.zip",
  "UrlSourceCode": "https://github.com/ryanbiddy/Flow.Launcher.Plugin.Uoink/tree/main",
  "IcoPath": "https://cdn.jsdelivr.net/gh/ryanbiddy/Flow.Launcher.Plugin.Uoink@main/Images/icon.png"
}
```

## 9. Edge Add-ons

Follow the Edge section of [`docs/store/SUBMIT-NOW.md`](../store/SUBMIT-NOW.md#edge-add-ons).
The catch: Edge assigns its own extension ID, and the helper only talks to IDs
it trusts. After Edge assigns the ID, add it to the helper's `extension_ids`
and ship that in a Uoink release before the Edge listing goes public.

## 10. Alfred Gallery

The Gallery is curated. Use the workflow yourself for a few weeks, then follow
[alfredapp/gallery-edits](https://github.com/alfredapp/gallery-edits). Until then,
attach `Uoink.alfredworkflow` (from `integrations/alfred/build_workflow.py`) to a
GitHub release.

## 10b. Obsidian community directory

1. Test it: `cd integrations/obsidian && npm install && npm run build`, then copy
   `main.js` and `manifest.json` into `<vault>/.obsidian/plugins/uoink/` and
   enable **Uoink** under Community plugins.
2. Create `ryanbiddy/obsidian-uoink` and copy that folder's contents to its root.
3. Push a tag `1.0.0`. The release workflow drafts a release with `main.js` and
   `manifest.json`; publish it.
4. Submit the repository at [community.obsidian.md](https://community.obsidian.md)
   (sign in with GitHub). Review is automated.

## 11. Claude directory and Goose

Both list one launch command that has to work on every user's machine. Today's
agent-kit plugin runs `${LOCALAPPDATA}\Uoink\python\python.exe`, which the
Claude directory blocks (its README and LICENSE blockers are fixed). Goose's
`servers.json` takes one `command` string as well.

| Option | What changes | Tradeoff |
|---|---|---|
| **A. Skills-only directory plugin** (recommended first) | Submit a plugin folder with the Uoink skill, README and LICENSE but no `.mcp.json`. The skill uses the `uoink` CLI, and users add the MCP server with `uoink connect claude-code`. | Passes validation today. Users do one extra setup step for MCP. Doesn't help Goose. |
| **B. A `uoink mcp` subcommand** | The CLI starts the stdio server, so every client can use `command: "uoink", args: ["mcp"]`. | One launch line for the directory, Goose, Smithery and others. On Windows, clients that don't resolve `.cmd` files need `cmd /c uoink mcp` or a small `uoink.exe`. A PATH command is held for a reviewer, not blocked. |

A now, B in the next release, is the fastest route.
