# Uoink installer build orchestrator.
#
# One-command build:  .\build.ps1
#
# Steps:
#   1. Download Python embeddable, ffmpeg, and get-pip into build\cache\
#      (skipped if already cached).
#   2. Stage the install layout under installer\staging\:
#        python\   embeddable Python with site-packages enabled and
#                  yt-dlp installed via pip
#        bin\      ffmpeg.exe (and ffprobe.exe if present)
#        server.py, migrate_install.py, channels.py, workspaces.py, claims.py,
#        scripts.py, memory_layer.py, podcasts.py, mobile_playlists.py,
#        whisper_runner.py, source_manifest.py, openapi_bridge.py,
#        reddit_extractor.py, uoink_mcp.py, uoink_mcp_tools.py, yoink_mcp.py
#        (shim), yt_extract.py, topics.json, skills\,
#        assets\dashboard\, stop-server.{bat,ps1}, uoink.ico
#   3. Run ISCC.exe against installer\uoink.iss to produce
#      build\Uoink-Setup-<version>.exe
#
# See docs\build-installer.md for the architecture rationale and
# instructions on updating Python / yt-dlp / ffmpeg versions.

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
# Suppress Invoke-WebRequest's progress UI -- on PS 5.1 it slows large
# downloads to a crawl due to a known performance bug.
$ProgressPreference = 'SilentlyContinue'

# ---- Paths --------------------------------------------------------------
$RepoRoot     = $PSScriptRoot
$InstallerDir = Join-Path $RepoRoot 'installer'
$BuildDir     = Join-Path $RepoRoot 'build'
$CacheDir     = Join-Path $BuildDir 'cache'
$StagingDir   = Join-Path $InstallerDir 'staging'
$TemplatesDir = Join-Path $InstallerDir 'templates'
$IconSrc      = Join-Path $InstallerDir 'uoink.ico'

# ---- Versions (pinned for v2 ship) --------------------------------------
$VersionSourceFile = Join-Path $RepoRoot 'helper\_version.py'
if (-not (Test-Path $VersionSourceFile)) {
    throw "Missing helper\_version.py version source"
}
$VersionSourceText = Get-Content -Raw $VersionSourceFile
$VersionMatch = [regex]::Match($VersionSourceText, '(?m)^__version__\s*=\s*["''](?<version>\d+\.\d+\.\d+)["'']')
if (-not $VersionMatch.Success) {
    throw "helper\_version.py must define __version__ = 'x.y.z'"
}
$VERSION = $VersionMatch.Groups['version'].Value
Write-Host "Building Uoink version $VERSION" -ForegroundColor Cyan

$VersionFile = Join-Path $RepoRoot 'VERSION'
if (-not (Test-Path $VersionFile)) {
    throw "Missing VERSION file at repo root"
}
$VersionFileValue = (Get-Content -Raw $VersionFile).Trim()
if ($VersionFileValue -ne $VERSION) {
    throw "VERSION file ($VersionFileValue) does not match helper\_version.py ($VERSION). Update helper\_version.py first, then mirror it into VERSION."
}

$ManifestPath = Join-Path $RepoRoot 'extension\manifest.json'
if (-not (Test-Path $ManifestPath)) {
    throw "Missing extension\manifest.json"
}
$ManifestJson = Get-Content -Raw $ManifestPath | ConvertFrom-Json
$ManifestVersion = [string]$ManifestJson.version
if ($ManifestVersion -ne $VERSION) {
    throw "helper\_version.py ($VERSION) does not match extension\manifest.json version ($ManifestVersion). Update helper\_version.py first, then mirror it into the manifest."
}

