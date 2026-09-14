# Stable retained-directory identity repair proposal

The admitted writer-exclusion03 diagnostic failed overall. Its existing ancestor
comparison recorded the generated run directory at prefix 7 of 9 with size 4,096
before and 8,192 after. Exact final path, volume serial, 128-bit file ID, link count
and directory flag matched. The controller reported PersistenceUnconfirmed and
exit 1. Preserve both failed02/03 sources, controls, receipts and journals; this
proposal does not relabel either observation.

The port currently compares the complete FileIdentity dataclass for every retained
directory. That combines physical/path identity with mutable directory length.
The observed size change is sufficient to explain this exact refusal. The receipt
does not establish which individual directory-entry operation caused the change.

Microsoft documents the volume serial plus file ID as the identity comparison for
two open handles. FILE_STANDARD_INFO separately reports end-of-file, link count,
delete-pending and directory state. These references support separating the fields;
the measured directory growth comes from the saved generated diagnostic, not a
claim in the documentation. [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info),
[FILE_STANDARD_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info).

Keep FileIdentity and its generated dataclass equality unchanged. Add one explicit
directory-only comparator in win32_worker_connection.py. Require exact FileIdentity
types, true directory flags, valid nonnegative signed-64-bit size observations,
and unchanged final path, volume serial, file ID and link count. Only equality of
the two directory sizes is omitted. Apply that comparator to retained directory
scope checks and the existing directory branch of pin_exact_members. The regular
file branch keeps complete equality, including byte size.

No new native call, requery, path lookup or authority is introduced. The existing
identity() rejects reparse points/tags, pending deletion, negative size and failed
identity queries before any comparison. Retained handle ownership, ancestor count,
scope retirement, exact expected path and snapshot physical-key checks remain.
The diagnostic continues to report both original sizes when another field fails.

The journal is a separate mutable regular file: its existing bounded size policy,
same-handle ownership, creation-empty assertion, append/readback, CRC/hash grammar,
flush confirmation and poison/release rules remain unchanged. Asset read sets,
inherited member descriptors and buffer materialization retain exact size and
digest checks. This repair gives no approval for model/runtime acquisition.

Use the existing guarded creation-transfer qualification as the source-only
starting point. Preserve its complete 70-case test files and ordered case IDs.
Add a separate regression module covering directory growth at each ancestor,
post-reservation growth through clear/release, replacement/path/link/type failures,
native reparse/delete-pending refusals, regular-file size drift and retained failure
custody. Adapt only runner membership, fresh label and input pins. Fake calls are
not Windows observations. Root and an independent peer must review exact source,
controls and protocol before any execution; no test/native run is admitted here.

The failed03 fixed-copy inventory is prepared separately. No failure evidence is
rewritten or nested into this repair as a claimed successful result.
