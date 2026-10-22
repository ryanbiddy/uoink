# Check the installed Mac app

Ryan, run this on an Apple Silicon Mac with macOS 15 or later. Use the DMG
and version from the same successful hosted build. Record the macOS version,
app version and result beside each step. A fresh macOS test account makes the
first-run check repeatable without changing your existing Uoink data.

## Download and open the signed app

In Safari, download `uoink-macos-arm64-signed` from the successful workflow
run being tested. Unzip it into `~/Downloads/uoink-mac`. Open its DMG, drag
Uoink to Applications, eject the disk, then double-click Uoink in Applications.
Confirm that it opens with no security prompt beyond the standard
"downloaded from the internet" confirmation. Do not bypass a security block.
Record the exact alert if this fails. Then run the strict receipt below.

## Run the strict receipt on your Mac

The signed artifact holds the DMG and `dmg.json`, the hash the hosted job
recorded after stapling. Make a fresh clone of
`https://github.com/ryanbiddy/uoink.git` and check out that run's exact commit.
From the clone's root, run this in Terminal:

```sh
version="$(cat VERSION)"
dmg="$HOME/Downloads/uoink-mac/Uoink-$version-macos-arm64.dmg"
expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$HOME/Downloads/uoink-mac/dmg.json")"
python3 -B scripts/mac/receipt.py --dmg "$dmg" --expected-sha256 "$expected" \
  --require-notarized --expected-team-id WTGFF582VY \
  --output "$HOME/Desktop/uoink-receipt"
```

The expected hash comes from the build, not from the downloaded file, so a
changed or corrupted download fails the receipt.
Strict mode also requires team `WTGFF582VY`, hardened runtime, secure timestamps,
valid app and DMG tickets, and spctl acceptance with app source
`Notarized Developer ID`. All existing runtime, cleanup and isolation checks
must still pass. Omitting the strict flag retains the ad-hoc receipt behavior.

Use Python 3.10 or later. System `python3` runs only the collector. You can
replace `python3` with the full quoted path to an app's
`Contents/Resources/Python/bin/python3`. All tested processes must use the
Python inside the disposable copy made from this DMG. Running the source
helper cannot earn `installed-pass`.

The receipt mounts read-only, installs into a temporary path with spaces,
uses a disposable home, profile, output folder and port, then removes that
app with `uninstall.sh --remove` and detaches the DMG. That flag removes the
app only. The disposable profile is kept at the path recorded in the receipt.
Real user data and matching LaunchAgents are listed by existence and mtime
only; port 5179 is observed without connecting. Any change fails the receipt.
An existing login agent belonging to another install makes uninstall refuse
to proceed. Use a fresh test account in that case.

Send back **`~/Desktop/uoink-receipt/receipt.json` only**, even if it says
`fail`. Keep any earlier receipt before rerunning; the collector refuses to
overwrite it. A passing receipt does not replace the visible UI checks below.

## Check the visible app

1. Complete the Safari download and double-click check above. Expected: Uoink
   starts from Applications, shows one menu-bar U and opens the welcome window.
   Any security block beyond the normal internet-download confirmation fails
   this check. No manual security override is part of acceptance.

2. Switch System Settings > Appearance between Light and Dark. Expected: the
   monochrome U remains visible in both modes, with clean edges on the Retina
   display. Open its menu. Expected: a status line, Open dashboard, Open folder,
   Settings, Recent items and Quit Uoink. Status appears as text, not a colored dot.

3. Read the status line before and during a capture. Expected: Running when
   healthy and idle, Yoinking while queue work is active, or Degraded health
   when the dashboard's diagnosis reports a problem. Allow five seconds for
   a refresh. Missing service setup can account for degraded health.

4. In the welcome window, copy the extension folder and paste into Notes.
   Expected: the complete path points to your user-owned
   `Library/Application Support/Uoink/extension`, including any spaces. Follow
   the Chrome instructions and mark the extension loaded. Expected: the window
   closes. Its Open dashboard and Settings buttons should open a separate
   window that stays open after the welcome window closes.

5. Choose Open dashboard from the menu bar. Expected: a Uoink window loads
   the dashboard, with working scrolling, links and controls. Close it.
   Expected: the menu bar and helper keep running. Open it again and choose
   Settings from the menu. Expected: the dashboard opens on Settings.

6. Choose Open folder. Expected: Finder opens the active output folder. Save
   a test source, then open Recent items. Expected: the saved title appears
   within five seconds; choosing it opens its folder. Before any captures,
   the menu should say No recent items yet.

7. In Settings, use the output-folder picker to choose an ordinary writable
   folder whose name has spaces and a non-ASCII character, such as `Uoink 雪`.
   Expected: a native folder dialog appears, the chosen path is saved, and
   Settings reports whether a restart is needed. After any requested restart,
   Open folder uses that path and a new capture lands there.

8. Open the picker again and cancel. Expected: the old output folder stays
   selected and the dashboard says No folder selected. Leave the dialog open
   for two minutes once. Expected: it ends with a timeout message and leaves
   the old setting intact. The helper remains responsive.

9. Try a folder in Desktop, Documents or Downloads and deny the macOS access
   prompt. If permission was already granted, use System Settings > Privacy
   & Security > Files and Folders to turn it off, then retry after reopening
   Uoink. Expected: no crash or indefinite wait; the dashboard explains that
   it cannot open or write that folder and says the output folder has not
   changed. Allow access and retry. Expected: selection and a test capture
   succeed. Record which app or process name macOS shows in the permission
   prompt; that attribution is part of this check.

10. Copy text from the dashboard and paste into Notes. Check a source's
    Markdown, an MCP config, a writing prompt and text containing accents,
    emoji and line breaks. Copy a capture with screenshots through the
    extension too. Expected: complete text with correct characters and line
    breaks. The multimodal corpus is Markdown with `data:image/...` links;
    Notes receives those links as text. It is not a rich image clipboard.

11. Open Uoink from Applications several times while it is running.
    Expected: one menu-bar icon and one helper remain. Existing captures and
    windows continue working. The welcome window does not repeat for this
    installed version after it has loaded once.

12. Choose Quit Uoink. Expected: the icon, dashboard and welcome windows
    close, and the helper stops. Wait 15 seconds. Expected: nothing restarts.
    Relaunch from Applications. Expected: one icon returns, the dashboard
    opens from its menu, settings remain saved and the welcome window stays
    closed. Repeat Quit from the dashboard's Settings > App > Stop Uoink action.

13. With login startup off in Settings, log out and back in. Expected: Uoink
    does not start. Open it, enable login startup, then log out and back in.
    Expected: exactly one helper and menu-bar icon start, without another
    welcome window. Quit. Expected: it stays stopped for the rest of this
    login session.

14. Relaunch, turn login startup off and reopen Uoink if disabling stopped
    it. Log out and back in. Expected: no helper or menu-bar icon starts.
    The login setting stays off. This check exercises launchctl, not just
    the displayed switch.

15. When a later test version is available, Quit and replace the app using
    its DMG. Expected: the new version shows its welcome window once; a
    second launch does not. Settings and captures remain. Mark this step
    pending until a second version has actually been tested.

Hosted CI checks processes and imports. It cannot certify menu visibility,
WebKit rendering, clipboard results in Notes, permission prompts or login
sessions. Record those results here before treating the UI as accepted.
