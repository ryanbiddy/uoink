# Ship the attribution index and exact supplemental upstream texts.
# Confirm-Hash deletes a mismatched cache file, so do not use it on source notices.
$noticeRoot = Join-Path $RepoRoot 'third-party-notices'
$noticePins = @{
    'antlr4-python3-runtime-4.9.3-LICENSE.txt' = 'b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a'
    'proxy-tools-0.1.0-UPSTREAM-LICENSE.txt' = 'a428fb8a2e762af3eb0a6edbbb88e9b42ccfee80fd9b423958bcacf9b9abbfe4'
}
$noticeLock = @(Get-Content -LiteralPath $InstallerLock | ForEach-Object { $_.Trim() })
foreach ($noticePin in @('antlr4-python3-runtime==4.9.3', 'proxy_tools==0.1.0')) {
    if (@($noticeLock | Where-Object { $_ -ceq $noticePin }).Count -ne 1) {
        throw "Supplemental notice version requires review: $noticePin"
    }
}
foreach ($noticeName in $noticePins.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $noticeRoot $noticeName) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $noticePins[$noticeName]) {
        throw "Upstream notice bytes differ: $noticeName"
    }
}
New-Item -ItemType Directory -Force -Path (Join-Path $StagingDir 'third-party-notices') | Out-Null
foreach ($noticeRelative in @('THIRD-PARTY-NOTICES.md', 'third-party-notices\README.md',
        'third-party-notices\antlr4-python3-runtime-4.9.3-LICENSE.txt',
        'third-party-notices\proxy-tools-0.1.0-UPSTREAM-LICENSE.txt')) {
    $noticeSource = Join-Path $RepoRoot $noticeRelative
    $noticeTarget = Join-Path $StagingDir $noticeRelative
    $noticeHash = (Get-FileHash -LiteralPath $noticeSource -Algorithm SHA256).Hash
    Copy-Item -LiteralPath $noticeSource -Destination $noticeTarget -Force
    if ((Get-FileHash -LiteralPath $noticeSource -Algorithm SHA256).Hash -cne $noticeHash -or
        (Get-FileHash -LiteralPath $noticeTarget -Algorithm SHA256).Hash -cne $noticeHash) {
        throw "Staged notice bytes differ: $noticeRelative"
    }
}

