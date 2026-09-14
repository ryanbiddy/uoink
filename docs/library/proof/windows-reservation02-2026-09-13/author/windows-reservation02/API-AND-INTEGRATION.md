# Exact Windows journal and startup integration proposal

This is source preparation over injected native services. No new Win32 call,
ctypes import, generated test, asset read or model execution has occurred.

| Function | Proposed Windows x64 ABI | Use |
|---|---|---|
| SetFilePointerEx | BOOL(HANDLE, signed int64, signed int64*, DWORD) | Absolute bounded journal position; returned position must equal request. |
| ReadFile | BOOL(HANDLE, void*, DWORD, DWORD*, void*) | At most 65,536 bytes; synchronous journal uses null OVERLAPPED. |
| WriteFile | BOOL(HANDLE, void*, DWORD, DWORD*, void*) | At most 65,536 bytes; exact positive short counts are completed by retained journal. |
| FlushFileBuffers | BOOL(HANDLE) | Successful observed Windows flush before readback and confirmation. |

BOOL is signed 32-bit, DWORD unsigned 32-bit, HANDLE/pointers 64-bit. The binder
refuses a non-64-bit pointer ABI. ReadFile/WriteFile already exist in the reviewed
pipe function map with compatible ABI; only SetFilePointerEx and FlushFileBuffers
are additional API names for a combined map. The new declaration function loads
no DLL and invokes none of these functions. A future native bootstrap must bind
its exact dispatcher, function identities and revised API-count assertions; the
old native04 or timeout bootstrap is not automatically authorized for this map.
The new declarations/constants are proposed source, not an observed ABI test or
a new independently captured SDK binding.

The exclusive OPEN_EXISTING uses GENERIC_READ (0x80000000) | GENERIC_WRITE
(0x40000000), share mode 0, null security attributes/template, and
FILE_FLAG_OPEN_REPARSE_POINT (0x00200000) | FILE_FLAG_WRITE_THROUGH (0x80000000).
The journal handle is non-inherited. FILE_BEGIN is 0. Sharing/lock violation
errors 32/33 without a returned handle mean a busy physical gate; other uncertain
acquisitions retain their local attempt. Existing identity queries bind volume,
file ID, final path, link count, reparse/deletion state and maximum length. Every
registry/snapshot ancestor is already retained through the bootstrap lifetime.
The directory's physical volume/file identity alone derives the journal name;
choice, revision, generation and store aliases cannot select a different gate.

The journal has a 4-MiB total cap and the existing 4,096-frame/4,096-byte-frame
limits. Read, write and seek result uncertainty permanently poisons that handle.
A successful flush/readback cache is invalidated by a later write or observed
identity/native-result failure. Final release uses that cache and CloseHandle;
it does not redo journal I/O while the reservation transition lock is held.
This relies on the private ReservationService pending/revision and gate-owner
protocol excluding another operation; arbitrary concurrent direct stream or
journal calls are not supported. Streams have no ownership-closing destructor.
FlushFileBuffers success is an observed OS result, not a guarantee against every
storage failure. Synchronous calls are not a hard wall-time cancellation bound.

Startup proceeds in this order: confirmed RESERVED journal; retained read guards;
exact owned permit/session; create suspended; observe exact retained process
creation; append/flush/read back WORKER_BOUND; guarded nonblocking resume; blocking
finish_start outside both state locks; recheck current owner before facade
publication. finish_start performs the original channel, read-set adoption and
policy acknowledgement. A failed finish or late publication attempts exact
retained-worker stop and keeps quarantine. Stop failure is not release credit.

The adapter's exact class check intentionally changes from OwnedRuntimeFactory to
DurableOwnedRuntimeFactory bound to that same manager. The original qualified
adapter remains in origins. Constructor policy literals, LocalBinding assertions,
owned session/facade checks and exception-aware cleanup are retained. The old
combined generated start_owned_worker entry refuses; only the new durable path
can reach the split implementation.

No-worker cleanup is separate: an actual PROTECTED lease with no permit/owner,
no startup/resume attempt, no worker or pipe and a current unrevoked RESERVED
token may retire its actual read set and issue a local record/token/guard witness.
Completion requires the base record to be RELEASED. This supports ensure_assets
and initial admission failure without fabricating child-exit observations.
Explicit live reconciliation can freshly inspect that same retained no-worker
witness after final persistence failure; it cannot rehabilitate a poisoned
journal or release through ordinary completion after quarantine. Each generated
port is one generation; reuse uses a fresh port/generation and the same registry.
No asset acquisition service or production writer implementation is added.

Still required before native integration: a reviewed retained registry-directory
and initial journal setup; exact native dispatcher/admission and generated-only
launcher; actual flush/exclusion/partial-I/O observations; and a separate restart
observer retaining exact process authority. A recorded PID, readable clean bytes
or caller-supplied profile is never enough. Public real entry points stay closed.