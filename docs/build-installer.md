# Uoink Installers — Build Guide

## Quick start (Windows)

```powershell
# From the repo root, on Windows with PowerShell 5.1 or later:
.\build.ps1
```

The script downloads and caches the pinned runtime dependency set under
`build\cache\`, stages the install layout, and compiles
`build\Uoink-Setup-<VERSION>.exe`.

To wipe everything and rebuild from scratch:

```powershell
.\build.ps1 -Clean
```

## Windows build prerequisites

You need both of these installed on the Windows build machine:

- **Inno Setup 6** — <https://jrsoftware.org/isdl.php>. The default install path (`C:\Program Files (x86)\Inno Setup 6`) is auto-detected, otherwise put `ISCC.exe` on `PATH`.
- **PowerShell 5.1+** — ships with Windows 10/11.

You do *not* need a system Python installed; the build downloads and uses an embeddable Python distribution exclusively.

## macOS status

There is no working macOS build command or `.dmg` artifact. `build-mac.sh` is
an incomplete scaffold: its Mac-only build, signing, notarization, and
packaging steps are marked `TODO(mac)`, and the script finishes by stating
that it produced no artifact. Do not use it to prepare an install.

See [mac-install.md](mac-install.md) for the current user-facing status.
[MAC-BUILD-PLAN.md](MAC-BUILD-PLAN.md) records the verified gaps, required Mac
hardware and signing setup, and the remaining implementation work.

## Architecture: why Python embeddable + Inno Setup

The original packaging review considered two options. The current Windows
installer uses **Option B (Python embeddable + Inno Setup)**.

| Concern | Option A (PyInstaller) | Option B (embeddable) |
|---|---|---|
| Antivirus behavior | Adds a PyInstaller bootloader | No PyInstaller bootloader; the unsigned installer is still subject to SmartScreen and AV checks |
| Build complexity | Spec file tuning, hidden imports | Embeddable-Python bootstrap, pinned pip install, staging, and Inno Setup |
| Hotfix path | Rebuild the frozen package | Rebuild the installer; manual edits inside an installed copy are unsupported |
| Install size | Measure the frozen candidate | Measure `installer\staging` and the compiled installer; the current shape includes local ASR and desktop dependencies |
| Startup time | Requires candidate measurement | Requires candidate measurement |
| Update mechanism | Replace the frozen application | Re-run the installer to replace the staged runtime |

The current Windows candidate is unsigned. Avoiding a PyInstaller bootloader
removes one packaging-specific heuristic surface, but it does not make an
unsigned installer trusted or exempt from SmartScreen and antivirus checks.

Do not copy a fixed install-size claim forward. Measure both
`installer\staging` and the compiled installer for every release candidate;
the local ASR and desktop runtime set makes size sensitive to dependency
changes.

## What gets bundled

The installer lays out `%LOCALAPPDATA%\Uoink\`:

```
python\           Python 3.11 embeddable + the pinned runtime packages listed below
bin\              ffmpeg.exe, ffprobe.exe (PATH-prepended by server.py)
server.py         The local HTTP helper
uoink_mcp.py      MCP stdio entry point for agent clients
uoink_mcp_tools.py Shared MCP tool registry
requirements.txt  Source-install pins; the installer uses an explicit build.ps1 subset
yt_extract.py     Imported by server.py (parse_srt, slugify, fmt_time)
topics.json       Topic-folder routing rules
stop-server.bat   Reads server.pid and kills the helper
stop-server.ps1   PowerShell variant + defensive command-line sweep
skills\uoink\     Uoink Operator Skill, plugin manifest, and system prompt
uoink.ico         Used for shortcuts and the uninstaller chrome
unins000.exe      Inno Setup writes this; runs the uninstaller
```

Plus, Windows-side:

- Start Menu group `Uoink` with **Uoink Server** (start), **Stop Uoink Server**, **Uoink folder**, **Uninstall Uoink**.
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Uoink` value pointing at `pythonw.exe server.py` so the helper auto-starts on login. Removed cleanly on uninstall (`uninsdeletevalue`).
- Optional **Launch Uoink Server now** checkbox on the finish page (default checked).

The helper runs under `pythonw.exe`, so there's no console window. `server.py` writes `server.pid` on startup and removes it on graceful exit; `stop-server.bat` reads it.

## Where dependencies come from

- **Python embeddable** — `https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip`. Update the `$PYTHON_VERSION` constant in `build.ps1` to bump.
- **ffmpeg** — BtbN `n7.1` Windows static win64 LGPL build:
  `https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2025-01-31-12-58/ffmpeg-n7.1-184-gdc07f98934-win64-lgpl-7.1.zip`.
  The build script extracts only `ffmpeg.exe` and `ffprobe.exe`; the rest of
  the archive is discarded.
- **get-pip.py** — `https://bootstrap.pypa.io/get-pip.py`. Used once during the build to bootstrap pip into the embeddable.

