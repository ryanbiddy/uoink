# Next unit: Windows reservation connection

Implement the generated reservation unit against retained Windows handles, then
connect it to the observed adapter/facade path. This is a concrete implementation
brief only. No new source, test, native call, asset access, or model execution is
authorized by this file. Generated engineering needs no new Ryan decision; root
reviews each bounded native protocol as before.

The starting reservation sources are pinned by
`e7efffb823d3af09b22133909e2ff58f85ff4c62305c00d9106c3789356da0bf`:
`snapshot_reservations.py` e80ae881, `reservation_file_port.py` 70855437,
`durable_lifecycle.py` fb2c783b, and unchanged lifecycle a80514aa. Both generated
runs passed 42 cases. Keep those files, cases, and outcomes unchanged as the
baseline; implement a fresh derivative with explicit source deltas.

The adapter target already captures the permit and yields the revocable facade.
Use the committed observation input
`docs/library/proof/generated-actual-adapter-2026-09-13/drain01/asr_loading_adapter.py`,
SHA-256 `2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c`
(12,073 bytes), rather than NEXT-WORK's older disconnected adapter. Its exact
`OwnedRuntimeFactory` check still needs a deliberate durable-factory migration.
The observed lifecycle source in that directory is a80514aa (22,138 bytes).

The exact current native connection map is
`_scratch/generated-actual-adapter-native-proposal01/SOURCE-INPUTS.json`, SHA-256
`3c5f6e5978f16cee0f6d3753a7acf21e855012955004528b96e73599b1cba44f`.
It binds the 12 source inputs and their actual locations. Relevant layers are
`generated_adapter_flow.py` 0cb97248, `generated_operation_flow.py` 6f09b4e6,
`generated_worker_flow.py` 4409fb6b, `win32_worker_connection.py` b39a29ce, and
the terminal-109 repaired `win32_private_pipe.py` 73a1109a. The API primitives
already separate suspended creation from the private reviewed resume mechanic;
the public real resume entry still refuses. The adapter/operation/adoption
controller methods currently combine those stages and therefore need the split.

## Small source changes

1. Add `windows_reservation_port.py` to the fresh generated proposal. It owns an
   exact retained snapshot-directory handle, a trusted registry-root/ancestor
   handle chain, and one exclusive journal handle. Bind directory volume/file
   identity through the existing file-information structures. Derive the sole
   gate filename from that physical identity alone inside the fixed registry;
   store, choice, revision, manifest and generation remain journal contents.
   Reject an ambiguous physical registration instead of making another gate.

   Use one exclusive open journal handle as both the cross-process gate and the
   retained stream. This avoids a separately released lock file. The future
   source must specify its exact CreateFileW access/share/disposition/flags and
   bind them to the reviewed API dispatcher. Require a plain non-reparse journal,
   expected file identity, contained fixed path, and no extra hard-link alias.
   Keep the protected directory chain alive through every path-based open and
   recheck final handle identities. A string-normalized path is insufficient.

   For the first generated protocol, fixture preparation supplies the exact
   registry/snapshot/journal identities. A first empty journal requires trusted
   observed creation; a pre-existing empty or replaced journal cannot mint that
   evidence. Production bootstrap of this namespace is a separate connection;
   do not pretend an unauthenticated disk manifest supplies its trust.

2. Adapt the handle to the existing `RetainedJournal` stream methods. Implement
   bounded seek/read/write with complete short-write handling on that retained
   handle. Bind file identity before and after each operation. Add the exact
   `FlushFileBuffers` binding and return True only after its observed successful
   result plus same-handle identity/readback. Preserve 4-KiB frames, 4-MiB journal
   cap, and all grammar/refusal rules. Never truncate a torn tail or rewrite a
   poisoned journal as part of cleanup. Empty/malformed/corrupt/unknown state
   still blocks before creation and resume.

   Record data-size bounds separately from elapsed time. Synchronous flush can
   block; a clock check before and after is not cancellation or a hard latency
   bound. Keep journal I/O outside the lifecycle state lock so worker revocation
   can proceed. The generated native protocol needs its existing exact-owner
   outer lifetime limit; if the controller must be stopped, record unknown
   persistence and require restart reconciliation. Do not claim power-loss
   durability from a successful Windows flush/readback observation.

