$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$proposal = Join-Path $repo '_scratch\real-startup-authority-repair01'
function Pin([string]$path) {
    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Nonplain text input' }
    if ($item.Length -gt 1048576) { throw 'Text input cap' }
    [pscustomobject]@{bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function PutNew([string]$path,[byte[]]$bytes) {
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
}
function Lines([string]$path) {
    $value=[IO.File]::ReadAllText($path).Replace("`r`n","`n")
    if(-not $value.EndsWith("`n")) {throw 'Terminal newline required'}
    ,$value.Substring(0,$value.Length-1).Split("`n")
}
function Write-StartupDiff([string]$oldPath,[string]$newPath,[string]$outPath,[string]$oldName,[string]$newName) {
    $old=Lines $oldPath; $new=Lines $newPath
    $prefix=0
    while($prefix -lt [Math]::Min($old.Count,$new.Count) -and $old[$prefix] -ceq $new[$prefix]) {$prefix++}
    $suffix=0
    while($suffix -lt [Math]::Min($old.Count-$prefix,$new.Count-$prefix) -and $old[$old.Count-$suffix-1] -ceq $new[$new.Count-$suffix-1]) {$suffix++}
    if($prefix -eq $old.Count -and $prefix -eq $new.Count) {throw 'Expected nonempty source delta'}
    $start=[Math]::Max(0,$prefix-3); $tail=[Math]::Min(3,$suffix)
    $oldCount=$old.Count-$suffix-$start+$tail; $newCount=$new.Count-$suffix-$start+$tail
    $patch=[Collections.Generic.List[string]]::new()
    $patch.Add('--- '+$oldName); $patch.Add('+++ '+$newName)
    $patch.Add(('@@ -{0},{1} +{2},{3} @@' -f ($start+1),$oldCount,($start+1),$newCount))
    for($i=$start;$i -lt $prefix;$i++) {$patch.Add(' '+$old[$i])}
    for($i=$prefix;$i -lt $old.Count-$suffix;$i++) {$patch.Add('-'+$old[$i])}
    for($i=$prefix;$i -lt $new.Count-$suffix;$i++) {$patch.Add('+'+$new[$i])}
    for($i=0;$i -lt $tail;$i++) {$patch.Add(' '+$old[$old.Count-$suffix+$i])}
    $text=($patch -join "`n")+"`n"
    PutNew $outPath ([Text.UTF8Encoding]::new($false).GetBytes($text))
    # Independently consume the emitted rows in each direction against the full
    # source text, including context and the remaining unchanged tail.
    foreach($reverse in @($false,$true)) {
        $inputLines=if($reverse){$new}else{$old}; $expected=if($reverse){$old}else{$new}
        $result=[Collections.Generic.List[string]]::new(); $position=0; $read=0; $written=0
        while($position -lt $start){$result.Add($inputLines[$position]);$position++}
        foreach($line in $patch.GetRange(3,$patch.Count-3)) {
            $kind=$line.Substring(0,1);$payload=$line.Substring(1)
            if($reverse){if($kind -ceq '+'){$kind='-'}elseif($kind -ceq '-'){$kind='+'}}
            if($kind -ceq ' ' -or $kind -ceq '-') {
                if($position -ge $inputLines.Count -or $inputLines[$position] -cne $payload){throw 'Patch input mismatch'}
                $position++;$read++
            }
            if($kind -ceq ' ' -or $kind -ceq '+') {$result.Add($payload);$written++}
        }
        if($read -ne $(if($reverse){$newCount}else{$oldCount}) -or $written -ne $(if($reverse){$oldCount}else{$newCount})){throw 'Hunk count mismatch'}
        while($position -lt $inputLines.Count){$result.Add($inputLines[$position]);$position++}
        if(($result -join "`n") -cne ($expected -join "`n")){throw 'Full reconstruction mismatch'}
    }
    [pscustomobject]@{path=[IO.Path]::GetFileName($outPath);forward=$true;reverse=$true;old_count=$oldCount;new_count=$newCount}
}

$before=Join-Path $proposal 'before\asr_loading_adapter.py'
if((Pin $before).sha256 -ne '635d2c22db75d12ffe6965fb656fdca47450ccbbaeb4d8cc8aaff9fcc79dd243'){throw 'Original adapter changed'}
$original=[IO.File]::ReadAllBytes($before)
$addition=[IO.File]::ReadAllBytes((Join-Path $proposal 'startup_addition.py.txt'))
$current=Join-Path $proposal 'asr_loading_adapter.py'
[IO.File]::WriteAllBytes($current,[byte[]]($original+$addition))
$actual=[IO.File]::ReadAllBytes($current)
for($i=0;$i -lt $original.Length;$i++){if($actual[$i] -ne $original[$i]){throw 'Qualified adapter prefix changed'}}
$patches=@(
    (Write-StartupDiff $before $current (Join-Path $proposal 'asr_loading_adapter.diff') 'before/asr_loading_adapter.py' 'asr_loading_adapter.py'),
    (Write-StartupDiff (Join-Path $proposal 'before\asr_loading_adapter-before-consume01.py') $current (Join-Path $proposal 'review-corrections.diff') 'before/asr_loading_adapter-before-consume01.py' 'asr_loading_adapter.py'),
    (Write-StartupDiff (Join-Path $proposal 'before\startup_authority_fixture-draft01.py') (Join-Path $proposal 'startup_authority_fixture.py') (Join-Path $proposal 'startup_authority_fixture.diff') 'before/startup_authority_fixture-draft01.py' 'startup_authority_fixture.py'),
    (Write-StartupDiff (Join-Path $proposal 'before\test_startup_authority-draft01.py') (Join-Path $proposal 'test_startup_authority.py') (Join-Path $proposal 'test_startup_authority.diff') 'before/test_startup_authority-draft01.py' 'test_startup_authority.py')
)
$sources=@(
    @('_scratch/windows-interrupted-owner-native-proposal02/asr_loading_adapter.py','before/asr_loading_adapter.py','qualified adapter; full'),
    @('_scratch/windows-interrupted-owner-native-proposal02/trusted_asr_resolver.py','inputs/trusted_asr_resolver.py','qualified resolver; full'),
    @('_scratch/windows-interrupted-owner-native-proposal02/snapshot_lifecycle.py','inputs/snapshot_lifecycle.py','qualified lifecycle; 1-46 and 123-386'),
    @('_scratch/windows-interrupted-owner-native-proposal02/durable_lifecycle.py','inputs/durable_lifecycle.py','qualified durable connection; 1-78 and 374-576'),
    @('_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py','inputs/snapshot_reservations.py','qualified reservation; 31-58,213-283,371-426'),
    @('_scratch/windows-interrupted-owner-native-proposal02/reservation_file_port.py','inputs/reservation_file_port.py','unchanged fixture dependency; byte binding only'),
    @('_scratch/protected-engine-ownership-repair02/owned_generation_protocol.py','inputs/owned_generation_protocol.py','qualified bootstrap reference; targeted startup/owner methods'),
    @('_scratch/windows-reservation-implementation-proposal02/test_reservations.py','inputs/test_reservations.py','unchanged inert fixture; 1-80,534-588,703-722'),
    @('_scratch/windows-interrupted-owner-native-proposal02/generated_adapter_flow.py','inputs/generated_adapter_flow.py','unchanged generated-route reference; 690-849 plus symbol inventory')
)
[IO.Directory]::CreateDirectory((Join-Path $proposal 'inputs')) | Out-Null
$originals=@(foreach($source in $sources){
    $path=Join-Path $repo $source[0];$destination=Join-Path $proposal $source[1];$pin=Pin $path
    if($source[1] -ne 'before/asr_loading_adapter.py'){PutNew $destination ([IO.File]::ReadAllBytes($path))}
    if((Pin $destination).sha256 -ne $pin.sha256){throw 'Original input copy mismatch'}
    [pscustomobject]@{source=$source[0];copy=$source[1];bytes=$pin.bytes;sha256=$pin.sha256;scope=$source[2]}
})
$methods=[regex]::Matches([IO.File]::ReadAllText((Join-Path $proposal 'test_startup_authority.py')),'(?m)^    def (test_[a-z0-9_]+)\(self\):')
$ids=@($methods|ForEach-Object{'test_startup_authority.ControllerStartupContracts.'+$_.Groups[1].Value})
if($ids.Count -ne 16 -or @($ids|Select-Object -Unique).Count -ne 16){throw 'Proposed case membership mismatch'}
$caseText=([pscustomobject]@{scope='proposed and unexecuted';count=$ids.Count;cases=$ids}|ConvertTo-Json -Depth 5)+"`n"
PutNew (Join-Path $proposal 'EXPECTED-CASES.json') ([Text.UTF8Encoding]::new($false).GetBytes($caseText))
$derivatives=@(foreach($name in @('asr_loading_adapter.py','startup_authority_fixture.py','test_startup_authority.py','startup_addition.py.txt','EXPECTED-CASES.json','asr_loading_adapter.diff','review-corrections.diff','startup_authority_fixture.diff','test_startup_authority.diff','REPORT.md','SOURCE-CORRECTIONS.md','FIXTURE-LOADER-CONTRACT.md')){
    $pin=Pin (Join-Path $proposal $name);[pscustomobject]@{path=$name;bytes=$pin.bytes;sha256=$pin.sha256}
})
$contexts=@(foreach($name in @('docs/library/REAL-STARTUP-AUTHORITY-REPAIR-BRIEF-2026-09-14.md','docs/library/proof/real-engine-connection-plan-2026-09-14/plan/BRIEF.md','docs/library/proof/real-engine-connection-plan-2026-09-14/plan/SOURCE-INPUTS.json','docs/library/ASTRA-REAL-ENGINE-CONNECTION01-FAILURE-2026-09-14.md','_scratch/real-engine-connection01-namespace-peer/VERDICT.md','_scratch/real-engine-connection01-owner-peer/VERDICT.md','_scratch/protected-engine-ownership-fake39-author01/qualify_owner.py')){
    $pin=Pin (Join-Path $repo $name);[pscustomobject]@{path=$name;bytes=$pin.bytes;sha256=$pin.sha256}
})
$map=[pscustomobject]@{schema='uoink.controller-startup-source-bindings.v1';scope='source and proposed tests only; no execution admission';original_inputs=$originals;derivatives=$derivatives;context_inputs=$contexts;qualified_adapter_prefix_bytes=$original.Length;qualified_adapter_prefix_unchanged=$true;new_case_count=16;patch_reconstruction=$patches;real_authority_populated=$false;child_transport_implemented=$false;candidate_executed=$false}
PutNew (Join-Path $proposal 'SOURCE-INPUTS.json') ([Text.UTF8Encoding]::new($false).GetBytes(($map|ConvertTo-Json -Depth 8)+"`n"))
[pscustomobject]@{status='SOURCE_TEXT_BINDINGS_PREPARED';adapter=(Pin $current);map=(Pin (Join-Path $proposal 'SOURCE-INPUTS.json'));original_inputs=$originals.Count;derivatives=$derivatives.Count;cases=$ids.Count;patches=$patches;original_prefix_bytes=$original.Length;candidate_executed=$false}|ConvertTo-Json -Depth 6
