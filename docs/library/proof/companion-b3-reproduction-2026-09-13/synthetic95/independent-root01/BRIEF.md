# B3 combined source and synthetic builder brief — 2026-09-13

Prepare a distinct proposed `faster-whisper 1.2.1+uoink.localassets2` from the
same exact upstream wheel identity. Preserve all B2 source, wheel, recipe and
evidence bytes. Do not read a real wheel or model asset during this task.

Combine the unchanged 82,612-byte B2 transcribe source, SHA-256
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`,
with the reviewed 4,897-byte utils source, SHA-256
`ecec29ad34688e2d559218685672c3c2f1086f524d78bcfd53e633a5739d5b19`.
The latter removes the obsolete `local_dir_use_symlinks` assignment; no other
helper behavior changes. The builder must also bind the original utils bytes,
SHA-256 `5b36ceb9d0fd3961de8cfb144bd82f9a4ef3151b2e5958405a11efb4f3ac4f82`.

Adapt exact reviewed builder `ef718918…b4c3f`: output version localassets2,
five fixed recipe inputs including utils, an original-utils identity gate,
and replacement of the two repaired Python members. Preserve upstream hash,
path/size/ZIP/RECORD gates and fixed packaging format. Keep WHEEL generator
`uoink-localassets-wheel (1)`, MIT license and dependency metadata unchanged.
Update local version/METADATA, NOTICE, aggregate patch, every member identity
and regenerated RECORD. Output wheel hash remains unknown; no wheel is built.
The asset row is inherited from recorded identity evidence, not a B3 observation.

Preserve the 62 existing builder behavior cases. Only two existing expectations
change: add utils to the approved changed-member set, and expect localassets2
in version.py. Keep every other assertion unchanged. Add six cases for original
and patched utils binding, a missing utils recipe, exact repaired source hashes,
the precise changed Python-member set, and unchanged dependencies/license/asset.
Record source, expectation and guard diffs before execution.

Coordinate the concrete source/recipe design and hashes with the independent
reviewer before synthetic qualification. After that review, use fresh label
`b3w01` under C:\Python314\python.exe `-I -S -B`, offline flags, scrubbed keys
and the reviewed synthetic guard. Source fixtures are retained text; model
assets use an explicit in-memory placeholder. No upstream module or model is
executed. Block captured-wheel, runtime/staging, native model and network access.
Retain real exits and any failures. A failed run requires a repair brief and
fresh label, with the earlier protocol/results preserved.

This work qualifies the proposed builder against synthetic boundaries only.
Frozen lock/fixture changes, actual distribution build, runtime migration,
installed tests and release acceptance remain outside this task.
