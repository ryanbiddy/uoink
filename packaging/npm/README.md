# uoink

Uoink saves YouTube videos, podcasts, X posts, Reddit threads and web pages, with full transcripts, to a library on your computer. Your AI agent (Claude Code, Codex, Claude Desktop, Cursor) then searches it and cites the exact timestamp.

This package is the quick way to install it.

```sh
npx uoink
```

## What it does

1. Tells you what will happen and asks `y/N`. Nothing downloads before you say yes.
2. Downloads the official installer from the [GitHub release](https://github.com/ryanbiddy/uoink/releases/latest) (about 500 MB) and checks its SHA-256 against the release's `SHA256SUMS.txt`. If it does not match, it deletes the file and stops.
3. Installs Uoink.
   - Windows 10/11 (x64): runs the installer silently, per user, no admin needed.
   - Mac (Apple silicon, macOS 15+): copies Uoink.app to /Applications (or ~/Applications) and links the `uoink` command if it can.
   - Linux and Intel Macs: prints the right install guide and exits. Nothing is installed.
4. Shows the agents you can connect, for example `npx uoink connect claude-code`.

Already installed? `npx uoink <command>` runs the installed CLI, so `npx uoink search "eval setup"` works. `npx uoink update` installs the latest version only if it is newer.

## Options

```
npx uoink --dry-run          print the plan and URLs, download nothing
npx uoink --yes              skip the question
npx uoink --version 3.16.3   install a specific version
npx uoink install --version 3.16.3 --allow-downgrade
                             go back to an older version than you have (asks first)
npx uoink --no-connect       skip the agent hints
```

Before it downloads anything it says whether this is an update, a reinstall of the version you have, or a downgrade. After installing, it waits up to 90 seconds for Uoink to answer on this computer (`127.0.0.1:5179/health`). If Uoink does not come back, it exits with an error and says what to try next.

## Privacy and safety

- Installing this package runs nothing. There is no install script. Code runs only when you run `npx uoink`.
- It talks only to github.com (release files) and the GitHub file hosts they redirect to, over HTTPS. Redirects to any other host are refused.
- It sends no personal data and has no dependencies.
- Uoink itself is local-first: your library stays on your computer, with no account and no Uoink cloud.

Needs Node 18.17 or newer. MIT licensed. Source: [github.com/ryanbiddy/uoink](https://github.com/ryanbiddy/uoink/tree/main/packaging/npm). Site: [uoink.app](https://uoink.app).
