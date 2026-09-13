param([Parameter(Mandatory=$true)][string]$ProofPath)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$proof=[IO.Path]::GetFullPath($ProofPath)
function Digest([byte[]]$Bytes) { [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant() }
function Relative-Name([string]$Name) {
    if($Name -cnotmatch '^[A-Za-z0-9_./+\-]+$' -or $Name -match '(^/|(^|/)\.\.?(/|$)|//)'){throw 'Invalid proof/member path'}
}
function Chain([string]$Path) {
    $leaf=[IO.Path]::GetFullPath($Path);$cursor=$leaf
    while($cursor) {
        $item=Get-Item -Force -LiteralPath $cursor
        if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Linked proof path'}
        if($cursor -cne $leaf -and -not $item.PSIsContainer){throw 'Nondirectory proof ancestor'}
        $parent=[IO.Directory]::GetParent($cursor);$cursor=if($null -eq $parent){$null}else{$parent.FullName}
    }
}
function Read-File([string]$Name,[long]$Cap=4194304) {
    Relative-Name $Name;$path=Join-Path $proof $Name;Chain $path
    $file=Get-Item -Force -LiteralPath $path
    if($file.PSIsContainer -or $file.Length -gt $Cap){throw 'Proof file bound/type'}
    $bytes=[IO.File]::ReadAllBytes($path);if($bytes.Length -gt $Cap){throw 'Proof file grew'}
    return ,$bytes
}
Chain $proof
$manifest=([Text.Encoding]::UTF8.GetString((Read-File 'SHA256.json' 131072))|ConvertFrom-Json)
$rows=@($manifest.files)
if($rows.Count -lt 10 -or $rows.Count -gt 100){throw 'Proof membership bound'}
$files=@{}
foreach($row in $rows) {
    Relative-Name $row.path
    if($row.path -ceq 'SHA256.json' -or $files.ContainsKey($row.path) -or $row.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $row.bytes -lt 0 -or $row.bytes -gt 157286400){throw 'Invalid root manifest row'}
    $path=Join-Path $proof $row.path;Chain $path;$item=Get-Item -Force -LiteralPath $path
    if($item.PSIsContainer -or $item.Length -ne $row.bytes -or (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -cne $row.sha256){throw 'Root proof hash differs'}
    $files[$row.path]=$row
}
$actual=@(Get-ChildItem -Force -LiteralPath $proof -File -Recurse)
if($actual.Count -ne $rows.Count+1){throw 'Proof contains extra/missing files'}
foreach($file in $actual){$name=[IO.Path]::GetRelativePath($proof,$file.FullName).Replace([char]92,[char]47);if($name -cne 'SHA256.json' -and -not $files.ContainsKey($name)){throw 'Unsealed proof file'}}
$plan=([Text.Encoding]::UTF8.GetString((Read-File 'SOURCE-PLAN.json'))|ConvertFrom-Json)
if($plan.format -cne 'uoink-graph-documentary-source-plan-v1' -or @($plan.files).Count -ne 2266 -or $plan.source_files -ne 2266 -or $plan.source_bytes -gt 1073741824 -or $plan.unique_payloads -gt 1000 -or $plan.unique_bytes -gt 134217728){throw 'Source map scope/bounds'}
$paths=@{};$members=@{};$logicalBytes=0L
foreach($row in $plan.files) {
    Relative-Name $row.path
    if($paths.ContainsKey($row.path) -or $row.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $row.member -cne ('sha256/'+$row.sha256) -or $row.bytes -lt 0 -or $row.bytes -gt 16777216){throw 'Invalid source-to-member mapping'}
    if([IO.Path]::GetFullPath($row.source) -cne [IO.Path]::GetFullPath((Join-Path $plan.scratch_root $row.path))){throw 'Source identity mapping differs'}
    if($members.ContainsKey($row.member) -and $members[$row.member].bytes -ne $row.bytes){throw 'Conflicting payload size'}
    $members[$row.member]=$row;$paths[$row.path]=$row;$logicalBytes+=$row.bytes
}
if($logicalBytes -ne $plan.source_bytes -or $members.Count -ne $plan.unique_payloads){throw 'Source map totals differ'}
$zipPath=Join-Path $proof 'payloads.zip';Chain $zipPath
if((Get-Item -LiteralPath $zipPath).Length -gt 157286400){throw 'ZIP size bound'}
$archive=[IO.Compression.ZipFile]::OpenRead($zipPath)
$seen=@{};$expanded=0L;$lastName=$null
try {
    if($archive.Entries.Count -ne $members.Count){throw 'ZIP member count differs'}
    foreach($entry in $archive.Entries) {
        $name=$entry.FullName
        if($name -cnotmatch '^sha256/[0-9a-f]{64}$' -or $seen.ContainsKey($name) -or -not $members.ContainsKey($name)){throw 'Extra/duplicate ZIP member'}
        if($null -ne $lastName -and [StringComparer]::Ordinal.Compare($lastName,$name) -ge 0){throw 'ZIP member order differs'}
        $lastName=$name;$expected=$members[$name]
        if($entry.Length -ne $expected.bytes -or $entry.Length -gt 16777216 -or $entry.ExternalAttributes -ne 0 -or $entry.LastWriteTime.DateTime -ne [DateTime]::new(1980,1,1,0,0,0)){throw 'ZIP size/header differs'}
        $stream=$entry.Open();$hash=[Security.Cryptography.IncrementalHash]::CreateHash([Security.Cryptography.HashAlgorithmName]::SHA256)
        $buffer=[byte[]]::new(65536);$readTotal=0L
        try {while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0){$readTotal+=$n;if($readTotal -gt $expected.bytes -or $readTotal -gt 16777216){throw 'Expanded member exceeds bound'};$hash.AppendData($buffer,0,$n)};$digest=[Convert]::ToHexString($hash.GetHashAndReset()).ToLowerInvariant()}
        finally {$hash.Dispose();$stream.Dispose()}
        if($readTotal -ne $expected.bytes -or $digest -cne $expected.sha256){throw 'ZIP payload hash differs'}
        $expanded+=$readTotal;if($expanded -gt 134217728){throw 'Expanded total bound'}
        $seen[$name]=$true
    }
    if($expanded -ne $plan.unique_bytes){throw 'Expanded total differs'}
    function Read-ArchivedJson([string]$LogicalPath) {
        if(-not $paths.ContainsKey($LogicalPath)){throw 'Referenced source absent'}
        $row=$paths[$LogicalPath];if($row.bytes -gt 4194304){throw 'Archived JSON bound'}
        $entry=$archive.GetEntry($row.member);$stream=$entry.Open();$memory=[IO.MemoryStream]::new()
        try {$buffer=[byte[]]::new(65536);while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0){if($memory.Length+$n -gt $row.bytes){throw 'Archived JSON grew'};$memory.Write($buffer,0,$n)};$bytes=$memory.ToArray()}
        finally {$memory.Dispose();$stream.Dispose()}
        if($bytes.Length -ne $row.bytes -or (Digest $bytes) -cne $row.sha256){throw 'Archived JSON binding differs'}
        return ([Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json)
    }
    $bindings=@([Text.Encoding]::UTF8.GetString((Read-File 'MANIFEST-BINDINGS.json'))|ConvertFrom-Json)
    foreach($binding in $bindings) {
        if($paths[$binding.manifest_path].sha256 -cne $binding.manifest_sha256){throw 'Original manifest hash not preserved'}
        $original=@(Read-ArchivedJson $binding.manifest_path)
        if($original.Count -ne $binding.count -or @($binding.members).Count -ne $binding.count){throw 'Original manifest membership differs'}
        for($i=0;$i -lt $original.Count;$i++) {
            $o=$original[$i];$b=$binding.members[$i]
            if($o.path -cne $b.path -or $o.bytes -ne $b.bytes -or $o.sha256 -cne $b.sha256 -or $b.member -cne ('sha256/'+$o.sha256) -or -not $seen.ContainsKey($b.member) -or $members[$b.member].bytes -ne $o.bytes -or $paths[$b.source_witness].sha256 -cne $o.sha256){throw 'Original manifest payload not retained'}
            if($binding.kind -eq 'current' -and $paths[($binding.current_root+'/'+$o.path)].sha256 -cne $o.sha256){throw 'Current manifest source mapping differs'}
        }
    }
    $captureManifest=Read-ArchivedJson 'runtime-candidate02-metadata/evidence/SHA256.json'
    if(@($captureManifest.PSObject.Properties).Count -ne 313 -or $paths['runtime-candidate02-metadata/evidence/SHA256.json'].sha256 -cne '216571a9f97de87ed96ad61dc64262a3703e2395c913a871e9df7eb692ed431d'){throw 'Original313 manifest differs'}
    foreach($property in $captureManifest.PSObject.Properties){if($paths[('runtime-candidate02-metadata/evidence/'+$property.Name)].sha256 -cne $property.Value){throw 'Original313 member differs'}}
} finally {$archive.Dispose()}
$readable=@([Text.Encoding]::UTF8.GetString((Read-File 'READABLE-BINDINGS.json'))|ConvertFrom-Json)
foreach($copy in $readable){Relative-Name $copy.path;if($files[$copy.path].sha256 -cne $copy.sha256 -or $files[$copy.path].bytes -ne $copy.bytes -or $paths[$copy.original_path].sha256 -cne $copy.sha256 -or $paths[$copy.original_path].member -cne $copy.member){throw 'Readable exact-copy binding differs'}}
$instrumentCopies=@([Text.Encoding]::UTF8.GetString((Read-File 'INSTRUMENT-COPY-BINDINGS.json'))|ConvertFrom-Json)
foreach($copy in $instrumentCopies){Relative-Name $copy.path;if($files[$copy.path].sha256 -cne $copy.sha256 -or $files[$copy.path].bytes -ne $copy.bytes){throw 'Instrument copy binding differs'}}
if([Text.Encoding]::ASCII.GetString((Read-File '.gitattributes')) -cne "* -text`n"){throw 'Proof byte attributes missing'}
[ordered]@{verification='PASS';proof=$proof;root_payloads=$rows.Count;mapped_source_paths=$paths.Count;zip_members=$seen.Count;expanded_bytes=$expanded;original_manifests=$bindings.Count;original313=313;extracted_or_executed_files=0;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $proof 'SHA256.json')).Hash.ToLowerInvariant()}|ConvertTo-Json
