# Normal-drain native instrument scope and bounds

This source derivative adds one symbol: FlushFileBuffers. Its Windows x64 ABI is
BOOL(HANDLE), bound as c_int32(c_void_p), with the existing WinDLL calling
convention and last-error support. SetFilePointerEx, ReadFile and WriteFile retain
their reviewed prototypes. The final function map has 33 names, plus the separate
bootstrap GetLastError lookup. Each process must record exactly 33 binding casts,
one GetModuleFileNameW dispatch, its recorded API calls and the existing controller
attribute-buffer cast (one controller, zero child). Every dispatch still requires
one matching audit event and clears its same-thread context in finally.

Controller additions are fixed ancestor-directory opens, one exclusive CREATE_NEW
journal open, and synchronous journal seek/read/write/flush against that retained
handle. The journal never enters the inherited worker handle list. Directory
opens use FILE_READ_ATTRIBUTES, FILE_SHARE_READ, OPEN_EXISTING and
BACKUP_SEMANTICS|OPEN_REPARSE_POINT. The journal uses GENERIC_READ|GENERIC_WRITE,
share zero, CREATE_NEW and WRITE_THROUGH|OPEN_REPARSE_POINT. None uses inheritable
security attributes. The child's existing exact read-set and pipe scopes stay
unchanged; FlushFileBuffers is not a child permission.

The creation observer records native success. It does not itself issue authority:
the registry's separate trusted callback checks that exact still-owned empty
handle and issues a private ticket. stage_created_handle transfers only ownership.
acquire moves it into its retained attempt before further identity work. Neither
the ticket nor a recorded PID is converted into new native ownership.

The fixed snapshot path has eight prefixes including the volume anchor. Its
registry child has nine. Every stream identity check queries both retained chains
and the journal: (8 + 9 + 1) * 4 = 72 native identity calls. Each stream operation
checks identity before and after its one native call: 145 calls. For a successful
full-transfer normal path, a read_all of empty state costs 434 calls; a nonempty
journal fitting one 65,536-byte chunk costs 579, including the final EOF read.
The four framed records fit 6 + 4 * (4 + 4096 + 32) = 16,534 bytes.

For that full-transfer path, the first append costs 1,664 calls and each later
append 1,809: four appends total 7,091. Setup, initial read, creation/acquire
identity checks, retained worker-time observation, journal close and ancestor
retirement add 927 or fewer, for 8,018 additional calls. Reserving the former
2,048-call ceiling for unchanged process/pipe/member flow gives a normal-path
planning envelope of 10,066. This is source arithmetic, not a measured count or
a guarantee that short I/O/OS scheduling follows the full-transfer path.

The new finite ceiling is 16,384 normal API calls per process, the existing
60-second cooperative work clock, at most 256 numeric journal events and a
1,048,576-byte final receipt. Short transfers may consume the remaining margin;
exhaustion fails this observation rather than widening the bound. No retries are
added. The existing 64-call/10-second owned pipe/process cleanup reserve does not
permit journal creation, read/write, flush or journal/ancestor closure. Native
blocking calls, especially FlushFileBuffers, are not made cancellable by a clock
check. The receipt byte cap is enforced after serialization; an oversized receipt
is a failure, not permission to truncate or emit a success summary.

Before CreateProcessW, the observer requires confirmed RESERVED bytes and two
successful flushes. Before ResumeThread it requires WORKER_BOUND, the exact
retained worker and three flushes. Before journal CloseHandle it requires the
confirmed CLEARED head, actual retired-worker witness and four flushes. These
are before-call observations, not process capabilities or retrospective proof
that a failed native call succeeded. The normal completion checks and independent
outer exit/receipt checks must also pass.

After the controller exits, the outer launcher derives one journal path from
bounded physical fields inside its fixed registry directory. It opens that file
once without sharing, reads at most 16,534 bytes, closes it and compares all bytes,
SHA-256, magic and final frame digest to the controller's confirmed-byte receipt.
This is an observation of the generated file after successful handle retirement.
It does not prove persistence through power loss, crash/restart reconciliation,
cross-process writer exclusion, production namespace authority or real models.
