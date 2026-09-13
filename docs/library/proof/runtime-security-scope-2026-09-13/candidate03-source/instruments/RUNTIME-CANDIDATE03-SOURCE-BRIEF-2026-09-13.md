# Candidate03 source compatibility review

Review the candidate02 reference stack as source text only. The task is to
identify concrete changed symbols used by Uoink/WhisperX, distinguish default
transcription from optional alignment, diarization and training paths, and
specify the source changes needed for a real derivative.

Use the thirteen retained source bindings first. Copy only additional installed
Python source files needed to trace existing PyAnnote, torch-audiomentations,
faster-whisper and WhisperX imports, recording their local paths and hashes.
These source files are data: never import or execute them.

Fresh output: _scratch/runtime-candidate03-source. Resolve explicit upstream
release tags to Git commit IDs through public GitHub JSON; fetch at most fifteen
needed Python/TOML source text files by those immutable IDs from the official
repositories. Initial scope is Transformers 5.17 Pipeline/iterator/processor
interfaces, Hub 1.31 download/error interfaces, TorchAudio 2.11 entry points,
TorchCodec 0.16 decoder/metadata interfaces, and WhisperX 3.8.6 packaging.
Preserve request URLs, UTC times, statuses, raw text, hashes and failures. An
unresolved tag or missing file stays missing; no implicit branch fallback.

Produce a compact matrix with exact source lines, actual symbol differences,
path reachability and required edits. Do not claim runtime compatibility from
imports, documentation or a completed metadata graph. Keep the unsafe default
VAD loader, incomplete-cache consent and independent tokenizer/data download
paths in scope. Checkpoint classes, tensor shapes and conversion behavior remain
unknown until an authorized observation.

No model/media fetch, archive/wheel/binary download, dependency installation,
runtime/import/model execution, accepted-test or production-source edit, paid
provider, credentials, live index, port 5179, website, marketing, commit or push.
