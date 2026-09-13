$ErrorActionPreference='Stop'
$base='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\two-wheel-license-notices01'
function Require($condition,[string]$reason){if(-not $condition){throw $reason}}
function Json([string]$relative){Get-Content -LiteralPath (Join-Path $base $relative) -Raw|ConvertFrom-Json}
function Sha([byte[]]$bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
Require ((Get-FileHash (Join-Path $base 'SHA256.json')).Hash.ToLowerInvariant() -ceq '5f6d0c52ef8e4080869ec0915d55ace294f186478520aa2222940288fb5a1475') 'Frozen notice seal differs'
$seal=Json 'SHA256.json'
Require ($seal.files.Count -eq 52 -and @(Get-ChildItem -Force -Recurse -File -LiteralPath $base).Count -eq 53) 'Notice proof membership differs'
foreach($row in $seal.files){
 Require ($row.path -notmatch '(^/|\\|:|(^|/)\.\.?(/|$))') 'Noncanonical proof path'
 $path=Join-Path $base $row.path
 Require ((Get-Item -LiteralPath $path).Length -eq $row.bytes -and (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ceq $row.sha256) 'Notice proof byte mismatch'
}
$requests=@(1..5|ForEach-Object{Json ('plan0'+$_+'.json')})
Require ($requests.Count -eq 15) 'Expected fifteen saved requests'
foreach($request in $requests){
 $receipt=Json ('responses/'+$request.id+'/receipt.json')
 $raw=[IO.File]::ReadAllBytes((Join-Path $base ('responses/'+$request.id+'/body.json')))
 Require ($request.url.StartsWith('https://api.github.com/repos/') -and $receipt.url -ceq $request.url -and $receipt.status -eq 200 -and $null -eq $receipt.error) 'Saved request differs'
 Require ($raw.Length -le 524288 -and $raw.Length -eq $receipt.bytes -and (Sha $raw) -ceq $receipt.sha256) 'Saved response differs'
}
$bindings=Json 'SOURCE-BINDINGS.json'
Require ($bindings.blobs.Count -eq 6 -and $bindings.local_inputs.Count -eq 3) 'Binding membership differs'
foreach($row in $bindings.blobs){
 $body=Json $row.response
 Require ($body.encoding -ceq 'base64' -and $body.sha -ceq $row.git_blob -and $body.size -eq $row.bytes) 'Git blob declaration differs'
 $bytes=[Convert]::FromBase64String($body.content)
 $prefix=[Text.Encoding]::ASCII.GetBytes(('blob '+$bytes.Length+[char]0))
 $gitHash=[Convert]::ToHexString([Security.Cryptography.SHA1]::HashData([byte[]]($prefix+$bytes))).ToLowerInvariant()
 Require ($gitHash -ceq $row.git_blob -and (Sha $bytes) -ceq $row.sha256 -and $bytes.Length -eq $row.bytes) 'Git blob content differs'
 Require ((Get-FileHash -LiteralPath (Join-Path $base $row.output)).Hash.ToLowerInvariant() -ceq $row.sha256) 'Materialized text differs'
}
foreach($row in $bindings.local_inputs){Require ((Get-FileHash -LiteralPath (Join-Path $base $row.target)).Hash.ToLowerInvariant() -ceq $row.sha256) 'Retained input differs'}
$inspection=Json 'inputs/inspection02.json'
Require ($bindings.retained_member_comparisons.Count -eq 2) 'Two retained comparisons required'
foreach($row in $bindings.retained_member_comparisons){
 $wheel=@($inspection.results|Where-Object package -CEQ $row.package)
 Require ($wheel.Count -eq 1 -and $wheel[0].sha256 -ceq $row.wheel_sha256) 'Inspected wheel identity differs'
 $member=@($wheel[0].inventory|Where-Object path -CEQ $row.member)
 Require ($member.Count -eq 1 -and $member[0].sha256 -ceq $row.sha256 -and $member[0].bytes -eq $row.bytes) 'Retained member differs'
 Require ((Get-FileHash -LiteralPath (Join-Path $base $row.source)).Hash.ToLowerInvariant() -ceq $row.sha256) 'Retained source differs'
}
function TreeEntry($tree,[string]$path,[string]$type,[string]$sha){
 Require ($tree.truncated -cne $true) 'Truncated source tree'
 $entry=@($tree.tree|Where-Object path -CEQ $path)
 Require ($entry.Count -eq 1 -and $entry[0].type -ceq $type -and $entry[0].sha -ceq $sha) ('Tree entry differs: '+$path)
}
$tag=Json 'responses/antlr-tag/body.json'
$commit=Json 'responses/antlr-commit/body.json'
Require ($tag.ref -ceq 'refs/tags/4.9.3' -and $tag.object.type -ceq 'commit' -and $tag.object.sha -ceq 'e4c1a74c66bd5290364ea2b36c97cd724b247357' -and $commit.sha -ceq $tag.object.sha) 'ANTLR tag/commit differs'
$rootTree=Json 'responses/antlr-root-tree/body.json'
Require ($rootTree.sha -ceq $tag.object.sha -and $rootTree.truncated -ceq $false) 'ANTLR requested commit/tree response differs'
$entries=@($rootTree.tree)
Require ($entries.Count -eq 23) 'Complete saved root tree expected'
$names=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
foreach($entry in $entries){
 Require ($entry.path -cmatch '^[A-Za-z0-9_.-]+$' -and $entry.sha -cmatch '^[0-9a-f]{40}$') 'Root tree entry spelling differs'
 $key=$entry.path
 if($entry.type -ceq 'tree'){Require ($entry.mode -ceq '040000') 'Directory mode differs';$key+='/' }
 else{Require ($entry.type -ceq 'blob' -and $entry.mode -cin @('100644','100755')) 'Blob mode differs'}
 Require (-not $names.ContainsKey($key)) 'Duplicate root tree entry'
 $names.Add($key,$entry)
}
$keys=[string[]]@($names.Keys)
[Array]::Sort($keys,[StringComparer]::Ordinal)
$treeBytes=[IO.MemoryStream]::new()
try{
 foreach($key in $keys){
  $entry=$names[$key]
  $mode=if($entry.type -ceq 'tree'){'40000'}else{$entry.mode}
  $prefix=[Text.Encoding]::ASCII.GetBytes($mode+' '+$entry.path+[char]0)
  $object=[Convert]::FromHexString($entry.sha)
  $treeBytes.Write($prefix,0,$prefix.Length)
  $treeBytes.Write($object,0,$object.Length)
 }
 $rawTree=$treeBytes.ToArray()
}finally{$treeBytes.Dispose()}
$treePrefix=[Text.Encoding]::ASCII.GetBytes('tree '+$rawTree.Length+[char]0)
$computedTree=[Convert]::ToHexString([Security.Cryptography.SHA1]::HashData([byte[]]($treePrefix+$rawTree))).ToLowerInvariant()
Require ($computedTree -ceq $commit.tree.sha -and $computedTree -ceq 'f79be338c3ed514d258f7d54e59eaac09a320c49') 'Reconstructed ANTLR tree differs from commit'
TreeEntry $rootTree 'LICENSE.txt' 'blob' '2042d1bda6c933e504d9dc2fe3197a6e42a71fe2'
TreeEntry $rootTree 'runtime' 'tree' '26883533a700a997b7791daab044f7f9b6485422'
$runtime=Json 'responses/antlr-runtime-tree/body.json'
Require ($runtime.sha -ceq '26883533a700a997b7791daab044f7f9b6485422') 'Runtime tree differs'
TreeEntry $runtime 'Python3' 'tree' '0d3cc9f6896094a259dffa11a7d649d8f72a7b24'
$python=Json 'responses/antlr-python3-tree/body.json'
Require ($python.sha -ceq '0d3cc9f6896094a259dffa11a7d649d8f72a7b24') 'Python source tree differs'
TreeEntry $python 'setup.py' 'blob' '75d0dc5f55c117e03801da4fe0f8a6552ef3f62a'
TreeEntry $python 'src/antlr4/Recognizer.py' 'blob' 'd87738be57ebfd87569615ef24de72e04094ecaf'
$commits=@(Json 'responses/proxy-commits/body.json')
Require ($commits.Count -eq 14 -and @(Json 'responses/proxy-tags/body.json').Count -eq 0) 'Saved proxy history differs'
$old=@($commits|Where-Object sha -CEQ 'f82ae43524fd6d9917b0e9490c7d0394dff8d155')
$current=@($commits|Where-Object sha -CEQ 'db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6')
Require ($old.Count -eq 1 -and $current.Count -eq 1) 'Proxy commits absent'
foreach($pair in @(@('proxy-preupload-tree',$old[0]),@('proxy-current-tree',$current[0]))){
 $tree=Json ('responses/'+$pair[0]+'/body.json')
 Require ($tree.sha -ceq $pair[1].commit.tree.sha) 'Proxy commit/tree differs'
 TreeEntry $tree 'LICENSE.txt' 'blob' '078411c7399fbc0454f36cbe8c8cdbaaba7ebc95'
 TreeEntry $tree 'proxy_tools/__init__.py' 'blob' 'ea266c8f49da949ec6199a616609637c9aab3fb8'
}
$oldTree=Json 'responses/proxy-preupload-tree/body.json'
TreeEntry $oldTree 'setup.py' 'blob' '2376239e25d530a4909c0d85437f133ef53fca73'
[ordered]@{verification='PASS';sealed_payloads=52;saved_http_responses_checked=15;decoded_git_blobs_checked=6;retained_wheel_member_matches=2;antlr_tag='4.9.3';proxy_release_commit_not_established=$true;proxy_metadata_license_conflict_preserved=$true;network_or_wheel_access=0;archived_code_executed=0;headers_values_not_available=$true}|ConvertTo-Json
