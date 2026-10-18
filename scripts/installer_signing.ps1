# Shared by the build preflight and Inno's per-file signing callback.

function Assert-UoinkSigningToken {
    param([Parameter(Mandatory)][string]$Value, [Parameter(Mandatory)][string]$Name)
    # Inno constructs a Windows command line. Permit spaces, not expansion,
    # quotes, controls or command separators in configuration paths.
    if ($Value -match '[\x00-\x1f"%!?&|<>$`^]') { throw "Unsafe character in $Name" }
}

function Assert-UoinkSigningConfiguration {
    param(
        [Parameter(Mandatory)][string]$CertificateThumbprint,
        [Parameter(Mandatory)][string]$TimestampUrl,
        [Parameter(Mandatory)][string]$SignToolPath
    )
    if ($CertificateThumbprint -notmatch '^[A-Fa-f0-9]{40}$') {
        throw 'Specify the exact 40-hex certificate thumbprint; automatic selection is forbidden'
    }
    if ($TimestampUrl -cnotmatch '^https://[A-Za-z0-9.-]+(?::443)?(?:/[A-Za-z0-9._~/-]*)?$') {
        throw 'TimestampUrl must be an explicit HTTPS RFC 3161 endpoint without credentials, query or fragment'
    }
    Assert-UoinkSigningToken $SignToolPath 'SignToolPath'
    if ($SignToolPath -notmatch '^[A-Za-z]:[\\/]' -or
        -not (Test-Path -LiteralPath $SignToolPath -PathType Leaf) -or
        [IO.Path]::GetFileName($SignToolPath) -ine 'signtool.exe') {
        throw 'SignToolPath must name an existing absolute Windows SDK signtool.exe'
    }
}

function Assert-UoinkSigningCertificate {
    param([Parameter(Mandatory)][string]$CertificateThumbprint)
    if ($CertificateThumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Invalid certificate thumbprint' }
    if (-not (Get-PSDrive -Name Cert -ErrorAction SilentlyContinue)) {
        Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
    }
    $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint" -ErrorAction Stop
    $now = [DateTime]::UtcNow
    if (-not $certificate.HasPrivateKey -or
        $certificate.NotBefore.ToUniversalTime() -gt $now -or
        $certificate.NotAfter.ToUniversalTime() -le $now) {
        throw 'Signing certificate needs an available private key and current validity'
    }
    $usages = @($certificate.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value })
    if ($usages -notcontains '1.3.6.1.5.5.7.3.3') { throw 'Certificate lacks the code-signing EKU' }
    if (-not $certificate.Verify()) { throw 'Signing certificate trust-chain verification failed' }
}

function Get-UoinkSigningPowerShellPath {
    # PSHOME names the invoking host (possibly PowerShell 7). The callback is
    # qualified against the Windows PowerShell shipped in the system directory.
    $hostPath = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $hostPath -PathType Leaf)) { throw 'Windows PowerShell signing host is missing' }
    return $hostPath
}

function Invoke-UoinkSignTool {
    param([string]$SignToolPath, [string[]]$Arguments)
    $preference = $ErrorActionPreference
    $global:LASTEXITCODE = $null
    try {
        # Preserve native stderr as diagnostic data instead of a terminating
        # Windows PowerShell error that hides the process exit status.
        $ErrorActionPreference = 'Continue'
        $output = @(& $SignToolPath @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $toolExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $preference }
    $output | Out-Host
    if ($null -ne $script:UoinkSigningDiagnostics) {
        $script:UoinkSigningDiagnostics.Add(@{operation=$Arguments[0]; exit=$toolExit; output=$output})
    }
    if ($null -eq $toolExit -or $toolExit -ne 0) { throw "SignTool returned $toolExit (warnings also reject the release)" }
}

function Get-UoinkFileSha256 {
    param([Parameter(Mandatory)][string]$FilePath)
    $stream = [IO.File]::OpenRead($FilePath)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
}

function Assert-UoinkSignedFile {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$CertificateThumbprint,
        [Parameter(Mandatory)][string]$SignToolPath
    )
    if ($CertificateThumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Invalid certificate thumbprint' }
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw 'Signed file does not exist' }
    Invoke-UoinkSignTool $SignToolPath @('verify', '/pa', '/all', '/tw', $FilePath)
    $signature = Get-AuthenticodeSignature -LiteralPath $FilePath -ErrorAction Stop
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Thumbprint -ine $CertificateThumbprint) {
        throw 'Signature must be trusted and match the selected publisher certificate'
    }
    if ($null -eq $signature.TimeStamperCertificate) { throw 'A verified timestamp is required' }
    return [ordered]@{
        path = [IO.Path]::GetFullPath($FilePath)
        sha256 = Get-UoinkFileSha256 $FilePath
        bytes = (Get-Item -LiteralPath $FilePath).Length
        signer_subject = $signature.SignerCertificate.Subject
        signer_thumbprint = $signature.SignerCertificate.Thumbprint
        timestamp_thumbprint = $signature.TimeStamperCertificate.Thumbprint
        verified_utc = [DateTime]::UtcNow.ToString('o')
        signature_verified = $true
        release_ready = $false
    }
}

