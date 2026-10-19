# Install Uoink with an AI agent on Windows

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

6. Ask the person to start **Uoink** from the Start menu. Silent install does not
   launch the helper; local CLI reads and MCP work without it. For browser capture,
   use the setup splash to copy the installed extension path, open
   `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**,
   and select that folder. Then click Chrome's puzzle-piece **Extensions** icon
   and pin **Uoink**. The Chrome Web Store listing is pending.

Chrome (tested); other Chromium browsers such as Edge and Brave may work but are not tested.
