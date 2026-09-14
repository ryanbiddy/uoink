# Remaining generated Windows setup

No native protocol is ready to execute. The failed65 run and fixture ruling stay
separate from this source plan. Existing product pins and the qualified generated
native observations remain unchanged.

The current native origin is generated-actual-adapter-native-proposal01,
SOURCE-INPUTS 3c5f6e59 and bootstrap dbc0ac0a. Its module list lacks the four
reservation/durable modules and does not call connect_durable_registry. A fresh
source map/bootstrap must add those modules in dependency order and bind the
new adapter and split-flow bytes. Reuse its actual fixed dispatcher and pending-I/O
abrupt-exit guard; do not reuse an old approval or widen arbitrary ctypes calls.

One API distinction matters: that latest native bootstrap already has
SetFilePointerEx for child-local generated reads. Relative to its current
32-function dispatch map, only FlushFileBuffers is a new symbol. The frozen API
note's two added names describe the primitives-plus-pipe binder before the
child-reader additions. The actual combined-bootstrap change is one new symbol
plus a new controller-journal permission for the existing seek/read/write calls.
Derive the final exact names/counts from the selected declarations; do not copy a
count assertion by assumption. Retain pointer/argument identity and one-event
accounting, including binding casts and module query.

Add fixed monitor rules for retained directory ancestors, the one physical-key
journal pathname and its exact handle. Existing CreateFileW rules admit only five
generated members and the pipe; they must explicitly allow directory attributes/
backup-semantics opens and the journal's exclusive OPEN_EXISTING flags. Existing
SetFilePointerEx guard rejects every controller call. Add a separate journal rule
for offsets0..4MiB, bounded char buffers/count outputs, synchronous null-OVERLAPPED
ReadFile/WriteFile and FlushFileBuffers on that exact journal handle. Preserve all
child generated-read constraints and pipe OVERLAPPED rules. No arbitrary path or
caller-selected handle becomes allowed.

The fresh outer setup must create only named generated registry/snapshot/journal
fixtures, record exact creation and source/control bindings, and keep the ancestor
identity/retention boundary explicit. Current WindowsGateRegistry needs an expected
journal FileIdentity and a trusted creation ticket; a JSON path or readable empty
file cannot supply either. The first generated setup may rely on an explicitly
quiescent private fixture namespace, but that is not production creation/restart
trust. Production transfer from a creation handle to the exclusive journal owner
needs a separate retained-identity design; do not silently claim that an open/close
probe plus recorded file ID defeats concurrent replacement.

Per-operation ancestor checks add many identity calls. Derive a finite per-case
API budget from the fixed path depths and operation counts before execution;
the old 2,048-call cap is not assumed adequate. Keep payload bounds separate from
this call budget and synchronous Windows latency. Journal writes/flushes are not
permitted as a new emergency cleanup operation. After persistence uncertainty,
retain the handle and quarantine; a source-bound supervisor may stop only its
exact controller, and cannot claim a timed-out flush succeeded.

| Observation | Concrete remaining source/setup |
|---|---|
| Normal facade drain | Add registry/snapshot ancestor retention, exact initial journal binding, creation-ticket issuance and connect_durable_registry before the existing actual adapter flow. Record confirmed RESERVED before CreateProcess and WORKER_BOUND before ResumeThread, then exact process/job/I/O/read-guard retirement before CLEARED and journal close. Bind the full journal bytes and ordered API events in raw receipts. |
| Competing process | Add a fixed second helper and handoff of the same physical snapshot identity/registry path, with different semantic fields in its record only. The helper must observe sharing/lock refusal while the first owns the journal; separately exercise a second physical directory. No generic CLI path or process-ID authority. |
| Bind persistence uncertainty | Add a one-shot, source-bound generated fault at WORKER_BOUND confirmation after suspended creation. Record whether the actual Windows flush ran/succeeded separately from the injected refusal. Assert no ResumeThread, exact retained-worker stop attempt, pending-I/O disposition and retained quarantine/gate. |
| Torn/replaced state | Prepare two separate predeclared generated variants: bounded truncated journal bytes, and an expected-versus-actual journal file identity mismatch. Both must refuse before worker creation. No deletion, truncation or fallback registry during recovery. Keep original bytes and observed handle facts. |
| Controller crash | Add a fixed external observer/controller topology. Transfer only an exact child PROCESS handle to the observer, never the job handle. Stop the exact controller after a recorded reserved/bound stage; observe retained child exit and member-handle release. Keep single-process job/no-breakaway assumptions explicit. A new service must still refuse the interrupted journal without reconciliation. |
| Explicit reconciliation | Implement a narrow trusted observer bound to the surviving generated controller/child evidence, physical identity, current head/generation and unique attempt. Demonstrate forged/unknown evidence refusal and late ordinary completion refusal first. The separate recovery API must renew durability and clear only with that evidence. No retained process authority means blocked; PID absence is insufficient. |

A controller crash releases its kernel handles through OS teardown; it does not
prove which final journal bytes were durable. The anonymous job cannot be reopened
from a recorded PID. The external observer's retained child-process identity plus
an already established one-process job/no-breakaway invariant is only a proposed
generated reconciliation basis until its exact protocol is reviewed and observed.
General restart without surviving trusted evidence remains deliberately closed.

No new Ryan permission is needed to prepare generated engineering. The two test
fixture expectations require the separately recorded ruling requested by root.
Real model assets, native runtime imports, installed receipts and market release
remain outside these six observations.