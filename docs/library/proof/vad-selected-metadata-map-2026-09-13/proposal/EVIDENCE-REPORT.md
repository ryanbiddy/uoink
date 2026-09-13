# Default VAD: recorded configuration and proposed fixed factory

2026-09-13. The selected static graph now supplies a concrete PyanNet declaration, constructor mapping, task-state declaration and 54 tensor descriptors. These support the explicit factory in `fixed-factory.proposal.txt` and the 54-entry manifest in `manifest.proposal02.json`. The proposed bridge fills two absent Specifications fields with explicit current-source values. Neither the bridge nor the factory has run or been approved.

The full artifact remains **refused: `Reference cycle refused`, reader exit 2**. Parent reports outer exit 2. The acyclic selected closure is a **partial, untrusted diagnostic**, not artifact acceptance. It cannot establish the producer's identity, historical execution state, tensor contents or model compatibility.

## Evidence identity and limits

The only model-derived input read here was the safe JSON receipt `_scratch/vad-symbolic-adapter-proposal01/results/symbolic-projection01.json`: **190,182 bytes**, SHA-256 `60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d`. Its original reader elapsed time is 0.034605 seconds. It reports artifact SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`, 17,719,103 bytes and 131 ZIP members. No checkpoint or storage payload was reopened in this task. Parent archived this receipt with proof228 in commit `ba8d2c8`, seal `700044423a8a8c0728524b8c3621c7378e41daf302d2137df4f0492d2d1ee8cf`.

The selected roots are `state_dict` → **10**, `hyper_parameters` → **3022**, and `pyannote.audio` → **3052**. Their union contains **1,069 nodes** and **1,344 examined edges including root entries**. Architecture and specifications occur under node 3052, not as separate top-level selected roots.

Every reference below is a node ID in that receipt. Literal dict/list/tuple associations describe the final reference graph. `GLOBAL`, `REDUCE`, `NEWOBJ` and `BUILD` remain tagged records; nothing was called, imported, constructed or assigned to a legacy object. The graph lacks global event order and historical snapshots of constructor arguments. Acyclic values shared with omitted roots may appear; semantic ownership and provenance remain unknown.

## Recorded declarations

Node **3062** is the literal architecture dict under key 3061 in node 3052:

| Field | Recorded value | References |
| --- | --- | --- |
| Module | `pyannote.audio.models.segmentation.PyanNet` | key 3063 → string 3064 |
| Class | `PyanNet` | key 3065 → string 3066 |
| PyAnnote version token | `0.0.1` | versions dict 3054, key 3051 → string 3060 |
| Torch version constructor argument | `1.10.0+cu102` | newobj 3059, global 3056 `torch.torch_version TorchVersion`, args tuple 3058 → string 3057 |

The last row records a symbolic constructor argument. It is not an evaluated version object, current runtime version or authenticated producer receipt. The architecture declaration matches the class supplied by retained `PYANNET`; that establishes a candidate source mapping, not trusted origin.

The constructor values below are literal entries under node **3022**:

| Path | Recorded value | Value reference |
| --- | --- | ---: |
| sample_rate | 16000 | 3024 |
| num_channels | 1 | 3026 |
| sincnet.stride | 10 | 3030, in dict 3028 |
| sincnet.sample_rate | 16000 | 3032, in dict 3028 |
| lstm.hidden_size | 128 | 3036, in dict 3034 |
| lstm.num_layers | 4 | 3038 |
| lstm.bidirectional | true | 3040 |
| lstm.monolithic | true | 3042 |
| lstm.dropout | 0.5 | 3044 |
| lstm.batch_first | true | 3046 |
| linear.hidden_size | 128 | 3049, in dict 3048 |
| linear.num_layers | 2 | 3050 |

`PYANNET:84–99` copies defaults, overwrites SincNet sample_rate with the outer value and forces LSTM batch_first true. Both overwritten values already agree with the recorded mapping. The recorded stride **10** resolves the earlier source/docstring discrepancy for this declaration. Four layers and dropout 0.5 are recorded overrides; current `PYANNET:63–69` defaults are two layers and dropout 0.0. Do not replace the recorded values with those defaults.

Node **3086** is a `Specifications` newobj tag, global **3084**, empty args tuple **3085**, with one recorded BUILD state dict **3087**:

| Field in BUILD-state dict | Recorded association | Proposed current-source interpretation |
| --- | --- | --- |
| problem | reducer 3092 → global 3089 `Problem`, args 3091 → int 3090 = 2 | `TASK:59–64`: MULTI_LABEL_CLASSIFICATION = 2 |
| resolution | reducer 3097 → global 3094 `Resolution`, args 3096 → int 3095 = 1 | `TASK:71–73`: FRAME = 1 |
| duration | float 3099 = 5.0 | Proposed 5-second inference chunks |
| warm_up | tuple 3103 → floats 3101/3102 = (0.0, 0.0) | Proposed no warm-up trimming |
| classes | list 3105 → strings 3106/3107/3108 | Ordered `speaker#1`, `speaker#2`, `speaker#3` |
| permutation_invariant | bool 3110 = true | Proposed true |
| min_duration | **Absent** | Propose explicit `None`, current `TASK:89` default |
| powerset_max_classes | **Absent** | Propose explicit `None`, current `TASK:104` default |

