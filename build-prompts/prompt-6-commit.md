# Prompt 6 — Stop. Test. Commit. Prepare folder rename.

We're done with this weekend's build. Don't add new features. Run a final audit, commit, and prepare for the parent folder to be renamed.

## TASK 1 — END-TO-END SMOKE TEST

Walk the user through testing the full flow one more time:

1. Server is running with the new startup message
2. Extension is loaded with the new "Yoink" button label
3. Yoink a YouTube video. Verify `yoink.md` has all v1 spec sections (metadata, thumbnail, description, tags, transcript, screenshots, comments, channel context)
4. Verify clipboard works in both Claude and ChatGPT
5. Verify the prompt library works (clicking a prompt copies it to clipboard)
6. Verify topic classification puts the video in the right folder
7. Verify error messages are on-voice when the server is offline

If anything fails the smoke test, fix it before continuing. Don't proceed to commit with broken code.

## TASK 2 — DEPENDENCY DOCUMENTATION

Create `REQUIREMENTS.md` with the manual setup steps a user needs today (before the installer ships next weekend):

```markdown
# Yoink — Manual Setup

The one-click installer is shipping in v1 launch. Until then, here's the manual setup.

## Prerequisites

- Windows 10 or 11
- Python 3.11 or higher
- Git (for cloning this repo)
- A Chromium-based browser (Chrome, Edge, Brave, Comet, Arc)

## Setup steps

1. Clone the repo:
   ```
   git clone https://github.com/REPLACE_WITH_YOUR_USERNAME/yoink.git
   cd yoink
   ```

2. Install yt-dlp:
   ```
   pip install yt-dlp
   ```

3. Install ffmpeg:
   ```
   winget install Gyan.FFmpeg
   ```
   Restart your terminal so the new PATH takes effect.

4. Verify both tools are available:
   ```
   yt-dlp --version
   ffmpeg -version
   ```

5. Start the Yoink server:
   ```
   double-click start_server.bat
   ```
   Or from PowerShell:
   ```
   pythonw server.py
   ```

6. Verify the server is running:
   ```
   Invoke-RestMethod http://127.0.0.1:5179/ping
   ```
   Should return `ok : True`.

7. Load the extension in your browser:
   - Open `chrome://extensions/` (or `comet://extensions/`)
   - Toggle Developer mode on
   - Click "Load unpacked"
   - Select the `extension/` folder

8. Pin the Yoink extension to your toolbar.

9. Open any YouTube video. Click the Yoink button under the video.

## Known caveats

- The server must be running for the extension to work
- ffmpeg PATH only refreshes for shells started after the install
- If you start the server from an elevated shell, it may conflict with the regular shell instance — use the regular shell unless you have a specific reason

## Troubleshooting

If the Yoink button doesn't appear, refresh the YouTube page once. YouTube is a SPA and the extension's MutationObserver sometimes loses the race on first load.

If clicking Yoink does nothing, open DevTools (F12), Console tab, and look for errors prefixed with `[Yoink]`.
```

## TASK 3 — UPDATE README

Update `README.md`'s "Install" section to point at `REQUIREMENTS.md` for now, with a clear note: "One-click installer ships in v1 launch (target: 2 weeks). Manual setup until then."

## TASK 4 — FOLDER RENAME PREPARATION

The parent folder is currently named `yt-extractor`. We want to rename it to `Yoink` after this build is complete. We can't do that from inside the folder while the Claude Code CLI is using it, so we'll prepare a script the user runs after Claude Code exits.

Create `RENAME_FOLDER.md` in the project root with these instructions:

```markdown
# Rename the parent folder from yt-extractor to Yoink

After Claude Code exits and the orchestrator script finishes, the parent folder will be auto-renamed by the orchestrator script.

If for any reason that fails, you can rename manually:

1. Close Claude Code, VS Code, any open terminals in this folder, and any text editor with files from this folder open.

2. In a fresh PowerShell window, run:

   ```
   cd C:\Users\hello\OneDrive\Desktop
   Rename-Item -Path "yt-extractor" -NewName "Yoink"
   ```

3. Update any shortcuts, batch files, or environment variables that reference the old path.

4. Restart the Yoink server from the new location:
   ```
   cd C:\Users\hello\OneDrive\Desktop\Yoink
   .\start_server.bat
   ```

5. The extension doesn't need to be reloaded — it talks to the server via HTTP, not the file system.
```

## TASK 5 — COMMIT AND PUSH

```bash
git add .
git commit -m "v1 build complete: corpus format, prompt library, polish, store assets"
git push
```

If the push fails, report the error. Don't proceed with the celebration.

## TASK 6 — PROGRESS SUMMARY

Write `docs/progress.md`:

```markdown
# Yoink Progress Log

## Weekend 1 — v1 build (this weekend)

### Done
- Rebrand from yt-extractor to Yoink
- Full v1 corpus format (metadata, thumbnail, description, tags, transcript, screenshots, comments, channel context)
- Two destination buttons (Claude + ChatGPT)
- Prompt library with 8 starter prompts
- Polish pass on error messages and notifications
- Chrome Web Store assets prepped (icons, listing draft, screenshot list)
- README, BACKLOG, STYLE, REQUIREMENTS docs

### Ships next weekend
- Inno Setup one-click installer for Windows
- 60-90 second demo video
- Chrome Web Store submission
- Final landing page copy at yoink.video

### Ships at launch (2-3 weekends out)
- Public Show HN post
- Launch tweet thread
- Product Hunt submission (optional)
- Chrome Web Store live (gated on review approval)

### Known issues / rough edges to address during the week
- [Claude Code, fill in any rough edges you noticed during the build]
```

## TASK 7 — FINAL OUTPUT

Print this exactly:

```
=== PROMPT 6 COMPLETE ===
=== ALL PROMPTS COMPLETE ===

v1 weekend build complete. Stop here.

Next steps for the user:
1. Exit Claude Code (Ctrl+C or type 'exit')
2. Close any terminals/editors with files in the yt-extractor folder open
3. The orchestrator script will rename the folder to Yoink
4. See you next weekend for installer + Web Store + demo video.
```
