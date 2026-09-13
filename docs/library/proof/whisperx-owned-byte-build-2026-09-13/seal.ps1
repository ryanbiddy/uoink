$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
function Assert-That($Condition,[string]$Reason) { if (-not $Condition) { throw $Reason } }
function Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Save-New([string]$Path,[byte[]]$Data) {
    $stream = [IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try { $stream.Write($Data,0,$Data.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Json-Here([string]$Name) { return Get-Content -LiteralPath (Join-Path $base $Name) -Raw | ConvertFrom-Json }
Assert-That (-not (Test-Path -LiteralPath (Join-Path $base 'SHA256.json'))) 'Refuse resealing'
Assert-That ((Hash (Join-Path $base 'SOURCE-COPY-MAP.json')) -ceq '61eca821c33056bb083d8cea0d70257d67f0ca7a48f8c6fa390339f30dbe7d65') 'Original copy map changed'
$authorMap = Json-Here 'SOURCE-COPY-MAP.json'
$rootRows = @(Json-Here 'ROOT-COPY-BINDINGS.json')
Assert-That ($authorMap.files.Count -eq 28 -and $rootRows.Count -eq 2) 'Copy map counts'
$rows = @($authorMap.files) + $rootRows
foreach ($row in $rows) {
    Assert-That ($row.path -notmatch '(^/|\\|:|(^|/)\.\.?(/|$))') 'Noncanonical copy path'
    foreach ($path in @($row.source,(Join-Path $base $row.path))) {
        $item = Get-Item -LiteralPath $path
        Assert-That (-not $item.PSIsContainer -and $item.Length -eq $row.bytes -and $item.Length -le 262144 -and
            -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -and (Hash $path) -ceq $row.sha256) 'Copy/source identity mismatch'
    }
}
Assert-That ((Hash (Join-Path $base 'root/verify_whisperx_byte_build_root01.py')) -ceq
    '078606ff5c23e02bce9faa770ee1d388985a06f00496eb08b6a781371c550755') 'Root verifier identity'
Assert-That ((Hash (Join-Path $base 'prior-seal/owned-contracts217-SHA256.json')) -ceq
    '144d6b9a05b58a82ce7fbb4f129e2e90ff82e00f2748b7e81f92566abd2ff4bd') 'Original 217-payload seal changed'
$actual = Json-Here 'launch-proposal/ACTUAL-BUILD01-OUTER-TOOL.json'
$launch = Json-Here 'launch-proposal/launch-build01/result.json'
$build = Json-Here 'build-receipts/result.json'
$verify = Json-Here 'build-receipts/independent-verification.json'
$rootActual = Json-Here 'root/WHISPERX-BYTE-BUILD-ROOT01-ACTUAL.json'
$rootResult = $rootActual.output | ConvertFrom-Json
$wheelHash = '0c23ec175b663eaafe9955ff93b1ccc6e93ed66a61665951baac5799a75c92d4'
Assert-That ($actual.exit_code -eq 0 -and $actual.chunk_id -ceq '405e18' -and
    $launch.status -ceq 'BYTE_BUILD_VERIFIED' -and $launch.intended_outer_exit -eq 0 -and
    $null -eq $launch.instrumentation_error -and $launch.phases.Count -eq 2) 'Author outcome mismatch'
Assert-That (($launch.before | ConvertTo-Json -Depth 10 -Compress) -ceq ($launch.after | ConvertTo-Json -Depth 10 -Compress)) 'Author before/after identity mismatch'
Assert-That ($launch.before.inputs.Count -eq 46 -and $launch.before.instruments.Count -eq 5 -and
    $launch.before.runtime.Count -eq 34) 'Author identity counts'
foreach ($mode in @('build','verify')) {
    $native = Json-Here ('launch-proposal/launch-build01/' + $mode + '-actual-native-exit.json')
    $guard = Json-Here ('launch-proposal/launch-build01/' + $mode + '-guard.json')
    Assert-That ($native.actual_native_exit -eq 0 -and $native.native_type -ceq 'System.Int32' -and
        $guard.exit -eq 0 -and $guard.guard_valid -eq $true -and $guard.violations.Count -eq 0 -and
        $guard.preloaded_heavy.Count -eq 0 -and $guard.postloaded_heavy.Count -eq 0 -and
        $guard.metadata_wrappers_installed -eq $true -and $guard.finder_installed -eq $true -and
        $guard.startup_binding -eq $true) 'Native/guard mismatch'
    Assert-That ((Get-Item -LiteralPath (Join-Path $base ('launch-proposal/launch-build01/' + $mode + '-stderr.log'))).Length -eq 0) 'Nonempty stderr'
}
foreach ($value in @($build,$verify,$rootResult.byte_verification)) {
    Assert-That ($value.sha256 -ceq $wheelHash -and $value.bytes -eq 134793 -and $value.members -eq 22) 'Wheel receipt identity mismatch'
}
Assert-That ($build.exit -eq 0 -and $verify.exit -eq 0 -and $verify.record_rows -eq 22 -and
    $verify.all_payloads_verified -eq $true -and $verify.complete_byte_layout_verified -eq $true) 'Author byte verification mismatch'
Assert-That ($rootActual.exit_code -eq 0 -and $rootActual.chunk_id -ceq '6edd74' -and $rootResult.status -ceq 'ROOT_BYTE_VERIFIED' -and
    $rootResult.byte_verification.record_rows -eq 22 -and $rootResult.byte_verification.all_payloads_verified -eq $true -and
    $rootResult.byte_verification.complete_byte_layout_verified -eq $true -and $rootResult.source_files_rechecked -eq 46 -and
    $rootResult.instruments_rechecked -eq 5 -and $rootResult.runtime_identity_rows_compared -eq 34 -and
    $rootResult.runtime_files_read_by_root -eq 0 -and $rootResult.bound_files_unchanged -eq 64 -and
    $rootResult.wheel_imported_or_installed -eq $false -and $rootResult.model_executed -eq $false) 'Root verification mismatch'
Save-New (Join-Path $base '.gitattributes') ([Text.Encoding]::ASCII.GetBytes("* -text`n"))
$receipt = [ordered]@{status='DOCUMENTARY_VERIFIED'; copied_payloads=30; source_and_copy_hashes_verified=$true;
    author_outer_exit=0; author_native_phases=2; root_outer_exit=0; wheel_sha256=$wheelHash; wheel_bytes=134793; members=22; record_rows=22;
    wheel_bytes_copied=$false; test_or_build_rerun=$false; model_or_runtime_binary_read=$false;
    prior217_manifest_preserved=$true; historical_maps_preserved=$true; finished_utc=[DateTime]::UtcNow.ToString('o')}
Save-New (Join-Path $base 'SEAL-VERIFICATION.json') ([Text.UTF8Encoding]::new($false).GetBytes(($receipt|ConvertTo-Json -Depth 6) + "`n"))
$manifest = @()
foreach ($file in @(Get-ChildItem -LiteralPath $base -File -Recurse)) {
    $name = [IO.Path]::GetRelativePath($base,$file.FullName).Replace([char]92,[char]47)
    Assert-That ($file.Extension -notin @('.whl','.dll','.pyd','.bin','.pt','.npz') -and $file.Length -le 262144) 'Unexpected artifact payload'
    $manifest += [ordered]@{path=$name; bytes=$file.Length; sha256=(Hash $file.FullName)}
}
Assert-That ($manifest.Count -eq 38) 'Expected 30 copied payloads plus eight reports/maps/instruments/attributes'
$manifest = @($manifest|Sort-Object { $_.path } -CaseSensitive)
Save-New (Join-Path $base 'SHA256.json') ([Text.UTF8Encoding]::new($false).GetBytes(($manifest|ConvertTo-Json -Depth 5) + "`n"))
[ordered]@{status='SEALED'; payloads=38; manifest_sha256=(Hash (Join-Path $base 'SHA256.json'))} | ConvertTo-Json -Compress
