# Remove only the retained package-06 isolated test application; preserve receipts.
$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\installation-receipts\Agent Install 06'
$taskApp=Join-Path $taskRoot 'app'
$taskProfile=Join-Path $taskRoot 'c22\profiles\empty'
$taskOut=Join-Path $taskRoot 'uninstall-before-package07-2026-09-12'
$taskIsoId='{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1'
$taskOrdinaryId='{1CCDA47D-2347-43D1-99F4-BD6E7C231288}_is1'
$taskUninstallBase='Software\Microsoft\Windows\CurrentVersion\Uninstall'
$taskIsoKey='HKCU:\'+$taskUninstallBase+'\'+$taskIsoId
$taskPrincipal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if($taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Do not run elevated'}
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
function Write-Receipt([string]$taskPath,$taskValue) {
    if (Test-Path -LiteralPath $taskPath) { throw ('Receipt already exists: ' + $taskPath) }
    [IO.File]::WriteAllText($taskPath,($taskValue | ConvertTo-Json -Depth 15),[Text.UTF8Encoding]::new($false))
}
function Get-TextHash([string]$taskText) {
    $taskSha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($taskSha.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskText)))).Replace('-','').ToLowerInvariant() }
    finally { $taskSha.Dispose() }
}
function Test-UntraversedDesktop([string]$Folder,[string]$Desktop,[IO.FileAttributes]$Attributes) {
    return ([IO.Path]::GetFullPath($Folder) -ieq [IO.Path]::GetFullPath($Desktop)) -and [bool]($Attributes -band [IO.FileAttributes]::ReparsePoint)
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
    $taskUntraversed = [ordered]@{}
    foreach ($taskFolder in (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Uoink'),
                            (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'),
                            [Environment]::GetFolderPath('Desktop')) {
        if (-not (Test-Path -LiteralPath $taskFolder)) { continue }
        $taskFolderEntry = Get-Item -LiteralPath $taskFolder -Force
        if (Test-UntraversedDesktop $taskFolder ([Environment]::GetFolderPath('Desktop')) $taskFolderEntry.Attributes) {
            $taskDescriptor = [ordered]@{ path=$taskFolder; attributes=[string]$taskFolderEntry.Attributes; link_type=[string]$taskFolderEntry.LinkType; target=@($taskFolderEntry.Target); created_utc=$taskFolderEntry.CreationTimeUtc.ToString('o'); contents_observed=$false }
            $taskUntraversed[$taskFolder] = [ordered]@{ metadata_sha256=(Get-TextHash ($taskDescriptor | ConvertTo-Json -Compress -Depth 5)); contents_observed=$false; reason='Ordinary reparse Desktop not traversed; selected tasks must exclude desktopicon' }
            continue
        }
        Assert-PlainPath $taskFolder
        foreach ($taskLink in Get-ChildItem -LiteralPath $taskFolder -File -Filter '*.lnk' | Sort-Object FullName) {
            if ($taskFolder -notlike '*\Uoink' -and $taskLink.Name -notlike '*Uoink*') { continue }
            Assert-PlainPath $taskLink.FullName
            $taskLinks[$taskLink.FullName] = (Get-FileHash -LiteralPath $taskLink.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return [ordered]@{ registry=$taskRegistry; ordinary_autorun_hash=(Get-TextHash ([string]$taskRunValue)); ordinary_shortcut_hashes=$taskLinks; untraversed_desktop=$taskUntraversed }
}

foreach($taskPath in @($taskRoot,$taskApp,$taskProfile,$taskOut)){Assert-PlainPath $taskPath}
if([IO.Path]::GetFullPath($taskApp) -ine 'E:\AI\projects\uoink\installation-receipts\Agent Install 06\app'){throw 'Unexpected deletion target'}
$taskLinks=@(Get-ChildItem -LiteralPath $taskApp -Recurse -Force -Attributes ReparsePoint)
if($taskLinks.Count){throw 'Reparse entry below isolated app; refuse uninstall'}
if(Test-Path -LiteralPath $taskOut){throw 'Preserve prior uninstall attempt'}
$taskMarker=Get-Content -LiteralPath (Join-Path $taskApp 'isolated-install.json') -Raw | ConvertFrom-Json
if($taskMarker.mode -ne 'isolated' -or $taskMarker.app_dir -ine $taskApp -or $taskMarker.profile -ine $taskProfile -or $taskMarker.port -ne 18081){throw 'Isolated marker mismatch'}
$taskLocation=Get-ItemPropertyValue -LiteralPath $taskIsoKey -Name InstallLocation
if($taskLocation.TrimEnd('\') -ine $taskApp){throw 'Isolated uninstall entry mismatch'}
$taskExpected=@{
 'unins000.exe'='f93db03c7a52c5ad336c086be7f2573f6578e9fb21262b039aa0d2337a30fbe0'
 'unins000.dat'='3b213b96f87003b421802101e19927ca3e152210a07a30f0404137ca3143dbff'
 'isolated-install.json'='5fd9049eb9b08235981b4c18cd9811e51bee3e9218c1ad3dbaf752509628ff76'
}
foreach($taskName in $taskExpected.Keys){if((Get-FileHash -LiteralPath (Join-Path $taskApp $taskName) -Algorithm SHA256).Hash.ToLower() -ne $taskExpected[$taskName]){throw ('Retained installed artifact differs: '+$taskName)}}
New-Item -ItemType Directory -Path $taskOut | Out-Null
$taskBefore=Get-Effects;Write-Receipt (Join-Path $taskOut 'before.json') $taskBefore
$taskTemp=Join-Path $taskOut 'temp';New-Item -ItemType Directory -Path $taskTemp | Out-Null
$env:TEMP=$taskTemp;$env:TMP=$taskTemp
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE='1';$env:HF_HUB_OFFLINE='1';$env:TRANSFORMERS_OFFLINE='1'
$taskArgs=@('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="'+(Join-Path $taskOut 'uninstall.inno.log')+'"'))
$taskRecord=[ordered]@{utc_start=[DateTimeOffset]::UtcNow.ToString('o');app=$taskApp;profile_preserved=$taskProfile;scope='Only package06 isolated test installation; ordinary index and port 5179 prohibited';arguments=$taskArgs;exit=$null;verified_generated_files=$taskExpected}
try{
 $taskProcess=Start-Process -FilePath (Join-Path $taskApp 'unins000.exe') -ArgumentList $taskArgs -WindowStyle Hidden -PassThru
 $taskRecord.process_id=$taskProcess.Id;$taskProcess.WaitForExit();$taskProcess.Refresh();$taskRecord.exit=$taskProcess.ExitCode
}finally{
 $taskRecord.utc_end=[DateTimeOffset]::UtcNow.ToString('o');Write-Receipt (Join-Path $taskOut 'uninstall.json') $taskRecord
}
$taskAfter=Get-Effects;Write-Receipt (Join-Path $taskOut 'after.json') $taskAfter
if($taskRecord.exit -ne 0){throw 'Uninstaller did not exit zero; preserve attempt'}
foreach($taskKey in $taskBefore.registry.Keys){
 if(($taskKey.EndsWith($taskOrdinaryId) -or $taskKey.StartsWith('HKLM:')) -and (($taskBefore.registry[$taskKey]|ConvertTo-Json -Compress) -ne ($taskAfter.registry[$taskKey]|ConvertTo-Json -Compress))){throw 'Ordinary or machine registry changed'}
}
foreach($taskName in @('ordinary_autorun_hash','ordinary_shortcut_hashes','untraversed_desktop')){
 if(($taskBefore[$taskName]|ConvertTo-Json -Compress -Depth 8) -ne ($taskAfter[$taskName]|ConvertTo-Json -Compress -Depth 8)){throw ('Ordinary effects differ: '+$taskName)}
}
if(Test-Path -LiteralPath $taskIsoKey){throw 'Isolated uninstall entry remains'}
if(-not (Test-Path -LiteralPath $taskProfile -PathType Container)){throw 'Retained receipt profile missing'}
Write-Output 'Old isolated test app uninstalled with exit zero; ordinary effects unchanged and receipt profile preserved.'
