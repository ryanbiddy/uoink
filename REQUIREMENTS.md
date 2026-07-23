# Uoink — Manual source setup

Most Windows users should use the
[published v3.4.0 installer](https://github.com/ryanbiddy/uoink/releases/tag/v3.4.0).
Use this path when developing Uoink or testing the current source checkout.

## Prerequisites

- Windows 10 or 11
- Python 3.11 or higher
- Git (for cloning this repo)
- A Chromium-based browser (Chrome, Edge, Brave, Comet, Arc)

## Setup steps

1. Clone the repo:
   ```
   git clone https://github.com/ryanbiddy/uoink.git
   cd uoink
   ```

2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the pinned Python runtime dependencies:
   ```
   python -m pip install -r requirements.txt
   python -m pip install "yt-dlp==2026.07.04"
   ```
   The second pin matches the version bundled by `build.ps1`.

4. Install ffmpeg:
   ```
   winget install Gyan.FFmpeg
   ```
   Restart your terminal so the new PATH takes effect.

5. Reactivate the virtual environment and verify both tools are available:
   ```
   .\.venv\Scripts\Activate.ps1
   yt-dlp --version
   ffmpeg -version
   ```

6. Start the Uoink server:
   ```
   python server.py
   ```
   Keep that terminal open while testing. `start_server.bat` is the
   double-click alternative.

7. Verify the server is running from a second PowerShell window:
   ```
   Invoke-RestMethod http://127.0.0.1:5179/ping
   ```
   Should return `ok : True`.

8. Load the extension in your browser:
   - Open `chrome://extensions/` (or `comet://extensions/`)
   - Toggle Developer mode on
   - Click "Load unpacked"
   - Select the `extension/` folder

9. Pin the Uoink extension to your toolbar.

10. Open any YouTube video. Click the Uoink button under the video.

## Known caveats

- The server must be running for the extension to work
- ffmpeg PATH only refreshes for shells started after the install
- If you start the server from an elevated shell, it may conflict with the regular shell instance — use the regular shell unless you have a specific reason

## Troubleshooting

If the Uoink button doesn't appear, refresh the YouTube page once. YouTube is a SPA and the extension's MutationObserver sometimes loses the race on first load.

If clicking Uoink does nothing, open DevTools (F12), Console tab, and look for errors prefixed with `[Uoink]`.
