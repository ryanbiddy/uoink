$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSelectionPath=Join-Path $taskRepo 'docs\library\proof\writer-exclusion-correction02-brief-2026-09-13\INPUT-SELECTION.json'
$taskReportRoot='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\5444c59a-8ae\gemini\docs\library'
$taskReportPath=Join-Path $taskReportRoot 'GEMINI-WRITER-EXCLUSION-CORRECTION02-2026-09-13.md'
$taskCoveragePath=Join-Path $taskReportRoot 'GEMINI-WRITER-EXCLUSION-CORRECTION02-2026-09-13.coverage.json'
$taskExpected=@(
    @('B-01',11647,'8173d7394f4a893c14d2979283a0c17ed273e25f196e14560590be3a0f22058b',197),
    @('B-02',26951,'ca4676060382e189953f56b830f2c08227c1079280cd09b2b36fb6770ce6e4ce',427),
    @('B-03',11954,'df7ed56cdcbd23352b3e69a6f6790a012182b294491f38f8ed19610f000b485d',206),
    @('B-04',35768,'57ae722cda705e7f7a79a79442b316594719aeb390d63575aeaee3422949a469',636),
    @('B-05',34055,'8212531968abdc9fbf55f4d9607768d1cf14198b62f8443b670715ce0da07c26',307)
)
function Read-TextBinding([string]$taskPath,[int]$taskCap){
    $taskItem=Get-Item -LiteralPath $taskPath
    if($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $taskItem.Length -gt $taskCap){throw 'Fixed text leaf/cap required'}
    $taskRaw=[IO.File]::ReadAllBytes($taskPath)
    $taskText=[Text.UTF8Encoding]::new($false,$true).GetString($taskRaw)
    [pscustomobject]@{path=$taskPath;bytes=$taskRaw.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskRaw)).ToLowerInvariant();text=$taskText}
}
$taskSelectionBinding=Read-TextBinding $taskSelectionPath 16384
$taskSelection=$taskSelectionBinding.text | ConvertFrom-Json
if($taskSelection.schema -cne 'uoink-source-review-selection-1' -or $taskSelection.selected_count -ne 5 -or $taskSelection.selected_bytes -ne 120375 -or $taskSelection.selected_lines -ne 1773 -or @($taskSelection.files).Count -ne 5){throw 'Fixed five-source selection required'}
$taskReport=Read-TextBinding $taskReportPath 65536
$taskCoverage=Read-TextBinding $taskCoveragePath 16384
$taskRanges=@($taskCoverage.text | ConvertFrom-Json)
if($taskRanges.Count -ne 5){throw 'Five coverage records required'}
$taskSources=[Collections.Generic.List[object]]::new()
$taskAll=[Collections.Generic.List[object]]::new()
foreach($taskItem in @($taskSelectionBinding,$taskReport,$taskCoverage)){$taskAll.Add($taskItem)}
for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){
    $taskEntry=$taskSelection.files[$taskIndex]
    $taskPin=$taskExpected[$taskIndex]
    if($taskEntry.id -cne $taskPin[0] -or $taskEntry.bytes -ne $taskPin[1] -or $taskEntry.sha256 -cne $taskPin[2] -or $taskEntry.lines -ne $taskPin[3]){throw 'Selection pin differs'}
    if($taskEntry.path -cnotmatch '^docs/library/proof/windows-writer-exclusion-native-2026-09-13/proposal04/[A-Za-z0-9_\.]+$'){throw 'Unexpected selected source path'}
    $taskBinding=Read-TextBinding (Join-Path $taskRepo $taskEntry.path) 65536
    $taskSlots=$taskBinding.text.Split([char]10)
    if($taskBinding.bytes -ne $taskEntry.bytes -or $taskBinding.sha256 -cne $taskEntry.sha256 -or $taskSlots.Count -ne $taskEntry.lines){throw 'Selected source bytes/hash/line slots differ'}
    $taskCoverageEntry=$taskRanges[$taskIndex]
    if($taskCoverageEntry.id -cne $taskEntry.id -or @($taskCoverageEntry.PSObject.Properties).Count -ne 2 -or @($taskCoverageEntry.PSObject.Properties.Name | Where-Object {$_ -cnotin @('id','viewed_ranges')}).Count -ne 0){throw 'Coverage object schema differs'}
    $taskPreviousEnd=0
    foreach($taskRange in $taskCoverageEntry.viewed_ranges){
        if(@($taskRange).Count -ne 2 -or ($taskRange[0] -isnot [int] -and $taskRange[0] -isnot [long]) -or ($taskRange[1] -isnot [int] -and $taskRange[1] -isnot [long]) -or $taskRange[0] -le $taskPreviousEnd -or $taskRange[1] -lt $taskRange[0] -or $taskRange[1] -gt $taskSlots.Count){throw 'Invalid inclusive coverage range'}
        $taskPreviousEnd=$taskRange[1]
    }
    $taskSources.Add([ordered]@{id=$taskEntry.id;path=$taskEntry.path;bytes=$taskBinding.bytes;sha256=$taskBinding.sha256;catalog_lf_slots=$taskSlots.Count;terminal_empty_slot=($taskSlots[-1] -ceq '');declared_viewed_ranges=$taskCoverageEntry.viewed_ranges;declared_ranges_prove_actual_worker_views=$false})
    $taskAll.Add($taskBinding)
}
$taskWordCount=[regex]::Matches($taskReport.text,'\S+').Count
if($taskWordCount -gt 600 -or $taskReport.text.Contains('```')){throw 'Report length or fenced-code restriction failed'}
$taskBeforeAfter=[Collections.Generic.List[object]]::new()
foreach($taskBinding in $taskAll){
    $taskAfter=Read-TextBinding $taskBinding.path 65536
    if($taskAfter.bytes -ne $taskBinding.bytes -or $taskAfter.sha256 -cne $taskBinding.sha256){throw 'Read-only input changed'}
    $taskBeforeAfter.Add([ordered]@{path=$taskBinding.path;bytes=$taskBinding.bytes;before_sha256=$taskBinding.sha256;after_sha256=$taskAfter.sha256})
}
[ordered]@{
    schema='uoink.writer-correction02-peer-text-check.v1'
    passive_check='PASS'
    scope='Only selected source text, selection JSON and two worker outputs; no candidate execution or native/execution receipts'
    selected_source_count=5
    selected_bytes=120375
    catalog_lf_slots=1773
    report_whitespace_word_count=$taskWordCount
    report_under_600_words=$true
    coverage_schema_valid=$true
    worker_view_trace_verified=$false
    source_accuracy_verdict_is_separate=$true
    sources=$taskSources.ToArray()
    eight_text_inputs_unchanged=$true
    before_after=$taskBeforeAfter.ToArray()
} | ConvertTo-Json -Depth 12
