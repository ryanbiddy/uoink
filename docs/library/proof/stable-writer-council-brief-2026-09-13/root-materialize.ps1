$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskPrepared=Join-Path $taskRepo '_scratch\gemini-stable-writer-council-proposal02'
$taskRelative='docs/library/proof/stable-writer-council-brief-2026-09-13'
$taskDestination=Join-Path $taskRepo $taskRelative
$taskBriefDestination=Join-Path $taskRepo 'docs/library/GEMINI-STABLE-DIRECTORY-WRITER-REVIEW-BRIEF-2026-09-13.md'
$taskUtf8=[Text.UTF8Encoding]::new($false,$true)
function Sha([byte[]]$Raw){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Raw)).ToLowerInvariant()}
function WriteNew([string]$Path,[byte[]]$Raw){$s=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$s.Write($Raw,0,$Raw.Length);$s.Flush($true)}finally{$s.Dispose()}}
function JsonBytes($Object){,$taskUtf8.GetBytes((ConvertTo-Json -InputObject $Object -Depth 60)+"`n")}
if((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath $taskBriefDestination)){throw 'Fresh council destinations required'}
$taskMapRaw=[IO.File]::ReadAllBytes((Join-Path $taskPrepared 'INPUT-SELECTION.json'))
if((Sha $taskMapRaw) -cne '3053c328e65636d895f8caa1545425638492f9cb816fc0ac8bdff4fe19baa51d'){throw 'Reviewed map changed'}
$taskMap=$taskUtf8.GetString($taskMapRaw)|ConvertFrom-Json
$taskProperties=@($taskMap.PSObject.Properties|Where-Object {$_.Value -is [array] -and $_.Value.Count -eq 48})
if($taskProperties.Count -ne 1){throw 'Expected one 48-row selection'}
$taskRows=$taskProperties[0].Value
$taskTotal=0
$taskMaterialized=[ordered]@{}
foreach($row in $taskRows){
  if($row.path -notlike 'docs/library/proof/*' -or $row.path.Contains('..') -or $row.path.Contains('\')){throw 'Bounded proof path required'}
  $taskPath=Join-Path $taskRepo $row.path
  if($row.root_materialization_pending){
    if($row.prepared_source -cnotin @('_scratch/gemini-stable-writer-council-proposal02/controller-selected-fields.json','_scratch/gemini-stable-writer-council-proposal02/extract-controller.ps1')){throw 'Unknown prepared source'}
    $taskPath=Join-Path $taskRepo $row.prepared_source
  }
  $taskRaw=[IO.File]::ReadAllBytes($taskPath)
  if($taskRaw.Length -ne $row.bytes -or (Sha $taskRaw) -cne $row.sha256){throw "Selected input changed: $($row.id)"}
  $null=$taskUtf8.GetString($taskRaw)
  $taskTotal+=$taskRaw.Length
  if($row.root_materialization_pending){$taskMaterialized[$row.member]=$taskRaw}
}
if($taskTotal -ne 480562 -or $taskMaterialized.Count -ne 2){throw 'Selection totals changed'}
$taskRawController=[IO.File]::ReadAllBytes((Join-Path $taskRepo 'docs/library/proof/windows-writer-exclusion-native-2026-09-13/run04/controller-result.json'))
if($taskRawController.Length -ne 309037 -or (Sha $taskRawController) -cne '3e74a30295288c4892f6545fe71dc23516e1fcd5198653196692f0e2f47651f3'){throw 'Original controller receipt changed'}
$taskController=$taskUtf8.GetString($taskRawController)|ConvertFrom-Json
$taskExcerpt=$taskUtf8.GetString($taskMaterialized['controller-selected-fields.json'])|ConvertFrom-Json
if($taskController.native_api_calls.Count -ne 8230 -or @($taskExcerpt.receipt_fields.PSObject.Properties).Count -ne 31){throw 'Excerpt field shape mismatch'}
foreach($p in $taskController.PSObject.Properties){
  if($p.Name -eq 'native_api_calls'){continue}
  if((ConvertTo-Json -InputObject $p.Value -Depth 60 -Compress) -cne (ConvertTo-Json -InputObject $taskExcerpt.receipt_fields.($p.Name) -Depth 60 -Compress)){throw 'Excerpt value mismatch'}
}
$taskBriefRaw=[IO.File]::ReadAllBytes((Join-Path $taskPrepared 'BRIEF.md'))
if((Sha $taskBriefRaw) -cne 'ca5fafb6a9ddafc9d344d16d7f2f94c62208347281fc010333d297fec9b0784f'){throw 'Reviewed brief changed'}
$taskBrief=$taskUtf8.GetString($taskBriefRaw)
$taskBrief=$taskBrief.Replace('Status: prepared for root review; do not dispatch. INPUT-SELECTION.json binds','Status: root reviewed for a source-only Control Room dispatch. `docs/library/proof/stable-writer-council-brief-2026-09-13/INPUT-SELECTION.json` binds')
$taskBrief=$taskBrief.Replace('Two derived text destinations require exact root materialization before dispatch.','Both derived text destinations are materialized and verified in ROOT-MATERIALIZATION.json beside the map; the map retains its historical preparation flags.')
$taskBrief=$taskBrief.Replace('No dispatch is authorized by this draft.','Root authorizes this bounded review through the normal Control Room Gemini subscription route.')
if($taskBrief -ceq $taskUtf8.GetString($taskBriefRaw) -or $taskBrief.Contains('do not dispatch')){throw 'Brief status update failed'}
[IO.Directory]::CreateDirectory($taskDestination)|Out-Null
foreach($taskName in $taskMaterialized.Keys){WriteNew (Join-Path $taskDestination $taskName) $taskMaterialized[$taskName]}
$taskPreparedNames=@('INPUT-SELECTION.json','EXTRACTION-ACTUAL.json','EXTRACTION.md','COMPACT-MAP-ACTUAL.json','COMPACT-MAP-FAILED-ACTUAL.json','MAP-PREPARATION-REPAIR.md','ROOT-HANDOFF.md')
foreach($taskName in $taskPreparedNames){WriteNew (Join-Path $taskDestination $taskName) ([IO.File]::ReadAllBytes((Join-Path $taskPrepared $taskName)))}
WriteNew (Join-Path $taskDestination 'PREPARED-BRIEF.md') $taskBriefRaw
WriteNew (Join-Path $taskDestination '.gitattributes') $taskUtf8.GetBytes("* -text`n")
WriteNew (Join-Path $taskDestination 'root-materialize.ps1') ([IO.File]::ReadAllBytes($PSCommandPath))
$taskCheck=[ordered]@{selected_inputs=48;selected_bytes=$taskTotal;map_sha256=Sha $taskMapRaw;materialized=2;controller_preserved_fields=31;controller_omitted_call_rows=8230;original_controller_sha256=Sha $taskRawController;all_selected_bindings_verified=$true;no_source_or_native_execution=$true;model_or_checkpoint_access=$false;dispatch_occurred=$false;approved_brief_sha256=Sha $taskUtf8.GetBytes($taskBrief)}
WriteNew (Join-Path $taskDestination 'ROOT-MATERIALIZATION.json') (JsonBytes $taskCheck)
WriteNew $taskBriefDestination $taskUtf8.GetBytes($taskBrief)
$taskCheck|ConvertTo-Json -Depth 5
