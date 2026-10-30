# Uoink for Flow Launcher

Search the videos, podcasts, articles and notes you saved with
[Uoink](https://uoink.app) from [Flow Launcher](https://www.flowlauncher.com).
Open the exact moment, copy a citation, or paste a link to uoink it.

## Use it

| Type | What happens |
|---|---|
| `uk` | Your most recent captures; Enter opens the folder. The last background capture's status is shown first. |
| `uk working memory` | Search your library. Enter opens the source at the matched timestamp, Ctrl+C copies a Markdown citation, and Shift+Enter shows more actions (copy citation, copy link, open source, copy item ID). |
| `uk https://youtu.be/…` | Uoink that link: a YouTube video or playlist, X post, Reddit thread, podcast feed or web page. The capture runs in the background so Flow can close; Uoink shows a notification when a video is saved. |

## Setup

1. Install Uoink 3.10 or later for Windows from [uoink.app/install](https://uoink.app/install).
2. Install this plugin from Flow's plugin store, or with `pm install <zip URL>`.
3. For a custom install location, open the plugin's settings and set **Uoink folder**
   to the folder that contains `uoink_cli.py`.

The Uoink window doesn't need to be open. Library search reads the local index directly.

## How it works

The plugin runs `uoink_cli.py` with Uoink's bundled Python and an argument list,
never through a shell. Everything stays on your PC. Searching makes no network
calls; a capture fetches only the link you give it. Web pages follow Uoink's site
allowlist, so allow a new site in the Uoink dashboard first.

The plugin uses only the Python standard library and has no `lib` folder.

## Publishing

Flow's store updater reads the latest GitHub release of the plugin's source
repository, so the plugin needs a repository of its own (the Uoink app's releases
would confuse it). Copy this folder to the root of a new repository such as
`ryanbiddy/Flow.Launcher.Plugin.Uoink`; `.github/workflows/publish-release.yml`
then publishes `Flow.Launcher.Plugin.Uoink.zip` whenever `plugin.json`'s version
changes. Submit it with a pull request to
[Flow.Launcher.PluginsManifest](https://github.com/Flow-Launcher/Flow.Launcher.PluginsManifest)
as described there.
