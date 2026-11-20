# One-command Uoink smoke test (Windows). Dev only, never shipped.
# Seeds an isolated library, starts the helper hidden on a non-5179 port, runs the
# API, CLI, dashboard, accessibility and extension suites, stops the helper and
# prints a pass/fail table. Arguments pass through to scripts/qa_smoke.py, e.g.
#   .\scripts\qa_smoke.ps1 --suites api
#   .\scripts\qa_smoke.ps1 --break search-500
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = if ($env:UOINK_QA_PYTHON) { $env:UOINK_QA_PYTHON } else { "python" }
if (-not $env:PLAYWRIGHT_BROWSERS_PATH) {
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $repo "_scratch\ms-playwright"
}
& $python (Join-Path $repo "scripts\qa_smoke.py") @args
exit $LASTEXITCODE
