$ErrorActionPreference = 'Stop'
$d2Task = $PSScriptRoot
$d1Source = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d1-activated-invocation01'
$utf8 = [Text.UTF8Encoding]::new($false)
function New-Text([string]$name, [string]$value) {
    $stream = [IO.File]::Open((Join-Path $d2Task $name), [IO.FileMode]::CreateNew)
    try { $bytes = $utf8.GetBytes($value); $stream.Write($bytes) } finally { $stream.Dispose() }
}
function Replace-Exact([string]$value, [string]$before, [string]$after) {
    if (-not $value.Contains($before)) { throw 'Expected source block absent' }
    return $value.Replace($before, $after)
}
$beforeDir = Join-Path $d2Task 'before-d1'
[IO.Directory]::CreateDirectory($beforeDir) | Out-Null
foreach ($name in @('launch_d1.py','d1_child.py','run-root.ps1')) {
    [IO.File]::Copy((Join-Path $d1Source $name), (Join-Path $beforeDir $name), $false)
}
$child = [IO.File]::ReadAllText((Join-Path $beforeDir 'd1_child.py'))
$child = $child.Replace('Activated D1 static child', 'Dormant D2 conversion child')
$child = Replace-Exact $child "OWNER_DECISION_SHA256 = '3b395b5ab39d711502c69ce9c5f87ecb1587f1a9e619f713ddc3ac808c8390d2'  # Exact recorded Ryan D1-only decision." 'OWNER_DECISION_SHA256 = None  # No D2 approval exists.'
$child = $child.Replace('vad-buffer-version-approved-output','vad-fixed-converter-approved-output').Replace('d1-buffer-version-01.json','default-vad-d2-01.safetensors').Replace('D1_STATIC_VERSION_AND_BUFFERS_ONLY','D2_ONE_LOCAL_FIXED54_CONVERSION_ONLY')
$start = $child.IndexOf("MODULES = ")
$end = $child.IndexOf("HEAVY = ")
if ($start -lt 0 -or $end -le $start) { throw 'Child constants region missing' }
$constants = @'
MODULES = ('zip_bounds', 'fixed_converter', 'd2_adapter')
SOURCE_NAMES = ('d2_child.py', 'zip_bounds.py', 'fixed_converter.py', 'd2_adapter.py',
                'fixed-plan.json', 'D1-RESULT.json', 'known-inventory.json', 'D2-PROFILE.json')
READ_NAMES = SOURCE_NAMES + ('INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D2-DECISION.json')
FIXED_HASHES = {
    'fixed_converter.py': 'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b',
    'zip_bounds.py': 'bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6',
    'fixed-plan.json': '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf',
    'D1-RESULT.json': '754ca6dea6aed81de072940b35ad4c283f270b5770a88236ef55fd0a09d46e75',
    'known-inventory.json': '73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc',
    'D2-PROFILE.json': 'f0c60e2fa349b945108b4d15dccc8fe2d68ca4cab8588e8c0ff7f2e8762f75d3',
}
'@
$child = $child.Substring(0,$start) + $constants + "`n" + $child.Substring($end)
$child = $child.Replace('D1 guard denied ','D2 guard denied ').Replace('exact D1 allowance','exact D2 allowance').Replace('receipt_opens','output_opens')
$start = $child.IndexOf("        require(sha(raw['RYAN-D1-DECISION.json'])")
$end = $child.IndexOf('        bindings = ', $start)
if ($start -lt 0 -or $end -le $start) { throw 'Child decision region missing' }
$decision = @'
        require(sha(raw['RYAN-D2-DECISION.json']) == OWNER_DECISION_SHA256, 'Owner decision hash mismatch')
        decision = decode(raw['RYAN-D2-DECISION.json'])
        require(decision.get('owner') == 'Ryan' and decision.get('approved') is True
                and decision.get('scope') == SCOPE and decision.get('conversion_authorized') is True,
                'No exact D2 owner decision')
        admission = decode(raw['ROOT-ADMISSION.json'])
        require(admission.get('root_reviewed') is True and admission.get('scope') == SCOPE
                and admission.get('owner_decision_sha256') == OWNER_DECISION_SHA256
                and admission.get('run_id') == 'd2-real-01', 'Missing exact root admission')
'@
$child = $child.Substring(0,$start) + $decision + "`n" + $child.Substring($end)
$start = $child.IndexOf("        adapter, archive = ")
$end = $child.IndexOf('    except Exception as error:', $start)
if ($start -lt 0 -or $end -le $start) { throw 'Child operation region missing' }
$operation = @'
        adapter, archive = sys.modules['d2_adapter'], sys.modules['fixed_converter']
        require(adapter.OWNER_DECISION_SHA256 == OWNER_DECISION_SHA256
                and archive.REAL_PROFILE is None, 'D2 adapter pin/profile mismatch')
        # All decision, admission and evidence gates precede active artifact allowances.
        adapter._decision(raw['RYAN-D2-DECISION.json'], OWNER_DECISION_SHA256)
        adapter._admission(raw['ROOT-ADMISSION.json'], OWNER_DECISION_SHA256)
        adapter._evidence(raw['D2-PROFILE.json'], raw['D1-RESULT.json'],
                          raw['known-inventory.json'], raw['fixed-plan.json'])
        access['active'] = True
        access['invocations'] += 1
        result = adapter.run_once(archive, profile_raw=raw['D2-PROFILE.json'],
            d1_raw=raw['D1-RESULT.json'], inventory_raw=raw['known-inventory.json'],
            plan_raw=raw['fixed-plan.json'], decision_raw=raw['RYAN-D2-DECISION.json'],
            admission_raw=raw['ROOT-ADMISSION.json'])
        code = 0
'@
$child = $child.Substring(0,$start) + $operation + "`n" + $child.Substring($end)
$child = Replace-Exact $child "        code = 1`n    finally:" "        code = 2 if ((adapter is not None and isinstance(error, adapter.Refusal))`n                     or (archive is not None and isinstance(error, archive.Refusal))) else 1`n    finally:"
$child = Replace-Exact $child "        if adapter is not None:`n            adapter.D1_OWNER_APPROVAL = None" "        if archive is not None:`n            archive.REAL_PROFILE = None"
$child = $child.Replace("'inspection_result': result", "'conversion_result': result").Replace("'forbidden_conversion_calls': trapped", "'forbidden_calls': trapped")
$child = Replace-Exact $child "'adapter_owner_gate_reset': adapter is None or adapter.D1_OWNER_APPROVAL is None," "'adapter_owner_pin_unchanged': adapter is None or adapter.OWNER_DECISION_SHA256 == OWNER_DECISION_SHA256,"
New-Text 'd2_child.py' $child
$wrapper = [IO.File]::ReadAllText((Join-Path $beforeDir 'run-root.ps1'))
$wrapper = $wrapper.Replace('outer-d1-real-01','outer-d2-real-01').Replace('launch_d1.py','launch_d2.py')
New-Text 'run-root.ps1' $wrapper
Write-Output 'Prepared child/wrapper source text only; no Python, test, artifact or wrapper invocation.'
