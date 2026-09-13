param([Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPreparationSha256)
$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$scratch='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$proof=Join-Path $scratch 'five-wheel-graph-proof01'
function Hash([byte[]]$Bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()}
function Canonical([string]$Name){if($Name -cnotmatch '^[A-Za-z0-9_./+\-]+$' -or $Name -match '(^/|(^|/)\.\.?(/|$)|//)'){throw 'Noncanonical path'}}
function Chain([string]$Path){
 $leaf=[IO.Path]::GetFullPath($Path);$cursor=$leaf
 while($cursor){
  if(Test-Path -LiteralPath $cursor){$i=Get-Item -Force -LiteralPath $cursor;if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or ($cursor -cne $leaf -and -not $i.PSIsContainer)){throw 'Reparse or nondirectory ancestor'}}
  $p=[IO.Directory]::GetParent($cursor);$cursor=if($p){$p.FullName}else{$null}
 }
}
function Read-Bytes([string]$Path,[long]$Cap=16777216){Chain $Path;$i=Get-Item -Force -LiteralPath $Path;if($i.PSIsContainer -or $i.Length -gt $Cap){throw 'Input bound'};$r=[IO.File]::ReadAllBytes($Path);if($r.Length -gt $Cap){throw 'Input grew'};return ,$r}
function Write-New([string]$Path,[byte[]]$Bytes){Chain $Path;$s=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough);try{$s.Write($Bytes,0,$Bytes.Length);$s.Flush($true)}finally{$s.Dispose()}}
function Json-Bytes($Value){return ,([Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 30)+"`n"))}
$prepPath=Join-Path $base 'PREPARATION-HASHES.json'
$prepRaw=Read-Bytes $prepPath 131072
if((Hash $prepRaw) -cne $ExpectedPreparationSha256){throw 'Preparation admission mismatch'}
$prep=@([Text.Encoding]::UTF8.GetString($prepRaw)|ConvertFrom-Json)
function Check-Preparation{
 foreach($r in $prep){Canonical $r.path;$raw=Read-Bytes (Join-Path $base $r.path);if($raw.Length -ne $r.bytes -or (Hash $raw) -cne $r.sha256){throw 'Preparation changed'}}
 if((Hash (Read-Bytes $prepPath 131072)) -cne $ExpectedPreparationSha256){throw 'Preparation manifest changed'}
}
Check-Preparation
$plan=Get-Content -LiteralPath (Join-Path $base 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
if($plan.format -cne 'uoink-five-wheel-graph-documentary-v1' -or $plan.scratch_root -cne $scratch -or $plan.source_files -ne 1050 -or @($plan.files).Count -ne 1050 -or $plan.new_payloads -ne 63 -or $plan.external_payloads -ne 415){throw 'Fixed source plan differs'}
$byPath=@{};$byHash=@{};$new=@{};$total=0L;$newBytes=0L
foreach($r in $plan.files){
 Canonical $r.path
 if([IO.Path]::GetFullPath($r.source) -cne [IO.Path]::GetFullPath((Join-Path $scratch $r.path)) -or $byPath.ContainsKey($r.path) -or $r.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $r.member -cne ('sha256/'+$r.sha256) -or $r.bytes -lt 0 -or $r.bytes -gt 16777216){throw 'Source binding invalid'}
 if([IO.Path]::GetExtension($r.source) -notin @('.iss','.json','.log','.md','.metadata','.ps1','.py','.txt','.gitattributes') -and [IO.Path]::GetFileName($r.source) -cne 'METADATA'){throw 'Unexpected source type'}
 if($r.storage -cnotin @('new-payload','archive-4827288')){throw 'Unknown storage'}
 if($byHash.ContainsKey($r.sha256) -and ($byHash[$r.sha256].bytes -ne $r.bytes -or $byHash[$r.sha256].storage -cne $r.storage)){throw 'Conflicting duplicate'}
 $byPath[$r.path]=$r;$byHash[$r.sha256]=$r;$total+=$r.bytes
 if($r.storage -ceq 'new-payload'){$new[$r.sha256]=$r}
}
foreach($r in $new.Values){$newBytes+=$r.bytes}
if($total -ne 251301442 -or $plan.source_bytes -ne $total -or $byHash.Count -ne 478 -or $new.Count -ne 63 -or $newBytes -ne 2050594 -or $plan.new_bytes -ne $newBytes){throw 'Source totals differ'}
function Check-Sources{
 foreach($tree in $plan.tree_roots){Chain $tree.path;$actual=@(Get-ChildItem -Force -LiteralPath $tree.path -Recurse -File);if($actual.Count -ne $tree.files){throw 'Source tree count changed'};foreach($f in $actual){$name=[IO.Path]::GetRelativePath($scratch,$f.FullName).Replace([char]92,[char]47);if(-not $byPath.ContainsKey($name)){throw 'Extra source path'}}}
 foreach($r in $plan.files){$raw=Read-Bytes $r.source;if($raw.Length -ne $r.bytes -or (Hash $raw) -cne $r.sha256){throw ('Source changed: '+$r.path)}}
}
Check-Sources
$archive='E:\AI\projects\uoink\checkouts\Yoink-library\docs\library\proof\runtime-candidate03-graph-2026-09-13'
if($plan.archive.path -cne $archive -or $plan.archive.commit -cne '4827288' -or (Hash (Read-Bytes (Join-Path $archive 'SHA256.json'))) -cne '793a1c4826eabc278b795d0d2fbc06c642dfb2ca1cdf42d73cc4bb8e4fb941ec' -or (Hash (Read-Bytes (Join-Path $archive 'SOURCE-PLAN.json'))) -cne '68c1a0927b3154788372026488b8332e4e66f6239736ee357a70eeab781a35e6'){throw 'Referenced archive metadata changed'}
if((Hash (Read-Bytes (Join-Path $archive 'payloads.zip') 33554432)) -cne '8dba369e6f9063af80ca46c725a4e41e7d893dc7cb0b7c2324feab838a4175ed'){throw 'Referenced archive bytes changed'}
$prior=Get-Content -LiteralPath (Join-Path $archive 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
$oldHashes=@{};foreach($r in $prior.files){$oldHashes[$r.sha256]=$r}
foreach($r in $byHash.Values){if($r.storage -ceq 'archive-4827288' -and (-not $oldHashes.ContainsKey($r.sha256) -or $oldHashes[$r.sha256].bytes -ne $r.bytes)){throw 'External payload not bound'}}
$bindings=@(Get-Content -LiteralPath (Join-Path $base 'MANIFEST-BINDINGS.json') -Raw|ConvertFrom-Json)
if($bindings.Count -ne 4){throw 'Preparation bindings absent'}
foreach($b in $bindings){
 if($byPath[$b.manifest_path].sha256 -cne $b.manifest_sha256){throw 'Manifest pin mismatch'}
 $rows=@(Get-Content -LiteralPath $byPath[$b.manifest_path].source -Raw|ConvertFrom-Json)
 if($rows.Count -ne $b.count -or @($b.members).Count -ne $b.count){throw 'Manifest row count mismatch'}
 for($i=0;$i -lt $rows.Count;$i++){$r=$rows[$i];$m=$b.members[$i];$mapped=$byPath[$b.root+'/'+$r.path];if($r.path -cne $m.path -or $r.bytes -ne $m.bytes -or $r.sha256 -cne $m.sha256 -or $mapped.sha256 -cne $r.sha256 -or $mapped.storage -cne $m.storage){throw 'Manifest payload mismatch'}}
}
function Record([string]$Name){Get-Content -LiteralPath $byPath[$Name].source -Raw|ConvertFrom-Json}
$author='runtime-candidate03-five-wheel-qualification01';$root='astra-five-wheel68-qualification01';$graphRoot='runtime-candidate03-five-wheel-graph01'
$a=Record ($author+'/runs/qualification01/result.json');$b=Record ($root+'/runs/qualification01/result.json')
foreach($r in @($a,$b)){
 if($r.status -cne 'PASS' -or $r.tests_run -ne 68 -or $r.passed -ne 68 -or $r.failed -ne 0 -or $r.errors -ne 0 -or $r.skipped -ne 0 -or $r.subtests -ne 0 -or $r.exit -ne 0 -or $r.guard.valid -ne $true -or @($r.guard.violations).Count -ne 0 -or $r.inputs_unchanged -ne $true){throw '68-case outcome differs'}
 if(($r.case_ids|ConvertTo-Json -Compress) -cne ($r.expected_case_ids|ConvertTo-Json -Compress)){throw 'Case IDs differ'}
}
if(($a.observations|ConvertTo-Json -Depth 15 -Compress) -cne ($b.observations|ConvertTo-Json -Depth 15 -Compress)){throw 'Ordered observations differ'}
foreach($name in @($author,$root)){$l=Record ($name+'/launch-qualification01/result.json');$n=Record ($name+'/launch-qualification01/actual-native-exit.json');if($l.actual_native_exit -ne 0 -or $l.intended_outer_exit -ne 0 -or $l.instrumentation_verdict -cne 'VALID' -or $n.actual_native_exit -ne 0){throw 'Qualification native/outer status differs'}}
$g=Record ($graphRoot+'/results/graph01/raw-graph.json');$inv=Record ($graphRoot+'/results/graph01/invocation.json');$launch=Record ($graphRoot+'/launch-graph01/result.json');$native=Record ($graphRoot+'/launch-graph01/actual-native-exit.json')
if($g.status -cne 'PASS' -or $g.passed -ne $true -or $g.selection_count -ne 144 -or $g.active_edges_count -ne 287 -or @($g.active_edges).Count -ne 287){throw 'Full graph outcome differs'}
foreach($field in @('missing_packages','conflicting_constraints','wheel_failures','incomplete_evidence','manifest_errors','marker_errors','direct_url_errors','selection_errors')){if(@($g.$field).Count -ne 0){throw 'Graph gap list differs'}}
if($inv.invocation_status -cne 'VALID' -or $inv.exit -ne 0 -or $inv.graph_exit -ne 0 -or $inv.guard.valid -ne $true -or @($inv.guard.violations).Count -ne 0 -or $inv.artifact_verified_in_this_invocation -ne $false -or $inv.local_claims_valid -ne $true -or $launch.actual_native_exit -ne 0 -or $launch.intended_outer_exit -ne 0 -or $launch.instrumentation_verdict -cne 'VALID' -or $native.actual_native_exit -ne 0){throw 'Graph invocation status differs'}
if(@($inv.captures_before).Count -ne 313 -or @($inv.source_after).Count -ne 47 -or ($inv.captures_before|ConvertTo-Json -Depth 12 -Compress) -cne ($inv.captures_after|ConvertTo-Json -Depth 12 -Compress) -or ($inv.identities_before|ConvertTo-Json -Depth 12 -Compress) -cne ($inv.identities_after|ConvertTo-Json -Depth 12 -Compress)){throw 'Graph before/after differs'}
$owned=@($g.wheel_details.PSObject.Properties|Where-Object {$_.Value.origin -ceq 'owned-built-wheel'})
if(($owned.Name|Sort-Object|ConvertTo-Json -Compress) -cne (@('antlr4-python3-runtime','faster-whisper','nltk','proxy-tools','whisperx')|ConvertTo-Json -Compress)){throw 'Five local entries differ'}
foreach($p in $owned){$w=$p.Value;if($null -ne $w.url -or $w.public_release_record -ne $false -or $w.artifact_verified_in_this_invocation -ne $false -or ($p.Name -in @('antlr4-python3-runtime','proxy-tools') -and $null -ne $w.requires_python)){throw 'Local provenance/absence claim differs'}}
foreach($name in @('FIVE-WHEEL68-AUTHOR-ACTUAL.json','FIVE-WHEEL68-ROOT-ACTUAL.json','FIVE-WHEEL-FULL144-ACTUAL.json')){if((Record $name).exit_code -ne 0){throw 'Actual outer tool outcome differs'}}
Chain $proof;if(Test-Path -LiteralPath $proof){throw 'Fresh proof required'}
[IO.Directory]::CreateDirectory($proof)|Out-Null
$copies=@(foreach($name in @($prep.path)+@('PREPARATION-HASHES.json')){Canonical $name;$dest=Join-Path $proof $name;[IO.Directory]::CreateDirectory((Split-Path -Parent $dest))|Out-Null;$raw=Read-Bytes (Join-Path $base $name);Write-New $dest $raw;[ordered]@{path=$name;bytes=$raw.Length;sha256=Hash $raw}})
$stream=[IO.FileStream]::new((Join-Path $proof 'payloads.zip'),[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{$zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create,$true);try{
 $keys=[string[]]@($new.Keys);[Array]::Sort($keys,[StringComparer]::Ordinal)
 foreach($hash in $keys){$r=$new[$hash];$raw=Read-Bytes $r.source;if($raw.Length -ne $r.bytes -or (Hash $raw) -cne $hash){throw 'Source changed during write'};$entry=$zip.CreateEntry($r.member,[IO.Compression.CompressionLevel]::Optimal);$entry.LastWriteTime=[DateTimeOffset]::new(1980,1,1,0,0,0,[TimeSpan]::Zero);$entry.ExternalAttributes=0;$s=$entry.Open();try{$s.Write($raw,0,$raw.Length)}finally{$s.Dispose()}}
 }finally{$zip.Dispose()};$stream.Flush($true)}finally{$stream.Dispose()}
[IO.Directory]::CreateDirectory((Join-Path $proof 'readable'))|Out-Null
$names=@(($author+'/runs/qualification01/result.json'),($root+'/runs/qualification01/result.json'),($graphRoot+'/results/graph01/raw-graph.json'),($graphRoot+'/results/graph01/invocation.json'),'FIVE-WHEEL-FULL144-ACTUAL.json','FIVE-WHEEL-GRAPH-PREPARATION-READER-CORRECTION.md')
$readable=@(for($i=0;$i -lt $names.Count;$i++){$r=$byPath[$names[$i]];$target=('readable/{0:D2}-' -f $i)+[IO.Path]::GetFileName($r.path);Write-New (Join-Path $proof $target) (Read-Bytes $r.source);[ordered]@{path=$target;source_path=$r.path;sha256=$r.sha256;bytes=$r.bytes;member=$r.member;storage=$r.storage}})
Write-New (Join-Path $proof 'READABLE-BINDINGS.json') (Json-Bytes $readable)
Write-New (Join-Path $proof 'INSTRUMENT-COPY-BINDINGS.json') (Json-Bytes $copies)
Check-Sources;Check-Preparation
Write-New (Join-Path $proof 'SEAL-CHECKS.json') (Json-Bytes ([ordered]@{source_paths=1050;new_unique_payloads=63;new_bytes=2050594;external_payloads=415;external_archive_commit='4827288';current_preparations=4;current_preparation_members=797;author_root_cases=68;full_graph_pins=144;full_graph_edges=287;source_hashes_before_after_equal=$true;archived_source_execution=0;scope='Documentary seal only; archive4827288 is required'}))
Write-New (Join-Path $proof '.gitattributes') ([Text.Encoding]::ASCII.GetBytes("* -text`n"))
$out=@(Get-ChildItem -Force -LiteralPath $proof -Recurse -File|Sort-Object FullName|ForEach-Object{[ordered]@{path=[IO.Path]::GetRelativePath($proof,$_.FullName).Replace([char]92,[char]47);bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
Write-New (Join-Path $proof 'SHA256.json') (Json-Bytes ([ordered]@{files=$out}))
& (Join-Path $proof 'verify_proof.ps1') -ProofPath $proof
if(-not $?){throw 'Proof verification failed'}
[ordered]@{proof=$proof;payload_files=$out.Count;new_zip_members=63;external_members=415;zip_bytes=(Get-Item -LiteralPath (Join-Path $proof 'payloads.zip')).Length;sha256=(Get-FileHash -LiteralPath (Join-Path $proof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()}|ConvertTo-Json