function Invoke-UoinkSignFile {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$CertificateThumbprint,
        [Parameter(Mandatory)][string]$TimestampUrl,
        [Parameter(Mandatory)][string]$SignToolPath
    )
    Assert-UoinkSigningConfiguration $CertificateThumbprint $TimestampUrl $SignToolPath
    Assert-UoinkSigningCertificate $CertificateThumbprint
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw 'File to sign does not exist' }
    Invoke-UoinkSignTool $SignToolPath @('sign', '/sha1', $CertificateThumbprint,
        '/s', 'My', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256', $FilePath)
    return Assert-UoinkSignedFile $FilePath $CertificateThumbprint $SignToolPath
}

function Get-UoinkInnoSignCommand {
    param(
        [Parameter(Mandatory)][string]$PowerShellPath,
        [Parameter(Mandatory)][string]$CallbackPath,
        [Parameter(Mandatory)][string]$CertificateThumbprint,
        [Parameter(Mandatory)][string]$TimestampUrl,
        [Parameter(Mandatory)][string]$SignToolPath,
        [string]$ReceiptDirectory
    )
    Assert-UoinkSigningConfiguration $CertificateThumbprint $TimestampUrl $SignToolPath
    foreach ($path in @($PowerShellPath, $CallbackPath)) {
        Assert-UoinkSigningToken $path 'signing callback path'
        if ($path -notmatch '^[A-Za-z]:[\\/]' -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'Signing callback and PowerShell must be existing absolute files'
        }
    }
    # $f and $q are Inno substitutions. No -Command, Invoke-Expression,
    # arbitrary SignTool parameters or certificate passwords.
    $command = ('/Suoinkrelease=$q{0}$q -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $q{1}$q -FilePath $f -CertificateThumbprint {2} -TimestampUrl {3} -SignToolPath $q{4}$q' -f
        $PowerShellPath, $CallbackPath, $CertificateThumbprint, $TimestampUrl, $SignToolPath)
    if ($ReceiptDirectory) {
        Assert-UoinkSigningToken $ReceiptDirectory 'ReceiptDirectory'
        if ($ReceiptDirectory -notmatch '^[A-Za-z]:[\\/]' -or
            -not (Test-Path -LiteralPath $ReceiptDirectory -PathType Container)) {
            throw 'Signing receipt directory must be an existing absolute directory'
        }
        $command += (' -ReceiptDirectory $q{0}$q' -f $ReceiptDirectory)
    }
    return $command
}

