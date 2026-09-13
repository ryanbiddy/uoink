2026-09-13. Root documentary verifier 01 exited 1 in tool chunk 02a385
(0.2182696 seconds). It verified all 199 sealed payloads, 197 original copies,
the two 40-case records and 23 HTTP response/body pairs, then failed its
timestamp-file count before creating the destination proof directory.

The collector has 51 JSON files beneath retrievals: 48 request, response and
final receipt records, plus two plans and one source-URL list. The prior
timestamp review counted only the 48 receipt records. Verifier 01 mistakenly
applied that count to all JSON files.

Fresh verifier 02 selects receipt.json, request-*.json and response-*.json for
the timestamp comparison. All 51 files remain covered by the unchanged outer
seal and exact byte-copy checks. The expected 48 records and 119 literal UTC
strings are unchanged. This repairs a documentary selection error; no source
capture, source bytes, tests or product outcomes change or rerun.

Run verifier 02 once under C:\Python314\python.exe -I -S -B with the existing
IG_FORBIDDEN_LIVE startup binding. It reads only the sealed documentary files
and their recorded checkout sources, then copies the unchanged 200-file proof
into docs/library/proof/torch213-vad-source-2026-09-13. It imports no collected
source and makes no network call. Retain verifier 01 and its failure alongside
the new verification result.
