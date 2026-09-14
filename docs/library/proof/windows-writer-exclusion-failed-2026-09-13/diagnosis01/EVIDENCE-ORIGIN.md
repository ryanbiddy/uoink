# Diagnostic evidence origin

PASSIVE-JOURNAL-READ-COMMAND.ps1 transcribes the exact PowerShell command text
executed inline by the reviewer. The saved file itself was not executed.
PASSIVE-JOURNAL-READ-STDOUT.json transcribes the full displayed JSON output of
that command. No separate raw exec result object was retained for this passive
read, and none is reconstructed here. It is not a native candidate run receipt.

CALL-TAIL-DERIVED.json is a fresh data extraction from the unchanged saved
controller receipt. It contains selected receipt facts and the last110 API-name
entries with their original zero-based indices. It does not claim observed
arguments/results that the source receipt did not record.

Root independently owns the complete failed native run and its actual829f4f
tool object. This directory adds diagnosis only. All reads were limited to fixed
generated source/JSON and the explicit bounded generated journal.
