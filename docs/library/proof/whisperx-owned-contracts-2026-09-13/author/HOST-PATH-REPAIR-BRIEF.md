# Outer host-path repair — 2026-09-13

The first outer attempt failed with tool exit 1 before the reviewed launcher or
Python started. The command incorrectly named
`C:\Program Files\PowerShell\7\pwsh.exe`. Tool bc920e reported that command was
not recognized. `actual-outer-tool-result.json` retains the actual tool object.
This is a failed invocation with zero cases, not a failed or passed test suite.

Read-only diagnosis in tool 169d9e found the current shell is PowerShell 7.6.5
and `Get-Command pwsh` resolves to
`C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe`.
Both `launch-qualification01` and `runs/qualification01` are absent. The exact
manifest and launcher still match root's original admission.

The proposed repair changes only the outer executable path. No launcher,
source, fixture, assertion, input manifest or child label changes. A fresh root
admission is required before the following command is used once:

```powershell
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\whisperx-owned-builder-proposal01\run_preflight01.ps1' -ExpectedManifestSha256 '5602d0e46f91739c40799e0ce2592560274cc70c252421f856d3cf77133bcd9f'
```

Preserve its actual outer result under the separate name
`actual-outer-tool-result-host02.json`; do not replace the original failure.
The child and launch labels remain fresh because neither directory was created.
The scope remains exactly 50 inert cases. No wheel publication, model/native
runtime, asset access, installation or broader rerun is authorized here.
