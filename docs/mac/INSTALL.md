# Install the macOS test build

These are draft steps for the private Apple Silicon build. Use the DMG from
the matching successful `mac-build` job, named `Uoink-<VERSION>-macos-arm64.dmg`.
The artifact also contains `dmg.json` with its SHA-256 and size. This build has
an ad-hoc signature. Developer ID signing, notarization and interactive Mac
acceptance are still pending. Apple Silicon and macOS 15 or later are required.

## Install and open

1. Download and open the DMG. Drag Uoink to the Applications shortcut.
2. Eject the mounted disk, then open Uoink from Applications once.
3. If macOS blocks an unidentified developer, dismiss the alert. Open Apple
   menu > System Settings > Privacy & Security. Find the blocked Uoink entry
   in Security and choose **Open Anyway**. Authenticate if asked, then confirm
   **Open**. Exact wording needs confirmation on the supported Mac releases.
4. Do not use that flow for a damaged-signature or malware alert. A managed
   Mac may prohibit overrides. A later update can require another override.

The installed app starts a menu-bar process and shows the welcome window once
per version. Open dashboard, Open folder, Settings, Recent items and Quit Uoink
are in its menu. The splash and dashboard use WKWebView, with a default-browser
fallback if Cocoa cannot start. Follow [ACCEPTANCE.md](ACCEPTANCE.md) to check
these paths on a real Mac.

## Put the CLI on your PATH

The app does not change your shell or write to `/usr/local`. For a user-local
command, run:

```sh
mkdir -p "$HOME/.local/bin"
ln -s /Applications/Uoink.app/Contents/Helpers/uoink "$HOME/.local/bin/uoink"
export PATH="$HOME/.local/bin:$PATH"
uoink status
```

Add that PATH setting to your shell profile if you want it in new terminals.
If `/usr/local/bin` is already writable by you and on PATH, this also works:

```sh
ln -s /Applications/Uoink.app/Contents/Helpers/uoink /usr/local/bin/uoink
```

For an app installed elsewhere, use its actual path in the link. The shim
follows that link back to the bundle. `uoink status` reports the helper state;
it does not start the helper.

## Load the Chrome extension

Start Uoink once so it creates the user-owned extension copy at:

```text
~/Library/Application Support/Uoink/extension
```

In Chrome, open `chrome://extensions`, turn on Developer mode, choose **Load
unpacked**, and select that folder. Finder's Go to Folder command can open
the path. Use the copy under Application Support so updates and edited prompts
stay outside the app's signature. Chrome onboarding still needs a real-Mac test.

## Connect your AI

Run one of these commands to print a recipe. They do not edit client files:

```sh
uoink connect claude-desktop
uoink connect cursor
uoink connect codex
uoink connect claude-code
uoink connect vscode --deeplink
```

The output uses your current app location, with
`Contents/Resources/Python/bin/python3`, `-B -s`, and
`Contents/Resources/uoink_mcp.py`. It works with spaces in the app path.
Merge the printed entry into the client's existing configuration and keep
unrelated entries. Back up the file first. Restart the client after editing.

| Client | Configuration |
|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| Codex | `~/.codex/config.toml` |
| VS Code | `.vscode/mcp.json` in the project |

The dashboard's MCP config and Add to Cursor / VS Code links use the same
resolver. Its Claude Desktop connect action preserves other entries and writes
a backup. Client acceptance remains untested until someone tries these on a Mac.

For Claude Desktop's extension flow, open `uoink-<VERSION>-macos.mcpb` from the
same build. Select the installed **Uoink.app** in its Uoink app setting. The
default is `/Applications/Uoink.app`; change it if you moved the app. The
connector reports a missing install on stderr. It contains no Python runtime.
Use the Darwin connector, not the Windows `.mcpb`.

For skills and the Claude Code plugin route, see [the agent kit](../../agent-kit/README.md).
On Mac use the standalone skill and `uoink connect claude-code`; the kit's
static plugin MCP entry is still for Windows. Library mirroring is unavailable
on macOS in this build. The full and core MCP inventories remain 91 and 35.

## Login startup and Quit

Login startup is off until you enable it in Uoink settings. It writes
`~/Library/LaunchAgents/com.ryanbiddy.uoink.plist`, then uses `launchctl bootstrap`
in `gui/<uid>`. Logs go to `~/Library/Logs/Uoink`. Status uses `launchctl print`;
disabling uses `bootout` and removes the plist. Disabling can stop the helper
for the current session. Open Uoink again to run it manually.

Quit from the menu bar or dashboard stops the helper and its native UI
processes without restarting them. The LaunchAgent
uses `KeepAlive: false`. If login startup is still enabled, Uoink starts again
at the next login. After moving or replacing the app, disable and re-enable
login startup so its absolute paths match. Quit Uoink and close MCP clients
before replacing the app; automated upgrades are not part of this pass.

## Remove the app

Close AI clients that use Uoink, then preview removal:

```sh
bash /Applications/Uoink.app/Contents/Resources/scripts/mac/uninstall.sh /Applications/Uoink.app
```

To carry out that plan, add `--remove`:

```sh
bash /Applications/Uoink.app/Contents/Resources/scripts/mac/uninstall.sh /Applications/Uoink.app --remove
```

The helper unloads and removes the LaunchAgent, stops the recorded helper only
when its app path, executable and process creation identity match, and removes
the app. Unknown ownership or failed termination leaves the app in place.
It never stops processes by name. It keeps captures, settings, Keychain entries,
the extension copy, logs and client configurations. Remove your CLI symlink and
Uoink client entries separately if you no longer need them. No data deletion
option is included. A system-owned app may need removal through Finder after
the agent and helper have stopped.
