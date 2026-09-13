Preparation only. Root must review the exact sealed reader, full harness,
launch.py, run-root.ps1, both prequalification repair notes, source bindings and
admission template before admitting execution. The template is deliberately
false and cannot launch a passing run by itself.

Root records its verdict separately and makes a fresh admission JSON from
ROOT-ADMISSION.TEMPLATE.json, retaining all exact source hashes and the fixed
generated-synthetic-plain-state-only scope. Set root_reviewed to true, cite the
review document and use an unused vprNN label. Do not edit the sealed template.

The prepared invocation from the checkout is:

```powershell
& '.\_scratch\vad-plain-state-reader-proposal01\run-root.ps1' -Admission '<absolute path to root admission JSON>'
```

The wrapper launches the already-known C:\Python314\python.exe with -I -S -B.
The child receives only generated synthetic fixtures and four copied text inputs.
No private model runtime or original embedded interpreter is involved. Expected
membership is the 76 exact IDs in EXPECTED-CASES.json; no count is passed yet.

Retain runs/vprNN and its actual-exit.json, stdout.json, stderr.log, copied inputs,
root admission and launch plan. Retain the corresponding outer timestamp folder
including command, logs and actual-exit.json. A guard failure invalidates the
qualification regardless of assertion counts. Do not relabel a failure or
overwrite an existing run. No real artifact or native execution is authorized.
