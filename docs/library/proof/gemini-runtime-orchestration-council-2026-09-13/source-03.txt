2026-09-13. Concrete splices against the hash-bound working sources in SOURCE-BINDINGS.json. These are reviewable replacements, not an applied or complete migration patch. The new adapter file is implemented; the external ports and runtime profile remain unavailable.

In whisper_runner.py, import the new adapter and stop the two module-level side effects: `_PACKAGED_DECODER_DLL_HANDLE = _register_packaged_decoder_dlls()` at line 73 and `_WHISPERX_AVAILABLE = _probe_whisperx()` at line 137. Move decoder registration and the actual package import into the approved owned runtime factory. Health/status must report cheap configured policy plus last qualified runtime evidence; do not replace a real availability claim with a bare conjunction of non-None globals. The current probe/helper functions must not remain a bypass that the shipped profile calls directly. Legacy Hub-cache structural status may remain separately labeled but may not authorize construction.

Replace the acquisition/import/device/constructor block in transcribe_audio (current lines 403-439) and its optional speaker block with this bounded session shape. Keep the existing audio input checks, normalization and transcript assembly. Reject diarize=True before any acquisition/runtime call because the speaker scope is still blocked. This does not silently claim a requested speaker run succeeded.

```python
if diarize:
    raise RuntimeError("Speaker attribution is unavailable in this release profile")
# UNMET PRECONDITION: waveform must come from the owned validated decoder.
# That executable decoder/lifetime contract is not supplied by this proposal.
with asr_loading_adapter.whisperx_session(
        model_size, data_root=data_root, consent_given=consent_given) as model:
    result = model.transcribe(waveform, language=language)
    segments = list(result.get("segments") or [])
    detected_lang = result.get("language") or language or "en"
    shaped_segments = _shape_segments(segments)
# Keep the current output keys/model/language/generated_at, using shaped_segments
# and diarization_ran=False. No alignment or diarization method is invoked.
```

The waveform variable is deliberately not obtained from a filename fallback. It must be a bounded 16-kHz mono finite waveform with the owned decoder's required representation and lifetime, admitted under the eventual fixed media/runtime contract. No owned decoder implementation or native decoding qualification is supplied here. Do not substitute str(audio_path), whisperx.load_audio or another unreviewed file-decoding helper to make the splice executable. The prior Pipeline generator/source qualification did not qualify decoding. Reliability's existing file-input path likewise needs its separate owned media/decoder disposition before native execution; this source-only adapter does not grant it.

Remove `_prepare_model_snapshot`/`_download_model_snapshot` from the shipped execution/acquisition route. The adapter owns the single explicit-consent acquisition attempt, receives its exact plan from release authority, and never invokes faster_whisper.utils.download_model. A runtime/model failure must not fall back to those old helpers. Replace early server/runtime preflight error text with a specific approval/runtime-unavailable result when no accepted profile exists; no download modal can resolve absent release authority.

In uoink_reliability.py, replace `_load_model` with a context-returning adapter seam. This changes a private helper's return contract, so the later implementation brief must identify every existing test that mocks that helper; this task changes none of them. The public transcript/span behavior stays unchanged. The ordinary False path is refused rather than translated into a constructor download.

```python
def _load_model(model_name, model_root, *, local_files_only=True,
                _usage="reliability"):
    if local_files_only is not True:
        raise ReliabilityUnavailableError("Use explicit ensure_model acquisition")
    return asr_loading_adapter.faster_whisper_session(
        model_name, model_root=model_root, usage=_usage)
```

In transcribe_media, keep the `_transcribe` test seam unchanged. The real branch must consume segments before its model context exits:

```python
with _load_model(model_name, model_root, local_files_only=True,
                 _usage="capture_fallback") as model:
    segments, _info = model.transcribe(
        str(media), beam_size=1, best_of=1, vad_filter=True)
    return _transcript_entries_from_segments(segments)
```

In detect_unreliable_spans, keep the `_transcribe` seam and threshold/span formatting unchanged. The real branch performs `_words_from_segments` inside the lease:

```python
with _load_model(model_name, model_root, local_files_only=True) as model:
    segments, _info = model.transcribe(
        str(audio), language="en", word_timestamps=True,
        beam_size=1, best_of=1)
    word_rows = _words_from_segments(segments)
return _cluster_low_words(word_rows, threshold)
```

Replace ensure_model's constructor and .pt-marker writes with:

```python
def ensure_model(model_name=DEFAULT_MODEL, model_root=None, *,
                 consent_given=False):
    return asr_loading_adapter.ensure_assets(
        model_name, model_root=model_root, consent_given=consent_given)
```

In server.py `_handle_reliability_model_download` (current line 13916), the explicit user-triggered POST passes `consent_given=True`. Preserve its model validation and token/route protections. The response must report `assets_verified` from the returned verification result, not blindly set downloaded=True or claim a model was loaded. No constructor ran, and a previously accepted snapshot may have needed no transfer. A metadata sentinel is neither consent for a future request nor asset authority. Existing settings estimates remain dated estimates; no new source/model is added.

The ordinary server capture/reliability callers continue to pass the explicit model root. Do not treat `allow_model_download=True` on the compute endpoint as a model constructor permission: it currently only bypasses one status precheck, while the lower loader remains local-only. Acquisition should remain the dedicated consent endpoint or the existing transcription job's explicit consent flag. The server's asynchronous job/status/UI details need a bounded product patch after these ports are concrete; these splices do not claim that work is finished.
