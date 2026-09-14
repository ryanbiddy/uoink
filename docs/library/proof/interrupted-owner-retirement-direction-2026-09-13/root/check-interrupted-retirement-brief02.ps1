$ErrorActionPreference='Stop'
$taskMapPath='_scratch/interrupted-owned-session-retirement-brief02/INPUTS.json'
if((Get-FileHash -LiteralPath $taskMapPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne '8095884beb5a03eacfff58a1db044689d247a036dd2c630441a3212a33273eb6'){throw 'Map changed'}
if((Get-FileHash -LiteralPath '_scratch/interrupted-owned-session-retirement-brief02/BRIEF.md' -Algorithm SHA256).Hash.ToLowerInvariant() -cne '3ed998a704c668bf85819e2495574982780d20722abb39a9208db74d7c5857c5'){throw 'Brief changed'}
$taskMap=Get-Content -LiteralPath $taskMapPath -Raw | ConvertFrom-Json
if(@($taskMap.inputs).Count -ne 16){throw 'Membership'}
$taskTotal=0
$taskIds=@()
foreach($taskRow in $taskMap.inputs){
 if($taskRow.path -cnotmatch '^docs/library/proof/(runtime-owner-native-cancel-2026-09-13/native-preparation|retired-owner-recovery-qualification-2026-09-13/proposal)/[a-z0-9_]+\.py$' -or $taskRow.id -cin $taskIds){throw 'Fixed source path/id scope'}
 $taskIds+=$taskRow.id
 $taskData=[IO.File]::ReadAllBytes((Join-Path (Get-Location) $taskRow.path))
 if($taskData.Length -ne $taskRow.bytes -or [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskData)).ToLowerInvariant() -cne $taskRow.sha256){throw 'Source binding changed'}
 $taskTotal+=$taskData.Length
 $taskProofRoot=($taskRow.path -split '/')[0..3] -join '/'
 $taskRelative=($taskRow.path -split '/')[4..20] | Where-Object {$null -ne $_}
 $taskRelative=$taskRelative -join '/'
 $taskSeal=Get-Content -LiteralPath ($taskProofRoot+'/SHA256.json') -Raw | ConvertFrom-Json
 $taskMatch=@($taskSeal.files | Where-Object {$_.path -ceq $taskRelative})
 if($taskMatch.Count -ne 1 -or $taskMatch[0].bytes -ne $taskRow.bytes -or $taskMatch[0].sha256 -cne $taskRow.sha256){throw 'Prior sealed member differs'}
 git diff --quiet HEAD -- $taskRow.path
 if($global:LASTEXITCODE -ne 0){throw 'Committed source changed'}
}
if($taskTotal -ne 356810 -or (Test-Path -LiteralPath '_scratch/interrupted-owned-session-retirement-implementation01')){throw 'Input total or fresh output'}
[ordered]@{input_count=16;input_bytes=$taskTotal;input_map_sha256='8095884beb5a03eacfff58a1db044689d247a036dd2c630441a3212a33273eb6';brief_sha256='3ed998a704c668bf85819e2495574982780d20722abb39a9208db74d7c5857c5';selected_prior_seal_members_match=$true;committed_sources_unchanged=$true;implementation_output_absent=$true;candidate_executions=0} | ConvertTo-Json
