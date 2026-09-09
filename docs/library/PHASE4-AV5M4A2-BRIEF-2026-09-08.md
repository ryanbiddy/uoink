# AV-5m4a2: complete the failed binding and temp-identity repair

Engine: Grok. Gemini AV-5m4a `eb32f3b4` timed out without its required report.
Its complete partial diff is retained in
`patches/av5m4a-gemini-timeout-rejected-2026-09-08.patch`. Nothing from that
run is integrated. Independent verification: **213 passed, eight failed**,
76.63 seconds, worker scratch `av5m4a-wi`. The four AW-4 cases pass, but the
diff still violates the repair brief; a green reproduction count is not an
acceptance ruling.

Read AV-5m4a and AW-4 completely. Start from current `cc/living-library` and
apply the retained patch with three-way apply only as a starting point. The
lifetime/session/exclusion region remains AV-5m4b's parallel responsibility.
Preserve its changes if they are already integrated. Do not rewrite the file.

Complete these bounded corrections:

1. `_write_dest_binding` still uses direct `Path.write_text` for a new file
   before atomic persistence. Remove that direct write entirely. Persist
   consent time in the binding, and make the durable authority witness part
   of the acknowledged state. Do not swallow witness persistence failures.
   Missing or corrupt authority after consent/export must require explicit
   reconciliation, while a real newer consent can authorize a destination
   change. A failed initial write must not leave usable partial authority.
2. `_try_unlink_recorded_temp` catches TypeError and retries deletion without
   identity arguments. Remove that fallback. `_io_unlink` also falls back
   to parent-process mutation if the isolated worker is absent; remove it.
   An unavailable isolated mutation path must refuse and retain unresolved
   cleanup. Never add compatibility bypasses for a patched callback.
3. Make the file identity/content check authoritative at destructive I/O.
   Stat/hash followed by path unlink leaves a replacement race. On Windows,
   use a handle with appropriate sharing exclusion, check identity/content
   through that handle and delete that bound file, or another demonstrated
   equivalent. Keep volume/file identity explicit and protect same-byte
   replacement files. Unknown old records have no deletion authority. If a
   platform cannot provide the required exclusion, retain cleanup and refuse
   rather than delete a guessed path. No async Python exceptions or rollback.
4. Retain the staging/build/installer additions. Demonstrate the actual
   source-only staged worker can start, perform an isolated disposable write
   and exit with no source-tree runtime dependency. Add this focused new
   implementation test and any new refusal/race coverage needed above.

Run every AV-5m4a named suite and your new implementation tests. Existing
tests/helpers are frozen, including AW-4. If a legacy fixture intercepts a
removed direct write, preserve its failed result and identify the exact
setup mismatch for Ryan; do not restore the direct write to satisfy it.
The eight old parent-interceptor failures already require Ryan's ruling.

Write `docs/library/PHASE4-AV5M4A2-GROK-2026-09-08.md` immediately, then
update it with exact commands, results, staged-worker proof and limitations.
No report is a failed run. No live index, port 5179, model, API key, paid API,
commits, pushes or subagents. Apply remains false. Use short disposable roots
and resolved dependencies. Astra independently verifies and integrates.
