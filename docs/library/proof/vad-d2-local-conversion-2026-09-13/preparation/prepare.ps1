$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOriginal=Join-Path $taskRepo '_scratch\vad-d2-dormant-invocation-proposal02'
$taskTarget=Join-Path $taskRepo '_scratch\vad-d2-activated-invocation01'
$taskOutputRoot=Join-Path $taskRepo '_scratch\vad-fixed-converter-approved-output'
$taskUtf8=[Text.UTF8Encoding]::new($false,$true)
function HashBytes([byte[]]$Bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()}
function WriteNew([string]$Path,[byte[]]$Bytes){
  $taskStream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$taskStream.Write($Bytes,0,$Bytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
}
function JsonBytes($Object){,$taskUtf8.GetBytes((ConvertTo-Json -InputObject $Object -Depth 30)+"`n")}
if((Test-Path -LiteralPath $taskTarget) -or (Test-Path -LiteralPath $taskOutputRoot)){throw 'Fresh invocation and output roots required'}
$taskAdmissionTemplate=Get-Content -LiteralPath (Join-Path $taskOriginal 'ROOT-ADMISSION.TEMPLATE.json') -Raw|ConvertFrom-Json
$taskRequired=@('d2_child.py','zip_bounds.py','fixed_converter.py','d2_adapter.py','fixed-plan.json','D1-RESULT.json','known-inventory.json','D2-PROFILE.json','INPUTS.json','launch_d2.py','run-root.ps1')
if(@($taskAdmissionTemplate.source_hashes.PSObject.Properties).Count -ne 11){throw 'Exact original member count required'}
$taskOriginalBytes=[ordered]@{}
foreach($taskName in $taskRequired){
  $taskBytes=[IO.File]::ReadAllBytes((Join-Path $taskOriginal $taskName))
  if($taskBytes.Length -gt 65536 -or (HashBytes $taskBytes) -cne $taskAdmissionTemplate.source_hashes.$taskName){throw "Original binding failed: $taskName"}
  $taskOriginalBytes[$taskName]=$taskBytes
}
$taskNote=[ordered]@{
  schema='uoink.owner-approval.transcription.v1'
  source='User question reply in the active Codex conversation'
  questionItemId='["request_user_input_async","call_xhVUEOWXtRN8FbbcEXN1oopl",0]'
  question='May I perform the reviewed D2 local conversion at commit 017b559? It reads the existing checkpoint once and writes one new Safetensors file, without pickle evaluation, model execution or fetching. Approval accepts uniform little-endian binary32 storage interpretation, 54 dense tensor ranges with legacy metadata omitted, and local-only conversion while the model notice remains unresolved. D1 sampled two buffers; it did not validate every storage. Both 23-case adapter checks pass, but actual conversion is untested. Your D1-only approval and RELEASE-OWNER-DECISIONS-2026-09-12.md reserve this separate decision for you. I recommend approving this scope; Windows repairs continue meanwhile.'
  answer='Approve D2 local conversion only'
  source_message_id=$null
  approved_utc=$null
  recorded_utc=[DateTime]::UtcNow.ToString('o')
  timestamp_note='The recording time is not the approval time; no source message ID or approval timestamp was supplied.'
}
$taskNoteRaw=JsonBytes $taskNote
$taskDecision=Get-Content -LiteralPath (Join-Path $taskOriginal 'RYAN-D2-DECISION.TEMPLATE.json') -Raw|ConvertFrom-Json
$taskDecision.approved=$true
$taskDecision.decision_text=$taskNote.answer
$taskDecision.source_note_sha256=HashBytes $taskNoteRaw
foreach($taskName in @('accept_uniform_raw_storage_writer_assumption','accept_IEEE754_binary32_interpretation','accept_dense_fixed_ranges_and_omitted_legacy_metadata','accept_local_conversion_only_with_model_notice_unresolved','conversion_authorized')){$taskDecision.$taskName=$true}
foreach($taskName in @('model_execution_authorized','network_authorized','redistribution_authorized','real_reader_authorized','release_authorized')){if($taskDecision.$taskName -ne $false){throw 'Forbidden authority in template'}}
$taskDecisionRaw=JsonBytes $taskDecision
$taskOwnerSha=HashBytes $taskDecisionRaw
$taskActivated=[ordered]@{}
$taskPins=@('d2_child.py','d2_adapter.py','launch_d2.py')
foreach($taskName in $taskRequired){
  if($taskName -eq 'INPUTS.json'){continue}
  $taskBytes=$taskOriginalBytes[$taskName]
  if($taskName -in $taskPins){
    $taskText=$taskUtf8.GetString($taskBytes)
    if([regex]::Matches($taskText,'(?m)^OWNER_DECISION_SHA256 = None').Count -ne 1){throw 'Expected one owner pin'}
    $taskChanged=$taskText.Replace('OWNER_DECISION_SHA256 = None',("OWNER_DECISION_SHA256 = '"+$taskOwnerSha+"'"))
    if($taskChanged.Replace(("OWNER_DECISION_SHA256 = '"+$taskOwnerSha+"'"),'OWNER_DECISION_SHA256 = None') -cne $taskText){throw 'Non-pin source change'}
    $taskBytes=$taskUtf8.GetBytes($taskChanged)
  }
  $taskActivated[$taskName]=$taskBytes
}
$taskInputs=$taskUtf8.GetString($taskOriginalBytes['INPUTS.json'])|ConvertFrom-Json
foreach($taskProperty in $taskInputs.child_files.PSObject.Properties){$taskProperty.Value=HashBytes $taskActivated[$taskProperty.Name]}
if(@($taskInputs.child_files.PSObject.Properties).Count -ne 8){throw 'Exact child member count required'}
$taskActivated['INPUTS.json']=JsonBytes $taskInputs
$taskAdmission=$taskAdmissionTemplate
$taskAdmission.root_reviewed=$true
$taskAdmission.owner_decision_sha256=$taskOwnerSha
foreach($taskName in $taskRequired){$taskAdmission.source_hashes.$taskName=HashBytes $taskActivated[$taskName]}
$taskAdmissionRaw=JsonBytes $taskAdmission
$taskRecord=[ordered]@{
  scope='D2_ONE_LOCAL_FIXED54_CONVERSION_ONLY'
  reviewed_proposal_commit='017b559b67e529d9a05d89911b713499cf6006ce'
  original_relative='_scratch/vad-d2-dormant-invocation-proposal02'
  activated_relative='_scratch/vad-d2-activated-invocation01'
  owner_note_sha256=HashBytes $taskNoteRaw
  owner_decision_sha256=$taskOwnerSha
  root_admission_sha256=HashBytes $taskAdmissionRaw
  changed_source_pins=$taskPins
  pin_only_changes=$true
  unchanged_source_count=7
  child_map_count=8
  root_source_count=11
  metadata_note='Dormant labels and comments are preserved from reviewed source; authority comes only from the exact owner record and three activated pins.'
  approval_time_unknown=$true
  checkpoint_accessed=$false
  output_created=$false
  conversion_executed=$false
  original_hashes=[ordered]@{}
  activated_hashes=[ordered]@{}
}
foreach($taskName in $taskRequired){$taskRecord.original_hashes[$taskName]=HashBytes $taskOriginalBytes[$taskName];$taskRecord.activated_hashes[$taskName]=HashBytes $taskActivated[$taskName]}
foreach($taskName in $taskRequired){if((HashBytes ([IO.File]::ReadAllBytes((Join-Path $taskOriginal $taskName)))) -cne $taskRecord.original_hashes[$taskName]){throw 'Original changed before materialization'}}
[IO.Directory]::CreateDirectory($taskTarget)|Out-Null
foreach($taskName in $taskRequired){WriteNew (Join-Path $taskTarget $taskName) $taskActivated[$taskName]}
WriteNew (Join-Path $taskTarget 'RYAN-D2-APPROVAL-SOURCE.json') $taskNoteRaw
WriteNew (Join-Path $taskTarget 'RYAN-D2-DECISION.json') $taskDecisionRaw
WriteNew (Join-Path $taskTarget 'ROOT-ADMISSION.json') $taskAdmissionRaw
WriteNew (Join-Path $taskTarget 'ACTIVATION.json') (JsonBytes $taskRecord)
foreach($taskName in $taskRequired){if((HashBytes ([IO.File]::ReadAllBytes((Join-Path $taskTarget $taskName)))) -cne $taskRecord.activated_hashes[$taskName]){throw 'Materialized source differs'}}
$taskRecord|ConvertTo-Json -Depth 10
