# Integrations

Native integrations that call the installed `uoink` CLI. Each one passes text
as arguments, never through a shell, and needs no token. On Windows they start
Uoink's bundled Python with `uoink_cli.py` instead of `uoink.cmd`. All four copy
the same citation formats: a quote with a timestamped link when Uoink verified
the passage, otherwise just the link.

| Folder | App | Platforms | What you get | Status |
|---|---|---|---|---|
| [raycast](raycast/README.md) | Raycast | macOS, Windows | Search Library (Enter copies a citation), Uoink This URL, Recent Saves, Save Note; optional Raycast AI tools | Needs the owner's Raycast handle as `author` before the Raycast Store |
| [flow-launcher](flow-launcher/README.md) | Flow Launcher | Windows | `uk` search, cite, recent, uoink pasted links in the background | Needs its own repository for Flow's store |
| [alfred](alfred/README.md) | Alfred (Powerpack) | macOS | `uk` search with modifier actions, recent, Universal Action capture | Build the `.alfredworkflow` with `build_workflow.py` |
| [obsidian](obsidian/README.md) | Obsidian | Windows, macOS desktop | Insert timestamped citations into notes, open moments, save links | Needs its own repository for the community directory |

Package manager manifests are in [packaging](../packaging/README.md), and
step-by-step submissions for every store are in
[docs/submissions](../docs/submissions/README.md).
