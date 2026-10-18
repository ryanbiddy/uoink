# Security backport review: keep the release hold

Control Room Gemini run 940c7fc1 produced a useful default-loader trace, but its
report is not an approved implementation plan. No dependency or product repair
was made. Astra checked the 35 retained metadata payloads and archived 13 exact
source files for independent review. No model code or checkpoint was executed.

The default path is confirmed: whisper_runner.py calls whisperx.load_model
without selecting another VAD. WhisperX chooses PyAnnote, whose Model.from_pretrained
calls the Lightning loader with weights_only=False and obtains a class name from
checkpoint metadata. This occurs before the separate diarize branch. Keeping
speaker attribution disabled does not remove this deserialization path.

Several worker claims need correction before anyone acts on them:

- Safetensors is already locked at 0.8.0. Adding it is not a prerequisite to
  exploring a tensor-only format. Converting and qualifying the existing model
  still requires separately authorized checkpoint loading and inference.
- The named weights_only exception is hypothetical, not an observed result.
  Static source inspection does not establish which globals this specific
  checkpoint needs or that no safe loader implementation is possible.
- The weights_only advisory PYSEC-2026-2286 describes weights_only=True. The
  observed default uses False, which is independently unsafe for untrusted
  pickle. Do not describe those as the same demonstrated exploit. The pt2
  loading advisory is also not proven reachable by this ordinary VAD trace.
- PyanNet uses nn.LSTM. The inspected nn.LSTM implementation calls _VF.lstm;
  nn.LSTMCell separately calls _VF.lstm_cell. This does not prove that the
  torch.lstm_cell advisory is reachable through default PyanNet inference.
  The installed Torch package remains flagged regardless of this distinction.
- The alignment code requests a .pickle-named Punkt resource, but NLTK's loader
  routes that prefix through switch_punkt to its pickle-free tokenizer. It can
  still download missing Punkt data. The suffix alone does not prove unpickling.
- local_files_only is forwarded to faster-whisper's model resolver. Its missing
  tokenizer branch separately calls Tokenizer.from_pretrained without that
  argument. Merely adding local_files_only does not close every download path.
  A corrupt existing tokenizer is passed to from_file; the inspected branch
  does not fall back to a download when that parse fails.
- The normal installer root is LOCALAPPDATA/Uoink. A different Programs path
  is not an alternate default established by the Inno source. Runtime hashes
  do not establish protection against a process with the same user's rights.
- The proposed lockfile changes name versions without a verified co-installable
  wheel graph. NLTK 3.10.4 is not a verified fixed release. The suggestion to
  change frozen lock assertions or suppress OSV conflicts with Ryan's rules.
  Do not follow it. A 21-case security selection is not the complete test tree.

The retained advisory events include Torch fixes through 2.13.0 and Transformers
through 5.10.0, but an event list is not a qualified Windows runtime. WhisperX's
Torch 2.8.x and Hub-below-1 requirements still conflict with the proposed upgrade.
The raw scan stays **19 entries / 15 alias groups**; separating the already
verified Lightning patch leaves **18 entries / 14 groups**. No entry is hidden.

## Concrete next repair scope

The next stack repair needs a dedicated branch and the following artifacts
before a release decision: an exact dependency graph and available wheel hashes;
a proposed WhisperX compatibility patch; a safe VAD loader/format design that
does not execute arbitrary checkpoint-selected classes; a tokenizer/data policy
that makes every network fallback explicit; and a before/after inference and
navigation-quality protocol on approved synthetic audio. A version bump, a
runtime hash or a regex replacement for Punkt is insufficient qualification.

Offline work can verify graph constraints, imports, DLL loading, synthetic
decoding, refusal boundaries and mocked pipeline behavior. It cannot prove
transcription quality or that converted production weights behave correctly.
The current instruction prohibits checkpoint/model loading and inference, and
the immutable dependency test explicitly expects Torch 2.8.0 and WhisperX 3.8.6.
Those are concrete Ryan gates for this migration; this review does not change
them. No paid API, live index, resident helper or diarization is needed for the
separately proposed qualification.

The candidate therefore remains a held review build. Complete its authorized
note-display installation checks and documentation while preserving this security
hold. Do not present this second Gemini report as security certification.

One local metadata-reader attempt failed before verification because it expected
a files wrapper around the worker's direct hash mapping. The corrected reader
uses the actual mapping, keeps every byte/hash assertion and writes a fresh
review02 directory. The failure and reader diff are retained; no product scenario
was repeated for that correction.
