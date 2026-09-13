# Required owned runtime port

The new `_uoink_owned._RUNTIME` stays None. No public setter, model preference,
environment variable, path, type check or successful hash can supply it. A future
reviewed process bootstrap must connect this port to the accepted resolver and
the lifecycle adapter. This file defines missing executable work.

| Member | Required behavior before returning |
| --- | --- |
| `assert_active()` | Verify the exact process, interpreter, distributions, import policy and active owned session. Startup must set and verify `TORCH_DEVICE_BACKEND_AUTOLOAD=0` and `PYANNOTE_METRICS_ENABLED=0` before imports. These settings do not replace external network denial or native import review. |
| `assert_model_binding(path, vad)` | Match the selected choice, immutable revision, complete accepted SHA256/size manifest and exact fixed-VAD object. Revalidate the admitted snapshot; retain write/delete/reparse exclusion through constructor, generator and cleanup. It must not search caches, acquire assets or accept a replacement path. |
| `assert_load_parameters(...)` | Bind every supplied load argument to the immutable qualified profile before the ASR constructor. Refuse GPU/default compute, unqualified device index, threads, task, language or option dictionaries. The first reviewed target is CPU; any accepted int8/float32 choice and defaults must be explicit. Own the immutable option inputs rather than trusting caller-mutable containers after the check. No normalization may silently change the accepted policy. |
| `assert_vad_model_binding(model)` | Require the exact factory-owned fixed PyanNet instance and approved 54-key plain-state contract. `isinstance(Model)` alone proves neither provenance nor a safe construction path. No path, repository name, dictionary, pickle class or loader fallback is accepted. |
| `max_audio_samples` | Supply one positive integer fixed by the qualified process/audio policy, not client options. This proposal invents no accepted duration limit. |
| `assert_waveform_binding(audio, sample_rate=16000)` | Bind the exact private waveform to the owned validated decoder, its sample-rate receipt and session. Prevent concurrent mutation and use after cleanup. Array shape/dtype/finiteness alone cannot prove the sampling rate or decoder provenance. |
| `get_mel_filters(n_mels)` | Return the admitted, finite contiguous native F32 matrix of shape `(80,201)` or `(128,201)`. Its exact source, hash, notice, safe decoding and runtime lifetime remain to be implemented and qualified. No direct NPZ path or missing-asset download fallback is allowed. |

The port is an internal interface between trusted code components, not an OS
sandbox or an authority boundary against arbitrary Python execution. Its current
absence closes the proposal. A module-global active flag would not make an old
pipeline or model valid in a new session: the worker/facade must bind object
identities to a session and prevent retained references from being reused after
cleanup. Do not return unrestricted model objects to untrusted callers. The
existing adapter's private-directory, native reopen, cleanup/quarantine and crash
recovery gaps remain real implementation requirements.

Call order is release/manifest admission, lifetime lease, qualified process
bootstrap, plain-state VAD construction, parameter binding, local B3-backed ASR
construction, owned waveform transcription, full lazy-result consumption, then
confirmed cleanup. Explicit user consent can authorize the separate acquisition
service only; failure at construction or inference must never start a download.
The six choices remain tiny, base, small, medium, large and large-v3-turbo in the
external resolver. Their current captured manifests remain unaccepted with
twenty missing asset SHA256 values.