# Python 3.11.9 is the last 3.11.x with binary installers; later 3.11 are
# source-only security releases. v2 accepts this; v2.1 plan: move to 3.12.
$PYTHON_VERSION = '3.11.9'
$PYTHON_URL     = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"
$GETPIP_URL     = 'https://bootstrap.pypa.io/get-pip.py'
# C-02 (license compliance): ffmpeg is now BtbN's win64-LGPL build, not the
# gyan.dev "essentials" GPLv3 build. The essentials build links GPL
# components (x264/x265) and its GPL redistribution obligations (offer of
# source, license text) were never met, which is one leg of the false-MITs
# claim. BtbN publishes an LGPL variant built without the GPL encoders; we
# only need ffmpeg for audio extraction/decoding, so the LGPL build is
# feature-sufficient. Versioned release tag (not "latest") so the hash pin
# below stays meaningful. THIRD-PARTY-NOTICES.md records the LGPL text +
# where to get ffmpeg's source.
$FFMPEG_VERSION = 'n7.1'
# BtbN publishes dated release tags; the end-of-month builds are retained
# long-term (daily builds get pruned), so we pin to a monthly snapshot. The
# asset name carries the exact git revision, so this URL is fully pinned --
# it never moves. "win64-lgpl" is the static LGPL variant (no GPL encoders,
# single self-contained ffmpeg.exe -- no DLLs to ship).
$FFMPEG_URL     = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2025-01-31-12-58/ffmpeg-n7.1-184-gdc07f98934-win64-lgpl-7.1.zip"
# yt-dlp pip pin -- bump after compatibility-testing a new release.
$YTDLP_VERSION  = '2026.07.04'
# Pillow is used for the multimodal paste-corpus generator (resize +
# JPEG-recompress + base64-encode the embedded screenshots). Pinned to
# a recent stable; bump at release-prep time after testing.
$PILLOW_VERSION = '10.4.0'
# Official Model Context Protocol Python SDK for the stdio MCP server.
# Also pinned in requirements.txt for dev installs and docs.
$MCP_VERSION    = '1.27.1'
# Windows Credential Manager wrapper for Anthropic API key storage.
# Also pinned in requirements.txt for dev installs and docs.
$KEYRING_VERSION = '25.7.0'
# System-tray icon (Tier 1 v2.1.1). Pure-Python; Pillow (already pinned above)
# renders the glyph. Optional at runtime -- server.py degrades if it's missing.
$PYSTRAY_VERSION = '0.19.5'
# Tier 2 GUI: pywebview wraps Codex's helper-served HTML in native windows
# (splash, dashboard). On Windows it uses the Edge WebView2 backend via
# pythonnet/.NET interop -- WebView2 Runtime (Evergreen) ships with Win10/11.
# pythonnet is pinned explicitly so pywebview never silently falls back to the
# legacy MSHTML renderer.
$PYWEBVIEW_VERSION = '5.4'
$PYTHONNET_VERSION = '3.0.5'
# Transcript reliability detection (C-02: was whisper-timestamped, now
# faster-whisper for license compliance -- MIT, no dtw-python/openai-whisper).
# Library ships; the tiny Whisper model downloads lazily to
# %LOCALAPPDATA%\Uoink\models\whisper.
$FASTER_WHISPER_VERSION = '1.2.1'
# v3.1.2 podcast/A1 transcription runtime. This bundles WhisperX and its
# runtime deps into the embeddable Python so podcast transcription works on a
# fresh install; model weights still download only after user consent.
$WHISPERX_VERSION = '3.8.6'

# ---- Hash verification --------------------------------------------------
# Direct-download SHA256s are locked as of v2.0. When bumping Python,
# ffmpeg, or get-pip.py, run build.ps1 once, verify the new artifact source,
# paste the new hash here, and rebuild. Subsequent builds fail with
# "SHA256 mismatch" if anything changes; Confirm-Hash deletes the bad cached
# file so a re-run pulls fresh.
$PYTHON_SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"
$FFMPEG_SHA256 = "1475187ddaf367c6702856fe37bb00e8b3ce69963e9b453a9de78396846ff38c"
$GETPIP_SHA256 = "66904bccb878e363db6236ea900e6935e507dcb887e9f178f6212edfe7f46a76"

