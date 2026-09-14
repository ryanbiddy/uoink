# D2 source review findings before execution

2026-09-13. Review of dormant proposal02 found one authority-file preservation gap in two launch paths. No case, child, converter or artifact operation was executed.

`run_fake23_01.ps1` at SHA-256 `1bb8c66bdc4234adaad653a6c5da094504660e5c03f85447019bc5ae093549ec` records the fake admission hash in `plan.json` (line 53) but excludes that original file from the final before/after checks (lines 69–88). `launch_d2.py` at `d3712f745e8f5f7dd858c17e3575c42c644cf60165ac84bf977995aa1e1dec6c` rechecks the copied owner/admission files (lines 140–141), but not the originals read at lines 83–95. The resulting unchanged-input claim could survive a change to original authority records during an invocation.

The narrow correction is to bind the admission bytes actually parsed and include the original admission in the fake launcher's final integrity check; the real parent must compare its original owner/admission bytes after the child as well as the copied records. The author agreed to preserve these drafts and update the existing controls. No test assertion or converter change is required. This is an unexecuted instrument defect; there is no failed D2 measurement to reinterpret.

The preliminary fixed-text comparison independently matched all five documentary inputs to their archived sources and counted the unchanged 23 test methods. Its actual tool result is retained separately. D1 is already consumed; D2 remains unapproved.
