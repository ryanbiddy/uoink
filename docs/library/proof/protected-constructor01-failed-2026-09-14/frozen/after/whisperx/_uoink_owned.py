"""Closed integration port for the proposed Uoink-owned non-speaker runtime.

This is not manifest approval. Only a future reviewed process bootstrap may
provide this port after asset, import and lifetime qualification. It is absent
in this source proposal; caller arguments and environment variables cannot
enable it.
"""

import os


_RUNTIME = None


def require_owned_runtime():
    runtime = _RUNTIME
    if runtime is None:
        raise RuntimeError("The owned WhisperX runtime is not available")
    runtime.assert_active()
    return runtime


def require_owned_model(path, vad):
    runtime = require_owned_runtime()
    if type(path) is not str or not os.path.isabs(path):
        raise ValueError("An admitted absolute local model path is required")
    if vad is None:
        raise ValueError("Owned fixed VAD injection is required")
    # The real port must bind the exact admitted snapshot and VAD identity,
    # revalidate admission and keep its lease through all native/lazy work.
    runtime.assert_model_binding(path, vad)


def require_owned_namespace(namespace_record, vad):
    runtime = require_owned_runtime()
    if vad is None:
        raise ValueError("Owned fixed VAD injection is required")
    if namespace_record is None:
        raise ValueError("Admitted namespace record is required")
    runtime.assert_vad_binding(vad)
    runtime.assert_admitted_namespace_binding(namespace_record)


def validate_waveform(audio, *, owned_input=False):
    runtime = require_owned_runtime()
    # Import only after the closed process-level gate. No decoder is invoked.
    import numpy as np

    limit = runtime.max_audio_samples
    if type(limit) is not int or limit <= 0:
        raise RuntimeError("A qualified audio sample bound is required")
    if (type(audio) is not np.ndarray or audio.dtype != np.dtype("float32")
            or audio.ndim != 1 or not audio.flags.c_contiguous
            or not 0 < audio.size <= limit):
        raise ValueError("A bounded contiguous mono float32 waveform is required")
    for start in range(0, audio.size, 262144):
        if not np.isfinite(audio[start:start + 262144]).all():
            raise ValueError("The waveform must contain only finite samples")
    if owned_input:
        # Shape cannot prove a sampling rate or decoding provenance. The owned
        # decoder/session must attest 16 kHz and exclusive waveform lifetime.
        runtime.assert_waveform_binding(audio, sample_rate=16000)
    return audio
