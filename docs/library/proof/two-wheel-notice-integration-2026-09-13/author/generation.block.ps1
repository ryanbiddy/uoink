# C-02: regenerate THIRD-PARTY-NOTICES.md from the bundle we just built, so
# the shipped notices match the shipped dependency tree exactly. pip-licenses
# reads the embeddable Python's installed metadata. The generator's
# importlib.metadata fallback works without pip-licenses; generation failure
# is fatal so an old index cannot stand in for this build's inventory.
Write-Step 'Generating THIRD-PARTY-NOTICES.md'
$noticePriorNativePreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    & $embedPython -m pip install --no-warn-script-location --no-compile --no-cache-dir `
        --no-build-isolation `
        --constraint $InstallerLock "pip-licenses==5.0.0" 2>$null
    $noticeToolInstallExit = $global:LASTEXITCODE
    if ($noticeToolInstallExit -ne 0) {
        Write-Warning 'pip-licenses unavailable; generator will use importlib.metadata if needed.'
    }
    $noticesPath = Join-Path $RepoRoot 'THIRD-PARTY-NOTICES.md'
    # Stamp the notices from the same source-bound epoch used to normalize
    # installer input mtimes, so regenerating from unchanged source produces an
    # identical file instead of dirtying the tree on every build.
    $priorSourceDateEpoch = $env:SOURCE_DATE_EPOCH
    $noticeGenerationExit = $null
    try {
        $env:SOURCE_DATE_EPOCH = [string][DateTimeOffset]::new(
            (Get-PackageTimestampUtc), [TimeSpan]::Zero).ToUnixTimeSeconds()
        & $embedPython (Join-Path $RepoRoot 'scripts\gen_third_party_notices.py') $noticesPath
        $noticeGenerationExit = $global:LASTEXITCODE
    } finally {
        $env:SOURCE_DATE_EPOCH = $priorSourceDateEpoch
    }
    # pip-licenses is a build-time tool, not a runtime dep -- strip it back out.
    # Remove the tool and its tool-only dependencies. tomli is not required by
    # the runtime graph on Python 3.13; wcwidth arrives only through prettytable.
    & $embedPython -m pip uninstall -y pip-licenses prettytable tomli wcwidth 2>$null
    $noticeCleanupExit = $global:LASTEXITCODE
    if ($noticeGenerationExit -isnot [int] -or $noticeGenerationExit -ne 0) {
        throw "THIRD-PARTY-NOTICES generation failed (exit $noticeGenerationExit); refusing stale attribution"
    }
    if ($noticeCleanupExit -isnot [int] -or $noticeCleanupExit -ne 0) {
        throw "Notice build-tool cleanup failed (exit $noticeCleanupExit)"
    }
} finally {
    $PSNativeCommandUseErrorActionPreference = $noticePriorNativePreference
}

