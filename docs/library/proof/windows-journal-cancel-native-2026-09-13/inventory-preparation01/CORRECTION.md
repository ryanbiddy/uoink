# Documentary inventory preparation correction

The first data-only inventory command failed before creating COPY-MAP.json or
any archive destination. Tool chunk 0e1390 returned exit 1 in 0.5431477 seconds.
PowerShell concatenation/comma precedence in the pair expression produced a
combined source/destination element, so the first Get-Item used both paths as one.

The failing expression was:
`$taskPairs+=,@($taskFolder[0]+'/'+$taskRel,$taskFolder[1]+'/'+$taskRel)`

The corrected recipe uses named source/destination records in a List[object],
with each value assigned separately. It also sets ErrorActionPreference=Stop
before enumeration. This repairs documentary input selection only; no candidate,
test, native observation, source assertion or original evidence changed.

PREPARATION01-TOOL-TRANSCRIPT.json transcribes the observed tool response. It is
not a separately captured raw tool object. No native result is reconstructed.
