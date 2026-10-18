# Archived runtime track - 2026-09-15

Frozen by Ryan's 2026-09-15 09:30 PDT release decision, relayed by Fable.
3.8.0 ships on Torch 2.8.0 / WhisperX 3.8.6; migration is planned for 3.9.

This index archives in place all synthetic runtime-owner, journal, controller,
state-machine and fake-stack work, including related source snapshots, fixtures,
generated native observations, failed attempts and pending preparation through
`1ca39c0`. Existing files and commits are retained. Earlier queues and briefs
no longer authorize work. No further runtime-owner, controller, fake-stack,
D3 fetching or D4 stack/native execution is scheduled or authorized by this task.

## Commit index

These commits locate the retained tracks and their intervening preparation,
reviews and failures. Commit subjects describe historical work, not 3.8.0 claims.

| Track | Retained commits |
|---|---|
| VAD and loader preparation | `de07dfe` fixed VAD schema; `57abc97` synthetic converter; `9859a8a` generated buffer checks; `381985c` inspection adapter; `e6a2394` manifest resolver; `e826407` plain-state reader; `f0602f8` dormant runner |
| Owned-state bridge and CPU ports | `2b9068a` fake-port orchestration; `a3e02f4` ASR adapter and failed native capture; `3801cee` fake CPU storage checks |
| Owned WhisperX and lifecycle state machines | `1935012` owned contracts; `93f4996` owned text wheel; `803df4b` owned factory and registry |
| Windows namespace, handshake and cleanup | `9c40271` namespace contracts; `668b08a` generated worker; `e98f4c2` handshake and phase guards; `0d93186` timeout cleanup; `428707d` child file adoption |
| Permit, worker and recovery connection | `d58bebe` permit/facade connection; `7fba83a` drain/cancellation; `7ced134` generated worker adapter; `f9ab6fe` reservation recovery; `1f200eb` ownership/publication; `bbe10d6` bootstrap |
| Reservation and journal work | `58335df` failed reservation checks; `8fc3219` approved correction; `2f4311f` journal creation transfer; `67887c3` generated journal drain; `1c6ac4c` journal source corrections |
| Directory identity and writer exclusion | `c5e72a2` failed exclusion; `cc6bb7c` directory drift; `d317a88` directory repair; `f630264` generated writer exclusion and journal drain |
| Journal cancellation and retired-owner recovery | `60b3bb5` journal cancellation; `a25b34b` native cancellation; `a83ae1a` retired-owner recovery; `5671b51` generated native recovery |
| Connected runtime owner | `47d30c8` connection brief; `3661608` fake33 connection; `3b8f9e0` generated Windows cancellation |
| Interrupted owner | `0a1a211` rejected source; `feee2f7` fake28; `7f142e8` failed native observation; `c8e7a44` repaired prelock checks; `99ce3c9` repaired Windows observation |
| Dormant reliability caller and engine | `22949dc` rejected constructor; `4a01ef2` request/stream caller; `1e2167a` lifecycle metadata; `9e3a77d` generated engine construction |
| Controller startup and child namespace | `4d026c2` rejected constructor; `d7c86f9` startup source; `9c87ec2` fake81; `8611e31` namespace brief; `a152cbf` rejected child namespace |
| Controller worker stages and custody | `851bcdd` stage source; `fc17b67` stage95; `e0bbbd6` boundary brief; `fa27d47` rejected boundary; `71df9d3` custody repair |
| Controller10 and pending native preparation | `0a74367` retained Controller10 failure and exact expectation proposal; `1ca39c0` generated native compatibility preparation |
| Historical D1/D2 boundary | `4b38948` approved D1 inspection; `017b559` D2 decision; `d13534f` approved D2 local conversion; no further D3/D4 |

## Final disposition

Ryan approved only the two expectation substitutions at lines 128 and 300 of
`proof/controller-custody10-failed-2026-09-14/author/test_controller_resume_publication.py`,
followed by one run of that file. All other copies and the original failure
record remain historical. This exception closes the controller track; it does
not restart native compatibility, model migration or a review cycle.

The [release owner decisions](RELEASE-OWNER-DECISIONS-2026-09-12.md) govern
3.8.0. [Ryan decisions result](RYAN-DECISIONS-2026-09-15-RESULT.md) records the
final focused test outcomes. Fable owns publication and any removal of proof
bulk from the public tree; this archive index deletes no files.
