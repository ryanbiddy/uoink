param([Parameter(Mandatory)][string]$ProofPath)
$ErrorActionPreference='Stop'
function Hash([byte[]]$Bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()}
function Canonical([string]$Name){if($Name -cnotmatch '^[A-Za-z0-9_./+\-]+$' -or $Name -match '(^/|(^|/)\.\.?(/|$)|//)'){throw 'Noncanonical proof path'}}
function Read-Bytes([string]$Path,[long]$Cap=16777216){
 $leaf=[IO.Path]::GetFullPath($Path);$cursor=$leaf
 while($cursor){$i=Get-Item -Force -LiteralPath $cursor;if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or ($cursor -cne $leaf -and -not $i.PSIsContainer)){throw 'Reparse/nondirectory path'};$p=[IO.Directory]::GetParent($cursor);$cursor=if($p){$p.FullName}else{$null}}
 $file=Get-Item -Force -LiteralPath $leaf;if($file.PSIsContainer -or $file.Length -gt $Cap){throw 'Proof input size/type'}
 $raw=[IO.File]::ReadAllBytes($leaf);if($raw.Length -gt $Cap){throw 'Proof input grew'};return ,$raw
}
$ProofPath=[IO.Path]::GetFullPath($ProofPath)
$manifestPath=Join-Path $ProofPath 'SHA256.json'
$manifest=[Text.Encoding]::UTF8.GetString((Read-Bytes $manifestPath 131072))|ConvertFrom-Json
$rows=@($manifest.files);$proofNames=@{}
foreach($r in $rows){Canonical $r.path;if($proofNames.ContainsKey($r.path)){throw 'Duplicate proof entry'};$proofNames[$r.path]=$r;$raw=Read-Bytes (Join-Path $ProofPath $r.path);if($raw.Length -ne $r.bytes -or (Hash $raw) -cne $r.sha256){throw 'Proof payload mismatch'}}
$actual=@(Get-ChildItem -Force -LiteralPath $ProofPath -Recurse -File|Where-Object FullName -CNE $manifestPath)
if($actual.Count -ne $rows.Count){throw 'Proof file count differs'}
foreach($f in $actual){$name=[IO.Path]::GetRelativePath($ProofPath,$f.FullName).Replace([char]92,[char]47);if(-not $proofNames.ContainsKey($name)){throw 'Extra proof file'}}
$plan=Get-Content -LiteralPath (Join-Path $ProofPath 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
if($plan.format -cne 'uoink-five-wheel-graph-documentary-v1' -or @($plan.files).Count -ne 1050 -or $plan.new_payloads -ne 63 -or $plan.external_payloads -ne 415){throw 'Fixed source plan differs'}
$archive='E:\AI\projects\uoink\checkouts\Yoink-library\docs\library\proof\runtime-candidate03-graph-2026-09-13'
if($plan.archive.path -cne $archive -or $plan.archive.commit -cne '4827288'){throw 'External archive reference differs'}
if((Hash (Read-Bytes (Join-Path $archive 'SHA256.json'))) -cne '793a1c4826eabc278b795d0d2fbc06c642dfb2ca1cdf42d73cc4bb8e4fb941ec' -or (Hash (Read-Bytes (Join-Path $archive 'SOURCE-PLAN.json'))) -cne '68c1a0927b3154788372026488b8332e4e66f6239736ee357a70eeab781a35e6' -or (Hash (Read-Bytes (Join-Path $archive 'payloads.zip') 33554432)) -cne '8dba369e6f9063af80ca46c725a4e41e7d893dc7cb0b7c2324feab838a4175ed'){throw 'Referenced archive changed'}
$prior=Get-Content -LiteralPath (Join-Path $archive 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
$oldHashes=@{};foreach($r in $prior.files){if($oldHashes.ContainsKey($r.sha256) -and $oldHashes[$r.sha256].bytes -ne $r.bytes){throw 'Prior hash-size conflict'};$oldHashes[$r.sha256]=$r}
$byPath=@{};$byHash=@{};$newHashes=@{};$external=@{};$sourceBytes=0L
foreach($r in $plan.files){
 Canonical $r.path;if($byPath.ContainsKey($r.path) -or $r.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $r.member -cne ('sha256/'+$r.sha256) -or $r.bytes -lt 0 -or $r.bytes -gt 16777216){throw 'Source row invalid'}
 if($byHash.ContainsKey($r.sha256) -and ($byHash[$r.sha256].bytes -ne $r.bytes -or $byHash[$r.sha256].storage -cne $r.storage)){throw 'Source duplicate differs'}
 $byPath[$r.path]=$r;$byHash[$r.sha256]=$r;$sourceBytes+=$r.bytes
 if($r.storage -ceq 'new-payload'){$newHashes[$r.sha256]=$r}
 elseif($r.storage -ceq 'archive-4827288'){if(-not $oldHashes.ContainsKey($r.sha256) -or $oldHashes[$r.sha256].bytes -ne $r.bytes){throw 'Missing external payload binding'};$external[$r.sha256]=$r}
 else{throw 'Unexpected payload storage'}
}
if($sourceBytes -ne 251301442 -or $newHashes.Count -ne 63 -or $external.Count -ne 415){throw 'Source totals differ'}
$newZip=[IO.Compression.ZipFile]::OpenRead((Join-Path $ProofPath 'payloads.zip'))
$oldZip=[IO.Compression.ZipFile]::OpenRead((Join-Path $archive 'payloads.zip'))
try{
 function Index-Zip($Zip,$Expected){
  $index=@{}
  if($Zip.Entries.Count -ne $Expected.Count){throw 'ZIP member count differs'}
  foreach($e in $Zip.Entries){if($e.FullName -cnotmatch '^sha256/[0-9a-f]{64}$' -or $index.ContainsKey($e.FullName)){throw 'Unexpected/duplicate ZIP member'};$h=$e.FullName.Substring(7);if(-not $Expected.ContainsKey($h) -or $e.Length -ne $Expected[$h].bytes -or $e.Length -gt 16777216){throw 'ZIP declared payload differs'};$index[$e.FullName]=$e}
  return $index
 }
 $newIndex=Index-Zip $newZip $newHashes;$oldIndex=Index-Zip $oldZip $oldHashes
 $checked=@{};$expanded=0L
 function Payload($Row){
  $index=if($Row.storage -ceq 'new-payload'){$newIndex}else{$oldIndex}
  $entry=$index[$Row.member];if($null -eq $entry){throw 'Missing payload'}
  $stream=$entry.Open();$memory=[IO.MemoryStream]::new()
  try{$buffer=[byte[]]::new(8192);while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0){if($memory.Length+$n -gt $Row.bytes){throw 'Expanded member exceeds bound'};$memory.Write($buffer,0,$n)};$raw=$memory.ToArray()}finally{$stream.Dispose();$memory.Dispose()}
  if($raw.Length -ne $Row.bytes -or (Hash $raw) -cne $Row.sha256){throw 'ZIP payload bytes differ'}
  return ,$raw
 }
 foreach($r in $byHash.Values){$raw=Payload $r;$expanded+=$raw.Length;if($expanded -gt 134217728){throw 'Expanded total bound'};$checked[$r.sha256]=$true}
 $bindings=@(Get-Content -LiteralPath (Join-Path $ProofPath 'MANIFEST-BINDINGS.json') -Raw|ConvertFrom-Json)
 if($bindings.Count -ne 4){throw 'Preparation bindings absent'}
 $count=0
 foreach($b in $bindings){
  $m=$byPath[$b.manifest_path];if($m.sha256 -cne $b.manifest_sha256){throw 'Manifest pin differs'}
  $original=@([Text.Encoding]::UTF8.GetString((Payload $m))|ConvertFrom-Json)
  if($original.Count -ne $b.count -or @($b.members).Count -ne $b.count){throw 'Manifest count differs'}
  for($i=0;$i -lt $original.Count;$i++){$r=$original[$i];$bound=$b.members[$i];$source=$byPath[$b.root+'/'+$r.path];if($r.path -cne $bound.path -or $r.bytes -ne $bound.bytes -or $r.sha256 -cne $bound.sha256 -or $source.sha256 -cne $r.sha256 -or $source.storage -cne $bound.storage -or -not $checked.ContainsKey($r.sha256)){throw 'Manifest closure differs'}}
  $count+=$b.count
 }
 if($count -ne 797){throw 'Manifest member total differs'}
 $readable=@(Get-Content -LiteralPath (Join-Path $ProofPath 'READABLE-BINDINGS.json') -Raw|ConvertFrom-Json)
 foreach($r in $readable){Canonical $r.path;$source=$byPath[$r.source_path];$copy=$proofNames[$r.path];if($copy.sha256 -cne $source.sha256 -or $copy.bytes -ne $source.bytes -or $r.sha256 -cne $source.sha256 -or $r.storage -cne $source.storage){throw 'Readable copy differs'}}
}finally{$newZip.Dispose();$oldZip.Dispose()}
[ordered]@{proof_files=$rows.Count;source_paths=1050;new_members=63;referenced_members=415;current_manifest_rows=797;verified_payloads=$checked.Count;archive_required='4827288';archived_code_executed=$false;valid=$true}|ConvertTo-Json
