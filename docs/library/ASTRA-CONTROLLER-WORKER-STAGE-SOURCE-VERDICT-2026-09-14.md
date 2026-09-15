# Controller worker-stage source verdict — 2026-09-14

The smaller stage unit is ready for guarded qualification preparation. Root
and an independent reviewer found no blocking source issue. No test has run,
and this verdict grants no native or model authority.

The frozen source map is
`0fd7fe35f9936d1a102f5c1b70962b7df6ae022d34f7fb4c6ffb9959484e2835`.
Adapter `2f12cbf5` preserves all 28,922 bytes of accepted `6482b782`, then appends
6,046 bytes. Fixture `3996ca48`, tests `1c893756` and expected IDs `7fc70f1b`
define 14 proposed controls. The rejected Gemini child connection is excluded.

The new API requires an issued startup, its permit and consuming session,
an exact non-None worker and one of two explicit stages. It checks the retained
release/profile/admission, lease, record, reservation and worker bindings under
manager-then-reservation locks. During `finish_start`, the session is reserved
and unpublished. After factory publication, the record is running and the same
worker is in the session. Missing, incompatible, changed or revoked bindings
refuse. The check returns the existing startup and calls no lower service.

The fixture uses the actual startup/lease/factory path. Its inert create hook
returns the inherited generated worker; unchanged durable code retains, binds,
attempts resume and publishes it. Normal cleanup uses the existing close and
lease confirmation methods. New failure cases exercise real reservation
revocation and lease exit, plus the original finish exception through a failed
exact-worker stop. Positive cases do not seed product ownership or replace
the validator.

Root `31e4aa` reads the complete append, fixture and tests. `5be4e0` binds the
final map; `972e31/0` verifies 16 original/copy pairs, 11 derivatives, the complete
prefix/addition and all 14 ordered IDs. Close-path read `8f1c68` confirms the
fixture's idempotent cleanup contract. Independent verdict `5411dcf6` and
passive `de9767/0` agree, including reconstruction of all three complete diffs.
Root read that verdict in `a80fc1`. No executable draft correction was required.

Follow `CONTROLLER-STAGE-QUALIFICATION-BRIEF-2026-09-14.md`. Keep the original
81 cases and append the 14 frozen controls in a separately reviewed 95-case
instrument. Existing generated39 tests remain unchanged. Both fixture module
pairs start and finish with their real authorities absent.

This unit checks local records only while its locks are held. It does not prove
Windows resume, native job/read-set ownership, pipe or source authentication,
child namespace issuance, construction or validity across a later effect.
Those remain in the fixed connection and runtime work. D1/D2 stay complete;
D3/D4, current full-tree, package, installed-client and release gates stay open.
