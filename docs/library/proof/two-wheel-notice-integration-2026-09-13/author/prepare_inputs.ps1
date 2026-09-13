$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskHere=$PSScriptRoot
$taskOverlay=Join-Path $taskHere 'overlay'
if(Test-Path -LiteralPath $taskOverlay){throw 'Fresh source overlay required'}
$taskAfter=Join-Path $taskRepo '_scratch\two-wheel-notice-integration-proposal01\after'
$taskRows=@()
foreach($taskFile in @(Get-ChildItem -LiteralPath $taskAfter -Recurse -File)){
    $taskRelative=[IO.Path]::GetRelativePath($taskAfter,$taskFile.FullName)
    $taskRows += [ordered]@{source=$taskFile.FullName;relative=$taskRelative}
}
if($taskRows.Count -ne 8){throw 'Expected exact eight-path notice proposal'}
foreach($taskRelative in @('tests\test_runtime_setuptools_notices.py','tests\test_installer_dependency_lock.py','tests\test_c02_reliability_faster_whisper.py','tests\conftest.py','requirements-installer-lock.txt','requirements.txt','uoink_reliability.py','scripts\verify_installer_lock.py','docs\build-installer.md','docs\security.md','_scratch\integrator_verify.py','_scratch\agw_heavy_import_guard.py','_scratch\partition_receipt_plugin.py','_scratch\partition_exit_contract.py')){
    $taskRows += [ordered]@{source=(Join-Path $taskRepo $taskRelative);relative=$taskRelative}
}
$taskRows += [ordered]@{source=(Join-Path $taskHere 'test_notice_integration.py');relative='tests\test_notice_integration.py'}
$taskCopies=@()
foreach($taskRow in $taskRows){
    $taskTarget=Join-Path $taskOverlay $taskRow.relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskTarget) -Force | Out-Null
    Copy-Item -LiteralPath $taskRow.source -Destination $taskTarget -ErrorAction Stop
    $taskSourceHash=(Get-FileHash -LiteralPath $taskRow.source -Algorithm SHA256).Hash.ToLowerInvariant()
    if((Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskSourceHash){throw 'Source overlay copy differs'}
    $taskCopies += [ordered]@{source=$taskRow.source;path='overlay/'+$taskRow.relative.Replace('\','/');bytes=(Get-Item -LiteralPath $taskTarget).Length;sha256=$taskSourceHash}
}
[IO.File]::WriteAllText((Join-Path $taskOverlay 'pytest.ini'),"[pytest]`n",[Text.UTF8Encoding]::new($false))
$taskCopies | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskHere 'COPY-BINDINGS.json') -Encoding utf8
$taskBuild=[IO.File]::ReadAllText((Join-Path $taskOverlay 'build.ps1'),[Text.UTF8Encoding]::new($false,$true))
$taskBlocks=@()
foreach($taskSpec in @(@('generation','# C-02: regenerate THIRD-PARTY-NOTICES.md','# 2d-bis.'),@('staging','# Ship the attribution index and exact supplemental upstream texts.',"Copy-Item (Join-Path `$RepoRoot 'server.py')"))){
    $taskStart=$taskBuild.IndexOf($taskSpec[1],[StringComparison]::Ordinal)
    $taskEnd=$taskBuild.IndexOf($taskSpec[2],$taskStart,[StringComparison]::Ordinal)
    if($taskStart -lt 0 -or $taskEnd -le $taskStart -or $taskBuild.IndexOf($taskSpec[1],$taskStart+1,[StringComparison]::Ordinal) -ge 0){throw 'Block source anchors ambiguous'}
    $taskText=$taskBuild.Substring($taskStart,$taskEnd-$taskStart)
    $taskName=$taskSpec[0]+'.block.ps1'
    [IO.File]::WriteAllText((Join-Path $taskHere $taskName),$taskText,[Text.UTF8Encoding]::new($false))
    $taskBlocks += [ordered]@{name=$taskSpec[0];path=$taskName;start=$taskStart;characters=$taskText.Length;bytes=(Get-Item -LiteralPath (Join-Path $taskHere $taskName)).Length;sha256=(Get-FileHash -LiteralPath (Join-Path $taskHere $taskName) -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{source='overlay/build.ps1';source_sha256=(Get-FileHash -LiteralPath (Join-Path $taskOverlay 'build.ps1')).Hash.ToLowerInvariant();blocks=$taskBlocks;candidate_execution=0} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskHere 'BLOCK-BINDINGS.json') -Encoding utf8
[ordered]@{copied_files=$taskCopies.Count;exact_blocks=$taskBlocks.Count;candidate_execution=0} | ConvertTo-Json
