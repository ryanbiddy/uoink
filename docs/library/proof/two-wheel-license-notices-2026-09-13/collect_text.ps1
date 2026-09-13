param([Parameter(Mandatory)][string]$Plan)
$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$rows=Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$handler=[Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect=$false
$handler.UseDefaultCredentials=$false
$handler.UseProxy=$false
$client=[Net.Http.HttpClient]::new($handler)
$client.Timeout=[TimeSpan]::FromSeconds(25)
$client.DefaultRequestHeaders.UserAgent.ParseAdd('uoink-license-evidence/1.0')
$client.DefaultRequestHeaders.Accept.ParseAdd('application/vnd.github+json')
try {
 foreach($row in $rows){
  $uri=[Uri]$row.url
  if($uri.Scheme -cne 'https' -or $uri.Host -cne 'api.github.com' -or $uri.UserInfo -or $row.id -cnotmatch '^[a-z0-9-]+$'){throw 'Unsupported request'}
  if($uri.AbsolutePath -cnotmatch '^/repos/(antlr/antlr4|jtushman/proxy_tools|pallets/werkzeug)/'){throw 'Outside named official repositories'}
  $dir=Join-Path $base ('responses/'+$row.id)
  if(Test-Path -LiteralPath $dir){throw 'Reused request label'}
  [IO.Directory]::CreateDirectory($dir)|Out-Null
  $record=[ordered]@{url=$row.url;started_utc=[DateTime]::UtcNow.ToString('o');status=$null;content_type=$null;headers=$null;bytes=0;sha256=$null;error=$null}
  $resp=$null;$stream=$null;$memory=[IO.MemoryStream]::new()
  try {
   $resp=$client.GetAsync($uri,[Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
   $record.status=[int]$resp.StatusCode
   $record.content_type=[string]$resp.Content.Headers.ContentType
   $record.headers=([string]$resp.Headers)+([string]$resp.Content.Headers)
   if($record.content_type -notmatch '^application/json'){throw 'Non-JSON response refused'}
   $stream=$resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
   $buffer=[byte[]]::new(8192)
   while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0){
    if($memory.Length+$n -gt 524288){throw '512 KiB response bound exceeded'}
    $memory.Write($buffer,0,$n)
   }
   $bytes=$memory.ToArray()
   [void][Text.UTF8Encoding]::new($false,$true).GetString($bytes)
   if($record.status -ne 200){$record.error='HTTP status is not 200; response preserved'}
  } catch {$record.error=$_.Exception.Message} finally {
   $bytes=$memory.ToArray()
   [IO.File]::WriteAllBytes((Join-Path $dir 'body.json'),$bytes)
   $record.bytes=$bytes.Length
   $record.sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
   $record.finished_utc=[DateTime]::UtcNow.ToString('o')
   [IO.File]::WriteAllText((Join-Path $dir 'receipt.json'),($record|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
   if($stream){$stream.Dispose()};if($resp){$resp.Dispose()};$memory.Dispose()
  }
  [pscustomobject]$record|Select-Object url,status,bytes,error|ConvertTo-Json -Compress
 }
}finally{$client.Dispose();$handler.Dispose()}
