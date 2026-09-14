$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOut=Join-Path $taskRoot '_scratch/controller-resume-publication-brief01'
$taskDefinitions=@(
 @{path='_scratch/real-startup-authority-repair01/inputs/durable_lifecycle.py';sha256='3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3';ranges=@(@{first=462;last=559});role='factory/kernel origin'},
 @{path='_scratch/controller-worker-stage-repair01/asr_loading_adapter.py';sha256='2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee';ranges=@(@{first=1;last=45},@{first=65;last=145},@{first=200;last=228},@{first=251;last=642});role='startup/stage derivative origin'},
 @{path='_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py';sha256='e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98';ranges=@(@{first=345;last=399});role='unchanged reservation callback contract'},
 @{path='_scratch/real-startup-authority-repair01/startup_authority_fixture.py';sha256='fe82ffe16117a9a74b3194e607c86c69b4411076337965ccb5d78c8a9cec897a';ranges=@(@{first=1;last=170});role='unchanged isolated fixture origin'},
 @{path='_scratch/real-startup-authority-repair01/FIXTURE-LOADER-CONTRACT.md';sha256='8e59a89853faeb21c4ce8694fe7613856e44baed3feabe5c891174044b9952c4';ranges='full';role='unchanged existing isolated import contract'},
 @{path='_scratch/windows-interrupted-owner-native-proposal02/generated_worker_flow.py';sha256='1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238';ranges=@(@{first=62;last=174});role='unchanged generated sentinel gate'},
 @{path='_scratch/windows-interrupted-owner-native-proposal02/generated_adapter_flow.py';sha256='24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961';ranges=@(@{first=140;last=285},@{first=764;last=789});role='unchanged generated adapter gate; initial excerpt is not needed for new implementation'},
 @{path='_scratch/admitted-controller-connection-plan01/PLAN.md';sha256='20574f4516c1443347b8eb2f948379628a432b7ae51ba04cb437a7dea64ffad5';ranges='full';role='frozen parent plan, preserved'}
)
$taskRows=@()
foreach($taskDefinition in $taskDefinitions){
 $taskPath=Join-Path $taskRoot $taskDefinition.path
 $taskBytes=[IO.File]::ReadAllBytes($taskPath)
 $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
 if($taskHash -cne $taskDefinition.sha256){throw ('source pin mismatch: '+$taskDefinition.path)}
 $taskRows+= [ordered]@{path=$taskDefinition.path;bytes=$taskBytes.Length;sha256=$taskHash;role=$taskDefinition.role;viewed_ranges=$taskDefinition.ranges}
}
foreach($taskRow in $taskRows){
 $taskBytes=[IO.File]::ReadAllBytes((Join-Path $taskRoot $taskRow.path))
 $taskAfter=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
 if($taskAfter -cne $taskRow.sha256 -or $taskBytes.Length -ne $taskRow.bytes){throw 'source changed during passive binding'}
}
$taskMap=[ordered]@{schema='fixed-source-bindings.v1';root=$taskRoot;scope='source/document preparation only; not runnable closure or authority';inputs=$taskRows;source_hashes_unchanged=$true;candidate_executed=$false}
$taskJson=($taskMap | ConvertTo-Json -Depth 12)+"`r`n"
$taskMapPath=Join-Path $taskOut 'SOURCE-BINDINGS.json'
if(Test-Path -LiteralPath $taskMapPath){throw 'fresh map required'}
[IO.File]::WriteAllText($taskMapPath,$taskJson,[Text.UTF8Encoding]::new($false))
$taskBriefPath=Join-Path $taskOut 'BRIEF.md'
$taskPins=@()
foreach($taskName in @('BRIEF.md','SOURCE-BINDINGS.json','bind_sources.ps1')){
 $taskBytes=[IO.File]::ReadAllBytes((Join-Path $taskOut $taskName))
 $taskPins += [ordered]@{name=$taskName;bytes=$taskBytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()}
}
[ordered]@{source_count=$taskRows.Count;source_bytes=($taskRows|Measure-Object bytes -Sum).Sum;all_expected_pins_match=$true;all_sources_unchanged=$true;candidate_executed=$false;outputs=$taskPins} | ConvertTo-Json -Depth 6

