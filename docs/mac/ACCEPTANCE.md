# Check the installed Mac app

Ryan, run this on an Apple Silicon Mac with macOS 15 or later. Use the DMG
and version from the same successful hosted build. Record the macOS version,
app version and result beside each step. A fresh macOS test account makes the
first-run check repeatable without changing your existing Uoink data.

1. Open the DMG. Read the minimum version, drag Uoink to Applications, eject
   the disk and open the installed app. Expected: it starts from Applications,
   shows one menu-bar U and opens the welcome window. This private build is
   ad-hoc signed. Follow [INSTALL.md](INSTALL.md) if macOS blocks an unidentified
   developer. A damaged-signature alert is a failed check.

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
