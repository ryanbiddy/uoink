param(
  [Parameter(Mandatory=$true)][string]$Label,
  [Parameter(Mandatory=$true)][string]$Url,
  [ValidateSet('json','source','lfs-pointer')][string]$Kind = 'json',
  [ValidateRange(128,2097152)][int]$MaxBytes = 262144,
  [int]$ExpectedPointerBytes = 0,
  [string]$ExpectedBlobSha = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-provenance-text01'
if ($Label -cnotmatch '^[a-z0-9-]{1,80}$') { throw 'Invalid label' }
$taskUri = [Uri]$Url
if ($taskUri.Scheme -cne 'https' -or $taskUri.UserInfo -or -not $taskUri.IsDefaultPort) { throw 'Public HTTPS only' }
if ($Kind -eq 'source') {
  if ($taskUri.Host -cne 'raw.githubusercontent.com' -or $taskUri.AbsolutePath -cnotmatch '^/(m-bain/whisperX|pytorch/pytorch)/[a-f0-9]{40}/(?:.+\.(?:py|cpp|cc|h|rst|md)|LICENSE(?:\.txt)?|\.gitattributes)$') { throw 'Unapproved immutable source path' }
} else {
  if ($taskUri.Host -cne 'api.github.com' -or $taskUri.AbsolutePath -cnotmatch '^/repos/(m-bain/whisperX|pytorch/pytorch)/(?:git/(?:trees|commits|refs|ref|tags|blobs)/.+|commits(?:/.+)?|releases/tags/.+)$') { throw 'Unapproved public repository metadata path' }
  if ($taskUri.AbsolutePath -match '/git/blobs/') {
    if ($Kind -cne 'lfs-pointer' -or $ExpectedPointerBytes -lt 100 -or $ExpectedPointerBytes -gt 512 -or $ExpectedBlobSha -cnotmatch '^[a-f0-9]{40}$' -or -not $taskUri.AbsolutePath.EndsWith('/' + $ExpectedBlobSha) -or $MaxBytes -gt 8192) { throw 'Blob requires prior pointer-sized tree metadata' }
  } elseif ($Kind -eq 'lfs-pointer') { throw 'Pointer only through Git blob JSON' }
}
$attemptDir = Join-Path $taskRoot $Label
if (Test-Path -LiteralPath $attemptDir) { throw 'Fresh attempt required' }
[void](New-Item -ItemType Directory -Path $attemptDir)
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$requestRecord = [ordered]@{url=$Url;kind=$Kind;max_bytes=$MaxBytes;expected_pointer_bytes=$ExpectedPointerBytes;expected_blob_sha=$ExpectedBlobSha;utc=[DateTimeOffset]::UtcNow.ToString('o');redirects_allowed=$false;authentication=$false}
[IO.File]::WriteAllText((Join-Path $attemptDir 'request.json'), ($requestRecord | ConvertTo-Json) + "`n", $utf8)
$handler = [Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$handler.UseCookies = $false
$handler.Credentials = $null
$handler.UseDefaultCredentials = $false
$client = [Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)
$client.DefaultRequestHeaders.UserAgent.ParseAdd('uoink-source-metadata-review/1.0')
$client.DefaultRequestHeaders.Accept.ParseAdd($(if ($Kind -eq 'source') {'text/plain'} else {'application/vnd.github+json'}))
$record = [ordered]@{status='not_completed';utc_start=$requestRecord.utc;url=$Url;kind=$Kind}
$exitCode = 1
try {
  $response = $client.GetAsync($taskUri, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
  $record.http_status = [int]$response.StatusCode
  $record.content_type = $response.Content.Headers.ContentType.MediaType
  $record.advertised_bytes = $response.Content.Headers.ContentLength
  $record.headers = $response.Headers.ToString() + $response.Content.Headers.ToString()
  if ($record.content_type -notin @('application/json','text/plain','text/html')) { throw 'Nontext content type refused before body' }
  if ($null -ne $record.advertised_bytes -and $record.advertised_bytes -gt $MaxBytes) { throw 'Advertised response exceeds bound' }
  $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
  $buffer = [byte[]]::new(8192)
  $memory = [IO.MemoryStream]::new()
  while ($true) {
    $remaining = $MaxBytes + 1 - [int]$memory.Length
    if ($remaining -le 0) { throw 'Response exceeds bound' }
    $read = $stream.Read($buffer,0,[Math]::Min($buffer.Length,$remaining))
    if ($read -eq 0) { break }
    $memory.Write($buffer,0,$read)
  }
  $raw = $memory.ToArray()
  if ($raw.Length -gt $MaxBytes) { throw 'Response exceeds bound' }
  $body = $utf8.GetString($raw)
  if ($body -match '[\x00-\x08\x0B\x0C\x0E-\x1F]') { throw 'Nontext control bytes refused' }
  $record.bytes = $raw.Length
  $record.sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
  [IO.File]::WriteAllBytes((Join-Path $attemptDir 'response.txt'),$raw)
  if ([int]$response.StatusCode -ne 200) { throw 'HTTP response not 200; body preserved' }
  if ($Kind -ne 'source') {
    $metadata = $body | ConvertFrom-Json
    if ($Kind -eq 'lfs-pointer') {
      if ($metadata.sha -cne $ExpectedBlobSha -or $metadata.size -ne $ExpectedPointerBytes -or $metadata.encoding -cne 'base64') { throw 'Pointer Git metadata mismatch' }
      $pointerBytes = [Convert]::FromBase64String($metadata.content)
      if ($pointerBytes.Length -ne $ExpectedPointerBytes) { throw 'Pointer size mismatch' }
      $pointer = $utf8.GetString($pointerBytes)
      if ($pointer -cnotmatch '\Aversion https://git-lfs.github.com/spec/v1\noid sha256:[a-f0-9]{64}\nsize [0-9]{1,12}\n\z') { throw 'Exact LFS pointer text grammar refused' }
      $prefix = [Text.Encoding]::ASCII.GetBytes('blob ' + $pointerBytes.Length + [char]0)
      $gitBytes = [byte[]]::new($prefix.Length + $pointerBytes.Length)
      [Array]::Copy($prefix,0,$gitBytes,0,$prefix.Length)
      [Array]::Copy($pointerBytes,0,$gitBytes,$prefix.Length,$pointerBytes.Length)
      $blobHash = [Convert]::ToHexString([Security.Cryptography.SHA1]::HashData($gitBytes)).ToLowerInvariant()
      if ($blobHash -cne $ExpectedBlobSha) { throw 'Pointer Git blob digest mismatch' }
      [IO.File]::WriteAllBytes((Join-Path $attemptDir 'pointer.txt'),$pointerBytes)
      $record.pointer_sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($pointerBytes)).ToLowerInvariant()
      $record.pointer_git_blob_verified = $true
    }
  }
  $record.status = 'collected_text_only'
  $exitCode = 0
} catch {
  $record.status = 'refused_or_failed'
  $record.error = $_.Exception.Message
} finally {
  $record.utc_end = [DateTimeOffset]::UtcNow.ToString('o')
  $record.exit = $exitCode
  [IO.File]::WriteAllText((Join-Path $attemptDir 'result.json'), ($record | ConvertTo-Json -Depth 8) + "`n", $utf8)
  $client.Dispose()
}
[pscustomobject]$record | Select-Object status,http_status,bytes,sha256,error,exit | ConvertTo-Json -Compress
exit $exitCode
