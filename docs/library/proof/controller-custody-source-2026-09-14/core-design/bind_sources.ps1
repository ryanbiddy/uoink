$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOut=Join-Path $taskRoot '_scratch/controller-boundary-custody-design01'
$taskInputs=@(
 @('_scratch/real-startup-authority-repair01/inputs/durable_lifecycle.py','3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3'),
 @('_scratch/controller-worker-stage-repair01/asr_loading_adapter.py','2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee'),
 @('_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py','e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98'),
 @('_scratch/real-startup-authority-repair01/startup_authority_fixture.py','fe82ffe16117a9a74b3194e607c86c69b4411076337965ccb5d78c8a9cec897a'),
 @('_scratch/controller-worker-stage-repair01/worker_stage_fixture.py','3996ca4896ff2fc18308bca1caf14a7f87334309bd62f6bef408eeed87707bc4'),
 @('_scratch/controller-boundary01-root-review/frozen/durable_lifecycle.py','4eeeade5384ca8172c3724a3ee2a6574ca6801e3af3408f177e586c9cd9a4dc3'),
 @('_scratch/controller-boundary01-root-review/frozen/asr_loading_adapter.py','94e522e622b8de3304ef48c97258a91692e70f22c3112dd6afabd6b493438611'),
 @('_scratch/controller-boundary01-factory-peer/VERDICT.md','9f85fdc6d4be5b519b5b6059ca184b2197cc067a9947e5296a147ee449c5c66e'),
 @('docs/library/CONTROLLER-RESUME-PUBLICATION-IMPLEMENTATION-BRIEF-2026-09-14.md','691bc362c8aa2fd1b3e9623a2638dc68617d585a129a8dfee00e41dd0a822d36')
)
$taskRows=@()
[long]$taskTotal=0
foreach($taskInput in $taskInputs){
 $taskPath=Join-Path $taskRoot $taskInput[0]
 $taskBytes=[IO.File]::ReadAllBytes($taskPath)
 $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
 if($taskHash -cne $taskInput[1]){throw ('source pin mismatch: '+$taskInput[0])}
 $taskRows += [ordered]@{path=$taskInput[0];bytes=$taskBytes.Length;sha256=$taskHash}
 $taskTotal += $taskBytes.Length
}
foreach($taskRow in $taskRows){
 if((Get-FileHash -LiteralPath (Join-Path $taskRoot $taskRow.path) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRow.sha256){throw 'source changed'}
}
$taskMap=[ordered]@{scope='source design only; not a runnable closure or authority';root=$taskRoot;inputs=$taskRows;count=$taskRows.Count;bytes=$taskTotal;unchanged=$true;candidate_executed=$false;read_evidence=@('READ-ENTRY-CONTRACTS-ACTUAL.json','../controller-boundary01-factory-peer/READ-BRIEF-INVENTORY-ACTUAL.json','../controller-boundary01-factory-peer/READ-CURRENT-BOUNDARIES-ACTUAL.json','../controller-boundary01-factory-peer/READ-CALLED-CONTRACTS-ACTUAL.json')}
$taskMapPath=Join-Path $taskOut 'SOURCE-BINDINGS.json'
if(Test-Path -LiteralPath $taskMapPath){throw 'fresh map required'}
[IO.File]::WriteAllText($taskMapPath,($taskMap|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
$taskPins=@()
foreach($taskName in @('DESIGN.md','SOURCE-BINDINGS.json','bind_sources.ps1')){
 $taskPath=Join-Path $taskOut $taskName
 $taskPins += [ordered]@{name=$taskName;bytes=(Get-Item -LiteralPath $taskPath).Length;sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{count=$taskRows.Count;bytes=$taskTotal;unchanged=$true;candidate_executed=$false;outputs=$taskPins}|ConvertTo-Json -Depth 6

