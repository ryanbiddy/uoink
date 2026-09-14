# Controller boundary fixture/control design — 2026-09-14

Design only. No fixture, test, qualifier or candidate is written or run here. Preserve the rejected ten drafts and the complete accepted 95-case closure. The new controller unit uses its own canonical module family; it does not replace the old isolated fixture's modules.

The source contract is custody-design01/DESIGN.md, SHA `f65ab5d9bff0a4fddfec6363ce6074198e3b989d271c3cb5d02d20f681e0f2b3`, read completely. The source author additionally confirmed a fixed `_check_controller_entry(binding,startup,permit,session)` before create. It checks the original binding through the existing pre-worker validator and does not consume startup. The factory retains this helper too. Final derivative hashes and field spellings remain pending.

Use actual `_controller_startup_scope`, `_consume_controller_startup`, `DurableOwnedRuntimeFactory`, `ReservationService` and their real records. Reuse the generated manifest/metadata recipe from startup_authority_fixture and the unchanged test_reservations Fixture/Kernel. The new fixture changes only generated test configuration and declared lower services; no positive custody, consumed_by, WORKER_BOUND or factory-attempt state is seeded. Capture returned objects for assertions without publishing them on behalf of the implementation. Canonical temporary globals restore through ExitStack; real worker/constructor entry stays closed.

**Exact fault seams.** Declare a transparent test-only wrapper around the instance's actual `bind_worker`: retain the original bound method, call it once, require successful WORKER_BOUND, pending None, exact token/worker and retained _starts relation, then apply one fault before returning to the actual kernel. Restore the wrapper in finally. This is not an unchanged filesystem callback. No wrapper replaces factory, validation, consumption or resume_owned. A finish wrapper similarly calls the original delegate once before fault injection. Neither seam grants success.

Read factory-owned `_factory_starts[raw_identity] = (attempt, entered)`; never seed it positively. Validate the actual frozen attempt, full permit, manager/kernel/delegate/record/owner/token/protection and entry latch. Controller binding retains the initial custody and fixed functions. Negative helper replacements are refusal traps whose call count must remain zero, not permissive validators.

Ten proposed controller groups, with final IDs/bodies to be frozen after source review:

| Group | Meaningful observation |
|---|---|
| Issued positive | Actual issuance → entry check → consumption → bind → locked pre-resume → resume → finish → locked publication; exact objects/latch, one resume, actual close/release, canonical restoration. |
| Factory entry refusal | Unissued/foreign/subclassed controller, wrong full permit, absent factory entry and reentrant kernel call refuse before a second create. Negative-only registry faults stay labelled. |
| After-bind identity faults | Replace selection/value, _starts worker, token worker or record owner after successful binding; no resume/publication. Check the exact surviving original owner and quarantine, with stop credit only where ownership is still confirmed. |
| Before-publication faults | Mutate selection/worker/token/record after actual finish returns; one earlier resume, no owner publication, exact confirmed stop or retained uncertainty. |
| Captured custody/helpers | Delete or replace original custody with a same-field different object; replace snapshot tuple identity or each literal fixed entry/boundary helper at the relevant boundary. No replacement helper may execute; no fallback or recapture. |
| Resume state | Already-consumed entry, attempted resume, active/pending transition or wrong token phase refuse without resetting a latch. Use separate fresh attempts. |
| Actual revocation | Call the actual reservation revocation path at either seam, with confirmed and failing cleanup variants. Inspect retained attempt/token/worker identities; never clear uncertainty to satisfy cleanup. |
| Actual lease exit | Close the one owning ExitStack at either seam so the actual startup/lease exit runs once. Record the first real exception if exit raises; otherwise require the subsequent stale-start refusal. Preserve gate/custody and do not invoke the scope twice. |
| Known first error | Raise one retained exception object before a worker is returned and, separately, after actual bind/finish. Arm secondary stop/sync failure only at that event. Require original exception identity, specific cleanup evidence and correct no-worker versus retained-worker state. |
| Assertion-failure cleanup | Throw a retained sentinel from the positive test body. The fixture must attempt actual close/join while the scope is active, then confirm native closure only on exact success. A cleanup error adds evidence to the sentinel and retains owners; it never replaces the first error. |

Every failure assertion names what was reached and what was not. Do not require one successful stop for an intentionally replaced ownership record. The fixture's finally handles a published session; a factory failure with no returned session relies on the actual factory's retained unpublished-worker path and asserts that custody, without issuing a second stop loop.

The controller closure is nine planned modules: four unchanged resolver/lifecycle/reservation modules, repaired durable and adapter, unchanged test_reservations, new fixture and new tests. Load these under their actual canonical names in a separate guarded invocation. Both reverse imports occur only after module initialization; no alias switch during an operation. Exact paths/hashes and pending rows are in SOURCE-BINDINGS.json. Existing guard semantics and the original 95-case loader remain unchanged.

**Generated compatibility is separate and still required.** The latest pinned gate includes OwnedContender; do not substitute older generated bytes or a permissive contender. GENERATED-COMPATIBILITY.md distinguishes bounded gate-reach/refusal probes from a full successful generated start. The latter remains pending and must pass before this connection is called accepted. No such result is claimed here.

Root review of this design precedes fixture/test preparation. All observations here are text reads/hashes only. Read01 was truncated by an overlarge combined output; required gate bodies were read separately in 03/04. No new harness, admission or execution is authorized by this document.

