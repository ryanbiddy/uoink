2026-09-13. Astra reviewed the preserved vpr01 setup failure, the exact one-line
UTF-16LE preload repair, the new input hashes, and the unchanged reader and
launchers. The repair loads a fixed stdlib codec before import closure. It does
not change the malformed-input fixture, any of the 76 assertions, or the guard.

Admit one author vpr02 run from proposal02 after verifying its 25-payload seal,
the original 26 preparation payloads, and the separate 22 failure payloads.
Use the unchanged launch.py and run-root.ps1 with a separate root admission
JSON binding the ten exact input hashes. Set IG_FORBIDDEN_LIVE to the forbidden
live index path before the outer invocation; do not access that path. Retain
actual child, launcher and tool exits, including any setup failure. No real
artifact, model, native package, network or installation operation is admitted.

This admission qualifies only the reviewed generated-input experiment. It
does not authenticate caller-supplied synthetic profiles or constructed result
objects. If it passes, a separately labeled independent root repetition may
use the same bytes and protocol. Any further failure needs a documented repair
and a fresh label before another attempt.
