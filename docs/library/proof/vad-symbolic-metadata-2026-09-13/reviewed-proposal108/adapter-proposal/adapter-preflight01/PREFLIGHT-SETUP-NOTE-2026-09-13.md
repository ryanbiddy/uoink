# New synthetic expectation correction before execution

The retained reader's escaping-name refusal says `Non-contained ZIP name`.
The first unexecuted adapter harness expected `Unsafe`, a word the reader
does not emit. Preserve that harness in `harness-draft01` and change only
this new expected substring to `Non-contained ZIP name` before the first
qualification. The escaping-member input and refusal behavior stay the
same. No adapter, tracer, accepted test or artifact access changes.

Independent review also identified an overbroad read-log expectation.
`directory_bounds` scans an opaque final 65,557-byte ZIP window; that window
can overlap stored tensor bytes. The first harness counted those metadata
reads as if they were selected storage-member reads. Preserve the intermediate
harness in `harness-draft02`. Mark the read-log boundary immediately before
`parse_pickle`, then assert that this payload handoff reads no storage-member
range. Separately assert the known earlier metadata-tail overlap in this
synthetic archive. This retains the meaningful no-selected-storage boundary
and explicitly records the broader opaque reads made by the existing reader.
No claim is made that hashing is its only opaque read of storage bytes.
