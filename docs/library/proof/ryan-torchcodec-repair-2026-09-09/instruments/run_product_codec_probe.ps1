$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProfile=Join-Path $taskRepo '_scratch\python313-graph-01\profile'
$taskKeyNames=@(Get-ChildItem Env: | Where-Object { $_.Name -match 'API_KEY$|_TOKEN$|_SECRET$|^CLAUDE_CODE_USE_|^GOOGLE_APPLICATION_CREDENTIALS$' } | ForEach-Object Name)
foreach ($taskKeyName in $taskKeyNames) { Remove-Item -LiteralPath ('Env:\'+$taskKeyName) }
foreach ($taskName in @('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR','HF_HOME','TORCH_HOME','MPLCONFIGDIR')) { [Environment]::SetEnvironmentVariable($taskName,$taskProfile,'Process') }
$env:HF_HUB_OFFLINE='1';$env:TRANSFORMERS_OFFLINE='1';$env:HF_HUB_DISABLE_TELEMETRY='1';$env:PYTHONDONTWRITEBYTECODE='1'
$env:UOINK_INDEX_PATH=Join-Path $taskProfile 'unused-index.db'
$env:PATH=$env:SystemRoot+'\System32;'+$env:SystemRoot
& (Join-Path $taskRepo '_scratch\python313-graph-01\python\python.exe') -I -B (Join-Path $taskRepo '_scratch\probe_torchcodec_product.py')
exit $LASTEXITCODE
