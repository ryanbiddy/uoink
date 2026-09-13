# Companion B: exact local distribution proposal — 2026-09-13

The exact upstream wheel is available locally. An initial filename search found
no named wheel; the existing pip cache contains its bytes at
`_scratch/python313-graph-01/cache/http-v2/7/5/8/3/f/7583fef67084ddf87aa2564c995bb7778718a460ee10db0da2a67f4b.body`.
Its 1,118,909 bytes and SHA-256
`79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7`
match both the captured PyPI artifact record and the original pip installation
receipt for `faster_whisper-1.2.1-py3-none-any.whl`.

The wheel contains 15 members. All nine Python members were read as text and
match the retained installation. Its exact transcribe.py hash matches the input
used for companion B. Original wheel METADATA also matches the retained PEP 658
text. The local installation's RECORD has installer-added rows, so the recipe
must use the original wheel RECORD preserved here, not reconstruct a wheel from
the installed directory. No full upstream Git or source-distribution tree was
found in the scoped inventory; wheel-to-wheel preparation avoids relying on one.

Propose distribution version `1.2.1+uoink.localassets1`, wheel filename
`faster_whisper-1.2.1+uoink.localassets1-py3-none-any.whl`, and unchanged package
name `faster-whisper`. No wheel has been built or copied into vendor/staging.
The exact proposal is accepted only for further derivative planning. Ryan's
model-stack ruling still covers execution and frozen compatibility changes.

| Proposed member change | Exact identity or rule |
| --- | --- |
| `faster_whisper/transcribe.py` | Replace the verified 80,403-byte input `5d5ffb00018561d3d529b2c72e1d9f5fff055bea725f3cccc7c6c67f5cc8ffe4` with the exact 82,600-byte companion-B text `e500e12b0a58420ce5f41b202ba7d942b901a9b99c617d6ca3d3304b9493f269`. Preserve its bytes, including line endings. |
| `faster_whisper/version.py` | Replace only the version string with `1.2.1+uoink.localassets1`; proposed 69-byte result `de0f60699bec3dd135ee08449a5bfdd4267d2bba61e438354cbab03ffbbc68e8`. The unchanged package __init__.py exports this value. |
| Distribution directory | Rename `faster_whisper-1.2.1.dist-info` to `faster_whisper-1.2.1+uoink.localassets1.dist-info`. |
| `METADATA` | Change its single Version field only. Keep Name, Requires-Python, all Requires-Dist/extras, license fields and description byte content. |
| `WHEEL` | Keep Wheel-Version 1.0, Root-Is-Purelib true and Tag py3-none-any. Replace the original generator field with `uoink-localassets-wheel (1)` so the new archive does not attribute its construction to the upstream builder. |
| `UOINK-LOCALASSETS-NOTICE.txt` | Add the proposed derivative notice beside the preserved upstream LICENSE. |
| `RECORD` | Recompute every output row from actual output bytes, with SHA-256 URL-safe base64 without padding and decimal sizes; the RECORD self-row has empty hash/size. The exact proposed text is provided separately. |

All other package members remain byte-identical. The upstream MIT LICENSE is
1,064 bytes, SHA-256
`af6798135e729f8aa6c853936d037dfdea449734d26b8ea6a89805fca758c0d5`.
Preserve its copyright and permission text, existing source notices and the
upstream project attribution. Future THIRD-PARTY-NOTICES must report the local
distribution version and link its patch/provenance, while sealed older candidate
notices retain their original identities. No new claim of upstream endorsement
or advisory clearance follows from this delta.

The wheel includes `faster_whisper/assets/silero_vad_v6.onnx`, declared by its
original RECORD as 1,245,151 bytes. This task hashed the complete compressed wheel
as opaque bytes; it did not decompress, copy, inspect or execute that model
member. The future recipe must name this existing asset explicitly and preserve
its bytes, never replace it from a URL. Its per-member verification and runtime
behavior are unobserved here. Companion B changes no VAD/checkpoint loader and
provides no model-quality or artifact-safety acceptance.

