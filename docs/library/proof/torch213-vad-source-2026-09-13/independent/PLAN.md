The target tag is v2.13.0 in the official pytorch/pytorch repository. Its existence and commit have not been checked in this task. Resolve with https://api.github.com/repos/pytorch/pytorch/git/ref/tags/v2.13.0. If annotated, request https://api.github.com/repos/pytorch/pytorch/git/tags/{TAG_OBJECT_SHA}; at most two objects are allowed. Verify the final https://api.github.com/repos/pytorch/pytorch/git/commits/{COMMIT_SHA}. Each API body is capped at 16,384 bytes.

Every source URL is exactly https://raw.githubusercontent.com/pytorch/pytorch/{REVIEWED_COMMIT_SHA}/{path}, using a reviewed lowercase 40-hex commit from that chain. The collector's default output expands all paths into URL templates; source mode records the final URLs before fetching. Unknown immutable IDs remain placeholders until observed and reviewed.

| Path | Byte cap | Exact comparison target and reason |
| --- | ---: | --- |
| version.txt | 4,096 | Record repository version text alongside the tag/commit chain; do not infer wheel identity. |
| torch/__init__.py | 196,608 | Tensor/dtype/device exports, get_default_dtype, get/set_default_device and visible native-import boundaries used by the fixed factory. |
| torch/__future__.py | 16,384 | get_swap_module_params_on_conversion and related switches consulted by Module state loading; assign=False alone must not conceal a changed loading path. |
| torch/_tensor.py | 131,072 | Tensor Python behavior and inherited/native boundaries for the plain-state checks; no checkpoint reconstruction is invoked. |
| torch/utils/_device.py | 32,768 | DeviceContext enter/exit and constructor interception behind with torch.device('cpu'); list any functions exempt from that context. |
| torch/nn/parameter.py | 32,768 | Parameter construction and requires_grad defaults; fixed schema distinguishes parameters from persistent buffers. |
| torch/nn/modules/module.py | 262,144 | Module registration, state_dict/_save_to_state_dict, load_state_dict/_load_from_state_dict, _apply/to, train/eval and requires_grad_. Review strict, assign=False and absent _metadata behavior. |
| torch/nn/modules/rnn.py | 131,072 | RNNBase construction/reset/flatten/_apply and LSTM forward: four layers, two directions, bias=True, proj_size=0, batch_first=True, dropout=0.5 and all 32 state names/shapes. |
| torch/nn/modules/conv.py | 98,304 | _ConvNd and Conv1d construction/reset/_conv_forward: [60,80,5] and [60,60,5], bias and padding defaults. |
| torch/nn/modules/instancenorm.py | 32,768 | _InstanceNorm/InstanceNorm1d construction, forward and version-aware _load_from_state_dict when legacy _metadata is omitted. |
| torch/nn/modules/batchnorm.py | 65,536 | _NormBase constructor/reset/_load_from_state_dict inherited by InstanceNorm; affine tensors versus track_running_stats=False buffer absence. |
| torch/nn/modules/linear.py | 32,768 | Linear constructor/reset/forward and Identity used by non-powerset inference; hidden and classifier state shape rules. |
| torch/nn/modules/pooling.py | 98,304 | _MaxPoolNd/MaxPool1d arguments and forwarding: kernel 3, stride 3, zero padding, dilation 1 and floor geometry. |
| torch/nn/modules/activation.py | 131,072 | Sigmoid constructor/forward selected by the explicit multi-label Specifications bridge. |
| torch/nn/modules/container.py | 65,536 | ModuleList append/indexing and registration order underlying SincNet/linear numeric state-key prefixes. |
| torch/nn/modules/utils.py | 16,384 | _single/_ntuple argument normalization used by the reviewed layer constructors. |
| torch/nn/init.py | 65,536 | kaiming_uniform_, uniform_, ones_, zeros_, fan calculation and no-grad initialization used before the strict state load; constructor dtype/device effects. |
| torch/nn/functional.py | 393,216 | conv1d, instance_norm, max_pool1d, linear, leaky_relu, sigmoid and pad wrappers reached by the fixed model/sliding-window inference; identify native dispatch rather than claim kernel equivalence. |
| torch/autograd/grad_mode.py | 32,768 | inference_mode/no_grad wrappers reached by inference and construction/state-loading helpers. |

The list caps source bodies at 1,839,104 bytes; a run also has a 4-MiB global response budget. Imports visible inside these files are recorded as remaining boundaries, not followed automatically. No wheels, binaries, storage, model files, archives, directory listings or Git trees are requested.

Review outputs should classify each factory assumption as source-compatible, changed or unresolved. A source-compatible result still needs the exact target-wheel identity, import and native state-schema checks, then the approved CPU/F32 corpus measurement. Missing source or a changed path yields a preserved failed collection and a specific follow-up scope request.
