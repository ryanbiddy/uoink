# B2 wheel-builder preparation — 2026-09-13

Implement the reviewed distribution recipe as a small stdlib utility in this
scratch directory, with bound B2 source/notice/member-manifest inputs. It must
refuse expected-hash overrides, validate the exact upstream wheel identity,
safe paths, metadata and complete RECORD, change only the approved members,
and emit deterministic ZIP_STORED output plus provenance into a fresh directory.
No package import, upstream build hook or network belongs in the utility.

Current execution is limited to synthetic ZIP tests. Use placeholder asset
bytes; never invoke the builder on, copy, open or decompress the actual upstream
wheel/model asset. Parser/transform/serialization helpers may operate on these
synthetic members; the production build entry has no fixture bypass. Use the
retained B2 text only as inert replacement bytes. The original six/ten constructor
tests and all accepted checkout fixtures remain untouched.

Before test collection, block heavy/non-stdlib imports, networking, process
creation, native library loads and live-index access. Deny opening the known
actual wheel/cache and package/model trees. Use C:\Python314\python.exe -I -S -B,
scrub provider credentials/offline environment, retain actual exits and cases.
Test boundaries: identity/overrides, safe fresh paths, ZIP member names/types,
counts/sizes/compression, complete RECORD, duplicate/incorrect metadata, exact
recipe inputs, unchanged members, deterministic output and tamper detection.
Preserve failures and write a repair brief before any rerun. Root reviews the
frozen exact utility before any real artifact invocation, installation or build.
