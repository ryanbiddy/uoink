# run-build.ps1
# Orchestrator for the Uoink v1 weekend build.

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
if (-not $projectRoot) { $projectRoot = (Get-Location).Path }

$promptsDir = Join-Path $projectRoot "build-prompts"

if (-not (Test-Path $promptsDir)) {
    Write-Host ""
    Write-Host "ERROR: build-prompts folder not found at $promptsDir" -ForegroundColor Red
    exit 1
}

try {
    $null = Get-Command claude -ErrorAction Stop
} catch {
    Write-Host ""
    Write-Host "ERROR: 'claude' command not found on PATH." -ForegroundColor Red
    Write-Host "Install Claude Code or restart this terminal so PATH refreshes." -ForegroundColor Red
    exit 1
}

$prompts = @(
    @{ Number = 1; File = "prompt-1-rebrand.md";       Name = "Project rebrand and repo setup" }
    @{ Number = 2; File = "prompt-2-corpus.md";        Name = "Metadata enrichment + corpus rewrite" }
    @{ Number = 3; File = "prompt-3-destinations.md";  Name = "Destinations + prompt library" }
    @{ Number = 4; File = "prompt-4-polish.md";        Name = "Polish, error states, copy" }
    @{ Number = 5; File = "prompt-5-store-assets.md";  Name = "Web Store assets prep" }
    @{ Number = 6; File = "prompt-6-commit.md";        Name = "Final smoke test + commit" }
)

$smokeTests = @{
    1 = "Refresh extension. Click button on a YouTube video. Confirm Desktop\Uoink\ is created. Confirm git push succeeded."
    2 = "Restart server. Reload extension. Uoink a video with comments. Open the corpus .md and verify ALL sections (metadata, thumbnail, description, tags, transcript, screenshots, comments, channel context). Verify clipboard has the corpus content."
    3 = "Reload extension. Uoink a video. Confirm Send to Claude AND Send to ChatGPT both work. Click a prompt button, confirm clipboard gets the prompt. Edit prompts.json, reopen popup, confirm new prompt shows."
    4 = "Reload extension. Uoink works. Stop server, try to uoink, confirm clean error message. Restart server, confirm popup health indicator updates."
    5 = "Check extension/icons/ has all 4 sizes. Check assets/store/ has promo placeholders. Check docs/store-listing.md and docs/screenshot-list.md exist. Reload extension, confirm new icon shows."
    6 = "Uoink a real video, confirm full v1 spec is met. Verify git push succeeded. Confirm docs/progress.md exists."
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Uoink v1 weekend build orchestrator"          -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project folder: $projectRoot"
Write-Host "Prompts folder: $promptsDir"
Write-Host ""
Write-Host "6 prompts, smoke test pause between each."
Write-Host "Press Enter to start, Ctrl+C to cancel."
Read-Host

$startTime = Get-Date

foreach ($p in $prompts) {
    $promptPath = Join-Path $promptsDir $p.File

    if (-not (Test-Path $promptPath)) {
        Write-Host ""
        Write-Host "ERROR: prompt file not found: $promptPath" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host ("  PROMPT {0} - {1}" -f $p.Number, $p.Name)    -ForegroundColor Cyan
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Prompt file: $promptPath"
    Write-Host ""
    Write-Host "About to launch Claude Code with this prompt piped in."
    Write-Host "Watch its output. Answer any clarifying questions."
    Write-Host ""
    Write-Host ("Press Enter to launch Claude Code with prompt {0}..." -f $p.Number)
    Read-Host

    Get-Content $promptPath -Raw | claude

    Write-Host ""
    Write-Host "==============================================" -ForegroundColor Yellow
    Write-Host ("  PROMPT {0} DONE - SMOKE TEST" -f $p.Number)  -ForegroundColor Yellow
    Write-Host "==============================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host $smokeTests[$p.Number]
    Write-Host ""
    Write-Host "Type 'continue' to advance, 'retry' to re-run this prompt, or 'stop' to exit."
    Write-Host ""

    do {
        $choice = Read-Host "Your choice"
        $choice = $choice.Trim().ToLower()
    } while ($choice -notin @("continue", "retry", "stop"))

    if ($choice -eq "stop") {
        Write-Host ""
        Write-Host ("Stopping at prompt {0}." -f $p.Number) -ForegroundColor Yellow
        exit 0
    }

    if ($choice -eq "retry") {
        Write-Host ""
        Write-Host ("Re-running prompt {0}..." -f $p.Number) -ForegroundColor Yellow
        Get-Content $promptPath -Raw | claude
        Write-Host ""
        Write-Host "Retry done. Continuing." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  ALL PROMPTS COMPLETE"                         -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""

$elapsed = (Get-Date) - $startTime
Write-Host ("Total elapsed time: {0:hh\:mm\:ss}" -f $elapsed)
Write-Host ""

$parentFolder = Split-Path $projectRoot -Parent
$currentFolderName = Split-Path $projectRoot -Leaf
$newFolderName = "Uoink"
$newPath = Join-Path $parentFolder $newFolderName

if ($currentFolderName -eq $newFolderName) {
    Write-Host "Folder is already named 'Uoink'. No rename needed." -ForegroundColor Green
    Write-Host ""
    Write-Host "v1 weekend build complete." -ForegroundColor Green
    exit 0
}

Write-Host "Ready to rename the parent folder." -ForegroundColor Yellow
Write-Host "  From: $projectRoot"
Write-Host "  To:   $newPath"
Write-Host ""
Write-Host "Before renaming, close ALL of:" -ForegroundColor Yellow
Write-Host "  - Text editors with files from this folder open"
Write-Host "  - The Uoink server (close start_server.bat or kill pythonw.exe)"
Write-Host "  - File Explorer windows showing this folder"
Write-Host ""
Write-Host "The rename will happen in a NEW PowerShell process so this terminal"
Write-Host "can release its lock on the folder."
Write-Host ""
Write-Host "Press Enter to attempt the rename, or Ctrl+C to skip."
Read-Host

$renameCmd = "Start-Sleep -Seconds 3; Set-Location '$parentFolder'; try { Rename-Item -Path '$currentFolderName' -NewName '$newFolderName' -ErrorAction Stop; Write-Host 'Folder renamed to Uoink at $newPath' -ForegroundColor Green } catch { Write-Host 'Rename failed:' -ForegroundColor Red; Write-Host $_.Exception.Message -ForegroundColor Red; Write-Host 'Close any programs using this folder, then run manually: cd ''$parentFolder''; Rename-Item ''$currentFolderName'' ''$newFolderName''' -ForegroundColor Yellow }; Write-Host ''; Write-Host 'Press Enter to close.'; Read-Host"

Start-Process powershell -ArgumentList "-NoProfile", "-Command", $renameCmd

Write-Host ""
Write-Host "A new PowerShell window will rename the folder in 3 seconds." -ForegroundColor Cyan
Write-Host "Close this terminal NOW so the folder lock is released." -ForegroundColor Cyan
Write-Host ""
Write-Host "After the rename, restart your server from:" -ForegroundColor Cyan
Write-Host ("  cd '{0}'" -f $newPath)
Write-Host "  .\start_server.bat"
Write-Host ""