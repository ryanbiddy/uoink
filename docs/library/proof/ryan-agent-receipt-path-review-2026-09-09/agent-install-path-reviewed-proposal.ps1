param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$PackageHash,
    [Parameter(Mandatory=$true)][string]$ReceiptRoot,
    [Parameter(Mandatory=$true)][ValidateSet('install','same-version-reinstall')][string]$Stage
)
$ErrorActionPreference = 'Stop'
$taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskScratch = [IO.Path]::GetFullPath('E:\AI\projects\uoink\installation-receipts').TrimEnd('\') + '\'
$taskRoot = [IO.Path]::GetFullPath($ReceiptRoot).TrimEnd('\')
if (-not $taskRoot.StartsWith($taskScratch,[StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt must be inside the dedicated installation-receipts directory outside the checkout.' }
if (-not (Test-Path -LiteralPath $taskRoot -PathType Container)) { throw 'Prepare the receipt fixtures first.' }
$taskPrincipal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if ($taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'This receipt must not run elevated.' }
$taskApp = Join-Path $taskRoot 'app'
$taskProfile = Join-Path $taskRoot 'c22\profiles\empty'
$taskPackage = [IO.Path]::GetFullPath($Package)
$taskPort = 18081
$taskGroup = 'Uoink Living Library Receipt ' + (Split-Path -Leaf $taskRoot)
if ($taskGroup.IndexOfAny([char[]]'"/\') -ge 0) { throw 'Invalid shortcut group.' }

function Assert-PlainPath([string]$taskPath) {
    $taskResolved = [IO.Path]::GetFullPath($taskPath)
    if ($taskResolved.StartsWith('\\') -or $taskResolved.Contains('"')) { throw 'Device, network or quoted paths are forbidden.' }
    $taskAncestor = $taskResolved
    while ($taskAncestor) {
        if (Test-Path -LiteralPath $taskAncestor) {
            if ((Get-Item -LiteralPath $taskAncestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Reparse path: ' + $taskAncestor) }
        }
        $taskAncestor = Split-Path -Parent $taskAncestor
    }
}
foreach ($taskPath in @($taskRoot,$taskApp,$taskProfile,$taskPackage)) { Assert-PlainPath $taskPath }
if (-not (Test-Path -LiteralPath $taskProfile -PathType Container)) { throw 'Prepared empty profile is missing.' }
if ((Get-FileHash -LiteralPath $taskPackage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PackageHash) { throw 'Sealed package hash differs.' }
$taskRecord = Join-Path $taskRoot ($Stage + '.json')
if (Test-Path -LiteralPath $taskRecord) { throw 'Preserve the existing stage; a retry requires a new reviewed receipt.' }
$taskIsoId = '{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1'
$taskOrdinaryId = '{1CCDA47D-2347-43D1-99F4-BD6E7C231288}_is1'
$taskUninstallBase = 'Software\Microsoft\Windows\CurrentVersion\Uninstall'
$taskIsoKey = 'HKCU:\' + $taskUninstallBase + '\' + $taskIsoId
$taskGroupPath = Join-Path $env:APPDATA ('Microsoft\Windows\Start Menu\Programs\' + $taskGroup)
Assert-PlainPath $taskGroupPath

function Write-Receipt([string]$taskPath,$taskValue) {
    if (Test-Path -LiteralPath $taskPath) { throw ('Receipt already exists: ' + $taskPath) }
    [IO.File]::WriteAllText($taskPath,($taskValue | ConvertTo-Json -Depth 15),[Text.UTF8Encoding]::new($false))
}
function Get-TextHash([string]$taskText) {
    $taskSha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($taskSha.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskText)))).Replace('-','').ToLowerInvariant() }
    finally { $taskSha.Dispose() }
}
function Get-Effects {
    $taskRegistry = [ordered]@{}
    foreach ($taskHive in 'HKCU:','HKLM:') {
        foreach ($taskView in $taskUninstallBase,'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall') {
            foreach ($taskId in $taskOrdinaryId,$taskIsoId) {
                $taskKey = Join-Path $taskHive ($taskView + '\' + $taskId)
                $taskValues = [ordered]@{}
                $taskPresent = Test-Path -LiteralPath $taskKey
                if ($taskPresent) {
                    foreach ($taskProperty in (Get-ItemProperty -LiteralPath $taskKey).PSObject.Properties | Sort-Object Name) {
                        if ($taskProperty.Name -notlike 'PS*') { $taskValues[$taskProperty.Name] = $taskProperty.Value }
                    }
                }
                $taskRegistry[$taskKey] = [ordered]@{ present=$taskPresent; sha256=(Get-TextHash ($taskValues | ConvertTo-Json -Compress -Depth 8)) }
            }
        }
    }
    $taskRunValue = Get-ItemPropertyValue -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name Uoink -ErrorAction SilentlyContinue
    $taskLinks = [ordered]@{}
    foreach ($taskFolder in (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Uoink'),
                            (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'),
                            [Environment]::GetFolderPath('Desktop')) {
        if (-not (Test-Path -LiteralPath $taskFolder)) { continue }
        Assert-PlainPath $taskFolder
        foreach ($taskLink in Get-ChildItem -LiteralPath $taskFolder -File -Filter '*.lnk' | Sort-Object FullName) {
            if ($taskFolder -notlike '*\Uoink' -and $taskLink.Name -notlike '*Uoink*') { continue }
            Assert-PlainPath $taskLink.FullName
            $taskLinks[$taskLink.FullName] = (Get-FileHash -LiteralPath $taskLink.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return [ordered]@{ registry=$taskRegistry; ordinary_autorun_hash=(Get-TextHash ([string]$taskRunValue)); ordinary_shortcut_hashes=$taskLinks }
}
$taskBefore = Get-Effects
if ($Stage -eq 'install') {
    if ((Test-Path -LiteralPath $taskApp) -or (Test-Path -LiteralPath $taskGroupPath)) { throw 'Fresh app and shortcut group required.' }
    foreach ($taskKey in $taskBefore.registry.Keys) {
        if ($taskKey.EndsWith($taskIsoId) -and $taskBefore.registry[$taskKey].present) { throw 'An isolated install already exists; do not replace it.' }
    }
} else {
    $taskPrior = Get-Content -LiteralPath (Join-Path $taskRoot 'install.json') -Raw | ConvertFrom-Json
    if ($taskPrior.exit -ne 0 -or $taskPrior.package_sha256 -ne $PackageHash) { throw 'A successful install of these exact bytes is required.' }
    $taskMarker = Get-Content -LiteralPath (Join-Path $taskApp 'isolated-install.json') -Raw | ConvertFrom-Json
    if ($taskMarker.mode -ne 'isolated' -or $taskMarker.app_dir -ine $taskApp -or $taskMarker.profile -ine $taskProfile -or $taskMarker.port -ne $taskPort) { throw 'Installed ownership marker differs.' }
}
Write-Receipt (Join-Path $taskRoot ($Stage + '.before.json')) $taskBefore
foreach ($taskKey in 'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY') {
    Remove-Item -LiteralPath ('Env:' + $taskKey) -ErrorAction SilentlyContinue
}
$taskTemp = Join-Path $taskRoot ($Stage + '-temp')
if (Test-Path -LiteralPath $taskTemp) { throw 'Fresh stage temp directory required.' }
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$env:TEMP=$taskTemp; $env:TMP=$taskTemp
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'; $env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
$taskLog = Join-Path $taskRoot ($Stage + '.inno.log')
$taskArgs = @('/VERYSILENT','/NORESTART','/SUPPRESSMSGBOXES',('/DIR="'+$taskApp+'"'),
    '/ISOLATED=1',('/PROFILE="'+$taskProfile+'"'),('/PORT='+$taskPort),
    '/NOCLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS','/TASKS=""',('/GROUP="'+$taskGroup+'"'),('/LOG="'+$taskLog+'"'))
$taskIdentity=[Security.Principal.WindowsIdentity]::GetCurrent()
$taskObservation=[ordered]@{ stage=$Stage; executable=$taskPackage; arguments=$taskArgs; package_sha256=$PackageHash;
    user=$taskIdentity.Name; sid=$taskIdentity.User.Value; windows_profile=$env:USERPROFILE;
    isolation='same Windows account; isolated app/data/credential namespace'; throwaway_account=$false;
    utc_start=[DateTimeOffset]::UtcNow.ToString('o'); exit=$null; process_id=$null }
try {
    $taskProcess=Start-Process -FilePath $taskPackage -ArgumentList $taskArgs -PassThru -WindowStyle Hidden
    $taskObservation.process_id=$taskProcess.Id
    $taskProcess.WaitForExit()
    $taskProcess.Refresh()
    $taskObservation.exit=$taskProcess.ExitCode
} finally {
    $taskObservation.utc_end=[DateTimeOffset]::UtcNow.ToString('o')
    Write-Receipt $taskRecord $taskObservation
}
$taskAfter=Get-Effects
Write-Receipt (Join-Path $taskRoot ($Stage + '.after.json')) $taskAfter
if ($null -eq $taskObservation.exit -or $taskObservation.exit -ne 0) { throw 'Installer did not return exit zero; preserve all evidence.' }
$taskVerifyLog=Join-Path $taskTemp 'uoink-install-verify.log'
if (-not (Test-Path -LiteralPath $taskVerifyLog -PathType Leaf)) { throw 'Files-only verification log is missing.' }
$taskVerifyText=Get-Content -LiteralPath $taskVerifyLog -Raw
if ($taskVerifyText -notmatch 'files-only install verification OK; live health probe skipped' -or $taskVerifyText -match 'MISSING bundled file|VERSION mismatch|could not read VERSION|verification FAILED') { throw 'Files-only verification did not succeed.' }
foreach ($taskKey in $taskBefore.registry.Keys) {
    if ($taskKey.EndsWith($taskOrdinaryId) -and (($taskBefore.registry[$taskKey] | ConvertTo-Json -Compress) -ne ($taskAfter.registry[$taskKey] | ConvertTo-Json -Compress))) { throw 'Ordinary uninstall registry changed.' }
    if ($taskKey.StartsWith('HKLM:') -and (($taskBefore.registry[$taskKey] | ConvertTo-Json -Compress) -ne ($taskAfter.registry[$taskKey] | ConvertTo-Json -Compress))) { throw 'Machine-wide uninstall registry changed.' }
}
if ($taskBefore.ordinary_autorun_hash -ne $taskAfter.ordinary_autorun_hash -or ($taskBefore.ordinary_shortcut_hashes | ConvertTo-Json -Compress) -ne ($taskAfter.ordinary_shortcut_hashes | ConvertTo-Json -Compress)) { throw 'Ordinary autorun/shortcuts changed.' }
$taskInstalledMarker=Get-Content -LiteralPath (Join-Path $taskApp 'isolated-install.json') -Raw | ConvertFrom-Json
if ($taskInstalledMarker.mode -ne 'isolated' -or $taskInstalledMarker.app_dir -ine $taskApp -or $taskInstalledMarker.profile -ine $taskProfile -or $taskInstalledMarker.port -ne $taskPort) { throw 'New installed marker differs.' }
$taskInstalledLocation=Get-ItemPropertyValue -LiteralPath $taskIsoKey -Name InstallLocation
if ($taskInstalledLocation.TrimEnd('\') -ine $taskApp) { throw 'Isolated uninstall location differs.' }
if (-not (Test-Path -LiteralPath $taskGroupPath -PathType Container)) { throw 'Isolated shortcut group is missing.' }
Assert-PlainPath $taskGroupPath
$taskShell=New-Object -ComObject WScript.Shell
$taskExpectedLinks=@('Uoink Isolated.lnk','Stop Uoink Isolated.lnk','Open Uoink Isolated folder.lnk','Uninstall Uoink Isolated.lnk')
$taskActualLinks=@(Get-ChildItem -LiteralPath $taskGroupPath -File -Filter '*.lnk')
if ($taskActualLinks.Count -ne 4) { throw 'Unexpected isolated shortcut count.' }
$taskLinkEvidence=@()
foreach ($taskLinkName in $taskExpectedLinks) {
    $taskLinkPath=Join-Path $taskGroupPath $taskLinkName
    if (-not (Test-Path -LiteralPath $taskLinkPath -PathType Leaf)) { throw ('Missing shortcut: ' + $taskLinkName) }
    Assert-PlainPath $taskLinkPath
    $taskLink=$taskShell.CreateShortcut($taskLinkPath)
    $taskTarget=[IO.Path]::GetFullPath($taskLink.TargetPath)
    $taskArguments=[string]$taskLink.Arguments
    $taskLinkEvidence += [ordered]@{path=$taskLinkPath;target=$taskTarget;arguments=$taskArguments;working_directory=$taskLink.WorkingDirectory;sha256=(Get-FileHash -LiteralPath $taskLinkPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    switch ($taskLinkName) {
        'Uoink Isolated.lnk' {
            if ($taskTarget -ine (Join-Path $taskApp 'python\pythonw.exe') -or $taskArguments -ne ('"'+(Join-Path $taskApp 'server.py')+'" --isolated-profile "'+$taskProfile+'" --isolated-port '+$taskPort+' --show-dashboard')) { throw 'Isolated start shortcut differs.' }
        }
        'Stop Uoink Isolated.lnk' {
            if ($taskTarget -ine (Join-Path $taskApp 'python\python.exe') -or $taskArguments -ne ('"'+(Join-Path $taskApp 'uoink_install_isolation.py')+'" --isolated-stop --isolated-from-install-dir "'+$taskApp+'"')) { throw 'Isolated stop shortcut differs.' }
        }
        'Open Uoink Isolated folder.lnk' { if ($taskTarget -ine $taskApp -or $taskArguments) { throw 'Isolated folder shortcut differs.' } }
        'Uninstall Uoink Isolated.lnk' { if ((Split-Path -Parent $taskTarget) -ine $taskApp -or (Split-Path -Leaf $taskTarget) -notmatch '^unins\d+\.exe$' -or $taskArguments) { throw 'Isolated uninstall shortcut differs.' } }
    }
}
Write-Receipt (Join-Path $taskRoot ($Stage + '.shortcuts.json')) $taskLinkEvidence
Write-Output ($Stage + ' recorded with exit zero; installed helper/browser observations are still required.')
