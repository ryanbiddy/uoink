2026-09-13. The reviewed ASR adapter and its 58 cases remain unchanged. The lifecycle proposal is not yet a drop-in runtime factory.

Its first explicit handoff would change the ignored begin-native return into a capability passed to the owned runtime:

    permit = lease.begin_native_session()
    runtime = RUNTIME_FACTORY.open_owned_session(profile, permit)

The factory must then receive a complete admitted load plan before it can start any real runtime. The current proposal delegates that binding to an unimplemented trusted port; it does not implement WhisperX/faster-whisper constructors, fixed VAD injection or the owned media decoder. The previous calls to runtime.whisperx_load_model/faster_whisper_model must not be left in place against this factory.

The future caller receives runtime.operations(), and submits one TranscribeRequest containing an owned media ticket. It consumes the returned guarded SegmentStream inside the lease and shapes passive segments afterward. This intentionally replaces access to a raw model/generator. Exact legacy dict/tuple adaptation, language metadata, VAD policy and decoder-ticket issuance still need a bounded splice and focused tests; do not silently drop them or claim existing APIs already work.

Close-and-join must return exactly True before lease.confirm_native_closed() can succeed. That confirmation now checks the same owner/permit state rather than accepting a caller's unsupported assertion. No caller can request acquisition through this facade. Release manifest approval, complete artifact hashes, real runtime policy and all owner decisions remain unchanged and unavailable.