3. Add `durable_generated_flow.py` by narrowly splitting the observed generated
   port's combined start. `create_suspended` creates the pipe pair and exact job/
   process/primary-thread owner, records its native identity, and returns before
   resume or handshake. The reservation service then appends WORKER_BOUND and
   confirms its flush. `resume` performs only the identity-bound ResumeThread
   operation under the existing short lock. Perform channel/bootstrap/handshake
   and read-set adoption afterward, outside that lock, through a separate fixed
   `finish_start` step before facade publication. This requires a small explicit
   addition to the durable factory transaction; never hide blocking pipe I/O in
   the supposedly nonblocking resume callback.

   Preserve the current GeneratedAdapterLifecyclePort's exact `_OwnedASRStart`,
   resolver/manifest and usage checks in `create_suspended` before any process
   creation. Move its generated worker policy acknowledgement into `finish_start`
   after adoption, and require that acknowledgement before facade publication.

   Retain the returned worker immediately. Any bind, resume, handshake, adoption,
   or publication failure must stop that exact owner, preserve the first error,
   and retain uncertain handles and buffers. Reuse the qualified terminal-109
   pipe rule; pending I/O is not quiescent merely because the worker exited.
   Completed teardown evidence binds process wait/exit, empty retained job,
   zero pending I/O and operations, then actual guard retirement. The normal
   completion observer consumes that exact live evidence, not a PID or JSON.

4. Make the adapter migration explicit in a fresh `asr_loading_adapter.py` copy:
   require the exact durable factory and its exact lifecycle, while preserving
   resolver binding, the returned lease permit, exact OwnedSession and facade
   checks, exception-aware close, and passive segments. Do not use duck typing or
   accept any factory that happens to expose the right methods. Update the fixed
   bootstrap to construct the new manager/factory pair. Retain the original
   adapter evidence and run its existing connection controls against the new
   source, plus the small durable-order assertions. Real runtime services and
   authority remain absent.

## Six generated Windows observations

Use the existing fixed Python/System32 dispatcher, generated files, private pipe,
job, and actual-tool receipt conventions. No new general harness is needed.

| Case | Required observation |
|---|---|
| Normal facade drain | Durable RESERVED before child creation; durable WORKER_BOUND before resume; generated segments through the actual migrated adapter; exact exit/job/I/O/guard teardown before CLEARED and exclusive-handle release. |
| Competing process | A second fixed helper targeting the same retained snapshot identity cannot acquire the gate, including with different semantic aliases. A different approved physical snapshot remains independently usable. |
| Bind persistence uncertainty | A separately labeled injected refusal at the durability boundary stops the suspended exact worker and prevents resume. If the underlying Windows flush succeeded, state that fact; an injected unconfirmed result is not an observed OS flush failure. Gate/quarantine remains held. |
| Torn/replaced state | Predeclared generated truncated frame or changed journal identity refuses before worker creation. No automatic repair, alternate registry, or gate deletion. |
| Controller crash | An external generated observer retains only the exact child process handle, not the job handle. Stop the exact controller; observe child exit and eventual release of generated member guards. A new manager still refuses the interrupted reservation before reconciliation. Keep the single-process job restriction and no-breakaway binding explicit. |
| Explicit reconciliation | First show unknown/forged evidence and late ordinary completion cannot clear. With current trusted evidence for this exact generated controller/child lifetime and journal head, confirm the head's durability, then clear/release through the separate API. Any missing observation keeps the gate logically quarantined. |

The crash observation is narrow. Retaining a job handle in the external observer
would change kill-on-job-close behavior, so it must not do that. The current job
is anonymous; a fresh manager cannot reopen it by reading a PID. The existing
single-active-process/no-breakaway setup plus the retained child handle may form
the chosen generated reconciliation basis only after exact source review and
observation. It does not automatically provide general production restart
authority. If no surviving trusted evidence can establish a previous worker's
termination, that record stays blocked; absence or reuse of a recorded PID alone
never proves quiescence or grants kill authority.

## Completion boundary

The deliverable is the connected source, bounded generated receipts, and an
honest recovery policy. Source-only fake tests retain their scope; native checks
measure only the selected generated paths and observed flush behavior. The next
unit does not acquire models, convert VAD storage, import the runtime stack, open
the live index, use port 5179, change the frozen dependency assertions, or declare
the installer/release ready. Existing asset/runtime/release decisions remain
root's tracked gates, not new permissions invented by this brief.
