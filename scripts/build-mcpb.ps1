#requires -Version 5.1
<#
.SYNOPSIS
  Build the Uoink Claude Desktop MCP bundle (.mcpb).

.DESCRIPTION
  Packages the Uoink stdio MCP server as a one-click .mcpb bundle for
  Claude Desktop (formerly DXT). The bundle is a thin launcher: at runtime
  it connects Claude Desktop to the Uoink helper the user already installed
  from https://uoink.app/install (that install carries the bundled Python
  interpreter, the sibling modules, and the heavy dependencies). The
  install directory is resolved via a .mcpb user_config field that defaults
  to the standard Windows location (%LOCALAPPDATA%\Uoink).

  A .mcpb file is a ZIP archive with manifest.json at its root. If the
  official `mcpb` CLI (npm i -g @anthropic-ai/mcpb) is on PATH this script
  uses `mcpb pack`; otherwise it falls back to Compress-Archive and renames
  the result to .mcpb (byte-identical container).

.NOTES
  Spec: github.com/modelcontextprotocol/mcpb  (manifest_version 0.4)
  Working stdio command (server.py::_mcp_stdio_command):
    <install>\python\python.exe  <install>\uoink_mcp.py
#>
[CmdletBinding()]
param(
  [string]$OutDir
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$SrcDir    = Join-Path $RepoRoot ".mcpb"
$Manifest  = Join-Path $SrcDir "manifest.json"

if (-not (Test-Path $Manifest)) { throw "manifest.json not found at $Manifest" }

# --- Validate manifest is valid JSON and internally consistent -------------
$json = Get-Content $Manifest -Raw
try { $m = $json | ConvertFrom-Json } catch { throw "manifest.json is not valid JSON: $_" }

$version = $m.version
if (-not $version) { throw "manifest.version is missing" }

# M-2: derive the bundle version from the product VERSION at build time so the
# .mcpb can never drift from the release the way build.ps1 does for the iss.
# The committed manifest.version is a fallback; the test_release_version parity
# test keeps them equal, but the build authoritatively stamps VERSION here.
$VersionFile = Join-Path $RepoRoot "VERSION"
if (Test-Path $VersionFile) {
  $repoVersion = (Get-Content $VersionFile -Raw).Trim()
  if ($repoVersion -and $repoVersion -ne $version) {
    Write-Warning "manifest.version ($version) != VERSION ($repoVersion); stamping the bundle with VERSION."
    $version = $repoVersion
  }
} else {
  Write-Warning "VERSION file not found; using committed manifest.version ($version)."
}

$cmd  = $m.server.mcp_config.command
$args = $m.server.mcp_config.args -join " "
Write-Host "Bundle version : $version"
Write-Host "Entry command  : $cmd $args"

# The entry command MUST resolve to the working stdio command:
#   <uoink_dir>/python/python.exe  <uoink_dir>/uoink_mcp.py
if ($cmd -notmatch "python/python\.exe$") {
  throw "manifest server.mcp_config.command does not point at python.exe: $cmd"
}
if ($args -notmatch "uoink_mcp\.py") {
  throw "manifest server.mcp_config.args does not invoke uoink_mcp.py: $args"
}
if ($m.server.entry_point -ne "uoink_mcp.py") {
  throw "manifest server.entry_point must be uoink_mcp.py (got: $($m.server.entry_point))"
}
Write-Host "Manifest validated OK (valid JSON; entry command matches working stdio command)." -ForegroundColor Green

# --- Stage the bundle ------------------------------------------------------
$BuildDir = Join-Path $RepoRoot "build\mcpb\uoink"
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

# Stamp the derived version into the staged manifest (string replace keeps the
# original formatting; only the top-level "version" value changes).
$stagedJson = $json -replace '"version"\s*:\s*"[^"]*"', ('"version": "' + $version + '"')
Set-Content -Path (Join-Path $BuildDir "manifest.json") -Value $stagedJson -Encoding utf8

# Reference copies so entry_point resolves inside the bundle. The RUNTIME uses
# the installed copy (via user_config.uoink_dir) because that is where the
# dependencies and sibling modules live.
foreach ($f in @("uoink_mcp.py", "uoink_mcp_tools.py")) {
  $p = Join-Path $RepoRoot $f
  if (Test-Path $p) { Copy-Item $p (Join-Path $BuildDir $f) -Force }
}

# Bundle README
$bundleReadme = Join-Path $SrcDir "README.md"
if (Test-Path $bundleReadme) { Copy-Item $bundleReadme (Join-Path $BuildDir "README.md") -Force }

# Icon (single PNG referenced by manifest.icon)
$icon = Join-Path $RepoRoot "assets\logo-mark-256.png"
if (Test-Path $icon) { Copy-Item $icon (Join-Path $BuildDir "icon.png") -Force }
else { Write-Warning "icon assets\logo-mark-256.png not found; bundle will ship without icon.png" }

# --- Pack ------------------------------------------------------------------
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$OutFile = Join-Path $OutDir "uoink-$version.mcpb"
if (Test-Path $OutFile) { Remove-Item $OutFile -Force }

$mcpbCli = Get-Command mcpb -ErrorAction SilentlyContinue
if ($mcpbCli) {
  Write-Host "Packing with official mcpb CLI..."
  & mcpb pack $BuildDir $OutFile
} else {
  Write-Host "mcpb CLI not found; packing with Compress-Archive (ZIP -> .mcpb)..."
  $zip = "$OutFile.zip"
  if (Test-Path $zip) { Remove-Item $zip -Force }
  Compress-Archive -Path (Join-Path $BuildDir "*") -DestinationPath $zip -Force
  Move-Item $zip $OutFile -Force
}

if (-not (Test-Path $OutFile)) { throw "Failed to produce $OutFile" }
$size = [math]::Round((Get-Item $OutFile).Length / 1KB, 1)
Write-Host ""
Write-Host "Built $OutFile ($size KB)" -ForegroundColor Green
Write-Host "Install: double-click the .mcpb, or drag it into Claude Desktop > Settings > Extensions."
