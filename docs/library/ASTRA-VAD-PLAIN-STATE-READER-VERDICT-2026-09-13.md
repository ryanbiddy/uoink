2026-09-13. Accept the fixed plain-state reader as a qualified synthetic proposal.
It has no real artifact authority and is not installed or wired into the product.
The next integration needs the approved converter output and a reviewed bridge
to fresh CPU/F32 tensors; neither is supplied by this result.

Author vpr03 and independent Astra vpr04 each passed the same 82 cases, with zero
failures or skips, in 0.744954 and 0.739920 seconds. Exact case/result sequences,
input hashes and generated fixture identity agree. Child, launcher and invoking
tool exits were all zero. Guards were valid, inputs unchanged, stderr empty,
and no unexpected event or heavy import occurred. These are 82 distinct cases
repeated twice, not 164 distinct cases.

The first attempt, vpr01, failed before case functions ran because the guard
blocked a lazy UTF-16LE codec import during malformed-fixture construction.
Its secondary launcher JSONDecodeError and all exits 1 remain recorded. A
reviewed explicit codec preload preserved every fixture and assertion. The
next attempt, vpr02, completed 75 passed/1 failed with valid guard and all exits 1:
deep JSON reached the schema check instead of the expected malformed-JSON
refusal. The source repair now bounds structural nesting before parsing.

The depth-three limit matches the fixed root/descriptor/array format. A bounded
byte scan respects strings and escapes and checks the cooperative deadline
every 1024 bytes. The JSON parser still validates syntax and UTF-8; the scanner
alone is not a complete parser. All 76 original assertions remain unchanged;
six new cases cover boundary, escaping, pre-parser refusal and deadline behavior.
No failed result was relabeled. The separate preparer LF/CRLF assumption failure
and its documentary repair are also retained.

Reader SHA-256: 3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c.
Harness SHA-256: 354bb3341b23dd37f8d04f3254fdbbbf4f715e7a08220abe6dbe04075924945f.
The reviewed fixed 54-tensor schema covers 1,472,999 F32 elements and 5,891,996
data bytes. The generated complete fixture is 5,896,708 bytes,
SHA-256 31b6222a3c31569e81da0597dc3ef339511cdee543114001cd989b6fddfba1d1.
Whole-input identity precedes header parsing; exact names, shapes, offsets,
dense coverage, finite values and canonical encoding remain required.

Astra independently verified the 187 proof payloads, 885,205 bytes, six original
seals and 179 original disk copies. Seal SHA-256:
ac90903b83855c29c66d82a6a135a54045c113f67f9edf7b2f5b3475c6ea3eb7.
Evidence is in proof/vad-plain-state-reader-2026-09-13. Preparation copies retain
only their original seal membership; later runs are enclosed separately.

Real purpose is unconditionally refused, even if REAL_PROFILE is assigned.
Caller-created profiles, evidence digests and VerifiedState objects do not
authenticate authority. A native caller must independently bind approved bytes
and revalidate before constructing tensors. No real checkpoint, converted model,
native package, model constructor, inference or installation was exercised.
Production remains e8d058f; the historical full-tree failure and release hold
remain. Website and marketing have not started.
