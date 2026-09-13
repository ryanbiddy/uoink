$ErrorActionPreference='Stop'
$base=Join-Path (Get-Location) '_scratch/two-wheel-inspection02'
$r=Get-Content -LiteralPath (Join-Path $base 'inspection02.json') -Raw|ConvertFrom-Json
$launch=Get-Content -LiteralPath (Join-Path $base 'launch-inspection02/result.json') -Raw|ConvertFrom-Json
if($r.inspection_status -cne 'VALID' -or $r.exit -ne 0 -or $null -ne $r.error -or @($r.results).Count -ne 2 -or @($r.guard.violations).Count -ne 0 -or $r.guard.startup_binding -cne $true){throw 'Invalid inspection'}
if($launch.actual_native_exit -ne 0 -or $launch.intended_outer_exit -ne 0 -or $launch.instrumentation_verdict -cne 'VALID' -or $null -ne $launch.postcheck_error){throw 'Invalid launch'}
$expected=@(
    @{path='_scratch/python313-graph-01/cache/wheels/d5/b3/74/a35b66048c9de6631cd74cbc9475e6feb3e69a467983446bd8/antlr4_python3_runtime-4.9.3-py3-none-any.whl';bytes=144613;sha='d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37';members=61},
    @{path='_scratch/python313-graph-01/cache/wheels/1b/86/84/a8355e4f91698784a475f3eb40500d31a57c528e3217758043/proxy_tools-0.1.0-py3-none-any.whl';bytes=2943;sha='a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68';members=5}
)
$checked=@()
for($i=0;$i -lt 2;$i++){
    $plan=$expected[$i];$item=$r.results[$i];$p=Join-Path (Get-Location) $plan.path
    if([IO.Path]::GetFullPath($p) -cne [IO.Path]::GetFullPath($item.path)){throw 'Fixed wheel path mismatch'}
    $raw=[IO.File]::ReadAllBytes($p)
    $sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
    if($raw.Length -ne $plan.bytes -or $sha -cne $plan.sha -or $item.sha256 -cne $sha -or $item.bytes -ne $raw.Length){throw 'Whole wheel identity mismatch'}
    $memory=[IO.MemoryStream]::new($raw,$false)
    $zip=[IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Read)
    try{
        if($zip.Entries.Count -ne $plan.members -or $item.member_count -ne $plan.members -or @($item.inventory).Count -ne $plan.members){throw 'Wheel membership mismatch'}
        $seen=@{};$expanded=0L;$recordText=$null;$recordName=$null
        foreach($entry in $zip.Entries){
            if($entry.Length -gt 262144 -or $seen.ContainsKey($entry.FullName)){throw 'Member bound or duplicate'}
            $stream=$entry.Open();$content=[IO.MemoryStream]::new();$buffer=[byte[]]::new(65536)
            try{while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0){if($content.Length+$n -gt 262144){throw 'Expanded bound'};$content.Write($buffer,0,$n)};$bytes=$content.ToArray()}finally{$stream.Dispose();$content.Dispose()}
            $digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
            $rows=@($item.inventory|Where-Object {$_.path -ceq $entry.FullName})
            if($rows.Count -ne 1 -or $rows[0].sha256 -cne $digest -or $rows[0].bytes -ne $bytes.Length -or $bytes.Length -ne $entry.Length){throw 'Inventory member mismatch'}
            $seen[$entry.FullName]=@{bytes=$bytes.Length;record_hash='sha256='+[Convert]::ToBase64String([Security.Cryptography.SHA256]::HashData($bytes)).TrimEnd('=').Replace('+','-').Replace('/','_')}
            $selected=$item.selected_text.PSObject.Properties[$entry.FullName]
            if($null -ne $selected -and [Text.UTF8Encoding]::new($false,$true).GetString($bytes) -cne $selected.Value){throw 'Selected text mismatch'}
            if($entry.FullName.EndsWith('/RECORD',[StringComparison]::Ordinal)){$recordName=$entry.FullName;$recordText=[Text.UTF8Encoding]::new($false,$true).GetString($bytes)}
            $expanded+=$bytes.Length
        }
        if($expanded -ne $item.expanded_bytes -or $null -eq $recordText){throw 'Expanded/RECORD mismatch'}
        $recorded=@{}
        foreach($line in ($recordText -split '\r?\n')){
            if($line -ceq ''){continue};$fields=$line.Split(',')
            if($fields.Count -ne 3 -or -not $seen.ContainsKey($fields[0]) -or $recorded.ContainsKey($fields[0])){throw 'RECORD membership mismatch'}
            $recorded[$fields[0]]=$true
            if($fields[0] -ceq $recordName){if($fields[1] -cne '' -or $fields[2] -cne ''){throw 'RECORD self row'}}
            elseif($fields[1] -cne $seen[$fields[0]].record_hash -or $fields[2] -cne [string]$seen[$fields[0]].bytes){throw 'RECORD digest/size mismatch'}
        }
        if($recorded.Count -ne $plan.members){throw 'Incomplete RECORD'}
        $checked += [ordered]@{package=$item.package;bytes=$raw.Length;sha256=$sha;members=$seen.Count;record_rows=$recorded.Count;expanded_bytes=$expanded;missing_dist_info_license_text=$item.license_text_missing}
    }finally{$zip.Dispose();$memory.Dispose()}
}
$manifest=Join-Path $base 'PREPARATION-HASHES.json'
if((Get-FileHash -LiteralPath $manifest).Hash.ToLowerInvariant() -cne '7ea8f1951bbbc7324bda36ab5528df19a864b45c0738a9a970235b704f465b42'){throw 'Preparation changed'}
$rows=@(Get-Content -LiteralPath $manifest -Raw|ConvertFrom-Json)
if($rows.Count -ne 28){throw 'Preparation count mismatch'}
foreach($row in $rows){if((Get-FileHash -LiteralPath (Join-Path $base $row.path)).Hash.ToLowerInvariant() -cne $row.sha256){throw 'Preparation input changed'}}
foreach($saved in @($r.source_hashes_after,$launch.input_hashes_before,$launch.input_hashes_after)){
    if(($saved|ConvertTo-Json -Depth 4 -Compress) -cne ($rows|ConvertTo-Json -Depth 4 -Compress)){throw 'Before/after source rows mismatch'}
}
[ordered]@{verification='PASS';method='Independent .NET ZIP/member and RECORD hashing; no extraction or code execution';wheels=$checked;preparation_inputs=28;script_execution_or_installation=$false;license_notices_still_open=$true}|ConvertTo-Json -Depth 4
