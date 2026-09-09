# Eight interrupted-I/O checks still require a compatible observation boundary

The corrected tree retains eight failures in the AW, AW-2 and AW-3 files.
The lifecycle worker's independent union reproduces exactly those eight
failures with 161 passes. No existing test was changed or deselected.

Their injected failures live in the parent Python process. The production
destination writes run in a separately launched Python worker, as required
by `PHASE4-CONTRACT-2026-09-08.md:456` and the later lifetime reviews. Windows
does not transfer a parent's patched Python functions and threading Events
into that independently launched interpreter.

| Cases | Frozen setup and failed observation |
|---|---|
| AW-3 D12, three cases | `interrupted_item_temp` patches parent `os.replace` and `Path.unlink`; it requires one recorded allocated temporary file before testing retry/purge/user replacement. The child completes its own replacement, so the parent list stays empty. |
| AW purge-temp, one case | The parent replacement/unlink exceptions never reach child I/O, so the fixture's required orphan is absent. |
| AW-2 D13 and AW-3 D13, four cases | Parent replacement callbacks must set a parent threading Event before the timeout result. The real child does not execute those callbacks. Three of the callbacks call the captured original replacement after their release signal. |

Ryan's D13 correction moved the independent user edit after timeout. It did
not move the replacement interceptor into the cancellable writer, and did
not authorize that additional setup change. The final preservation/timeout
assertions remain valuable and unchanged; their required failure injection
is at a different process boundary from the shipped operation.

A parent destination-write fallback would restore the unbounded syscall that
the isolated writer was introduced to remove. Serializing arbitrary callback
closures or changing behavior when a test wrapper is detected would be a test
workaround. Neither is an acceptable product repair. Manually setting the
fixture Events, inventing an orphan, or calling a harmless fake replacement
would not test the required operation either.

This review identifies the remaining incompatibility; it grants no waiver,
passing label or further fixture-edit authority. Keep the eight checks in the
full tree and their product repair brief open. Complete all independent source,
package and operator-kit work. The next full tree must report their actual
outcomes alongside any newly found product defects.
