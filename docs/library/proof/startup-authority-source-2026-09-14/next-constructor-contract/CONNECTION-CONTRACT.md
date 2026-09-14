This checklist is for the next fixed constructor connection. It grants no runtime authority. The current controller repair ends before child construction; the rejected connection01 and all accepted tests remain unchanged. The nine fixed inputs and twelve byte-preserving excerpts are bound in SOURCE-BINDINGS.json and SOURCE-EXCERPTS.json. The additional import read is retained in FIXED-IMPORT-LINKS-READ12-ACTUAL.json.

The captured B3 recipe is historically named B2.py.txt. Its TranscriptionOptions declaration (lines 70–97) requires these 26 fields, with no dataclass defaults. Annotations do not validate values. “Policy” below means an explicit private record bound to the exact approved profile; that record is still to be implemented.

| Field | Captured annotation | Required source of value |
| --- | --- | --- |
| beam_size | int | Validated request; exactly 1 |
| best_of | int | Validated request; exactly 1 |
| patience | float | Policy |
| length_penalty | float | Policy |
| repetition_penalty | float | Policy |
| no_repeat_ngram_size | int | Policy |
| log_prob_threshold | Optional[float] | Policy |
| no_speech_threshold | Optional[float] | Policy |
| compression_ratio_threshold | Optional[float] | Policy |
| condition_on_previous_text | bool | Policy |
| prompt_reset_on_temperature | float | Policy |
| temperatures | List[float] | Policy |
| initial_prompt | Optional[Union[str, Iterable[int]]] | Policy |
| prefix | Optional[str] | Policy |
| suppress_blank | bool | Policy |
| suppress_tokens | Optional[List[int]] | Policy |
| without_timestamps | bool | Policy |
| max_initial_timestamp | float | Policy |
| word_timestamps | bool | Validated request, subject to the still-missing real mapping |
| prepend_punctuations | str | Policy |
| append_punctuations | str | Policy |
| multilingual | bool | Bound model's model.is_multilingual |
| max_new_tokens | Optional[int] | Policy |
| clip_timestamps | Union[str, List[float]] | Policy; resolve captured None mismatch |
| hallucination_silence_threshold | Optional[float] | Policy |
| hotwords | Optional[str] | Policy |

RuntimeProfile currently contains only profile_id, device, compute_type, whisperx_fixed_vad_contract and capture_vad_contract (adapter lines 36–42). It does not supply decoding policy, device_index, cpu_threads, num_workers, task, language or pipeline settings. TranscribeRequest contains the media ticket, language, word_timestamps, vad_filter, beam_size and best_of (lifecycle lines 63–71). Its facade fixes beam/best-of to 1 and checks language/boolean shape (392–410). This syntax acceptance does not establish language detection, word timing or filtering support. Language can come only through that validated request plus the selected runtime policy; task is not a request field. Neither vad_filter nor suppress_numerals is one of the 26 fields.

Owned WhisperX supplies baseline defaults at asr.py:381–417, including beam/best-of 5, and removes suppress_numerals before constructing TranscriptionOptions. Those defaults are source facts, not an approved policy. Its clip_timestamps=None contradicts the captured annotation above. Resolve that combination against the fixed downstream use before enabling it; do not silently inherit defaults or allow arbitrary asr_options.

The connected sequence must satisfy these checks in order:

1. Consume the exact controller-owned release/selection/admission/profile and live permit through the fixed child seam. Establish child-local namespace authority and complete approved buffers before the private entry. Hashes, paths, supplied modules, reconstructed records and callbacks grant no authority. Bind the actual owned module and exact WhisperModel, Tokenizer, TranscriptionOptions, FasterWhisperPipeline and VoiceActivitySegmentation classes in trusted bootstrap. Owned asr.py:35 subclasses faster_whisper.WhisperModel; the imported base must be the captured B3 implementation.
2. Serialize factory construction/binding/build/release. The fixed factory registers its verified segmentation model lease before constructing VoiceActivitySegmentation(segmentation=model), retains the VAD, instantiates fixed parameters and publishes it under that lease (owned_factory_port.py:208–283). build_strict_owned returns the VAD itself; the model/VAD/lease record is factory._completed. Register that actual product in the runtime owner. The owned guard module's _RUNTIME must be the exact registry.
3. Enter one engine operation and retain its attempt before construction. Pass a fresh dictionary of all five approved buffers to the fixed owned WhisperModel's inherited B3 constructor. B3 pops tokenizer.json and preprocessor_config.json (674–677), then passes the remaining dictionary to CTranslate2 (698–706). Retain the immutable namespace separately. Nonempty approved tokenizer/preprocessor bytes must be checked before entry. Bind model identifier, explicit device/compute/device-index/thread/worker settings and closed acquisition parameters; no caller-selected model_kwargs.
4. Immediately retain every returned model, tokenizer and pipeline before any next setter, validation or liveness check. B3's prepared tokenizer comes from tokenizer.json, becomes model.hf_tokenizer, and is distinct from the higher-level Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task=task, language=language) (owned asr.py:375–379). Construct the complete 26-field options record and retain its exact identity.
5. Call the fixed pipeline with model, vad, vad_params, options and tokenizer plus explicit approved language/device/framework/settings. Its actual links are .model, .tokenizer, .options and .vad_model; it also stores .preset_language, .suppress_numerals and ._vad_params (118–155). Its signature defaults device=-1/framework="pt"; negative integers select CPU. Make that choice explicit. Retain the returned pipeline before assigning model_path (the baseline assigns it at 437).
6. Publish only after rechecking the current namespace/read-set, profile, generation, exact factory/VAD/model lease and all actual pipeline links under the serial operation. Preserve the first error and uncertain owners on failure or cancellation. Constructor allocations that never return remain a worker-retirement obligation. Factory release revokes before dropping references and explicitly provides no native-close receipt (306–319).

Keep the existing guards unconditional: require_owned_runtime before heavy imports (owned asr.py:4 and VAD module:3); active runtime and absolute admitted path/model binding; exact VoiceActivitySegmentation; local_files_only is True; download_root/use_auth_token/model/vad_method remain None; public assert_load_parameters remains required (asr.py:351–365). VAD construction checks the owned model binding before its parent constructor (pyannote.py:170–173); legacy load_vad_model remains refused. Waveform shape, finiteness, sample bound and owned 16-kHz provenance checks remain intact. A private entry must validate its own issued attempt without making any public guard permissive.

The remaining unknowns are concrete. The captured VAD calls self._segmentation(file), but these sources do not establish the parent inference object's model-storage attribute; generated .segmentation is not evidence of that real link. B3 still uses lexical path joins, has filesystem/download fallback branches when buffers are missing, and handles invalid preprocessor JSON by logging/returning a fallback result. Complete buffers do not by themselves prove CTranslate2's complete native reader/import closure. Approved policy values, real state/recipe authority, authenticated child transport, constructor-failure retirement and request-to-inference/PCM/filter behavior remain unimplemented or unmeasured here. No source was patched or imported, and no constructor or test ran.