The proposed preparation utility should follow the reviewed NLTK wheel
precedent's small stdlib approach. Read the pinned local wheel once, validate its
size/SHA-256, ZIP names and original RECORD before writing, then transform only
the allowlisted members above. Reject expected-hash overrides, unexpected
metadata singleton values, duplicate/case-colliding names, traversal, absolute,
UNC, ADS/device names, links/reparse points, destination reuse and overlapping
input/output paths. Reject unexpected extra distribution roots, unsafe
compression/encryption, and unbounded member sizes before decompression. Keep
all failure receipts; never fall back to installed source, PyPI or an upstream
build hook. No setup.py, build backend or package import is needed.

Use a fresh destination, ZIP_STORED, fixed timestamp `(2026, 9, 13, 0, 0, 0)`,
create_system 3, mode 0o100644, sorted non-RECORD names followed by RECORD, and no
archive/member comments or ambient epoch. Reject upstream RECORD signatures if
unexpected; any approved source signature removal must be explicit and cannot
be carried forward as a signature of modified contents. The observed wheel has
no RECORD signature members. Omit installed-only INSTALLER/REQUESTED files.
The proposed output has 16 members, including its new notice; expected hashes
and sizes are in `proposed-member-manifest.json`. The model entry there is still
derived from the upstream RECORD until actual preparation verifies its bytes.

The build receipt should bind the original wheel path/name/size/hash and its
captured URL, the original wheel member map, preparation script and patch hashes,
all changed before/after member hashes, renamed metadata directory, removed and
added members, local version, final wheel size/hash, deterministic parameters,
Python identity, actual exit and verification outcomes. Keep timestamps and
working-directory paths outside the wheel. No final wheel hash or build success
is supplied in this plan.

Before accepting a produced wheel, an independent verifier must check the exact
member set, original-to-output unchanged-member equality, every RECORD hash and
size, version agreement across filename/METADATA/version.py, unchanged dependency
and license content, safe paths and ZIP parameters. Build twice into fresh roots
with different ambient time/path settings and compare full wheel bytes. Use
synthetic ZIPs for boundary negatives, including wrong wheel size/hash, bad
RECORD, duplicate metadata, extra members, path tricks and destination reuse.
Never relabel missing real-artifact tests as passes. These checks qualify
packaging only; retain the separate six-case synthetic source receipts.

For the eventual installer change, the exact frozen assertion proposal is in
`frozen-installer-lock-expectation.patch.txt`: change only faster-whisper's
expected version from `1.2.1` to `1.2.1+uoink.localassets1`. This follows a newly
identified distribution; it is not a fixture correction and requires the
reserved review. The captured original test, current lock and all other
expectations remain unchanged. `verify_installer_lock.py` already parses a plus
suffix and compares versions as exact strings, so no parser relaxation is
proposed. Keep the current Torch and WhisperX assertions in this narrowly scoped
diff; their eventual stack decisions are separate.

After approval and wheel qualification, a corresponding build change would pin
the local version in requirements-installer-lock.txt and FASTER_WHISPER_VERSION,
declare a vendor wheel path and fixed measured SHA-256, call Confirm-Hash before
pip, and pass that explicit local wheel instead of the existing faster-whisper
index requirement. Preserve the existing constraint and final inventory checks.
Do not introduce a find-links fallback or silently retain upstream version
metadata. Stage/install/runtime checks and a corrected full tree follow their
own approved protocol and must carry the changed source commit id.

The remaining preparation work is concrete: implement/review the stdlib utility
and its boundary fixtures, obtain the reserved decision on this exact derivative
and one frozen expectation, then perform byte-bound packaging verification.
The upstream wheel/input gap is closed; output wheel identity, independent
determinism, full-module/native behavior, model manifest/loading/quality and
installed acceptance are still pending. This plan requests no execution itself.
