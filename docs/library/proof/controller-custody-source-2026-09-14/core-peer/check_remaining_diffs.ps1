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

$taskPairs=@(
 @{name='asr_loading_adapter.py';before='before\rejected-asr_loading_adapter.py';diff='asr_loading_adapter.from-rejected.final03.diff'},
 @{name='durable_lifecycle.py';before='before\rejected-durable_lifecycle.py';diff='durable_lifecycle.from-rejected.final03.diff'},
 @{name='durable_lifecycle.py';before='before\pre-review-cleanup03-durable_lifecycle.py';diff='CLEANUP-ERROR-REPAIR03.diff'}
)
$rows=@()
foreach($pair in $taskPairs){
  $before=Read-Source (Join-Path $taskAuthor $pair.before)
  $current=Read-Source (Join-Path $taskAuthor $pair.name)
  $patch=Read-Source (Join-Path $taskAuthor $pair.diff)
  $forward=Reconstruct-Source $before $patch $false
  $reverse=Reconstruct-Source $current $patch $true
  Assert-Source ($forward.text -ceq $current.Replace([string][char]13,'')) 'Remaining full forward'
  Assert-Source ($reverse.text -ceq $before.Replace([string][char]13,'')) 'Remaining full reverse'
  $src=Join-Path $taskAuthor $pair.diff;$dst=Join-Path $taskReview ('FINAL-'+$pair.diff)
  Assert-Source (-not (Test-Path -LiteralPath $dst)) 'Fresh diff copy'
  [IO.File]::Copy($src,$dst,$false)
  $rows+=[ordered]@{before=$pair.before;after=$pair.name;diff=$pair.diff;sha256=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant();hunks=$forward.hunks;forward=$true;reverse=$true}
}
[ordered]@{scope='Passive rejected-origin and cleanup diff checks only';result='PASS';pairs=$rows}|ConvertTo-Json -Depth 6

