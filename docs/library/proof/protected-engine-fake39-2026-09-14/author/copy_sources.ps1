$ErrorActionPreference='Stop'
$taskRoot='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-fake39-author01'
$taskPlan=Get-Content -LiteralPath (Join-Path $taskRoot 'COPY-SOURCE-PLAN.json') -Raw | ConvertFrom-Json
if($taskPlan.target -cne $taskRoot -or $taskPlan.execution_authority -cne $false -or @($taskPlan.files).Count -ne 42){throw 'Fixed source-only plan refused'}
if(Test-Path -LiteralPath (Join-Path $taskRoot 'ROOT-ADMISSION.json')){throw 'Actual admission forbidden during preparation'}
if(Test-Path -LiteralPath (Join-Path $taskRoot 'runs')){throw 'Run tree forbidden during preparation'}
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'before') -ErrorAction Stop | Out-Null
$taskRows=@()
foreach($taskRow in $taskPlan.files){
    $taskTarget=Join-Path $taskRoot $taskRow.name
    if(Test-Path -LiteralPath $taskTarget){throw 'Never overwrite prepared input'}
    $taskBytes=[IO.File]::ReadAllBytes($taskRow.source)
    $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
    if($taskHash -cne $taskRow.sha256){throw 'Frozen source changed'}
    [IO.File]::WriteAllBytes($taskTarget,$taskBytes)
    $taskCopy=[IO.File]::ReadAllBytes($taskTarget)
    $taskAfter=[IO.File]::ReadAllBytes($taskRow.source)
    $taskCopyHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskCopy)).ToLowerInvariant()
    $taskAfterHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskAfter)).ToLowerInvariant()
    if($taskCopyHash -cne $taskHash -or $taskAfterHash -cne $taskHash){throw 'Before/copy/after mismatch'}
    $taskRows += [ordered]@{name=$taskRow.name;source=$taskRow.source;bytes=$taskBytes.Length;sha256=$taskHash;copy_sha256=$taskCopyHash;source_after_sha256=$taskAfterHash;role=$taskRow.role}
}
$taskPayload=[ordered]@{schema='uoink.protected-engine-fake39-source-copy.v1';execution_authority=$false;subject_executed=$false;files=$taskRows}
[IO.File]::WriteAllText((Join-Path $taskRoot 'COPY-BINDINGS.json'),($taskPayload | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$taskRows | ConvertTo-Json -Depth 8

