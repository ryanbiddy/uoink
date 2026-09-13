# Captured pipeline contract verdict — 2026-09-13

The selected Transformers 5.17.0 and WhisperX 3.8.6 pipeline bodies passed
23 synthetic contracts in pc01: 23 passed, 0 failed, 0 errors, 0 skipped,
0.009 seconds. Child, launcher and actual outer exits were 0. The exact input
bytes remained unchanged. No rerun or assertion repair was needed.

The separate direct-empty-list probe raised `IndexError: list index out of range`
at captured `base.py:1242`. That optional API path remains unaccepted. It earns
no passing-test credit. The empty generator used at the no-speech pipeline
boundary returned an empty result with no preprocessing or model call.

| Boundary | Captured source | Qualified observation |
| --- | --- | --- |
| Constructor | `asr.py:114–151` | Preserves model, tokenizer, options, device and defaults; intentional `super(Pipeline, self).__init__()` bypass works with the selected class hierarchy. |
| Generator dispatch | `base.py:1217–1292`, `_reform_generator:79` | Peeks once, restores the first item and preserves order; later consumption follows demand. A five-item stream batches 2/2/1. |
| List dispatch | `base.py:1241–1246`, `1274–1283` | Nonempty lists return eagerly. Direct empty list fails at the first index. |
| Batch defaults | `base.py:1249–1258`; `pt_utils.py:50–55`, `119–151` | None uses the configured batch or 1. Batch1 keeps one-element text/logprob lists; larger batches unwrap each element, including the final partial batch. |
| Stage forwarding | `base.py:1260–1266`, `1183–1190`, `1301–1305`; `asr.py:176–195` | Parameter-spy contracts preserve original maps, apply per-call overrides and forward stage parameters through selected base/iterator bodies. |
| Actual WX stages | `asr.py:159–174` | Fake mel receives feature size 128 or fallback 80 and correct padding; fake model receives the exact stored tokenizer/options objects. Its output dictionary matches the keys/list shape declared by `asr.py:93`. |
| Device transfer | `base.py:1041–1070`, `1086–1102`, `1183–1190` | Fake input tensors move to the selected device; fake outputs return to CPU. Nested containers retain type/shape. Fake contexts close when a model error propagates. |
| Iterator | `pt_utils.py:23–151` | None/batch1 preserves result identity; tensor/array unwrapping keeps a leading dimension; partial batches, laziness and exact exception propagation pass. |

The real WhisperX sanitizer and stage signatures do not support arbitrary
inference kwargs (`asr.py:153–174`). The parameter-spy subclass overrides those
seams explicitly; its tests support the inherited merge/forward protocol only.
The captured transcribe loop unwraps batch1 values at `asr.py:274–276`, consistent
with the observed pipeline shapes. That loop, VAD and language detection were
read as text and were not executed.

Three exact source files are bound to the archived 68-payload source manifest:

- `base.py.txt`: `853e42ad66b34aed2b8b523450c822632d3f162f82a1d9e46f003d6963e98bf2`
- `pt_utils.py.txt`: `0ed35580ed6e7759f46d833025c94cbe7209aada0db3d69e75c5ee0af24bfd23`
- `asr.py.txt`: `f25d2dfd0cfcbcb6cd2850ba213bf715f92d4369401274e534557448876da565`

The Transformers source is commit `856157a2f3e9594954310df18fdccc31ffddebe9`;
the WhisperX source is bound to retained 3.8.6 source and upstream commit
`3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0`. Original capture receipts and
their limits remain in `inputs/REVIEW.md` and `inputs/commit-bindings.json`.

The AST scaffold removes signature annotations and class documentation/decorators
while preserving all 19 selected bodies exactly. Eighteen bodies executed with
explicit stdlib fakes. The captured Pipeline initializer was defined unchanged
and prohibited by a profile guard; it had zero calls. Profile counters include
generator resumes and must not be interpreted as distinct method invocations.

The reviewed input hashes are:

- `seams.py`: `a649c31edf1584a8641c5e409d802da73264d0aaee1ff4b2231715183c252b09`
- `tests.py`: `c49215e080c1d6687f20b9e5128cce60e5ef543dab2d0c7985ca1ff44077ba63`
- `run.py`: `0bfb1960f492af846b20b9085065114c1c335b62e2743609f88a2c8c3660dbf0`
- `launch.py`: `5f349c9594b3db19dc635f3c7112ff170959691b8266c41a1208a4093fcdc829`

Command: `C:\Python314\python.exe -I -S -B _scratch/pipeline-candidate05-contracts01/launch.py`.
The launcher records its absolute child command and environment variable names
scrubbed. Runtime was CPython 3.14.6 with isolated/no-site/no-bytecode flags.
The import finder and initializer profile guard remained installed; no heavy
package was loaded before or after, and no file/network/process/native-library
violation was observed. Tracebacks use a source-free formatter.

This supports continued review of the captured default pipeline interface.
It does not accept five dependency-cap changes, a full WhisperX derivative,
actual Torch/NumPy tensors, loader workers, native/model execution, checkpoints,
tokenization, GPU behavior, installation or market readiness. Keep the remaining
source and distribution checks explicit before changing the dependency contract.