These three direct downloads are cached under `build\cache\`. Delete the cache
or pass `-Clean` to force a refresh. The remaining runtime packages are
installed into the embeddable Python with the exact pip versions below.

## Current pin snapshot

| Component | Version | SHA256 | Notes |
|---|---|---|---|
| Python embeddable | 3.11.9 (amd64) | Locked in `build.ps1` | Current embedded runtime; any bump requires a clean installer build and smoke test. |
| ffmpeg | n7.1 BtbN win64 LGPL | Locked in `build.ps1` | Pinned to one versioned BtbN archive and SHA256. |
| yt-dlp | 2026.07.04 | (pip) | Pinned via `pip install yt-dlp==2026.07.04`. Bump after compatibility-testing a new release. |
| Pillow | 10.4.0 | (pip) | Drives the multimodal paste-corpus generator (resize + JPEG-recompress + base64-encode screenshots for clipboard embedding). Pinned via `pip install Pillow==10.4.0`. |
| MCP Python SDK | 1.27.1 | (pip) | Official Model Context Protocol Python SDK. Powers the stdio MCP server. Pinned via `pip install mcp==1.27.1` and `requirements.txt`. |
| keyring | 25.7.0 | (pip) | Stores the BYO Anthropic API key in Windows Credential Manager. Pinned via `pip install keyring==25.7.0` and `requirements.txt`. |
| pystray | 0.19.5 | (pip) | Windows tray integration. |
| pywebview | 5.4 | (pip) | Local desktop shell. |
| pythonnet | 3.0.5 | (pip) | Runtime bridge used by the Windows desktop shell. |
| faster-whisper | 1.2.1 | (pip) | Local transcript reliability backend. |
| whisperx | 3.8.6 | (pip) | Optional local transcription and diarization runtime. |

### SHA256 hashes

The `Confirm-Hash` helper in `build.ps1` verifies SHA256 for the directly-downloaded artifacts (Python embeddable + ffmpeg + get-pip.py). The `$..._SHA256` constants are locked in source, which means:

- A normal build prints `<component> hash OK`.
- A compromised mirror or silent upstream change fails the build with `SHA256 mismatch`.
- `Confirm-Hash` deletes the bad cached file so a re-run pulls fresh after you intentionally update the hash.

When bumping a directly-downloaded component:

1. Run `.\build.ps1` once on a network-connected machine.
2. If the version changed, copy the computed hash from the warning/error output after verifying the artifact source.
3. Paste them into the matching `$PYTHON_SHA256`, `$FFMPEG_SHA256`, `$GETPIP_SHA256` constants in `build.ps1`.
4. Re-run `.\build.ps1` -- it should now print `<component> hash OK` instead of the warnings.
5. Commit the version bump and matching hash update together.

Pip-installed packages (`yt-dlp`, `Pillow`, `mcp`, `keyring`, `pystray`,
`pywebview`, `pythonnet`, `faster-whisper`, and `whisperx`) are version-pinned
but not hash-locked yet. Full pip hash-locking would require a
`requirements.txt` with `--require-hashes`; for now the installer accepts the
trust-pip-itself model while keeping exact package versions stable.

## Updating versions

| Component | Where to change |
|---|---|
| Python | `$PYTHON_VERSION` in `build.ps1`, and the `python*._pth` glob in stage step 2b — Python 3.12 would be `python312._pth` (no other code change needed). |
| yt-dlp | Update `$YTDLP_VERSION` in `build.ps1`. |
| MCP Python SDK | Update `$MCP_VERSION` in `build.ps1` and the matching `mcp==...` pin in `requirements.txt`. |
| keyring | Update `$KEYRING_VERSION` in `build.ps1` and the matching `keyring==...` pin in `requirements.txt`. |
| Pillow, pystray, pywebview, pythonnet | Update `$PILLOW_VERSION`, `$PYSTRAY_VERSION`, `$PYWEBVIEW_VERSION`, or `$PYTHONNET_VERSION` in `build.ps1` and the matching `requirements.txt` pin. |
| faster-whisper, whisperx | Update `$FASTER_WHISPER_VERSION` or `$WHISPERX_VERSION` in `build.ps1` and the matching `requirements.txt` pin; verify their shared dependency resolution together. |
| ffmpeg | Update `$FFMPEG_VERSION`, `$FFMPEG_URL`, and `$FFMPEG_SHA256` together after verifying the replacement is still a BtbN win64 LGPL build. |
| Uoink itself | Update `helper\_version.py`, then mirror the same value into the repo-root `VERSION` file and `extension\manifest.json`. `build.ps1` rewrites `installer\uoink.generated.iss`, stages `VERSION` from the helper constant, and fails if any version value drifts. |

## How `server.py` finds bundled binaries

`server.py` calls `subprocess.run(["ffmpeg", ...])` with no path. To make that work post-install, the top of `server.py` prepends `<install dir>\bin` to the process `PATH`:

```python
_BIN_DIR = HERE / "bin"
if _BIN_DIR.is_dir():
    os.environ["PATH"] = str(_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")
```

In dev mode (running from the repo) `bin\` doesn't exist and the line is a no-op — `ffmpeg` resolves via the user's existing PATH like before.

yt-dlp is invoked as `[sys.executable, "-m", "yt_dlp"]`, so the right interpreter (the embeddable) drives the right `yt_dlp` package automatically.

### Dev mode output root override

By default, Uoink writes extracted videos under the user's Desktop output root (`Desktop\Uoink`, honoring Windows known-folder / OneDrive Desktop redirection). In dev mode, that can be awkward if the repo itself lives on the Desktop: personal yoinks may appear inside or next to the worktree.

Set `UOINK_OUTPUT_DIR` to an existing writable directory before starting `server.py` to override the output root:

```powershell
New-Item -ItemType Directory -Force C:\TestYoinkOut | Out-Null
$env:UOINK_OUTPUT_DIR = 'C:\TestYoinkOut'
python server.py
```

If the env var is missing, points at a non-existent path, or is not writable, Uoink falls back to the normal Desktop root. The installed Start Menu shortcut does not set this variable; it is intended for local development and support smoke tests.

## Known issues

### Antivirus warnings on unsigned builds

`Uoink-Setup-<VERSION>.exe` is currently unsigned. SmartScreen or antivirus
software may warn, block, or quarantine an unsigned candidate; behavior varies
by machine, policy, reputation, and scanner.

There is no signing step in `build.ps1` today. Any release-signing change needs
an explicit release-owner decision, secure certificate/key handling,
timestamping, and verification of the installer and shipped executables. Do
not promise that a certificate will suppress every warning. Test the exact
candidate on the supported Windows matrix and record what happened.

### Pip bootstrap pulls files we don't ship

`get-pip.py` installs pip + setuptools + wheel into the embeddable. We strip those after runtime packages are installed (see step 2e in `build.ps1`) so the shipped install only contains what the server actually imports. If a future package adds a transitive dependency, it'll land in `site-packages` automatically and get included.

### Packaged prompts are read-only

The popup ships with 11 starter prompts loaded from `extension/prompts.json`
inside the browser-extension package. Installed helper users do not have that
extension source tree beside `server.py`. The helper's `/open-prompts` endpoint
therefore remains dev-only and is not surfaced in the UI. There is no portable
prompt editor in the current product, and this guide does not promise one for a
specific release.

### `topics.json` is read-only after install

`topics.json` ships with the installer and lives in `%LOCALAPPDATA%\Uoink\`. Users can edit it (the path is user-writable) but there's no UI for it; today this is a power-user knob. Treat it as configuration that the next installer version will overwrite.

## Launch checklist

Before updating the extension's download button for a new release:

1. **Build a release artifact:** `.\build.ps1` → produces `build\Uoink-Setup-<VERSION>.exe`.
2. **Smoke-test on a clean Windows VM** (see Testing matrix below).
3. **Set the approved version from the repository:** in PowerShell, run
   `$version = (Get-Content VERSION -Raw).Trim()` and confirm the approved
   release tag will be `v$version`. Tagging and pushing happen only after the
   release owner approves the build.
4. **Prepare the GitHub release as a draft:**
   - Create a new release at `https://github.com/ryanbiddy/uoink/releases/new`.
   - Tag: `v$version`. Title: `Uoink v$version`.
   - Attach `build\Uoink-Setup-$version.exe`.
   - Keep the release in draft until the release owner approves publication.
5. **After the non-draft release asset exists, update the extension link:**
   - Set `PUBLISHED_INSTALLER_VERSION` in `extension/setup.js` to the published
     version.
   - Reload the extension, visit `setup.html`, and verify the Windows button
     resolves to
     `https://github.com/ryanbiddy/uoink/releases/download/v$version/Uoink-Setup-$version.exe`.
6. **Publish the extension** only as a separate, explicit release-owner action.

There is no separate boolean publication switch. The versioned asset URL is
the control: update it only after that exact public asset exists, so the
shipped extension never points users at a draft or missing installer.

## Testing matrix

After `build.ps1` finishes, smoke-test by:

1. **Fresh install** — run `Uoink-Setup-<VERSION>.exe` on a Windows VM that doesn't have Uoink. Confirm:
   - Default install path is `%LOCALAPPDATA%\Uoink`.
   - "Launch Uoink Server now" is checked by default on the finish page.
   - After finish, `Get-Process pythonw` shows a process whose path is inside the install dir.
   - The browser extension's popup turns green within ~3 seconds.
2. **Auto-start** — restart Windows (or sign out and back in). Confirm the helper is running again from the registry Run key.
3. **Stop and restart** — Start Menu → Uoink → Stop Uoink Server. Extension popup goes orange. Start Menu → Uoink → Uoink Server. Goes green again.
4. **Uninstall** — Settings → Apps → Uoink → Uninstall. After completion verify:
   - `%LOCALAPPDATA%\Uoink` is gone (or close to gone — log files may remain if the server was hard-killed).
   - The HKCU `Run\Uoink` value is gone (`reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
   - The Start Menu group is gone.
