# Install Uoink with an AI agent

## Windows

For Cline or another agent with a local PowerShell shell on Windows 10/11.
Run these steps on the person's PC. See [README](README.md#install) for details.

1. Download the latest release's installer and `SHA256SUMS.txt` into a fresh
   temporary folder. Resolve both assets from the same release:

   ```powershell
   $release = Invoke-RestMethod 'https://api.github.com/repos/ryanbiddy/uoink/releases/latest'
   $asset = @($release.assets | Where-Object name -Match '^Uoink-Setup-[0-9.]+\.exe$')
   $sums = @($release.assets | Where-Object name -EQ 'SHA256SUMS.txt')
   if ($asset.Count -ne 1 -or $sums.Count -ne 1) { throw 'Release assets missing or ambiguous' }
   $stage = Join-Path $env:TEMP ('uoink-install-' + [guid]::NewGuid())
   New-Item -ItemType Directory -Path $stage | Out-Null
   $installer = Join-Path $stage $asset[0].name
   $checksums = Join-Path $stage 'SHA256SUMS.txt'
   Invoke-WebRequest -UseBasicParsing $asset[0].browser_download_url -OutFile $installer
   Invoke-WebRequest -UseBasicParsing $sums[0].browser_download_url -OutFile $checksums
   ```

2. Verify SHA-256 before running the installer. Stop on a missing or mismatched hash:

   ```powershell
   $pattern = '^([0-9a-fA-F]{64})\s+\*?' + [regex]::Escape($asset[0].name) + '$'
   $lines = @(Get-Content -LiteralPath $checksums | Where-Object { $_ -match $pattern })
   if ($lines.Count -ne 1) { throw 'Expected exactly one installer checksum' }
   $expected = [regex]::Match($lines[0], $pattern).Groups[1].Value
   if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ine $expected) { throw 'SHA-256 mismatch' }
   ```

3. Install silently, per user, without admin rights:

   ```powershell
   $install = Start-Process -Wait -PassThru -FilePath $installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'
   if ($install.ExitCode -ne 0) { throw "Installer exit code: $($install.ExitCode)" }
   ```

   The default install is `%LOCALAPPDATA%\Uoink`. The checked installer option
   **Add the uoink command to PATH for AI agents** adds its `cli` folder to User PATH.
   If SmartScreen appears, the person must choose **More info -> Run anyway**
   after checksum verification. The installer is unsigned.

4. Open a new terminal so it sees the updated PATH, then check the install:

   ```powershell
   uoink status
   uoink connect --list
   uoink connect cline
   ```

   In an existing shell, use `& "$env:LOCALAPPDATA\Uoink\cli\uoink.cmd" status`
   and the same absolute launcher for `connect`. Use the actual path for a custom install.

5. Run `uoink connect <client>` for the person's client. It prints config to
   stdout and the destination and notes to stderr; it does not edit client files.
   For Cline, open **MCP Servers > Configure MCP Servers** and merge the printed
   `uoink` entry under `mcpServers` in `cline_mcp_settings.json`. Preserve other entries.
   For Claude Code, run the printed command in PowerShell. For Codex, merge the
   printed tables into `~/.codex/config.toml`. Other destinations are printed
   by `connect` and listed in [Connect your agent](docs/connect-your-agent.md).
   Restart the client's MCP connection and confirm it lists Uoink's tools.

   For a client with no recipe, or one that takes a single launch command,
   3.12.1 and later also accept `"command": "uoink"` with `"args": ["mcp"]`.
   If the client cannot start `.cmd` files, use `"command": "cmd"` with
   `"args": ["/c", "uoink", "mcp"]`. Check first with `uoink mcp --help`: on
   3.12.0 and earlier it is a usage error, so use the absolute command and
   args that `uoink connect` prints instead.

6. On 3.13.0 and later a silent install starts the helper with no window; check
   with `uoink status`. On 3.12.1 and earlier it does not, so ask the person to
   start **Uoink** from the Start menu. Local CLI reads and MCP work without the
   helper either way. For browser capture, have the person open **Uoink** from
   the Start menu, use the setup splash to copy the installed extension path, open
   `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**,
   and select that folder. Then click Chrome's puzzle-piece **Extensions** icon
   and pin **Uoink**. The Chrome Web Store listing is pending.

Chrome (tested); other Chromium browsers such as Edge and Brave may work but are not tested.

## Linux

For agents with a shell on a Linux desktop, server or headless sandbox. Run
these steps where the agent will run Uoink. See the [Linux guide](docs/linux.md)
for installer options, Docker, storage paths and capture limits.

1. Install Git, Python 3.11 or newer, venv support, ffmpeg and ffprobe. On
   Debian or Ubuntu, use the commands below. Other distributions are listed
   in the Linux guide.

   ```sh
   sudo apt-get update
   sudo apt-get install git python3 python3-venv
   sudo apt-get install ffmpeg
   ```

2. Install from a checkout.

   ```sh
   git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
   ```

   The app goes in `~/.local/lib/uoink` and the command symlink in
   `~/.local/bin/uoink`. The installer stages a pinned, SHA-256-checked
   Whisper `base` model for CPU transcription. Add `--with-whisperx` only
   if podcast speaker labels are needed; it adds CPU torch and a large
   download. Without it, podcast transcripts have no diarization.

3. Add the command folder to this shell's PATH and check the install.

   ```sh
   export PATH="$HOME/.local/bin:$PATH"
   ~/.local/bin/uoink status
   uoink tools
   uoink connect --list
   ```

   `capabilities.media.available` should be `true`. Code
   `media_requires_ffmpeg` means ffmpeg or ffprobe is missing from PATH.
   After a default install, `reliability_model.cached` should be `true`
   with source `"bundled"` and bundled model `"base"`.

4. Print the recipe for the person's client. These commands only print
   instructions; they do not edit client files.

   ```sh
   uoink connect claude-code
   uoink connect codex
   uoink connect cursor
   ```

   For Claude Code, run the printed `claude mcp add` command in the shell.
   For Codex, merge the printed tables into `~/.codex/config.toml`, or
   `CODEX_HOME/config.toml` if configured. For Cursor, merge the `uoink`
   entry into `~/.cursor/mcp.json`. Preserve other settings and servers.
   Restart the client's MCP connection and confirm it lists Uoink's tools.

5. Start the helper only if HTTP access or the dashboard is needed. Stdio
   MCP and CLI tool calls work without it.

   ```sh
   UOINK_HEADLESS=1 uoink serve
   ```

In a cloud sandbox, put the dependency and install commands in its setup
script. Ensure the agent process also has `~/.local/bin` on PATH, or use the
absolute paths printed by `connect`. The data folder
`${XDG_DATA_HOME:-$HOME/.local/share}/Uoink` holds the library; keep it on
persistent storage if the sandbox will be discarded. Re-run the installer
from an updated checkout to upgrade.

YouTube can block cloud IPs. Whisper fallback also fails when the audio
cannot be downloaded. Linux has no browser extension, tray or app windows.
