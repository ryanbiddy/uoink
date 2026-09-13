# Captured pipeline synthetic contracts — 2026-09-13

Qualify the captured Transformers 5.17 Pipeline/PipelineIterator and retained
WhisperX 3.8.6 FasterWhisperPipeline interface with stdlib fake seams only.
Bind the three source files to the committed candidate03 source manifest.
Copy source as text; import no package and fetch nothing.

Execute exact selected bodies: Pipeline initializer (defined but prohibited
from running), call/forward/device placement/device transfer/inference context/
single-input methods and generator reforming; the complete PipelineIterator
class; WhisperX constructor/sanitizer/preprocess/forward/postprocess/iterator.
Keep the deliberate `super(Pipeline, self).__init__()` bypass. Class infrastructure
bases are inert stubs; annotations are removed to avoid dependency evaluation.
Method bodies remain AST-identical. The captured Pipeline initializer is never
rewritten and a profile guard rejects any attempt to execute it.

Explicit fakes implement only device contexts, tensor/array shape/slice/stack/
transfer, lazy batch loading, mel preparation and deterministic model outputs.
No real torch, numpy, loader threads/processes, tokenizer, audio, model or VAD
executes. Non-chat classification is a scoped fake; chat inputs are rejected
by the seam. Test the empty generator supplied by the default no-speech path,
first-item/order preservation, final partial batch, batch1/None/configured
defaults, lazy consumption, options/tokenizer forwarding, device transfer and
original exception propagation. This is not a complete transcribe/VAD trial.

Per-call parameter merging is tested separately with a parameter-spy subclass
overriding stage/sanitizer seams. It exercises the exact base call/forward and
WhisperX iterator bodies; it does not claim the actual WhisperX sanitizer or
stage signatures accept arbitrary parameters. Preserve stored parameter maps.
Direct PipelineIterator cases cover batch1/None and tensor/array unwrapping.

Probe a direct empty list separately. The captured __call__ indexes inputs[0]
for that optional path; record its exception as an unaccepted diagnostic without
editing source or treating generator coverage as list support.

Use C:\Python314\python.exe `-I -S -B`, scrub keys/tokens, set offline flags and
the exact forbidden-live string. Before selected code execution, install an
import/network/process/ctypes/file guard and a source-free error formatter.
Only fresh label pc01 is allowed. Preserve failures with source, input hashes,
actual exits and a repair brief before any rerun. No dependency/cap/frozen-test,
production, staging, runtime, artifact, installation or release acceptance follows.
