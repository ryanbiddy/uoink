# Startup81 release-progress proposal — 2026-09-14

The proposed living release notes record the accepted controller qualification at
`9c87ec2`: 81 passed, zero failed or skipped, plus 48 passing subtests in each
independent copy. The original 65 cases remain unchanged. The new text identifies
the remaining worker connection and the active source-only Gemini work
`05a3bf93` under brief `8611e31`, without assigning an implementation or runtime
result to that work.

Three exact edit groups are in `DECLARED-EDITS.json` and the complete mechanical
diff. Besides startup81, they update the documented branch backup from
`7f142e8` to `ea1b9ba` and name the unresolved model notice and CPU/int8 profile
binding. The newer backup comes from the current handoff and owner decisions;
this preparation did not query the remote.

Only `proposed/RELEASE-NOTES-LIVING-LIBRARY.md` is offered for application.
The owner decisions, historical validation and package08 delivery record need
no change. Canonical documents remain untouched.

The proposal preserves production `71d3e70`, the complete-tree scope of
2,796 passed / one historical failure / three skips, package08 and installation
limits, completed D1/D2 scope, unapproved D3/D4, signing and isolated-profile
decisions. Website and marketing remain paused. Suggestions-only behavior,
0.90, apply=false, deferred Phase5B, blocked speaker material and X403 remain
unchanged. Historical failed observations and all 57 table lines are intact.

Passive actual `946e76` exited0. It checked all three hunks forward and reverse
against the complete before/after text, restored the unchanged final CRLF for
byte comparison, and verified all seven documentary input hashes remained
stable. The before copy is 51,896 bytes, SHA
`957db525ddd81f5e1302fd930eaf5f80d78d561ebd91a49d02b2bbda4e6c4d00`.
The proposal is 52,810 bytes, SHA
`0a2ab0112288bf641067b44d470bb265f3555c1b9353ec18bdb3c61556e5c8c0`.

Initial combined displays were truncated; subsequent bounded reads completed
the notes and relevant handoff sections. The first in-memory assembly assumed
uniform CRLF and stopped before writing a draft; its exact error and correction
are preserved. No test, subject startup, native/model operation, artifact access
or network check occurred. This is a prose proposal for root review.
