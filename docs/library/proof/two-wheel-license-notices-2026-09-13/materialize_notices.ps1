$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$utf8=[Text.UTF8Encoding]::new($false,$true)
if(Test-Path -LiteralPath (Join-Path $base 'notices')){throw 'Fresh materialization required'}
[IO.Directory]::CreateDirectory((Join-Path $base 'notices'))|Out-Null
[IO.Directory]::CreateDirectory((Join-Path $base 'source-text'))|Out-Null
[IO.Directory]::CreateDirectory((Join-Path $base 'inputs'))|Out-Null
$sources=@(
 @{id='antlr-license';target='notices/antlr4-python3-runtime-4.9.3-LICENSE.txt';blob='2042d1bda6c933e504d9dc2fe3197a6e42a71fe2';size=2699},
 @{id='proxy-license';target='notices/proxy-tools-0.1.0-UPSTREAM-LICENSE.txt';blob='078411c7399fbc0454f36cbe8c8cdbaaba7ebc95';size=1436},
 @{id='proxy-preupload-setup';target='source-text/proxy-setup.py.txt';blob='2376239e25d530a4909c0d85437f133ef53fca73';size=715},
 @{id='proxy-init';target='source-text/proxy-init.py.txt';blob='ea266c8f49da949ec6199a616609637c9aab3fb8';size=6409},
 @{id='antlr-setup';target='source-text/antlr-setup.py.txt';blob='75d0dc5f55c117e03801da4fe0f8a6552ef3f62a';size=527},
 @{id='antlr-recognizer';target='source-text/antlr-Recognizer.py.txt';blob='d87738be57ebfd87569615ef24de72e04094ecaf';size=5383}
)
$bindings=@()
foreach($s in $sources){
 $raw=Join-Path $base ('responses/'+$s.id+'/body.json')
 $j=Get-Content -LiteralPath $raw -Raw|ConvertFrom-Json
 if($j.encoding -cne 'base64' -or $j.sha -cne $s.blob -or $j.size -ne $s.size){throw 'Blob declaration mismatch'}
 $bytes=[Convert]::FromBase64String($j.content)
 [void]$utf8.GetString($bytes)
 $header=[Text.Encoding]::ASCII.GetBytes(('blob '+$bytes.Length+[char]0))
 $gitHash=[Convert]::ToHexString([Security.Cryptography.SHA1]::HashData([byte[]]($header+$bytes))).ToLowerInvariant()
 if($bytes.Length -ne $s.size -or $gitHash -cne $s.blob){throw 'Git blob bytes mismatch'}
 $path=Join-Path $base $s.target
 [IO.File]::WriteAllBytes($path,$bytes)
 $bindings+=@{response=('responses/'+$s.id+'/body.json');output=$s.target;bytes=$bytes.Length;git_blob=$gitHash;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$local=@(
 @{source='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-candidate02-metadata\evidence\pypi\antlr4-python3-runtime.json';target='inputs/antlr-pypi.json';sha256='f3f53611a3b5160738057d4b46b7a9d3a89c8655d16365a18257af6115668f15'},
 @{source='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-candidate02-metadata\evidence\pypi\proxy-tools.json';target='inputs/proxy-pypi.json';sha256='2af8516a011b42c20188191bfc6e78829d01a0ec083d226c5961dce876b2dfd0'},
 @{source='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\two-wheel-inspection02\inspection02.json';target='inputs/inspection02.json';sha256='950e4ff459397921765ad3aad43ae0120acd0d9efd27460c4560c12430948c0c'}
)
foreach($s in $local){
 if((Get-FileHash -LiteralPath $s.source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $s.sha256){throw 'Retained input changed'}
 [IO.File]::Copy($s.source,(Join-Path $base $s.target),$false)
 if((Get-FileHash -LiteralPath (Join-Path $base $s.target) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $s.sha256){throw 'Copy changed'}
}
$inspection=Get-Content -LiteralPath (Join-Path $base 'inputs/inspection02.json') -Raw|ConvertFrom-Json
$comparisons=@()
foreach($pair in @(@{package='proxy-tools';member='proxy_tools/__init__.py';source='source-text/proxy-init.py.txt'},@{package='antlr4-python3-runtime';member='antlr4/Recognizer.py';source='source-text/antlr-Recognizer.py.txt'})){
 $wheel=@($inspection.results|Where-Object package -CEQ $pair.package)
 $member=@($wheel.inventory|Where-Object path -CEQ $pair.member)
 if($wheel.Count -ne 1 -or $member.Count -ne 1){throw 'Missing exact wheel member'}
 $actual=(Get-FileHash -LiteralPath (Join-Path $base $pair.source) -Algorithm SHA256).Hash.ToLowerInvariant()
 if($actual -cne $member[0].sha256){throw 'Upstream source and retained wheel member differ'}
 $comparisons+=@{package=$pair.package;member=$pair.member;source=$pair.source;sha256=$actual;bytes=$member[0].bytes;equal=$true;wheel_sha256=$wheel[0].sha256;actual_wheel_read_in_this_invocation=$false}
}
$receipt=@{materialized_utc=[DateTime]::UtcNow.ToString('o');blobs=$bindings;local_inputs=$local;retained_member_comparisons=$comparisons;model_or_package_execution=$false}
[IO.File]::WriteAllText((Join-Path $base 'SOURCE-BINDINGS.json'),($receipt|ConvertTo-Json -Depth 12),$utf8)
$receipt|ConvertTo-Json -Depth 10
