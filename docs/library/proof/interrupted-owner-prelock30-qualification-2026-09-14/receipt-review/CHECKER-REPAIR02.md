# Passive checker path-literal correction

The first independent checker returned exit 1 in actual 3de2aa at its plan/startup predicate. It incorrectly expected doubled backslashes in PowerShell string values, confusing JSON display escaping with the decoded path. Its following argument predicate made the same mistake by doubling a constructed path.

Passive diagnostic 319fb7, exit 0, inspected the saved plan and decoded character codes: both paths use single backslashes (character 92). The fixed values are the ordinary `C:\Python314\python.exe` literal and the direct fixed `Join-Path` result. All other checks are unchanged. The initial checker is retained as `check_receipts.before02.ps1`, and its actual failure is CHECK01-ACTUAL.json. RESULT.json did not exist at diagnosis.

This is a checker correction, not a changed source, fixture, run or acceptance rule. No candidate was run by the failed checker or diagnostic. Earlier VIEW02 displays parsed UTC timestamps in local time; VIEW03 retains their original raw +00:00 text. The underlying receipts remain unchanged.
