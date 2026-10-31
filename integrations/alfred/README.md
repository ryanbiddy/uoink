# Uoink for Alfred

An [Alfred](https://www.alfredapp.com) workflow for the videos, podcasts,
articles and notes you saved with [Uoink](https://uoink.app). Search the
library, open the exact moment, copy a citation, and uoink new links.

Workflows need Alfred's Powerpack.

## Use it

| Input | Result |
|---|---|
| `uk` | Recent captures. ↩ reveals one in Finder. |
| `uk working memory` | Search. ↩ opens the source at the matched timestamp, ⌘↩ (or ⌘C) copies a Markdown citation, ⌥↩ copies the item ID, ⌃↩ opens the source page, ⌘Y previews it. |
| `uk https://youtu.be/…` | Uoink that link. A notification reports when it's saved, and a video's Markdown is copied to the clipboard. |
| **Uoink** Universal Action | Uoink a URL selected anywhere. |

## Install

1. Install [Uoink](https://uoink.app/install) for Mac.
2. Build the package with `python3 build_workflow.py`, then double-click
   `dist/Uoink.alfredworkflow`. The keyword, Uoink.app location and the
   clipboard option are in the workflow's configuration.

## How it works

Alfred passes your query to a two-line zsh wrapper as an argument. The wrapper
runs `src/uoink_alfred.py` with the Python inside Uoink.app (`-I` isolated
mode), and that script calls `Uoink.app/Contents/Helpers/uoink` with an
argument list. Query text never becomes part of a shell command. Searching makes no
network calls; a capture fetches only the link you give it, and web pages
follow Uoink's site allowlist.

## Develop

`src/info.plist` is generated. Edit `build_workflow.py`, then run
`python3 build_workflow.py` (or `--check` to confirm it's current). To try
changes live, symlink `src` into Alfred's workflows folder.

The [Alfred Gallery](https://alfred.app) is curated. Submit through its
[gallery-edits](https://github.com/alfredapp/gallery-edits) process once the
workflow has been used for a while.
