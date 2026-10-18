# Real engine connection01: source review failed

Control Room run 56af690a-060b-453d-bb64-d9621a5553c9 completed with outer exit 0 at 11:27:25 UTC on 2026-09-14 (actual 55e4a9). That confirms delivery. The implementation is rejected before execution. Its 15 proposed tests have not run; there is no 15-case pass or failure measurement.

The frozen delivery contains 25 text files, 301,499 bytes, bound by FROZEN-SOURCE-PINS.json (860ac157). Root reviewed the full engine and test file, the new private WhisperX entry, and the relevant original contracts. Independent reviews cover the complete namespace/adoption and owner/protocol changes. The worker's SOURCE-INPUTS.json is the unchanged 23-input planning map; it does not bind its new delivery.

The repair must address these defects:

1. Trust is not established. Shaped model/profile objects, supplied hashes and a ready read-set object can obtain a namespace lease. The controller's approved manifest, live admission/permit and exact profile are not retained through a trusted child start. Caller module/state/constructor arguments remain accepted.
2. The two constructor paths are disconnected. The engine never calls the new private WhisperX entry. That entry checks a supplied files map's keys without checking its values and retains returned objects only in local variables. The engine sets pipeline.model_path before retaining the pipeline.
3. The fixed factory returns the VAD itself; the new bootstrap consumes it as a wrapper with .vad. Options supply seven fields although captured B3's TranscriptionOptions requires 26. Policy defaults replace required explicit values, and final publication does not recheck every retained binding.
4. The owner removed the contextmanager import while retaining its decorator. It also removed frozen=True from the unrelated generated namespace. Restore both original contracts.
5. Proposed test setup imports an undefined ReadSetRefusal, uses an invalid GenerationBinding keyword and nonhex digests, allocates buffers before begin, and seeds private VAD wrappers directly. Its permissive fake options and manual dictionary pops bypass the actual B3/private-entry connection. No proposed test exercises that private entry.

These are pre-execution findings. Existing acceptance assertions and qualified fake39 source remain unchanged. Root's complete test read is 3a7633; contract/B3 read is 0f5144. Owner peer verdict f09c4824 and namespace peer verdict a0676993 are preserved alongside passive checks 5509b4 and f456f6. Missing-path and truncated review outputs remain review preparation records, not product measurements. Some provider command parameters are shortened previews; the retained stream cannot attest complete command coverage.

Follow REAL-STARTUP-AUTHORITY-REPAIR-BRIEF-2026-09-14.md first. Repair the controller authority transfer in a smaller source unit before reconnecting the child namespace and fixed constructors. Keep both rejected constructor proposals as failed source deliveries. Production remains 71d3e70; D1/D2 are complete and must not be repeated. No runtime, full-tree, package, installation or market acceptance follows from this review.
