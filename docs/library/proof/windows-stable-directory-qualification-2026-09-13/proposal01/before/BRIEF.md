# Generated creation-handle transfer qualification proposal

Root requested one new 70-case union because staged acquisition changes the
shared WindowsGateRegistry.acquire path. Use all 65 corrected cases unchanged
from windows-reservation-implementation-proposal02, plus five new focused
creation-transfer cases. Both original failed63/2 and corrected65 observations
remain historical, unchanged. No prior admission applies to this new run.

Only windows_reservation_port.py changes relative to that corrected baseline:
bootstrap may stage a still-retained handle, then acquire transfers that owner
before further identity queries. Creation authority is still a separate private
ticket. The new cases exercise same-handle/no-reopen transfer, retention after
post-transfer failure, duplicate/foreign handles, changed/nonempty identity and
absence of creation authority. They do not prove CREATE_NEW or Windows behavior.

Reuse the existing isolated C:\Python314 -I -S -B runner and ten final guards.
Retain all 65 case bodies/assertions and append the five methods without altering
fixture services. The exact native bootstrap/setup helper is excluded: no ctypes,
OS kernel, actual generated fixture, journal, model or installed-asset access.
The fixed fake services are the only source execution proposed here.

The launcher binds all 29 inputs, PINS and a new root admission, scrubs provider
and Python/proxy environment overrides, sets IG_FORBIDDEN_LIVE before startup,
and captures the actual global native exit immediately after return. Fresh label
creation-transfer01 only. Preserve every outcome; any failure requires diagnosis
and a documented repair before a new label. No execution is admitted by this brief.
