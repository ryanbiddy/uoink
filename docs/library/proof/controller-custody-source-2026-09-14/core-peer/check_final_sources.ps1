param([Parameter(Mandatory=$true)][string]$AdapterDiff,[Parameter(Mandatory=$true)][string]$DurableDiff)
$ErrorActionPreference='Stop'
$taskReview='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-custody-source-peer01'
$taskAuthor='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-boundary-custody-repair01'
function Assert-Source([bool]$ok,[string]$why){if(-not $ok){throw $why}}
function Read-Source([string]$path){
  $f=Get-Item -LiteralPath $path
  Assert-Source (-not $f.PSIsContainer -and ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and $f.Length -le 1048576) 'Expected bounded plain text'
  return [IO.File]::ReadAllText($f.FullName)
}
function Lines-Source([string]$text){
  $lines=$text.Replace([string][char]13,'').Split([char]10)
  Assert-Source ($lines[-1] -ceq '') 'Terminal newline required'
  return $lines[0..($lines.Count-2)]
}
function Reconstruct-Source([string]$source,[string]$patch,[bool]$reverse){
  $old=@(Lines-Source $source);$p=@(Lines-Source $patch)
  Assert-Source ($p.Count -gt 2 -and $p[0].StartsWith('--- ') -and $p[1].StartsWith('+++ ')) 'Separate patch headers required'
  $out=[Collections.Generic.List[string]]::new();$cursor=0;$i=2;$hunks=0
  while($i -lt $p.Count){
    Assert-Source ($p[$i] -match '^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@') 'Hunk header'
    $a=[int]$Matches[1];$ac=1;if($Matches[2] -ne ''){$ac=[int]$Matches[2]}
    $b=[int]$Matches[3];$bc=1;if($Matches[4] -ne ''){$bc=[int]$Matches[4]}
    if($reverse){$start=$b;$consumes=$bc;$adds=$ac;$output=$a}else{$start=$a;$consumes=$ac;$adds=$bc;$output=$b}
    $target=[Math]::Max(0,$start-1)
    Assert-Source ($target -ge $cursor) 'Ordered hunks'
    while($cursor -lt $target){$out.Add($old[$cursor]);$cursor++}
    Assert-Source ($out.Count -eq [Math]::Max(0,$output-1)) 'Output hunk position'
    $c=0;$n=0;$i++;$hunks++
    while($i -lt $p.Count -and -not $p[$i].StartsWith('@@ ')){
      $line=$p[$i];Assert-Source ($line.Length -gt 0) 'Body line marker'
      $tag=$line.Substring(0,1);$body=$line.Substring(1)
      if($reverse){if($tag -ceq '+'){$tag='-'}elseif($tag -ceq '-'){$tag='+'}}
      Assert-Source ($tag -in @(' ','+','-')) 'Known body line marker'
      if($tag -ceq ' ' -or $tag -ceq '-'){Assert-Source ($cursor -lt $old.Count -and $old[$cursor] -ceq $body) 'Exact source line';$cursor++;$c++}
      if($tag -ceq ' ' -or $tag -ceq '+'){$out.Add($body);$n++}
      $i++
    }
    Assert-Source ($c -eq $consumes -and $n -eq $adds) 'Exact hunk counts'
  }
  while($cursor -lt $old.Count){$out.Add($old[$cursor]);$cursor++}
  return @{text=([string]::Join([char]10,$out)+[char]10);hunks=$hunks}
}
$taskSpecs=@(
  @{name='asr_loading_adapter.py';diff=$AdapterDiff;snapshot='coherent01\asr_loading_adapter.py';sha='227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f'},
  @{name='durable_lifecycle.py';diff=$DurableDiff;snapshot='durable-cleanup-repair04.py';sha='ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222'}
)
$taskRows=@()
foreach($spec in $taskSpecs){
  Assert-Source ($spec.diff -match '^[A-Za-z0-9_.-]+$') 'Fixed flat diff name'
  $beforePath=Join-Path $taskReview ('before\'+$spec.name)
  $currentPath=Join-Path $taskAuthor $spec.name
  $snapshotPath=Join-Path $taskReview $spec.snapshot
  $diffPath=Join-Path $taskAuthor $spec.diff
  $before=Read-Source $beforePath;$current=Read-Source $currentPath;$snapshot=Read-Source $snapshotPath;$patch=Read-Source $diffPath
  $hash=(Get-FileHash -LiteralPath $currentPath -Algorithm SHA256).Hash.ToLowerInvariant()
  Assert-Source ($hash -ceq $spec.sha -and $current -ceq $snapshot) 'Final source unchanged from reviewed snapshot'
  $forward=Reconstruct-Source $before $patch $false;$reverse=Reconstruct-Source $current $patch $true
  Assert-Source ($forward.text -ceq $current.Replace([string][char]13,'')) 'Full forward reconstruction'
  Assert-Source ($reverse.text -ceq $before.Replace([string][char]13,'')) 'Full reverse reconstruction'
  $dest=Join-Path $taskReview ('FINAL-'+$spec.diff)
  Assert-Source (-not (Test-Path -LiteralPath $dest)) 'Fresh exact diff copy'
  [IO.File]::Copy($diffPath,$dest,$false)
  $taskRows+=[ordered]@{file=$spec.name;bytes=(Get-Item -LiteralPath $currentPath).Length;sha256=$hash;snapshot_exact=$true;diff=$spec.diff;diff_sha256=(Get-FileHash -LiteralPath $diffPath -Algorithm SHA256).Hash.ToLowerInvariant();hunks=$forward.hunks;forward=$true;reverse=$true}
}
[ordered]@{scope='Independent source/data check only; no subject execution';result='PASS';comparison='Complete text, CRLF normalized to LF; source file hashes exact';sources=$taskRows}|ConvertTo-Json -Depth 6
