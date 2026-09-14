"""Exact fixed-factory schema helpers; fake globals supplied only by reviewed fixture."""
def _fixed_shapes():
    shapes = {
        "sincnet.wav_norm1d.weight": (1,),
        "sincnet.wav_norm1d.bias": (1,),
        "sincnet.conv1d.0.filterbank.low_hz_": (40, 1),
        "sincnet.conv1d.0.filterbank.band_hz_": (40, 1),
        "sincnet.conv1d.0.filterbank.window_": (125,),
        "sincnet.conv1d.0.filterbank.n_": (1, 125),
        "sincnet.conv1d.1.weight": (60, 80, 5),
        "sincnet.conv1d.1.bias": (60,),
        "sincnet.conv1d.2.weight": (60, 60, 5),
        "sincnet.conv1d.2.bias": (60,),
        "sincnet.norm1d.0.weight": (80,),
        "sincnet.norm1d.0.bias": (80,),
        "sincnet.norm1d.1.weight": (60,),
        "sincnet.norm1d.1.bias": (60,),
        "sincnet.norm1d.2.weight": (60,),
        "sincnet.norm1d.2.bias": (60,),
        "linear.0.weight": (128, 256),
        "linear.0.bias": (128,),
        "linear.1.weight": (128, 128),
        "linear.1.bias": (128,),
        "classifier.weight": (3, 128),
        "classifier.bias": (3,),
    }
    for layer in range(4):
        for suffix in ("", "_reverse"):
            shapes[f"lstm.weight_ih_l{layer}{suffix}"] = (
                512, 60 if layer == 0 else 256
            )
            shapes[f"lstm.weight_hh_l{layer}{suffix}"] = (512, 128)
            shapes[f"lstm.bias_ih_l{layer}{suffix}"] = (512,)
            shapes[f"lstm.bias_hh_l{layer}{suffix}"] = (512,)
    return shapes


def _check_plain_state(state, *, require_zero_offset, require_finite):
    # Caller supplies tensors only after the immutable artifact/header gates.
    # This check alone is not an untrusted-file loader or a deserialization guard.
    if (type(state) is not dict or len(state) != 54
            or any(type(key) is not str for key in state)
            or set(state) != set(_fixed_shapes())):
        raise ValueError("Fixed VAD tensor key mismatch")
    for name, shape in _fixed_shapes().items():
        tensor = state[name]
        if type(tensor) is not torch.Tensor:
            raise ValueError("Fixed VAD requires ordinary tensors")
        if tensor.dtype != torch.float32 or tensor.device.type != "cpu":
            raise ValueError("Fixed VAD requires CPU float32 state")
        if tensor.layout != torch.strided or tuple(tensor.shape) != shape:
            raise ValueError("Fixed VAD tensor shape or layout mismatch")
        if not tensor.is_contiguous() or tensor.requires_grad:
            raise ValueError("Fixed VAD requires detached contiguous state")
        if require_zero_offset and tensor.storage_offset() != 0:
            raise ValueError("Plain export must have zero-offset tensor views")
        if require_finite and not torch.isfinite(tensor).all().item():
            raise ValueError("Fixed VAD tensor contains nonfinite values")
