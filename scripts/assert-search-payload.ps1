param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
# Inspect the finished stage, including unexpected files left by earlier builds.
$resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
foreach ($entry in Get-ChildItem -LiteralPath $resolvedRoot -Recurse -Force) {
    $relative = $entry.FullName.Substring($resolvedRoot.Length).Replace('\', '/')
    if ($relative -match '(?i)(^|/)(_scratch|embeddinggemma-300m-onnx-q8-v1)(/|$)' -or
        $entry.Name -match '(?i)^(embeddinggemma-terms\.json|search-settings\.json|search-vectors\.db|model_quantized\.onnx)([._-].*)?$') {
        throw "Search model or private search state in package: $relative"
    }
}
