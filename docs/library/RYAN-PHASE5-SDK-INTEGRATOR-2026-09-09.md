# Phase 5 SDK settlement integration review

The corrected SDK integration has **267 passed, zero failed** in both roots:
127.82 seconds in worker `8cef3e8a`, 138.83 seconds in the checkout. BA-4's
actual SDK serialization test, the corrected unary clock probe, the original
shipped entry and Phase 4 stdio all pass in this union. Part B remains deferred.
The dashboard byte-target failure is unchanged and was not remeasured.

The worker admitted the original SDK route through registered `Server.run`,
then replaced the shared SDK serializer class during that run. Its independent
union passed 266 tests in 122.99 seconds. Astra's separate review caught early
release: a handler's local diagnostic response copy with the same request ID
removed the live scope, changing active admission from one to zero before
the outgoing frame. That new case failed in 1.77 seconds; the original worker
patch and both results remain retained.

Astra's supplement attaches the scope to the outgoing response/error object
at the product stream adapter. The actual SDK writer calls that object's
serializer, which calls the real SDK encoding and checks the elapsed deadline
and completed-frame cap afterward. Success that expires during encoding becomes
a typed refusal. The owning admission releases in `finally`, including encoding
failure. Local diagnostic objects use the untouched shared SDK serializer and
cannot settle the outgoing request. A context variable distinguishes the shipped
bounded writer, which retains its existing settlement path.

The four focused checks passed in 2.05 seconds before the complete corrected
union. Three-way apply was clean. No installed third-party file, existing test,
fixture, assertion, skip or parameter changed. The original worker report is
historical; this review identifies the applied supplement separately.

The 27-file seal in `proof/ryan-phase5-integration-2026-09-09/SHA256.json`
retains commands, raw logs/XML, guard, source bindings, the original patch and
the applied patch. This is synthetic SDK verification, not an installed or
actual-client receipt. The final committed full tree and rebuilt package are
still required after the remaining integrations.
