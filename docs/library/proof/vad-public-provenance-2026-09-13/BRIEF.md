# VAD provenance and storage-format text research

2026-09-13. Read `docs/library/RELEASE-OWNER-DECISIONS-2026-09-12.md` before collection. Model migration, conversion, model loading and runtime qualification remain unapproved. This task collects public source, license and repository metadata only, under the parent integrator's bounded research assignment.

The known WhisperX 3.8.6 release commit is `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0`. The only local model identity used is the retained safe JSON receipt: 17,719,103 bytes, SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`. The archive advertises a two-byte `archive/version` entry and no byteorder entry. Neither entry nor any model/storage payload will be read here.

Seek an exact public identity association through immutable GitHub commit/tree/blob metadata or a small Git LFS pointer. Inspect tree metadata before requesting any candidate asset blob. An asset blob may be fetched only if metadata establishes a small pointer-sized text record; never follow a pointer, binary raw URL, LFS media URL or download redirect. Public model cards/licenses may be collected as bounded text, without resolving model files.

Separately bind PyTorch 1.10 release source and primary documentation describing the ZIP storage writer, version records, element units and byte order. Distinguish a source contract from evidence that this particular historical artifact used it. Do not infer writer architecture, byte order or provenance from the present machine, CUDA location token or unauthenticated version declaration.

Collection will use unauthenticated public HTTPS requests with recorded URLs, UTC times, statuses, content types, response hashes and exact retained text/JSON bytes. A local text collector may use fixed public-host/path allowlists, bounded responses, strict UTF-8/text or JSON validation and redirects disabled. No downloaded code may execute. Preserve failed requests and distinguish search leads from verified immutable records.

Outputs stay under this fresh scratch directory: collector source, raw metadata/text, source bindings, failure records and a concise findings report with exact remaining gaps. Prior seals and the handoff remain unchanged. No network requests may target the live index, port 5179, Phase 6 media/X scope or authenticated services. No model/audio/binary/package downloads, runtime imports, tests, inference, tracked edits, staging, commits or publication are authorized.