function Write-UoinkSigningJson {
    param([Parameter(Mandatory)][string]$FilePath, [Parameter(Mandatory)]$Record, [switch]$Replace)
    $temporary = $FilePath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Record | ConvertTo-Json -Depth 8) + "`n")
    $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    try {
        if ($Replace -and [IO.File]::Exists($FilePath)) { [IO.File]::Replace($temporary, $FilePath, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $FilePath) }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function New-UoinkBuildAttempt {
    param([Parameter(Mandatory)][string]$FilePath)
    $fullPath = [IO.Path]::GetFullPath($FilePath)
    $directory = Join-Path ([IO.Path]::GetDirectoryName($fullPath)) ('signing-attempts\' + [Guid]::NewGuid().ToString('N'))
    Assert-UoinkSigningToken $directory 'build attempt directory'
    if (Test-Path -LiteralPath $directory) { throw 'Build attempt directory already exists' }
    [void][IO.Directory]::CreateDirectory($directory)
    $callbacks = Join-Path $directory 'callbacks'
    [void][IO.Directory]::CreateDirectory($callbacks)
    # Retain historical bytes before replacing the current status or invoking Inno.
    if ([IO.File]::Exists($fullPath)) { [IO.File]::Copy($fullPath, (Join-Path $directory 'previous.exe'), $false) }
    if ([IO.File]::Exists("$fullPath.signature.json")) {
        [IO.File]::Copy("$fullPath.signature.json", (Join-Path $directory 'previous.signature.json'), $false)
    }
    $attempt = [pscustomobject]@{directory=$directory; callbacks=$callbacks; path=$fullPath; receipt_path="$fullPath.signature.json"}
    Set-UoinkBuildAttemptReceipt $attempt 'pending' @{}
    return $attempt
}

function Set-UoinkBuildAttemptReceipt {
    param([Parameter(Mandatory)]$Attempt,
        [Parameter(Mandatory)][ValidateSet('pending', 'failed', 'unsigned', 'verified')][string]$Status,
        [Parameter(Mandatory)]$Details)
    if ($Status -eq 'verified' -and (-not $Details.installer.signature_verified -or @($Details.uninstallers).Count -lt 1 -or
        @($Details.uninstallers | Where-Object { $_.signature_verified -ne $true }).Count -ne 0)) {
        throw 'Verified build receipt requires installer and uninstaller verification'
    }
    $record = [ordered]@{
        status=$Status; path=$Attempt.path; attempt_directory=$Attempt.directory;
        recorded_utc=[DateTime]::UtcNow.ToString('o');
        signature_verified=($Status -eq 'verified'); release_ready=$false; details=$Details;
        sha256=$(if ($Status -eq 'verified') { $Details.installer.sha256 } else { $Details.sha256 })
    }
    Write-UoinkSigningJson (Join-Path $Attempt.directory ($Status + '.json')) $record
    Write-UoinkSigningJson $Attempt.receipt_path $record -Replace
}

function Write-UoinkSigningCallbackReceipt {
    param([Parameter(Mandatory)][string]$ReceiptDirectory, [Parameter(Mandatory)]$Record)
    if (-not (Test-Path -LiteralPath $ReceiptDirectory -PathType Container)) { throw 'Callback receipt directory is missing' }
    $path = Join-Path $ReceiptDirectory ([Guid]::NewGuid().ToString('N') + '.json')
    Write-UoinkSigningJson $path $Record
}

function Get-UoinkVerifiedBuildSignatures {
    param([Parameter(Mandatory)]$Attempt, [Parameter(Mandatory)][string]$UninstallerDirectory,
        [Parameter(Mandatory)][string]$CertificateThumbprint, [Parameter(Mandatory)][string]$SignToolPath)
    $callbacks = @(Get-ChildItem -LiteralPath $Attempt.callbacks -Filter '*.json' -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    })
    if ($callbacks.Count -lt 2 -or @($callbacks | Where-Object { $_.status -ne 'verified' }).Count -ne 0) {
        throw 'Complete successful installer and uninstaller callback evidence is required'
    }
    $uninstallers = @(Get-ChildItem -LiteralPath $UninstallerDirectory -File)
    if ($uninstallers.Count -lt 1) { throw 'Fresh signed uninstaller cache is empty' }
    $verified = @()
    foreach ($path in (@($Attempt.path) + @($uninstallers | ForEach-Object { $_.FullName }))) {
        $receipt = Assert-UoinkSignedFile $path $CertificateThumbprint $SignToolPath
        $matches = @($callbacks | Where-Object {
            $_.receipt.signature_verified -eq $true -and
            $_.receipt.sha256 -ceq $receipt.sha256 -and
            $_.receipt.signer_thumbprint -ieq $CertificateThumbprint
        })
        if ($matches.Count -lt 1) { throw 'Final file has no matching verified signing callback hash' }
        $verified += $receipt
    }
    return @{installer=$verified[0]; uninstallers=@($verified | Select-Object -Skip 1); callback_count=$callbacks.Count}
}