The enum names and both `None` values are proposed version-bridge decisions. They are not values recovered by executing the legacy object. Under that proposal, `TASK:110–119` disables powerset; `PYANNET:142–162` makes a three-output classifier; `MODEL:271–300` selects sigmoid for multi-label classification. The recorded classifier shape is [3,128] plus [3] bias. This agreement supports the bridge; it does not qualify numerical equivalence. Retaining speaker-slot labels within this fixed internal schema grants no speaker attribution or diarization claim.

Introspection newobj **3070** (global **3068**, empty args **3069**) has BUILD-state dict **3071**. It records min_num_samples **1261** (3073), min_num_frames **2** (3075), inc_num_samples **270** (3077), inc_num_frames **1** (3079), dimension **3** (3081), sample_rate **16000** (3082). These are state associations, not applied attributes. Independently, arithmetic on `SINCNET:88–152` with stride 10 gives receptive-field length 991 samples and frame jump 270; two frames need 1,261 samples. This source agreement does not justify replaying Introspection. The proposed current factory computes its own geometry.

## Complete state and shared storage

Node **10** is a reducer tag targeting global **8**, `collections OrderedDict`, with empty args **9**. Its first recorded operation is SETITEMS with **54 pairs**. Its second is BUILD with state dict **899**, key **900** `_metadata` → reducer **902**, an OrderedDict tag with 28 recorded module-version associations. The four instance-normalization entries record version 2; the others record version 1. Some names concern validation metrics. The proposed plain export copies none of those BUILD operations or training objects. Current-module loading without legacy `_metadata` needs a separate compatibility check.

`tensor-table02.md` lists all 54 key/reducer/offset/shape/stride associations with explicit **Whole-storage declared elements** and **Whole-storage advertised bytes (repeats)** columns. The original `tensor-table.md` remains unchanged. Whole-storage lengths must not be summed per row: storage 16 appears 32 times. `mapping.json` retains every reducer argument, persistent operand tuple, offset, shape, stride, requires-grad value and hook record. `supplement01.json` gives every range grouped by storage-key literal.

All 54 tensor tags target global **12**, `torch._utils _rebuild_tensor_v2`. `TORCH_UTILS:216–236` binds the six recorded arguments: storage, storage_offset, size, stride, requires_grad and backward_hooks. All require-grad arguments are false. Each hook is an OrderedDict reducer tag with empty tuple arguments and no recorded mutations. The optional metadata argument is absent in all 54. These facts do not require calling any reducer.