# ---- Helpers ------------------------------------------------------------
function Write-Step($msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Find-Iscc {
    $candidates = @(
        (Join-Path ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($p in $candidates) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "ISCC.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isdl.php"
}

function Get-CachedFile($url, $dest) {
    if (Test-Path $dest) {
        Write-Host "    cached: $(Split-Path -Leaf $dest)"
        return
    }
    Write-Host "    downloading $(Split-Path -Leaf $dest) ..."
    $tmp = "$dest.tmp"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Move-Item -Force $tmp $dest
    } catch {
        if (Test-Path $tmp) { Remove-Item -Force $tmp }
        throw
    }
}

function Confirm-Hash($path, $expected, $label) {
    $actual = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
    if (-not $expected) {
        Write-Warning "    $label has no locked SHA256. Computed: $actual"
        Write-Warning "    Lock it by setting the matching `$..._SHA256 in build.ps1, then rebuild."
        return
    }
    if ($actual -ne $expected.ToLower()) {
        # Remove the bad cache so a re-run downloads fresh, in case the
        # corruption was transient. Don't ship a mismatched artifact.
        Remove-Item -Force -ErrorAction SilentlyContinue $path
        throw "$label SHA256 mismatch.`nExpected: $expected`nActual:   $actual"
    }
    Write-Host "    $label hash OK"
}

# ---- Optional clean -----------------------------------------------------
if ($Clean) {
    Write-Step 'Cleaning build/ and staging/'
    if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
    if (Test-Path $BuildDir)   { Remove-Item -Recurse -Force $BuildDir }
}

New-Item -ItemType Directory -Force -Path $CacheDir, $BuildDir | Out-Null

# ---- Sanity checks ------------------------------------------------------
# v2.2.0 brand fix: $IconSrc (installer\uoink.ico) is now a BUILD ARTIFACT
# regenerated from assets\logo-mark-color.png by installer\generate_icon.py
# (the regen step runs after pip install, since it uses the bundled Pillow).
# So the preflight here checks the SOURCE PNG instead of the generated .ico;
# the .ico itself is gitignored to prevent the v2.1.x staleness regression
# (it shipped the legacy Yoink-Y all the way through the rebrand).
$logoSrc = Join-Path $RepoRoot 'assets\logo-mark-color.png'
if (-not (Test-Path $logoSrc)) {
    throw "Missing $logoSrc -- can't regenerate installer\uoink.ico"
}
$dashboardIndex = Join-Path $RepoRoot 'assets\dashboard\index.html'
if (-not (Test-Path $dashboardIndex)) {
    throw "Missing assets\dashboard\index.html -- Tier 1 dashboard route would 404"
}
$splashIndex = Join-Path $RepoRoot 'assets\splash\index.html'
if (-not (Test-Path $splashIndex)) {
    throw "Missing assets\splash\index.html -- Tier 2 /splash route would 404"
}
foreach ($f in @(
    'VERSION',
    'helper\_version.py',
    'server.py',
    'index.py',
    '_platform.py',
    'migrate_install.py',
    'channels.py',
    'workspaces.py',
    'claims.py',
    'scripts.py',
    'memory_layer.py',
    'podcasts.py',
    'mobile_playlists.py',
    'whisper_runner.py',
    'source_manifest.py',
    'openapi_bridge.py',
    'reddit_extractor.py',
    'x_extractor.py',
    'x_article_extractor.py',
    'notes.py',
    'images.py',
    'taste_scoring.py',
    'defaults\style_anchors.json',
    'yt_extract.py',
    'topics.json',
    'installer\verify_install.ps1',
    'uoink_core\storage.py'
)) {
    if (-not (Test-Path (Join-Path $RepoRoot $f))) {
        throw "Missing $f at repo root"
    }
}
# The skill folder is renamed skills\yoink -> skills\uoink by the extension/
# skill agent (Antigravity's chore/rename-extension-to-uoink). That rename is
# a hard prerequisite for a v2.1 build: shipping the legacy skills\yoink\ folder
# would package a Yoink-branded Skill driving the deprecated alias tools. Require
# the renamed skill and fail loudly if it hasn't merged yet -- no legacy fallback.
$skillMd = Join-Path $RepoRoot 'skills\uoink\SKILL.md'
if (-not (Test-Path $skillMd)) {
    throw "Missing skills\uoink\SKILL.md -- Antigravity rename not merged; refusing to build"
}
# Sprint 19.6 / Fix 1: every migrations\NNNN_*.sql ships with the helper --
# missing them silently breaks index.py's _run_migrations at first boot.
$migrationFiles = Get-ChildItem -Path (Join-Path $RepoRoot 'migrations') `
    -Filter '*.sql' -ErrorAction SilentlyContinue
if (-not $migrationFiles -or $migrationFiles.Count -eq 0) {
    throw "Missing migrations\*.sql at repo root"
}

# ---- 1. Download dependencies ------------------------------------------
Write-Step 'Fetching dependencies'
$pythonZip = Join-Path $CacheDir "python-$PYTHON_VERSION-embed-amd64.zip"
$ffmpegZip = Join-Path $CacheDir 'ffmpeg-win64-lgpl.zip'
$getPipPy  = Join-Path $CacheDir 'get-pip.py'

Get-CachedFile $PYTHON_URL $pythonZip
Confirm-Hash $pythonZip $PYTHON_SHA256 'Python embeddable'
Get-CachedFile $FFMPEG_URL $ffmpegZip
Confirm-Hash $ffmpegZip $FFMPEG_SHA256 'ffmpeg'
Get-CachedFile $GETPIP_URL $getPipPy
Confirm-Hash $getPipPy $GETPIP_SHA256 'get-pip.py'

# ---- 2. Stage -----------------------------------------------------------
Write-Step 'Staging'
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Force -Path $StagingDir, "$StagingDir\python", "$StagingDir\bin" | Out-Null

# 2a. Extract Python embeddable
Write-Host '    extracting Python embeddable...'
Expand-Archive -Path $pythonZip -DestinationPath "$StagingDir\python" -Force

# 2b. Enable site-packages -- embeddable distributions ship with the
#     `import site` line commented out, which prevents Lib\site-packages
#     from being on sys.path. Uncomment it.
$pthFile = Get-ChildItem -Path "$StagingDir\python" -Filter '*._pth' | Select-Object -First 1
if (-not $pthFile) { throw 'Embeddable archive missing python*._pth' }
$pthContent = Get-Content -Raw $pthFile.FullName
$pthContent = $pthContent -replace '#\s*import\s+site', 'import site'
# Encode as ASCII (no BOM) -- the embeddable launcher reads _pth as bytes
# and a UTF-16 / UTF-8 BOM here will break sys.path setup.
[System.IO.File]::WriteAllText($pthFile.FullName, $pthContent, [System.Text.Encoding]::ASCII)

# 2c. Bootstrap pip into the embeddable
Write-Host '    bootstrapping pip in embeddable Python...'
$embedPython = "$StagingDir\python\python.exe"
& $embedPython $getPipPy --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }

# 2d. Install yt-dlp + Pillow + MCP + keyring at pinned versions. Pip's hash-locking would
#     require a requirements file with --require-hashes; for v2 we accept
#     the trust-pip-itself model since the version pins are the
#     load-bearing part (a compromised release on PyPI affects everyone,
#     not just us). Pillow drives the multimodal paste-corpus generator
#     (resize / re-encode / base64 screenshots for clipboard embedding).
#     MCP powers uoink_mcp.py for stdio agent integrations. keyring stores
#     the user's Anthropic API key in Windows Credential Manager.
Write-Host "    installing yt-dlp==$YTDLP_VERSION + Pillow==$PILLOW_VERSION + mcp==$MCP_VERSION + keyring==$KEYRING_VERSION + pystray==$PYSTRAY_VERSION + pywebview==$PYWEBVIEW_VERSION + pythonnet==$PYTHONNET_VERSION + faster-whisper==$FASTER_WHISPER_VERSION + whisperx==$WHISPERX_VERSION..."
& $embedPython -m pip install --no-warn-script-location --no-compile `
    "yt-dlp==$YTDLP_VERSION" "Pillow==$PILLOW_VERSION" "mcp==$MCP_VERSION" "keyring==$KEYRING_VERSION" "pystray==$PYSTRAY_VERSION" "pywebview==$PYWEBVIEW_VERSION" "pythonnet==$PYTHONNET_VERSION" "faster-whisper==$FASTER_WHISPER_VERSION" "whisperx==$WHISPERX_VERSION"
if ($LASTEXITCODE -ne 0) { throw 'pip install (yt-dlp + Pillow + MCP + keyring + pystray + faster-whisper + whisperx) failed' }

# C-02: regenerate THIRD-PARTY-NOTICES.md from the bundle we just built, so
# the shipped notices match the shipped dependency tree exactly. pip-licenses
# reads the embeddable Python's installed metadata. Best-effort: a missing
# pip-licenses (offline dev build) warns but doesn't fail the build; the
# committed file is the fallback.
Write-Step 'Generating THIRD-PARTY-NOTICES.md'
& $embedPython -m pip install --no-warn-script-location --no-compile "pip-licenses==5.0.0" 2>$null
if ($LASTEXITCODE -eq 0) {
    $noticesPath = Join-Path $RepoRoot 'THIRD-PARTY-NOTICES.md'
    & $embedPython (Join-Path $RepoRoot 'scripts\gen_third_party_notices.py') $noticesPath
    if ($LASTEXITCODE -ne 0) { Write-Warning 'THIRD-PARTY-NOTICES generation failed; committed file kept.' }
    # pip-licenses is a build-time tool, not a runtime dep -- strip it back out.
    & $embedPython -m pip uninstall -y pip-licenses prettytable 2>$null
} else {
    Write-Warning 'pip-licenses unavailable; THIRD-PARTY-NOTICES.md not regenerated.'
}

# 2d-bis. Regenerate installer\uoink.ico from assets\logo-mark-color.png. Uses
# the embeddable Pillow (just installed). Runs BEFORE the staging copy of
# uoink.ico and before ISCC reads SetupIconFile, so both consumers pick up the
# fresh .ico. Single source of truth -> no more rebrand staleness.
Write-Step 'Generating uoink.ico'
& $embedPython (Join-Path $InstallerDir 'generate_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'uoink.ico generation failed' }

# 2e. Trim dev-only and build-time files we don't need at runtime.
# distutils-precedence.pth is dropped by setuptools and tries to import
# `_distutils_hack` at every Python startup. We strip setuptools above, so
# the .pth file would print a noisy ModuleNotFoundError warning on every
# server launch -- delete it too.
Write-Host '    trimming embeddable...'
$stripGlobs = @(
    "$StagingDir\python\Lib\site-packages\pip*",
    "$StagingDir\python\Lib\site-packages\setuptools*",
    "$StagingDir\python\Lib\site-packages\_distutils*",
    "$StagingDir\python\Lib\site-packages\distutils-precedence.pth",
    "$StagingDir\python\Lib\site-packages\wheel*",
    "$StagingDir\python\Lib\site-packages\__pycache__"
)
foreach ($g in $stripGlobs) {
    Get-Item -ErrorAction SilentlyContinue $g | ForEach-Object {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $_.FullName
    }
}
# Strip any stray .pyc caches generated by pip's bootstrap.
Get-ChildItem -Path "$StagingDir\python" -Filter '__pycache__' -Recurse -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $_.FullName }

# 2f. ffmpeg -- pull just ffmpeg.exe (and ffprobe.exe if present)
Write-Host '    extracting ffmpeg...'
$ffmpegTmp = Join-Path $BuildDir '_ffmpeg_tmp'
if (Test-Path $ffmpegTmp) { Remove-Item -Recurse -Force $ffmpegTmp }
Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegTmp -Force
$ffmpegExe = Get-ChildItem -Path $ffmpegTmp -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
if (-not $ffmpegExe) { throw 'ffmpeg.exe not found inside the BtbN LGPL archive' }
Copy-Item $ffmpegExe.FullName "$StagingDir\bin\ffmpeg.exe" -Force
$ffprobeExe = Get-ChildItem -Path $ffmpegTmp -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1
if ($ffprobeExe) {
    Copy-Item $ffprobeExe.FullName "$StagingDir\bin\ffprobe.exe" -Force
}
Remove-Item -Recurse -Force $ffmpegTmp

# 2g. Server source + helpers + icon
Write-Host '    copying server source + templates...'
Copy-Item (Join-Path $RepoRoot 'server.py')      $StagingDir -Force
# System-tray module (Tier 1 v2.1.1). Imported by server.py at boot on
# installed builds; optional at runtime (degrades if pystray is unavailable).
Copy-Item (Join-Path $RepoRoot 'uoink_tray.py')  $StagingDir -Force
# Tier 2 GUI: splash + dashboard pywebview windows. Imported as subprocess
# entrypoints (not at server import time), but must ship or the tray's
# left-click + the first-run splash crash silently.
Copy-Item (Join-Path $RepoRoot 'uoink_splash.py')    $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'uoink_dashboard.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'index.py')       $StagingDir -Force
# Cross-platform path/OS helpers (added Sprint 19.5). server.py and
# migrate_install.py `import _platform` at module top -- omitting it ships a
# helper that crashes with ModuleNotFoundError before binding the port.
Copy-Item (Join-Path $RepoRoot '_platform.py')   $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'migrate_install.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'channels.py')    $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'workspaces.py')  $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'claims.py')      $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'scripts.py')     $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'voice_dna.py')   $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'writing_studio.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'page_extractor.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'source_manifest.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'openapi_bridge.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'reddit_extractor.py') $StagingDir -Force
# U-15 X text/thread capture. server.py imports x_extractor at module top,
# so it must ship or the helper crashes with ModuleNotFoundError before
# binding the port (cf. reddit_extractor.py). Added v3.2.6.
Copy-Item (Join-Path $RepoRoot 'x_extractor.py') $StagingDir -Force
# V-2c X Article capture. server.py imports x_article_extractor at module top.
Copy-Item (Join-Path $RepoRoot 'x_article_extractor.py') $StagingDir -Force
# Context-layer item 1: quick notes capture. server.py imports notes at module
# top, so it must ship or the helper crashes on launch (cf. x_extractor.py).
Copy-Item (Join-Path $RepoRoot 'notes.py') $StagingDir -Force
# Context-layer item 3: image / meme capture. server.py imports images at
# module top, so it must ship or the helper crashes on launch (cf. notes.py).
Copy-Item (Join-Path $RepoRoot 'images.py') $StagingDir -Force
# V-3 taste-aware auto-uoink. server.py imports taste_scoring at module top,
# so it must ship or the helper crashes with ModuleNotFoundError. Added v3.3.0.
Copy-Item (Join-Path $RepoRoot 'taste_scoring.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'memory_layer.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'podcasts.py')    $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'mobile_playlists.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'whisper_runner.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'uoink_mcp.py')   $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'uoink_mcp_tools.py') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'uoink_reliability.py') $StagingDir -Force
# Back-compat shim (removed in v3): keeps yoink_mcp.py launchable.
Copy-Item (Join-Path $RepoRoot 'yoink_mcp.py')   $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'requirements.txt') $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'yt_extract.py')  $StagingDir -Force
Copy-Item (Join-Path $RepoRoot 'topics.json')    $StagingDir -Force
Set-Content -Path (Join-Path $StagingDir 'VERSION') -Value $VERSION -Encoding ASCII
Copy-Item (Join-Path $RepoRoot 'helper') (Join-Path $StagingDir 'helper') -Recurse -Force
Copy-Item (Join-Path $InstallerDir 'verify_install.ps1') $StagingDir -Force
Copy-Item (Join-Path $TemplatesDir 'stop-server.bat') $StagingDir -Force
Copy-Item (Join-Path $TemplatesDir 'stop-server.ps1') $StagingDir -Force
Copy-Item $IconSrc (Join-Path $StagingDir 'uoink.ico') -Force
# Sprint 21: the uoink_core/ package holds modules split out of server.py.
# server.py imports it at module top, so it must ship or the helper crashes
# with ModuleNotFoundError before binding the port (cf. _platform.py).
Copy-Item (Join-Path $RepoRoot 'uoink_core') (Join-Path $StagingDir 'uoink_core') -Recurse -Force
Copy-Item (Join-Path $RepoRoot 'skills') (Join-Path $StagingDir 'skills') -Recurse -Force
# v3.2 Writing Studio: ship the canonical Voice DNA doc so the helper can
# load VOICE_DNA_PROMPT at boot. voice_dna.py looks in $HERE/voice_dna/
# first, falls back to $HERE/. Sync source is uoink-handoff/VOICE-DNA.md.
Copy-Item (Join-Path $RepoRoot 'voice_dna') (Join-Path $StagingDir 'voice_dna') -Recurse -Force
Copy-Item (Join-Path $RepoRoot 'assets\dashboard') (Join-Path $StagingDir 'assets\dashboard') -Recurse -Force
# Tier 2 GUI: splash HTML (served at /splash and wrapped by uoink_splash.py)
# and the brand tokens stylesheet used by both pages.
Copy-Item (Join-Path $RepoRoot 'assets\splash') (Join-Path $StagingDir 'assets\splash') -Recurse -Force
Copy-Item (Join-Path $RepoRoot 'assets\brand')  (Join-Path $StagingDir 'assets\brand')  -Recurse -Force
# v3.1.3: ship the unpacked Chrome extension beside the helper so the
# first-run hint can point Chrome's "Load unpacked" flow at a real folder.
Copy-Item (Join-Path $RepoRoot 'extension') (Join-Path $StagingDir 'extension') -Recurse -Force
# v2.2.0: canonical rust-U mark used by the tray glyph loader AND by
# installer\generate_icon.py. Shipping it makes the tray's PNG source-of-truth
# pattern work post-install (uoink_tray loads {app}\assets\logo-mark-color.png).
Copy-Item (Join-Path $RepoRoot 'assets\logo-mark-color.png') (Join-Path $StagingDir 'assets\logo-mark-color.png') -Force
# Sprint 19.6 / Fix 1: migrations\*.sql is required at runtime by
# index._run_migrations; if it's missing the helper crashes at first boot
# with "no such table: schema_version". Pre-Sprint-19.6 installers shipped
# without it -- C1 launch blocker.
Copy-Item (Join-Path $RepoRoot 'migrations') (Join-Path $StagingDir 'migrations') -Recurse -Force
# v3.2.3: curated default style anchors, seeded into style_anchors on first run
# by server._seed_default_style_anchors. Must ship or the seed silently no-ops
# (helper still boots, but users get an empty anchor library -- the friction
# this release exists to remove).
Copy-Item (Join-Path $RepoRoot 'defaults') (Join-Path $StagingDir 'defaults') -Recurse -Force

