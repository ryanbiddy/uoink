param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPreparationSha256)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$base=$PSScriptRoot
$scratch='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$proof=Join-Path $scratch 'runtime-candidate03-graph-proof01'
function Hash-Bytes([byte[]]$Bytes) { [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant() }
function Canonical([string]$Name) {
    if($Name -cnotmatch '^[A-Za-z0-9_./+\-]+$' -or $Name -match '(^/|(^|/)\.\.?(/|$)|//)'){throw 'Noncanonical mapped path'}
}
function Check-Chain([string]$Path) {
    $cursor=[IO.Path]::GetFullPath($Path)
    while($cursor) {
        if(Test-Path -LiteralPath $cursor) {
            $item=Get-Item -Force -LiteralPath $cursor
            if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Observed reparse point'}
            if($cursor -cne $Path -and -not $item.PSIsContainer){throw 'Nondirectory ancestor'}
        }
        $parent=[IO.Directory]::GetParent($cursor)
        $cursor=if($null -eq $parent){$null}else{$parent.FullName}
    }
}
function Read-Bounded([string]$Path,[long]$Cap=16777216) {
    Check-Chain $Path
    $file=Get-Item -Force -LiteralPath $Path
    if($file.PSIsContainer -or $file.Length -gt $Cap){throw 'Input type/size bound'}
    $bytes=[IO.File]::ReadAllBytes($Path)
    if($bytes.Length -gt $Cap){throw 'Input grew beyond bound'}
    return ,$bytes
}
function Write-New([string]$Path,[byte[]]$Bytes) {
    Check-Chain $Path
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try {$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}
function Json-Bytes($Value) { return ,([Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 30)+"`n")) }
$prepPath=Join-Path $base 'PREPARATION-HASHES.json'
$prepBytes=Read-Bounded $prepPath 131072
if((Hash-Bytes $prepBytes) -cne $ExpectedPreparationSha256){throw 'Preparation admission mismatch'}
$prepRows=@([Text.Encoding]::UTF8.GetString($prepBytes)|ConvertFrom-Json)
function Check-Preparation {
    foreach($row in $prepRows){Canonical $row.path;$raw=Read-Bounded (Join-Path $base $row.path);if($raw.Length -ne $row.bytes -or (Hash-Bytes $raw) -cne $row.sha256){throw 'Preparation changed'}}
    if((Hash-Bytes (Read-Bounded $prepPath 131072)) -cne $ExpectedPreparationSha256){throw 'Preparation manifest changed'}
}
Check-Preparation
$plan=Get-Content -LiteralPath (Join-Path $base 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
if($plan.format -cne 'uoink-graph-documentary-source-plan-v1' -or $plan.scratch_root -cne $scratch -or $plan.source_files -ne 2266 -or @($plan.files).Count -ne 2266 -or $plan.source_bytes -gt 1073741824 -or $plan.unique_bytes -gt 134217728){throw 'Source plan scope/bounds'}
$byPath=@{};$byHash=@{};$total=0L
foreach($row in $plan.files) {
    Canonical $row.path
    $expected=Join-Path $scratch $row.path
    if([IO.Path]::GetFullPath($row.source) -cne [IO.Path]::GetFullPath($expected) -or $row.source -cne $expected){throw 'Source path binding differs'}
    if($byPath.ContainsKey($row.path) -or $row.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $row.member -cne ('sha256/'+$row.sha256) -or $row.bytes -lt 0 -or $row.bytes -gt 16777216){throw 'Source row invalid'}
    $extension=[IO.Path]::GetExtension($row.source)
    if($extension -notin @('.iss','.json','.log','.md','.metadata','.ps1','.py','.txt') -and [IO.Path]::GetFileName($row.source) -cne 'METADATA'){throw 'Unexpected source content type'}
    $byPath[$row.path]=$row
    if($byHash.ContainsKey($row.sha256) -and $byHash[$row.sha256].bytes -ne $row.bytes){throw 'Conflicting duplicate payload size'}
    $byHash[$row.sha256]=$row;$total+=$row.bytes
}
if($total -ne $plan.source_bytes -or $byHash.Count -ne $plan.unique_payloads -or $byHash.Count -gt 1000){throw 'Source totals differ'}
function Check-Sources {
    foreach($tree in $plan.tree_roots) {
        Check-Chain $tree.path
        $actual=@(Get-ChildItem -Force -LiteralPath $tree.path -File -Recurse)
        if($actual.Count -ne $tree.files){throw 'Source tree membership changed'}
        foreach($file in $actual){$relative=[IO.Path]::GetRelativePath($scratch,$file.FullName).Replace([char]92,[char]47);if(-not $byPath.ContainsKey($relative)){throw 'Extra source path'}}
    }
    foreach($row in $plan.files){$raw=Read-Bounded $row.source;if($raw.Length -ne $row.bytes -or (Hash-Bytes $raw) -cne $row.sha256){throw ('Source changed: '+$row.path)}}
}
Check-Sources
$bindings=@(Get-Content -LiteralPath (Join-Path $base 'MANIFEST-BINDINGS.json') -Raw|ConvertFrom-Json)
foreach($binding in $bindings) {
    if($byPath[$binding.manifest_path].sha256 -cne $binding.manifest_sha256){throw 'Original manifest hash differs'}
    $original=@(Get-Content -LiteralPath $byPath[$binding.manifest_path].source -Raw|ConvertFrom-Json)
    if($original.Count -ne $binding.count -or @($binding.members).Count -ne $binding.count){throw 'Original manifest count differs'}
    for($i=0;$i -lt $original.Count;$i++) {
        $row=$original[$i];$copy=$binding.members[$i]
        if($row.path -cne $copy.path -or $row.bytes -ne $copy.bytes -or $row.sha256 -cne $copy.sha256 -or -not $byHash.ContainsKey($row.sha256) -or $byHash[$row.sha256].bytes -ne $row.bytes -or $copy.member -cne ('sha256/'+$row.sha256) -or $byPath[$copy.source_witness].sha256 -cne $row.sha256){throw 'Original manifest payload unavailable'}
        if($binding.kind -eq 'current' -and $byPath[($binding.current_root+'/'+$row.path)].sha256 -cne $row.sha256){throw 'Current manifest mapping differs'}
    }
}
$captures=Get-Content -LiteralPath $plan.original313.manifest -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $plan.original313.manifest).Hash.ToLowerInvariant() -cne $plan.original313.sha256 -or @($captures.PSObject.Properties).Count -ne 313){throw 'Original313 manifest differs'}
foreach($item in $captures.PSObject.Properties){if($byPath[('runtime-candidate02-metadata/evidence/'+$item.Name)].sha256 -cne $item.Value){throw 'Original313 content not mapped'}}
function Read-Record([string]$Name) { Get-Content -LiteralPath $byPath[$Name].source -Raw|ConvertFrom-Json }
$runNames=@('runtime-candidate03-graph-qualification01/runs/qualification01/result.json','runtime-candidate03-graph-qualification02/runs/qualification02/result.json','runtime-candidate03-final-qualification01/runs/qualification01/result.json','astra-runtime-candidate03-final-qualification01/runs/qualification01/result.json')
$runs=@(foreach($name in $runNames){Read-Record $name})
$expectedPass=@(51,62,59,59);$expectedFail=@(11,0,0,0)
for($i=0;$i -lt 4;$i++) {
    $r=$runs[$i]
    if($r.passed -ne $expectedPass[$i] -or $r.failed -ne $expectedFail[$i] -or $r.errors -ne 0 -or $r.skipped -ne 0 -or $r.subtests -ne 0 -or $r.tests_run -ne ($expectedPass[$i]+$expectedFail[$i])){throw 'Retained qualification counts differ'}
    if($i -eq 0){if($r.guard.valid -ne $false -or @($r.guard.violations).Count -ne 25 -or $r.exit -ne 1){throw 'Original failed qualification changed'}}
    elseif($r.guard.valid -ne $true -or @($r.guard.violations).Count -ne 0 -or $r.exit -ne 0){throw 'Qualified result/guard differs'}
}
if(($runs[2].observations|ConvertTo-Json -Depth 15 -Compress) -cne ($runs[3].observations|ConvertTo-Json -Depth 15 -Compress)){throw 'Author/root ordered observations differ'}
$graph=Read-Record 'runtime-candidate03-complete-graph01/results/graph01/raw-graph.json'
$inv=Read-Record 'runtime-candidate03-complete-graph01/results/graph01/invocation.json'
if($graph.status -cne 'FAIL' -or $graph.passed -ne $false -or $graph.selection_count -ne 144 -or $graph.active_edges_count -ne 287 -or @($graph.wheel_failures).Count -ne 2 -or @($graph.conflicting_constraints).Count -ne 0 -or @($graph.missing_packages).Count -ne 0 -or @($graph.incomplete_evidence).Count -ne 0){throw 'Complete graph finding differs'}
if($inv.invocation_status -cne 'VALID' -or $inv.guard.valid -ne $true -or @($inv.guard.violations).Count -ne 0 -or $inv.exit -ne 1 -or $inv.artifact_verified_in_this_invocation -ne $false){throw 'Complete graph invocation differs'}
if(($inv.captures_before|ConvertTo-Json -Depth 8 -Compress) -cne ($inv.captures_after|ConvertTo-Json -Depth 8 -Compress) -or @($inv.captures_before).Count -ne 313){throw 'Complete313 before/after differs'}
Check-Chain $proof
if(Test-Path -LiteralPath $proof){throw 'Fresh proof required'}
[IO.Directory]::CreateDirectory($proof)|Out-Null
$copied=@(foreach($name in @('BRIEF.md','PROTOCOL.md','VERDICT.md','SOURCE-PLAN.json','MANIFEST-BINDINGS.json','seal.ps1','verify_proof.ps1','PREPARATION-HASHES.json')){$raw=Read-Bounded (Join-Path $base $name);Write-New (Join-Path $proof $name) $raw;[ordered]@{source=Join-Path $base $name;path=$name;bytes=$raw.Length;sha256=Hash-Bytes $raw}})
$zipPath=Join-Path $proof 'payloads.zip'
$stream=[IO.FileStream]::new($zipPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    $zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create,$true)
    try {
        $keys=[string[]]@($byHash.Keys);[Array]::Sort($keys,[StringComparer]::Ordinal)
        foreach($hash in $keys) {
            $row=$byHash[$hash];$raw=Read-Bounded $row.source
            if($raw.Length -ne $row.bytes -or (Hash-Bytes $raw) -cne $hash){throw 'Source changed during ZIP write'}
            $entry=$zip.CreateEntry($row.member,[IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime=[DateTimeOffset]::new(1980,1,1,0,0,0,[TimeSpan]::Zero);$entry.ExternalAttributes=0
            $entryStream=$entry.Open();try{$entryStream.Write($raw,0,$raw.Length)}finally{$entryStream.Dispose()}
        }
    } finally {$zip.Dispose()}
    $stream.Flush($true)
} finally {$stream.Dispose()}
[IO.Directory]::CreateDirectory((Join-Path $proof 'readable'))|Out-Null
$readableNames=@('runtime-candidate03-graph-proposal01/before/graph01-result.json')+$runNames+@('runtime-candidate03-complete-graph01/results/graph01/raw-graph.json','runtime-candidate03-complete-graph01/results/graph01/invocation.json','CANDIDATE03-FINAL59-INDEPENDENT-REVIEW.json','COMPLETE144-AUTHOR-ACTUAL-2026-09-13.json')
$readable=@(for($i=0;$i -lt $readableNames.Count;$i++){$row=$byPath[$readableNames[$i]];$name=('readable/{0:D2}-' -f $i)+[IO.Path]::GetFileName($row.path);$raw=Read-Bounded $row.source;Write-New (Join-Path $proof $name) $raw;[ordered]@{path=$name;original_path=$row.path;bytes=$row.bytes;sha256=$row.sha256;member=$row.member}})
Write-New (Join-Path $proof 'READABLE-BINDINGS.json') (Json-Bytes $readable)
Write-New (Join-Path $proof 'INSTRUMENT-COPY-BINDINGS.json') (Json-Bytes $copied)
Check-Sources
Check-Preparation
$summary=[ordered]@{scope='Documentary copying only; no test/graph rerun';source_paths=$plan.source_files;source_bytes=$plan.source_bytes;zip_members=$byHash.Count;expanded_unique_bytes=$plan.unique_bytes;source_hashes_checked_before_after=$true;original_manifests=$bindings.Count;original313_hashes_bound=$true;author_root_ordered59_equal=$true;first62_qualification_remains_failed=$true;complete144_graph_remains_failed=$true;native_model_or_artifact_operations=0}
Write-New (Join-Path $proof 'SEAL-CHECKS.json') (Json-Bytes $summary)
Write-New (Join-Path $proof '.gitattributes') ([Text.Encoding]::ASCII.GetBytes("* -text`n"))
$proofRows=@(Get-ChildItem -Force -LiteralPath $proof -File -Recurse|Sort-Object FullName|ForEach-Object{[ordered]@{path=[IO.Path]::GetRelativePath($proof,$_.FullName).Replace([char]92,[char]47);bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}})
Write-New (Join-Path $proof 'SHA256.json') (Json-Bytes ([ordered]@{files=$proofRows}))
& (Join-Path $proof 'verify_proof.ps1') -ProofPath $proof
if(-not $?){throw 'Proof verifier failed'}
[ordered]@{proof=$proof;payload_files=$proofRows.Count;source_paths=$plan.source_files;unique_members=$byHash.Count;zip_bytes=(Get-Item -LiteralPath $zipPath).Length;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $proof 'SHA256.json')).Hash.ToLowerInvariant()}|ConvertTo-Json
