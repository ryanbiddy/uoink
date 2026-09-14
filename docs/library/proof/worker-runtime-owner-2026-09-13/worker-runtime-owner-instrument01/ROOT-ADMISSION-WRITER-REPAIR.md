2026-09-13. Root preparation6f04e8 exited1 before writing admission or invoking
the qualifier. PowerShell member enumeration makes PSObject.Properties.Count
yield per-property Count values; it is not the property collection count.
Use @(admission.input_sha256.PSObject.Properties).Count to check the15 entries.
Retain the original actual tool result. The input pins, cases, qualifier and
launcher are unchanged. The next root admission preparation may create the
previously absent ROOT-ADMISSION.json after exact input verification. Only then
may root execute the first rto01 observation. No test result exists for this
preparation failure, and no failed measurement is relabeled.