# ---- 2h. Staged smoke (Sprint 19.6 / Fix 1) -----------------------------
# Verifies the staged tree is actually runnable BEFORE ISCC packages it,
# so the works-in-repo-breaks-in-installer drift class is caught here
# rather than at first launch on a user's machine.
Write-Step 'Staged smoke'
Push-Location $StagingDir
try {
    & '.\python\python.exe' -m py_compile `
        server.py index.py migrate_install.py channels.py workspaces.py claims.py scripts.py voice_dna.py writing_studio.py page_extractor.py source_manifest.py openapi_bridge.py reddit_extractor.py x_extractor.py x_article_extractor.py notes.py images.py taste_scoring.py memory_layer.py podcasts.py mobile_playlists.py whisper_runner.py uoink_mcp.py uoink_mcp_tools.py uoink_reliability.py yoink_mcp.py yt_extract.py helper\_version.py
    if ($LASTEXITCODE -ne 0) {
        throw 'staged smoke: py_compile of staged Python files failed'
    }
    # Run the smoke from a temp .py FILE, not via `-c`: PowerShell 5.1 mangles
    # embedded double-quotes when handing a multi-line script to a native exe.
    # Two import facts about the embeddable distribution drive the sys.path line:
    # its python._pth lists only python\, the stdlib zip, and site-packages
    # (never the staging root), it ignores PYTHONPATH while a ._pth is present,
    # and it does NOT add the script's own directory either. So the smoke inserts
    # its own dir on sys.path -- exactly what server.py does at runtime
    # (sys.path.insert(0, HERE)) -- or neither index.py nor server.py would import.
    #
    # Checks: (1) index.py imports and migrations\*.sql apply (schema_version is
    # populated from the staged layout), and (2) server.py imports. py_compile
    # above only compiles -- it never runs server.py's top-level imports, so a
    # dropped runtime dependency (e.g. _platform.py) or a missing data file
    # (VERSION) would otherwise sail through and crash the helper at first launch
    # before it binds the port. The file is removed before ISCC packages staging.
    $smokePy = Join-Path $StagingDir '_staged_smoke.py'
    Set-Content -Path $smokePy -Encoding ASCII -Value @'
import json, os, sys, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index
p = pathlib.Path(tempfile.mkdtemp()) / "test.db"
idx = index.Index.open(p)
v = idx._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
idx.close()
if not v:
    raise SystemExit("smoke: Index.open ran but schema_version is empty; "
                     "migrations/*.sql likely missing from staging")
print("smoke: Index.open OK, schema_version=%s" % v)
import server
expected = (pathlib.Path(__file__).with_name("VERSION")).read_text(encoding="utf-8").strip()
if server.VERSION != expected:
    raise SystemExit("smoke: server.VERSION %s != staged VERSION %s" % (server.VERSION, expected))
print("smoke: import server OK, version=%s" % server.VERSION)
manifest = json.loads((pathlib.Path(__file__).parent / "extension" / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("version") != expected:
    raise SystemExit("smoke: extension manifest %s != staged VERSION %s" % (manifest.get("version"), expected))
print("smoke: extension manifest OK, version=%s" % manifest.get("version"))
import uoink_tray
print("smoke: import uoink_tray OK")
import uoink_splash, uoink_dashboard
print("smoke: import uoink_splash + uoink_dashboard OK")
import whisperx
print("smoke: import whisperx OK")
'@
    try {
        & '.\python\python.exe' $smokePy
        if ($LASTEXITCODE -ne 0) {
            throw 'staged smoke failed: import index/server or Index.open against the staged tree (a required module/file is missing -- e.g. _platform.py, VERSION, or migrations\*.sql)'
        }
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $smokePy
    }
    Write-Host '    Staged smoke OK' -ForegroundColor Green
} finally {
    Pop-Location
}

# ---- 2i. Wizard bitmaps -------------------------------------------------
# Regenerate the branded WizardImage/WizardSmallImage BMPs from source each
# build (no committed binary churn). Uses the staged embeddable Python, which
# has Pillow installed. ISCC reads them from installer\assets\ at compile time
# (they are baked into Setup.exe, not installed into {app}).
Write-Step 'Generating wizard bitmaps'
& $embedPython (Join-Path $InstallerDir 'generate_bitmaps.py')
if ($LASTEXITCODE -ne 0) { throw 'wizard bitmap generation failed' }

# ---- 3. Compile installer ----------------------------------------------
Write-Step 'Compiling installer'
$iscc = Find-Iscc
Write-Host "    using $iscc"
$issTemplate = Join-Path $InstallerDir 'uoink.iss'
$issGenerated = Join-Path $InstallerDir 'uoink.generated.iss'
$issText = Get-Content -Raw $issTemplate
# NOTE: the trailing \r? is load-bearing. uoink.iss is CRLF on Windows
# checkouts, and .NET's (?m)$ anchors *before* the \n -- with a \r still
# sitting after the closing quote, the bare ".*"$ pattern never matches, the
# AppVersion #define is left at its stale hardcoded value, and ISCC names the
# output Uoink-Setup-<old>.exe (hit during the v2.1.1 build: VERSION/manifest
# were 2.1.1 but the .exe came out 2.1.0). \r? lets $ match on CRLF lines too.
$issText = $issText -replace '(?m)^#define\s+AppVersion\s+".*"\r?$', "#define AppVersion    `"$VERSION`""
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($issGenerated, $issText, $utf8NoBom)
try {
    & $iscc /Q $issGenerated
    if ($LASTEXITCODE -ne 0) { throw 'ISCC compilation failed' }
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $issGenerated
}

$exe = Join-Path $BuildDir "Uoink-Setup-$VERSION.exe"
if (-not (Test-Path $exe)) { throw "ISCC reported success but $exe is missing" }

$sizeMb = (Get-Item $exe).Length / 1MB
Write-Host ''
Write-Host ("Built {0} ({1:N1} MB)" -f $exe, $sizeMb) -ForegroundColor Green
