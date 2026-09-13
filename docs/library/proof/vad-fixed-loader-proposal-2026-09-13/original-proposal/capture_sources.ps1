$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOut = Join-Path $taskRoot '_scratch\vad-fixed-loader-proposal01'
$taskSpecs = @(
    @('RUN', 'whisper_runner.py', 'source/whisper_runner.py'),
    @('LOCK', 'requirements-installer-lock.txt', 'source/requirements-installer-lock.txt'),
    @('WXASR', 'installer/staging/python/Lib/site-packages/whisperx/asr.py', 'source/whisperx/asr.py'),
    @('WXVAD', 'installer/staging/python/Lib/site-packages/whisperx/vads/pyannote.py', 'source/whisperx/vads/pyannote.py'),
    @('WXSILERO', 'installer/staging/python/Lib/site-packages/whisperx/vads/silero.py', 'source/whisperx/vads/silero.py'),
    @('MODEL', 'installer/staging/python/Lib/site-packages/pyannote/audio/core/model.py', 'source/pyannote/audio/core/model.py'),
    @('TASK', 'installer/staging/python/Lib/site-packages/pyannote/audio/core/task.py', 'source/pyannote/audio/core/task.py'),
    @('PYANNET', 'installer/staging/python/Lib/site-packages/pyannote/audio/models/segmentation/PyanNet.py', 'source/pyannote/audio/models/segmentation/PyanNet.py'),
    @('SINCNET', 'installer/staging/python/Lib/site-packages/pyannote/audio/models/blocks/sincnet.py', 'source/pyannote/audio/models/blocks/sincnet.py'),
    @('GETTER', 'installer/staging/python/Lib/site-packages/pyannote/audio/pipelines/utils/getter.py', 'source/pyannote/audio/pipelines/utils/getter.py'),
    @('VADPIPE', 'installer/staging/python/Lib/site-packages/pyannote/audio/pipelines/voice_activity_detection.py', 'source/pyannote/audio/pipelines/voice_activity_detection.py'),
    @('INFERENCE', 'installer/staging/python/Lib/site-packages/pyannote/audio/core/inference.py', 'source/pyannote/audio/core/inference.py'),
    @('PIPELINE', 'installer/staging/python/Lib/site-packages/pyannote/audio/core/pipeline.py', 'source/pyannote/audio/core/pipeline.py'),
    @('MULTITASK', 'installer/staging/python/Lib/site-packages/pyannote/audio/utils/multi_task.py', 'source/pyannote/audio/utils/multi_task.py'),
    @('PARAMS', 'installer/staging/python/Lib/site-packages/pyannote/audio/utils/params.py', 'source/pyannote/audio/utils/params.py'),
    @('SINC_FB', 'installer/staging/python/Lib/site-packages/asteroid_filterbanks/param_sinc_fb.py', 'source/asteroid_filterbanks/param_sinc_fb.py'),
    @('ENCODER', 'installer/staging/python/Lib/site-packages/asteroid_filterbanks/enc_dec.py', 'source/asteroid_filterbanks/enc_dec.py'),
    @('SAFE_TORCH', 'installer/staging/python/Lib/site-packages/safetensors/torch.py', 'source/safetensors/torch.py'),
    @('SAFE_INIT', 'installer/staging/python/Lib/site-packages/safetensors/__init__.py', 'source/safetensors/__init__.py'),
    @('METRICS', 'installer/staging/python/Lib/site-packages/pyannote/audio/telemetry/metrics.py', 'source/pyannote/audio/telemetry/metrics.py'),
    @('SECURITY', 'docs/library/ASTRA-RUNTIME-SECURITY-SCOPE-2026-09-13.md', 'context/runtime-security-scope.md'),
    @('SOURCE_REVIEW', '_scratch/runtime-candidate03-source/REVIEW.md', 'context/candidate03-source-review.md'),
    @('SOURCE_BINDINGS', '_scratch/runtime-candidate03-source/source-bindings.json', 'context/candidate03-source-bindings.json'),
    @('SELECTION', '_scratch/runtime-candidate02-metadata/selection.json', 'context/candidate02-selection.json'),
    @('INVENTORY', '_scratch/vad-static-inventory-proposal01/results/run03.json', 'context/static-inventory-run03.json')
)
$taskRows = @()
foreach ($taskSpec in $taskSpecs) {
    $taskSrc = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskSpec[1]))
    $taskDest = [IO.Path]::GetFullPath((Join-Path $taskOut $taskSpec[2]))
    if (!$taskSrc.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Source outside checkout' }
    if (!$taskDest.StartsWith($taskOut + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination outside proposal' }
    if ([IO.Path]::GetExtension($taskSrc) -notin @('.py', '.txt', '.md', '.json')) { throw 'Source extension refused' }
    if (Test-Path -LiteralPath $taskDest) { throw "Refusing reused output: $($taskSpec[2])" }
    $taskBefore = (Get-FileHash -LiteralPath $taskSrc -Algorithm SHA256).Hash.ToLowerInvariant()
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($taskDest)) -Force | Out-Null
    Copy-Item -LiteralPath $taskSrc -Destination $taskDest
    $taskCopied = (Get-FileHash -LiteralPath $taskDest -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskAfter = (Get-FileHash -LiteralPath $taskSrc -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskBefore -ne $taskCopied -or $taskBefore -ne $taskAfter) { throw "Hash changed during copy: $($taskSpec[0])" }
    $taskRows += [ordered]@{key=$taskSpec[0]; source=$taskSrc; saved_file=$taskSpec[2]; bytes=(Get-Item -LiteralPath $taskSrc).Length; sha256=$taskBefore; after_sha256=$taskAfter; copied_sha256=$taskCopied}
}
$taskBindingPath = Join-Path $taskOut 'source-bindings.json'
if (Test-Path -LiteralPath $taskBindingPath) { throw 'Refusing existing bindings' }
$taskReport = [ordered]@{scope='source bytes and prior receipt only; referenced checkpoint never opened'; captured_utc=[DateTime]::UtcNow.ToString('o'); source_or_lock_files=20; context_files=5; copies=$taskRows.Count; mismatches=0; bindings=$taskRows}
[IO.File]::WriteAllText($taskBindingPath, ($taskReport | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
$taskReport | Select-Object scope, captured_utc, source_or_lock_files, context_files, copies, mismatches | ConvertTo-Json
