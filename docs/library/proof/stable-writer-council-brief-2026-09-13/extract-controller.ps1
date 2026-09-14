$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSourceRelative='docs/library/proof/windows-writer-exclusion-native-2026-09-13/run04/controller-result.json'
$taskSourcePath=Join-Path $taskRepo $taskSourceRelative
$taskExpectedSha='3e74a30295288c4892f6545fe71dc23516e1fcd5198653196692f0e2f47651f3'
$taskExpectedBytes=309037
$taskOutput=Join-Path $PSScriptRoot 'controller-selected-fields.json'
if(Test-Path -LiteralPath $taskOutput){throw 'Fresh passive extraction required'}
$taskRaw=[IO.File]::ReadAllBytes($taskSourcePath)
$taskSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskRaw)).ToLowerInvariant()
if($taskSha -cne $taskExpectedSha -or $taskRaw.Length -ne $taskExpectedBytes){throw 'Exact sealed receipt required'}
$taskOriginal=[Text.UTF8Encoding]::new($false,$true).GetString($taskRaw)|ConvertFrom-Json
if($taskOriginal.native_api_calls -isnot [array] -or $taskOriginal.native_api_calls.Count -ne 8230){throw 'Expected omitted array shape/count'}
$taskProjection=[ordered]@{}
foreach($taskProperty in $taskOriginal.PSObject.Properties){
  if($taskProperty.Name -cne 'native_api_calls'){$taskProjection[$taskProperty.Name]=$taskProperty.Value}
}
$taskEnvelope=[ordered]@{
  schema='uoink.council.controller-receipt-passive-extract.v1'
  source_path=$taskSourceRelative
  source_bytes=$taskExpectedBytes
  source_sha256=$taskExpectedSha
  source_proof_commit='f630264114811a6d508f4c58c7e0d936b8e0380b'
  source_proof_manifest_sha256='393c1cc60616933e69baced60630c13867bdc8bb12f71c295b12d237b143ee57'
  transformation='Preserve all parsed JSON fields except the one top-level native_api_calls array. No source input or raw receipt is changed.'
  omitted=[ordered]@{json_pointer='/native_api_calls';array_items=$taskOriginal.native_api_calls.Count;full_array_read_by_council=$false;scope='The count is a passive extraction fact, not independent review of the individual call sequence.'}
  receipt_fields=$taskProjection
}
$taskText=($taskEnvelope|ConvertTo-Json -Depth 60)+[Environment]::NewLine
$taskRoundTrip=$taskText|ConvertFrom-Json
foreach($taskProperty in $taskOriginal.PSObject.Properties){
  if($taskProperty.Name -ceq 'native_api_calls'){continue}
  $taskBefore=ConvertTo-Json -InputObject $taskProperty.Value -Depth 60 -Compress
  $taskAfter=ConvertTo-Json -InputObject $taskRoundTrip.receipt_fields.($taskProperty.Name) -Depth 60 -Compress
  if($taskBefore -cne $taskAfter){throw 'Selected field roundtrip mismatch'}
}
if(@($taskRoundTrip.receipt_fields.PSObject.Properties).Count -ne @($taskOriginal.PSObject.Properties).Count-1){throw 'Field count mismatch'}
if([Text.Encoding]::UTF8.GetByteCount($taskText) -gt 65536){throw 'Bounded compact text required'}
if((Get-FileHash -LiteralPath $taskSourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskExpectedSha){throw 'Source changed'}
[IO.File]::WriteAllText($taskOutput,$taskText,[Text.UTF8Encoding]::new($false))
[ordered]@{path=$taskOutput;bytes=[Text.Encoding]::UTF8.GetByteCount($taskText);lines=$taskText.Split([char]10).Count;sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant();preserved_fields=@($taskProjection.Keys).Count;omitted_arrays=1;omitted_array_items=8230;original_unchanged=$true;candidate_execution=$false;dispatch=$false}|ConvertTo-Json -Depth 3
