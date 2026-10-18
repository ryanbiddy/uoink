# SDK settlement must belong to the outgoing frame

Astra's review of the finished SDK worker found a process-wide replacement
of `JSONRPCMessage.model_dump_json` during `Server.run`. It settles any
message with a matching request ID. The contract requires admission through
the final outgoing encoding; serializing a diagnostic copy is not that event.
This brief authorizes one independent probe of that distinction on the frozen
worker source before integration. The worker's passing union stays retained.

Drive the installed SDK stdio streams and registered server with synthetic
activity data. During the ordinary handler, serialize a separate response
object carrying the same request ID, as a diagnostic copy could. Observe
admission before and after that local dump and at the actual outgoing dump.
The local dump must not release the active request or remove its deadline.
Use the existing isolated integrator guard, no model, source fetch or live
data. Existing tests and fixtures remain unchanged; add a new review file.

If the probe fails, retain the original worker patch and verification, then
bind settlement to each outgoing message through a product-owned stream or
message adapter. Do not replace the shared SDK serializer class or infer
authority from a request ID alone. Call the real serializer and account for
its full cost, preserving error envelopes and final frame limits. Encoding
failure must release the owned admission. The shipped bounded entry keeps
its existing settlement path. No installed third-party file changes.

After that documented repair, run the new review, original-route tests and
BA-4, then the complete union in `RYAN-PHASE5-SDK-REPAIR-2026-09-09.md` in the
worker and checkout. Preserve every result and identify Astra's supplement
separately from the original worker. No new dashboard measurement or Part B.