The storage operands all contain tag `storage`, global **14** `torch FloatStorage`, a decimal key, location literal `cuda:0`, and an element-count integer. `TORCH_INIT:1874–1882` maps the current FloatStorage implementation to `torch.float`; each matched advertised member length is four times its declared element count. **F32 is the proposed plain-format interpretation. Actual byte order, scalar encoding and values remain unverified.** The CUDA location token is historical data; it does not select a device in the proposed factory.

| Source group | Entries | Declared structure and current source agreement |
| --- | ---: | --- |
| SincNet | 16 | Affine input normalization; two [40,1] filter parameters; [125] window and [1,125] time buffers; [60,80,5]/[60,60,5] convolutions and affine normalization. `SINCNET:42–80`, `SINC_FB:48–80`. |
| LSTM | 32 | Four layers × two directions × four tensors. Input weights are [512,60] at layer 0 and [512,256] later; recurrent weights [512,128], both biases [512]. `TORCH_RNN:145–200` supplies these shape/name rules for the recorded dimensions. |
| Linear | 4 | [128,256] and [128,128] weights, [128] biases. `PYANNET:127–140`. |
| Classifier | 2 | [3,128] weight, [3] bias. `PYANNET:142–162` under the proposed specification bridge. |

The 32 LSTM tensors share key **16**, declared length **1,380,352 elements**, advertised member `archive/data/16` length **5,521,408 bytes**. For example, tensor **301** uses offset ref **290** = 0 and range [0,30720); tensor **318** uses ref **307** = 30720 and range [30720,96256). The final bias tensor **796** uses ref **787** = 1379840 and range [1379840,1380352). All 32 exact ranges, including biases packed after the weights, are retained in the supplement.

Arithmetic across each group shows row-major declared strides and nonoverlapping intervals covering each declared storage exactly. There are **23 distinct storage-key literals**, **1,472,999 declared elements** and **5,891,996 distinct advertised storage bytes**. The current source classification expects 52 parameters and two persistent buffers, the latter totaling 250 elements. No tensor payload, finiteness or actual storage alias behavior was validated. The initial mapping's per-row storage-length sum is 177,055,644 because it repeats the shared member; it is not the unique payload size. Its aggregate shape-product-equals-entire-storage field is false for those shared views and is not a failed product test.

## Concrete proposal and open gates

`fixed-factory.proposal.txt` contains the full 54-key shape function, ordinary-string-key boundary, CPU/F32 state checks, fixed constructor, explicit Specifications bridge, `build()` once, strict state load and VAD instance injection. Its current SHA-256 is `69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b`. `manifest.proposal02.json` binds it and all 54 shape/stride/source-reference rows. The first factory/manifest drafts remain under `drafts/` and as `manifest.proposal.json`.

Two constructor choices are explicitly sourced rather than recorded: LSTM **bias=True** and **proj_size=0**, defaults at `TORCH_RNN:90,94`. The 16 bias vectors and lack of projection weights agree with these choices. `task=None`, CPU execution, inference gradients disabled and omission of checkpoint BUILD metadata are also proposed migration choices. No new default is presented as a recorded field.

The inference proposal fixes duration **5.0**, step **0.5**, batch size **32**, sliding-window aggregation and skip_conversion false. Duration/warm-up come from the recorded state; step 0.5 and batch size 32 follow the current `INFERENCE:79–88,117–167` defaults for that state. `VADPIPE:109–114` takes the maximum score over the three channels. The existing WhisperX profile provides onset **0.500**, offset **0.363**, min_duration_on/off **0.1** (`WXVAD:21,42–47`). These are source-defined caller settings, not checkpoint fields. `WXASR:419–421` accepts the injected object; its existing non-Vad fallback retains preprocessing/chunk merging. First qualification is CPU only; any GPU profile remains a separate check.

The following evidence is still required before a converter or runtime loader can be accepted:

1. **Producer and redistribution evidence.** Bind the intended model to an authoritative release or repository commit, expected original bytes, training/model version and license. The matching hash, class declaration and source copyright header do not authenticate checkpoint provenance or redistribution rights.
2. **Storage format and byte order.** The receipt contains `archive/data.pkl`, 129 numeric `archive/data/*` members, and a two-byte `archive/version` member. It contains no byteorder member. This task did not read version bytes. Establish the archive serialization version and writer/storage protocol from independently bound primary source or explicit bounded metadata evidence. Establish the original scalar byte order; do not infer it from the Windows reader, CUDA token or version string. Bind the mapping from persistent key/element units to member bytes. CRC advertisements and four-byte lengths do not settle these questions.
3. **A reviewed conversion protocol or authoritative plain export.** Specify exact selected-root/node grammar, immutable input snapshot, ZIP/CRC/span limits, allowed storage keys, scalar encoding, byte ranges, shapes/strides, and rejection cases. Preserve the shared-storage16 ranges. The concrete proposed export copies each disjoint range into a zero-offset dense F32 tensor without casts, renaming, reshaping or dropping buffers; changing sharing is an explicit migration choice. Do not import a checkpoint global, invoke a reducer, replay BUILD, call persistent_load or use unrestricted torch/pickle loading. No converter ran here.
4. **A real plain artifact and trust anchor.** The manifest proposes 54 tensors, 1,472,999 elements, 5,891,996 dense data bytes, a 32-KiB header bound and 6-MiB file cap. The artifact does not exist; its exact bytes/hash, reviewed format version and release trust anchor are unresolved. These proposed caps still need native reader/header/allocation qualification before data can allocate tensors.
5. **Version bridge and runtime qualification.** Review the explicit absent-field choices and enum interpretation; verify exact parameter/buffer schema and legacy-metadata omission on the chosen stack. The retained Torch source is from staged 2.8.0, not a qualification of the uninstalled candidate02 Torch 2.13.0 reference. Audit the complete fixed import graph/native dependencies and then qualify the proposed stack. First compare CPU states, frame counts, score ranges, finite outputs and end-to-end VAD/ASR on fixed fixtures under offline bounds. Numerical equivalence requires an approved reference; no legacy loader is implicitly authorized as an oracle. Installed/release and any GPU receipts remain separate.

## Source and reporting receipts

Source keys resolve through the unchanged original fixed-loader source bindings, SHA-256 `8dbd83213bceac5012bc342e001826902ce3a88fd420fa64f8f8d9a65366fa9c`, original 38-payload seal `129773fb33e4ec94a4e217373064d6d55de68d1db71f299a2372a91be1a76403`. This task rechecked 12 retained source/lock copies and captured three additional Python sources as text:

| Additional key | Saved file | SHA-256 |
| --- | --- | --- |
| TORCH_INIT | additional-source/torch-init.py | `6d6c92d0b1091fc8f437cfe8228e9c9ad088dc0faf8446b1df8738f61c0834f2` |
| TORCH_RNN | additional-source/torch-rnn.py | `4ca97c3133494a7b21bb07fdf90ec04b27d764a4803f02f9f139fb61614b5ecb` |
| TORCH_UTILS | additional-source/torch-utils.py | `a74c433f12e3f0867e4b9911d3fb071205198ee946f78ef7dbcfa438bdadd6cb` |

All three source/copy hashes agreed before and after capture; none was imported. The fixed-loader source text and this receipt mapping establish a proposed implementation, not a safe current runtime.

`map-run01.json` records one successful **receipt-reporting operation**, exit 0, 54 entries, ten initial source checks, 0.004137 seconds, explicit isolated/no-site/no-bytecode startup and live-path string binding. `source-extra-check01.json` supplies the other two retained checks. The supplemental arithmetic/source-text and manifest-writing commands returned exit 0. These are reporting outcomes; **no new product, model, inference or conversion tests ran**. The original strict refusal and every prior proof seal remain unchanged.
